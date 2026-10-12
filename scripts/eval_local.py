#!/usr/bin/env python3
"""Local, network-free eval harness for the RINSE detector.

Exercises the REAL endpoint code in-process via Flask's test client (no server
process, no network) over the local calibration corpus and local test videos.
Used as the before/after regression gate for detector changes.

Usage:
    .venv/bin/python scripts/eval_local.py --out /tmp/before.json
    # ...make changes...
    .venv/bin/python scripts/eval_local.py --out /tmp/after.json
    .venv/bin/python scripts/eval_local.py --compare /tmp/before.json /tmp/after.json

Every scan is sent with no_cache=true so results are always fresh.
"""
import argparse
import base64
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

IMG_AI_DIR = os.path.join(ROOT, "tests", "calibration_corpus", "ai")
IMG_REAL_DIR = os.path.join(ROOT, "tests", "calibration_corpus", "real")
VIDEO_DIR = os.path.join(ROOT, "test videos")

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VID_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}


def _b64(path, mime):
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _mime_for(ext):
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".webp": "image/webp", ".bmp": "image/bmp",
        ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".webm": "video/webm", ".m4v": "video/mp4", ".mkv": "video/x-matroska",
    }.get(ext, "application/octet-stream")


def scan_image(client, path):
    ext = os.path.splitext(path)[1].lower()
    payload = {"image_base64": _b64(path, _mime_for(ext)), "no_cache": True}
    r = client.post("/predict/image/deep", json=payload)
    return r.status_code, r.get_json()


def scan_video(client, path):
    ext = os.path.splitext(path)[1].lower()
    payload = {"video_base64": _b64(path, _mime_for(ext)), "no_cache": True}
    r = client.post("/predict/video/deep", json=payload)
    return r.status_code, r.get_json()


def _record(name, status, verdict, elapsed):
    out = {"name": name, "http_status": status, "elapsed_s": round(elapsed, 1)}
    if status != 200 or not isinstance(verdict, dict) or "error" in verdict:
        out["error"] = (verdict or {}).get("error", "unknown")
        return out
    out.update({
        "score": verdict.get("score"),
        "tier": verdict.get("tier"),
        "confidence": verdict.get("confidence"),
        "breakdown": verdict.get("breakdown"),
        "pwtf_metrics": verdict.get("pwtf_metrics"),
        "window_details": verdict.get("window_details"),
        "metadata_source": verdict.get("metadata_source"),
    })
    return out


def run(out_path):
    import server  # noqa: E402  (imports the Flask app + forensics stack)
    client = server.app.test_client()

    results = {"images_ai": [], "images_real": [], "videos": []}

    for label, d in (("images_ai", IMG_AI_DIR), ("images_real", IMG_REAL_DIR)):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if os.path.splitext(fn)[1].lower() not in IMG_EXTS:
                continue
            t0 = time.time()
            status, verdict = scan_image(client, os.path.join(d, fn))
            rec = _record(fn, status, verdict, time.time() - t0)
            results[label].append(rec)
            print(f"[{label}] {fn:28s} status={status} "
                  f"score={rec.get('score')} tier={rec.get('tier')} ({rec['elapsed_s']}s)")

    if os.path.isdir(VIDEO_DIR):
        for fn in sorted(os.listdir(VIDEO_DIR)):
            if os.path.splitext(fn)[1].lower() not in VID_EXTS:
                continue
            t0 = time.time()
            status, verdict = scan_video(client, os.path.join(VIDEO_DIR, fn))
            rec = _record(fn, status, verdict, time.time() - t0)
            results["videos"].append(rec)
            pm = rec.get("pwtf_metrics") or {}
            print(f"[videos] {fn:28s} status={status} "
                  f"score={rec.get('score')} tier={rec.get('tier')} "
                  f"p05={pm.get('coherence_p05')} flat={pm.get('spectral_flatness')} "
                  f"({rec['elapsed_s']}s)")

    results["run_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if out_path:
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote {out_path}")
    return results


def compare(before_path, after_path):
    def flat(d):
        rows = {}
        for k in ("images_ai", "images_real", "videos"):
            for r in d.get(k, []):
                rows[(k, r["name"])] = r
        return rows

    before = flat(json.load(open(before_path)))
    after = flat(json.load(open(after_path)))
    print(f"{'group':<14}{'name':<28}{'before':>18}{'after':>18}  changed")
    print("-" * 92)
    n_changed = 0
    for key in sorted(set(before) | set(after)):
        b, a = before.get(key), after.get(key)
        if not b or not a:
            print(f"{key[0]:<14}{key[1]:<28}{'MISSING':>18}  ")
            continue
        bs = f"{b.get('score')}/{b.get('tier')}"
        as_ = f"{a.get('score')}/{a.get('tier')}"
        changed = bs != as_
        if changed:
            n_changed += 1
        print(f"{key[0]:<14}{key[1]:<28}{bs:>18}{as_:>18}  {'<-- CHANGED' if changed else ''}")
    print("-" * 92)
    print(f"{n_changed} verdict(s) changed")
    return n_changed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="", help="write results JSON to this path")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"),
                    help="compare two result files and print deltas")
    args = ap.parse_args()

    if args.compare:
        compare(args.compare[0], args.compare[1])
        return 0
    run(args.out or "")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
