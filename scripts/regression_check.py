"""Regression check for the RINSE AI detectors against known-ground-truth assets.

Reads tests/detector_assets.json (AI-labeled and human-labeled posts/images),
scans each one through the running detector API, compares the verdict tier
against the expected set, and records everything to
tests/last_regression_results.json (merged by asset id, so image and video
batches can be run in separate invocations).

Usage:
    # Server already running on :5001
    .venv/bin/python scripts/regression_check.py

    # Let this script start/stop the server itself
    .venv/bin/python scripts/regression_check.py --start-server

    # Subset by asset id (comma separated)
    .venv/bin/python scripts/regression_check.py --ids web-ai-fortnite-brainrot

Instagram links are resolved with yt-dlp inside this script (the venv has it):
a downloaded .mp4/.mov/.webm goes to /predict/video/deep as video_base64, a
.jpg/.png/.webp goes to /predict/image/deep as image_base64. The post kind is
recorded in the results file either way.

Every scan is sent with no_cache=true so results are always fresh, never
served from the scan cache.
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_PATH = os.path.join(ROOT, "tests", "detector_assets.json")
RESULTS_PATH = os.path.join(ROOT, "tests", "last_regression_results.json")
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
BASE_URL = os.environ.get("RINSE_BASE_URL", "http://localhost:5001")

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

AI_TIERS = {"SYNTHETIC_AI", "SUSPICIOUS"}
HUMAN_TIERS = {"AUTHENTIC_HUMAN", "INCONCLUSIVE"}


def http_json(path, payload=None, timeout=300):
    url = BASE_URL + path
    if payload is None:
        req = urllib.request.Request(url)
    else:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"error": body[:400]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": f"request failed: {e}"}


def wait_for_health(timeout_s=120):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, body = http_json("/health", None, timeout=5)
        if status == 200:
            return body
        time.sleep(1.5)
    return None


def ytdlp_download(url):
    """Download the best media file for a social-platform post URL.

    Returns (bytes, extension, caption) or (None, error_message, "").
    Tries anonymous first, then browser cookies (brave -> chrome -> firefox),
    mirroring the server's layered cookie fallback - Instagram login-walls
    many posts for anonymous downloads.
    """
    try:
        import yt_dlp  # noqa: PLC0415
    except ImportError:
        return None, "yt-dlp is not installed in the venv", ""

    cookie_specs = [None, ("brave", None), ("chrome", None), ("firefox", None)]
    last_err = None
    for cookie_spec in cookie_specs:
        tmpdir = tempfile.mkdtemp(prefix="rinse_regr_")
        opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(tmpdir, "source.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "retries": 2,
        }
        if cookie_spec:
            opts["cookiesfrombrowser"] = cookie_spec
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info and info.get("_type") == "playlist":
                    entries = info.get("entries") or []
                    if entries:
                        info = entries[0]
            files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
                     if os.path.isfile(os.path.join(tmpdir, f))]
            if not files:
                last_err = "yt-dlp reported success but wrote no file"
                continue
            best = max(files, key=os.path.getsize)
            ext = os.path.splitext(best)[1].lower()
            caption = " ".join(str(info.get(k) or "") for k in ("title", "description")).strip()[:2000]
            with open(best, "rb") as f:
                return f.read(), ext, caption
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    return None, last_err or "all download attempts failed", ""


def scan_asset(asset):
    """Scan one asset. Returns a result dict."""
    url = asset["url"]
    label = asset["label"]
    t0 = time.time()

    kind = asset.get("kind", "video")
    payload = {"no_cache": True}

    if kind == "image":
        payload["image_url"] = url
        status, verdict = http_json("/predict/image/deep", payload)
        used_kind = "image"
    else:
        # Resolve the social post locally so we know whether it is a video or
        # a plain image post before choosing the endpoint.
        data, ext_or_err, caption = ytdlp_download(url)
        if data is None:
            status, verdict = 0, {"error": f"yt-dlp: {ext_or_err}"}
            used_kind = "unresolved"
        elif ext_or_err in VIDEO_EXTS:
            payload["video_base64"] = base64.b64encode(data).decode("ascii")
            # Passthrough the post caption so the server's AI-metadata layer
            # can use the same provenance evidence the video_url flow gets.
            if caption:
                payload["source_caption"] = caption
            status, verdict = http_json("/predict/video/deep", payload)
            used_kind = "video"
        elif ext_or_err in IMAGE_EXTS:
            payload["image_base64"] = (
                "data:image/" + ext_or_err.lstrip(".") + ";base64,"
                + base64.b64encode(data).decode("ascii")
            )
            status, verdict = http_json("/predict/image/deep", payload)
            used_kind = "image"
        else:
            status, verdict = 0, {"error": f"unexpected downloaded file type: {ext_or_err}"}
            used_kind = "unresolved"

    elapsed = round(time.time() - t0, 1)

    if status != 200 or "error" in verdict:
        return {
            "id": asset["id"],
            "url": url,
            "expected": label,
            "kind": used_kind,
            "http_status": status,
            "error": verdict.get("error", "unknown error")[:400],
            "pass": False,
            "elapsed_s": elapsed,
        }

    score = verdict.get("score")
    tier = verdict.get("tier")
    expected_tiers = AI_TIERS if label == "ai" else HUMAN_TIERS
    ok = tier in expected_tiers

    reasons = verdict.get("reasons", [])
    return {
        "id": asset["id"],
        "url": url,
        "expected": label,
        "kind": used_kind,
        "http_status": status,
        "score": score,
        "tier": tier,
        "confidence": verdict.get("confidence"),
        "breakdown": verdict.get("breakdown"),
        # Temporal-evidence audit trail: per-window pwtf/temporal/d3 scores
        # and the winning window's pwtf metrics (p05 coherence, whiteness,
        # residual autocorrelation, hotspots). Persisted so voter-threshold
        # changes are calibrated against recorded evidence, not guesses.
        "window_details": verdict.get("window_details"),
        "pwtf_metrics": verdict.get("pwtf_metrics"),
        "video_source": verdict.get("video_source"),
        "metadata_source": verdict.get("metadata_source"),
        "metadata_markers": verdict.get("metadata_markers", []),
        "character_match": (
            {
                "label": (verdict.get("character_match") or {}).get("label"),
                "match_strength": (verdict.get("character_match") or {}).get("match_strength"),
            }
            if verdict.get("character_match") else None
        ),
        "cached": verdict.get("cached"),
        "top_reasons": [str(r)[:220] for r in reasons[:4]],
        "expected_tiers": sorted(expected_tiers),
        "pass": ok,
        "elapsed_s": elapsed,
    }


def load_results():
    if os.path.exists(RESULTS_PATH):
        try:
            with open(RESULTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            pass
    return {"runs": []}


def merge_results(prev, run_record):
    """Merge by asset id: the newest verdict for an asset wins."""
    by_id = {}
    for r in prev.get("results", []):
        by_id[r["id"]] = r
    for r in run_record["results"]:
        by_id[r["id"]] = r
    merged = dict(prev)
    merged["results"] = [by_id[k] for k in sorted(by_id)]
    merged["last_run_at"] = run_record["run_at"]
    merged["health"] = run_record.get("health")
    merged["runs"] = (prev.get("runs") or [])[-9:] + [{
        "run_at": run_record["run_at"],
        "asset_ids": [r["id"] for r in run_record["results"]],
        "passed": sum(1 for r in run_record["results"] if r["pass"]),
        "total": len(run_record["results"]),
    }]
    return merged


def main():
    global BASE_URL
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-server", action="store_true",
                    help="start (and afterwards stop) the Flask server for this run")
    ap.add_argument("--ids", default="", help="comma-separated asset ids to scan (default: all)")
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--audit", action="store_true",
                    help="print the full temporal-evidence audit (pwtf p05, per-window "
                         "scores, breakdown) for each scanned asset")
    args = ap.parse_args()

    BASE_URL = args.base_url.rstrip("/")

    with open(ASSETS_PATH, "r", encoding="utf-8") as f:
        assets = json.load(f)["assets"]
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
        assets = [a for a in assets if a["id"] in wanted]
        missing = wanted - {a["id"] for a in assets}
        if missing:
            print(f"WARNING: unknown asset ids ignored: {sorted(missing)}")
    if not assets:
        print("No assets selected.")
        return 2

    server_proc = None
    health = None
    if args.start_server:
        health = wait_for_health(timeout_s=3)
        if health:
            print(f"Server already running at {BASE_URL}, reusing it.")
        else:
            log = open("/tmp/rinse_regression_server.log", "w")
            server_proc = subprocess.Popen(
                [VENV_PY, "server.py"],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
            )
            print(f"Started server pid {server_proc.pid}, waiting for health...")
            health = wait_for_health(timeout_s=120)
            if not health:
                print("Server did not become healthy; check /tmp/rinse_regression_server.log")
                return 2

    try:
        health = health or wait_for_health(timeout_s=15)
        print(f"Health: detectzoo={health and health.get('detectzoo_loaded')} "
              f"characters={health and health.get('characters_loaded')} "
              f"cache={health and health.get('cache_enabled')}")

        run_record = {
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "results": [],
        }
        for asset in assets:
            print(f"\n=== {asset['id']} [{asset['label']}] ({asset['kind']}) ===")
            res = scan_asset(asset)
            run_record["results"].append(res)
            if "error" in res:
                print(f"  ERROR ({res['http_status']}): {res['error'][:200]}")
                mark = "FAIL"
            else:
                print(f"  score={res['score']} tier={res['tier']} conf={res['confidence']} "
                      f"({res['elapsed_s']}s, cached={res['cached']})")
                if res.get("character_match"):
                    print(f"  character: {res['character_match']['label']} "
                          f"({res['character_match']['match_strength']})")
                if res.get("metadata_source") and res.get("metadata_source") != "none":
                    print(f"  metadata: source={res['metadata_source']} "
                          f"markers={res.get('metadata_markers', [])[:2]}")
                for r in res.get("top_reasons", [])[:2]:
                    print(f"  - {r}")
                mark = "PASS" if res["pass"] else "FAIL"
            print(f"  => {mark} (expected {res['expected']})")
            if args.audit:
                wd = res.get("window_details") or []
                pm = res.get("pwtf_metrics") or {}
                if wd:
                    print(f"  windows: {len(wd)}; per-window "
                          f"pwtf={[w.get('pwtf_score') for w in wd]} "
                          f"p05={[w.get('pwtf_p05_coherence') for w in wd]}")
                if pm:
                    keep = ["coherence_p05", "coherence_mean", "spectral_flatness",
                            "residual_ac1", "hotspot_fraction", "hotspot_cluster",
                            "temporal_var_p95"]
                    print("  pwtf:", {k: pm.get(k) for k in keep if pm.get(k) is not None})
                if res.get("breakdown"):
                    print("  breakdown:", res["breakdown"])

        passed = sum(1 for r in run_record["results"] if r["pass"])
        total = len(run_record["results"])

        prev = load_results()
        merged = merge_results(prev, run_record)
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
        print(f"\nResults written to {os.path.relpath(RESULTS_PATH, ROOT)}")

        print(f"\n{'='*60}")
        print(f"REGRESSION RUN: {passed}/{total} assets matched expected labels")
        for r in run_record["results"]:
            mark = "PASS" if r["pass"] else "FAIL"
            verdict = (f"score={r.get('score')} tier={r.get('tier')}"
                       if "error" not in r else f"error={r['error'][:60]}")
            print(f"  [{mark}] {r['id']:<32} expected={r['expected']:<6} {verdict}")
        print(f"{'='*60}")
        return 0 if passed == total else 1
    finally:
        if server_proc is not None:
            import signal
            try:
                os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
                server_proc.wait(timeout=10)
                print("\nServer stopped.")
            except Exception:  # noqa: BLE001
                try:
                    os.killpg(os.getpgid(server_proc.pid), signal.SIGKILL)
                except Exception:  # noqa: BLE001
                    pass


if __name__ == "__main__":
    sys.exit(main())
