#!/usr/bin/env python3
"""Dedicated video-detector tests.

Runs every video asset through the deep video path and prints the fused score,
tier, confidence, the PwTF-DD temporal coherence floor and the top reasons:

* ``POST /predict/video/deep`` - spatial layers on the analyzed windows plus the
  temporal layers (PwTF-DVD pixel-wise temporal frequency, temporal coherence,
  D3/dynamics metrics, temporal residual) fused in ``forensics/voter.py``.
* Local files are sent as ``video_base64`` (the test's own bytes).
* Social posts are sent as ``video_url`` so the server resolves them with
  yt-dlp exactly like the extension does (and its scan cache is keyed by URL,
  so re-runs are cheap).

Corpus:

* ``test videos/*.mp4``               - the repo's local manual clips
  (vid1 = AI, vid2/vid3 = real, per the measured table in
  ``docs/detector-review-and-video-plan.md`` §6; any other local file is
  reported score-only)
* ``tests/detector_assets.json``      - the Instagram posts already registered
  in the repo (video-kind entries)
* ``tests/media_test_assets.json``    - the Instagram posts added with these
  tests

Usage:
    .venv/bin/python tests/test_videos.py
    .venv/bin/python tests/test_videos.py --live http://localhost:5001
    .venv/bin/python tests/test_videos.py --ids ig-DegUdkFAiJd --audit
    .venv/bin/python tests/test_videos.py --skip-instagram   # local clips only
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import media_test_common as h

VIDEO_DIR = os.path.join(h.ROOT, "test videos")
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}

# Labels for the local manual clips (docs/detector-review-and-video-plan.md §6).
LOCAL_LABELS = {
    "vid1.mp4": "ai",
    "vid2.mp4": "human",
    "vid3.mp4": "human",
}


def collect_assets(skip_instagram: bool = False) -> list:
    assets = []

    if os.path.isdir(VIDEO_DIR):
        for fname in sorted(os.listdir(VIDEO_DIR)):
            if os.path.splitext(fname)[1].lower() not in VIDEO_EXTS:
                continue
            label = LOCAL_LABELS.get(fname, "unknown")
            assets.append({
                "id": f"local-{os.path.splitext(fname)[0]}",
                "label": label,
                "path": os.path.join(VIDEO_DIR, fname),
                "source": "test videos/",
                "note": "unlabeled local clip" if label == "unknown" else "",
            })
    else:
        print(f"NOTE: {os.path.relpath(VIDEO_DIR, h.ROOT)}/ not found; skipping local clips "
              f"(the directory is gitignored).")

    if skip_instagram:
        return assets

    for asset in h.load_detector_assets("video"):
        assets.append({
            "id": asset["id"],
            "label": asset.get("label", "unknown"),
            "url": asset["url"],
            "tier_expect": asset.get("tier_expect"),
            "source": f"tests/detector_assets.json ({asset.get('source', 'instagram')})",
            "note": "registered repo asset",
        })

    for asset in h.load_media_assets("videos"):
        assets.append({
            "id": asset["id"],
            "label": asset.get("label", "unknown"),
            "url": asset["url"],
            "tier_expect": asset.get("tier_expect"),
            "source": f"tests/media_test_assets.json ({asset.get('source', 'instagram')})",
            "note": asset.get("note", ""),
        })

    return assets


def scan(detector: h.Detector, asset: dict, flags: dict, timeout: int):
    payload = dict(flags)
    if asset.get("url"):
        payload["video_url"] = asset["url"]
    else:
        payload["video_base64"] = h.b64_data_uri(asset["path"])
    return detector.post("/predict/video/deep", payload, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    h.add_common_args(ap)
    ap.add_argument("--skip-instagram", action="store_true",
                    help="run the local clips only (no yt-dlp downloads)")
    ap.add_argument("--audit", action="store_true",
                    help="print the per-window temporal audit (including the coverage sweep) "
                         "for every asset")
    args = ap.parse_args()

    assets = h.filter_by_ids(collect_assets(args.skip_instagram), args.ids)
    if not assets:
        print("No video assets selected.")
        return 2

    detector = h.Detector(args.live)
    flags = h.payload_flags(args)
    records = []
    h.print_header("video", len(assets), detector)

    for asset in assets:
        t0 = time.time()
        status, verdict = scan(detector, asset, flags, args.timeout)
        elapsed = time.time() - t0

        if status != 200 or "error" in verdict:
            rec = h.make_record(
                asset["id"], expected=asset["label"], source=asset["source"],
                error=f"HTTP {status}: {verdict.get('error', 'unknown error')}",
                note=asset.get("note", ""), elapsed_s=elapsed)
        else:
            tier = verdict.get("tier")
            pwtf = verdict.get("pwtf_metrics") or {}
            tr_metrics = verdict.get("tr_metrics") or {}
            windows = verdict.get("window_details") or []
            coverage = verdict.get("temporal_coverage") or {}
            rec = h.make_record(
                asset["id"],
                expected=asset["label"],
                source=asset["source"],
                scores={
                    "score": verdict.get("score"),
                    "tier": tier,
                    "conf": verdict.get("confidence"),
                    "p05": pwtf.get("coherence_p05"),
                    "tr": verdict.get("tr_score"),
                    # Temporal coverage sweep: flagged windows / windows swept.
                    "cov": (f"{coverage.get('flagged')}/{coverage.get('analyzed')}"
                            if coverage.get("analyzed") else None),
                },
                verdict=h.tier_verdict(asset["label"], tier, asset.get("tier_expect")),
                note=asset.get("note", ""),
                elapsed_s=elapsed,
                extra={
                    "top_reasons": verdict.get("reasons", []),
                    "breakdown": verdict.get("breakdown"),
                    "cached": verdict.get("cached"),
                    "video_source": verdict.get("video_source"),
                    "windows": [
                        {"pwtf_score": w.get("pwtf_score"),
                         "pwtf_p05_coherence": w.get("pwtf_p05_coherence")}
                        for w in windows
                    ],
                    "pwtf_metrics": pwtf,
                    "tr_metrics": tr_metrics,
                    "tr_white_frac": tr_metrics.get("residual_white_frac"),
                    "temporal_coverage": coverage,
                    "audio": verdict.get("audio"),
                    "character_match": verdict.get("character_match"),
                },
            )
            if args.audit:
                print(f"  {asset['id']}: windows="
                      f"{[(w.get('pwtf_score'), w.get('pwtf_p05_coherence')) for w in windows]}")
                print(f"  {asset['id']}: pwtf={pwtf}")
                print(f"  {asset['id']}: tr_score={verdict.get('tr_score')} tr={tr_metrics}")
                print(f"  {asset['id']}: coverage={coverage}")
                print(f"  {asset['id']}: breakdown={verdict.get('breakdown')}")
        records.append(rec)
        h.log_record(rec)

    return h.print_summary("video", records, detector, args.out)


if __name__ == "__main__":
    sys.exit(h.run_main(main))
