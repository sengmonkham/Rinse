#!/usr/bin/env python3
"""MNW benchmark runner for the RINSE detector (Phase 0 eval gate).

Runs a deterministic slice of the MNW dataset through a *running* detector and
reports recall, tier distribution, latency, and per-layer value spread. The
layer spread is the point: a layer that returns the same value on every sample
carries no evidence even if its weight looks reasonable.

MNW stores media in Git LFS, so a plain clone contains pointer files. This
runner therefore sends GitHub's LFS media URLs to the detector (the detector
fetches the real bytes) instead of uploading local files.

Usage:
    .venv/bin/python scripts/eval_mnw.py                       # images + videos
    .venv/bin/python scripts/eval_mnw.py --images-per-generator 3 --limit-generators 10
    .venv/bin/python scripts/eval_mnw.py --only videos --videos 8 --json results.json
    .venv/bin/python scripts/eval_mnw.py --base-url http://localhost:5000

Exit code: 0 always (results are data, not a pass/fail gate yet).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MNW = ROOT / "MNW"
MEDIA = "https://media.githubusercontent.com/media/microsoft/MNW/main"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VID_EXT = {".mp4", ".mov", ".webm", ".mkv"}
TIERS = ("SYNTHETIC_AI", "SUSPICIOUS", "INCONCLUSIVE", "AUTHENTIC_HUMAN")

# Ground truth: every MNW asset is AI-generated or a deepfake by construction.
AI_TIERS = {"SYNTHETIC_AI", "SUSPICIOUS"}


def load_env() -> None:
    """Load env files: repo-local first, then the sibling rinse-web app.

    The detector URL/key live in the web app's .env.local; the backend repo has
    no copy of them, so a backend-only run has to reach one directory up.
    """
    candidates = [
        ROOT / ".env.local",
        ROOT / ".env",
        ROOT.parent / "rinse-web" / ".env.local",
        ROOT.parent / "rinse-web" / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def image_samples(per_generator: int, limit_generators: int) -> list[tuple[str, Path]]:
    root = MNW / "AI_Images"
    out: list[tuple[str, Path]] = []
    for gen in sorted(p for p in root.iterdir() if p.is_dir()):
        files = sorted(f for f in gen.iterdir() if f.suffix.lower() in IMG_EXT)
        if not files:
            continue
        for f in files[:per_generator]:
            out.append((gen.name, f))
        if limit_generators and len({g for g, _ in out}) >= limit_generators:
            break
    return out


def video_samples(limit: int) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for bucket in ("AI_Video", "Deepfake_Video"):
        root = MNW / bucket
        if not root.exists():
            continue
        for gen in sorted(p for p in root.iterdir() if p.is_dir()):
            files = sorted(f for f in gen.iterdir() if f.suffix.lower() in VID_EXT)
            if files:
                out.append((f"{bucket}/{gen.name}", files[0]))
            if limit and len(out) >= limit:
                return out
    return out


def media_url(path: Path) -> str:
    return f"{MEDIA}/{urllib.parse.quote(path.relative_to(MNW).as_posix(), safe='/')}"


def post(base: str, key: str, route: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        base.rstrip("/") + route,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = json.loads(res.read().decode() or "{}")
        status = 200
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = json.loads(exc.read().decode() or "{}")
        except Exception:
            body = {"error": str(exc)}
    except Exception as exc:  # network / timeout
        status = 0
        body = {"error": f"{type(exc).__name__}: {exc}"}
    return {"status": status, "body": body, "ms": round((time.time() - started) * 1000)}


def run(samples: list[tuple[str, Path]], route: str, field: str, base: str, key: str, timeout: int) -> list[dict[str, Any]]:
    results = []
    for label, path in samples:
        payload = {field: media_url(path)}
        r = post(base, key, route, payload, timeout)
        body = r["body"]
        results.append(
            {
                "label": label,
                "file": path.relative_to(MNW).as_posix(),
                "status": r["status"],
                "ms": r["ms"],
                "score": body.get("score"),
                "tier": body.get("tier"),
                "layers": body.get("breakdown") or {},
                "error": body.get("error"),
            }
        )
        print(
            f"  {label:<32} http={r['status']:<3} {str(body.get('tier')):<16} "
            f"score={str(body.get('score')):<4} {r['ms']:>6}ms"
            + (f"  {json.dumps(body.get('breakdown'))}" if body.get("breakdown") else "")
            + (f"  error={body.get('error')}" if r["status"] != 200 else ""),
            flush=True,
        )
    return results


def summarise(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r["status"] == 200]
    flagged = [r for r in ok if (r.get("score") or 0) >= 55 or r.get("tier") in AI_TIERS]
    tiers = {t: sum(1 for r in ok if r.get("tier") == t) for t in TIERS}
    ms = sorted(r["ms"] for r in ok)
    lat = {
        "p50": statistics.median(ms) if ms else 0,
        "max": max(ms) if ms else 0,
    }

    layer_values: dict[str, set[Any]] = {}
    for r in ok:
        for layer, value in (r.get("layers") or {}).items():
            layer_values.setdefault(layer, set()).add(value)
    constant = sorted(l for l, vals in layer_values.items() if len(vals) <= 2)

    print(f"\n== {name}: {len(ok)}/{len(rows)} answered, flagged {len(flagged)} "
          f"({100 * len(flagged) / max(1, len(ok)):.0f}% recall), p50 {lat['p50']}ms, max {lat['max']}ms")
    print("   tiers: " + ", ".join(f"{t}={n}" for t, n in tiers.items() if n))
    if layer_values:
        print("   layer value spread (distinct values across samples):")
        for layer in sorted(layer_values):
            vals = sorted(str(v) for v in layer_values[layer])
            flag = "  <-- CARRIES NO EVIDENCE" if len(vals) <= 2 else ""
            print(f"     {layer:<10} {len(vals):>2} distinct: {', '.join(vals[:8])}{flag}")
    return {
        "mode": name,
        "samples": len(rows),
        "answered": len(ok),
        "flagged": len(flagged),
        "recall_pct": round(100 * len(flagged) / max(1, len(ok)), 1),
        "tiers": tiers,
        "latency_ms": lat,
        "constant_layers": constant,
        "layer_values": {k: sorted(str(v) for v in vals) for k, vals in layer_values.items()},
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the MNW slice through the RINSE detector.")
    ap.add_argument("--base-url", default=os.environ.get("RINSE_DETECTOR_URL", ""))
    ap.add_argument("--api-key", default=os.environ.get("RINSE_DETECTOR_API_KEY", ""))
    ap.add_argument("--only", choices=("images", "videos", "both"), default="both")
    ap.add_argument("--images-per-generator", type=int, default=2)
    ap.add_argument("--limit-generators", type=int, default=8)
    ap.add_argument("--videos", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    load_env()
    base = args.base_url or os.environ.get("RINSE_DETECTOR_URL", "")
    key = args.api_key or os.environ.get("RINSE_DETECTOR_API_KEY", "")
    if not base:
        print("No detector URL (--base-url or RINSE_DETECTOR_URL).", file=sys.stderr)
        return 2
    base = base.replace("/predict", "").rstrip("/")

    print(f"detector: {base}")
    report: dict[str, Any] = {"base_url": base, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if args.only in ("images", "both"):
        imgs = image_samples(args.images_per_generator, args.limit_generators)
        print(f"\n== images: {len(imgs)} samples")
        report["images"] = summarise(
            "images",
            run(imgs, "/predict/image/deep", "image_url", base, key, args.timeout),
        )

    if args.only in ("videos", "both"):
        vids = video_samples(args.videos)
        print(f"\n== videos: {len(vids)} samples")
        report["videos"] = summarise(
            "videos",
            run(vids, "/predict/video/deep", "video_url", base, key, args.timeout),
        )

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
