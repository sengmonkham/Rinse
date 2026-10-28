#!/usr/bin/env python3
"""Dedicated image-detector tests.

Runs every image asset through the deep image path and prints the fused score,
tier, confidence and top reasons:

* ``POST /predict/image/deep`` - fuses the spatial layers (tier 0 provenance:
  SynthID / C2PA / metadata; then frequency forensics, the DetectZoo neural
  classifier, SPAI) plus the color-structure pixel signature.

Corpus (local, no network):

* ``tests/calibration_corpus/ai/*``   - AI-labeled stills
* ``tests/calibration_corpus/real/*`` - real-photo negatives

The AI stills that were extracted from reels (``reel*_frame.jpg``,
``reel*_w*.jpg``) are reported **score-only**: they are single photorealistic
frames from generated video, and the repo already documents them as an
unasserted corpus extra (the photoreal-without-context gap in
``docs/detector-review-and-video-plan.md``) rather than a pass/fail target.

The image assets registered in ``tests/detector_assets.json`` (Brave-proxy URLs
of web images) are included with ``--remote-images``; they need network access,
so they are off by default.

Usage:
    .venv/bin/python tests/test_images.py
    .venv/bin/python tests/test_images.py --live http://localhost:5001 --remote-images
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import media_test_common as h

CORPUS_DIR = os.path.join(h.ROOT, "tests", "calibration_corpus")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

# Single frames extracted from generated reels: known-unasserted extras.
UNASSERTED_PREFIXES = ("reel",)


def collect_assets(include_remote: bool = False) -> list:
    assets = []
    for label, subdir in (("ai", "ai"), ("human", "real")):
        d = os.path.join(CORPUS_DIR, subdir)
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if os.path.splitext(fname)[1].lower() not in IMAGE_EXTS:
                continue
            unasserted = fname.lower().startswith(UNASSERTED_PREFIXES)
            assets.append({
                "id": f"img-{subdir}-{os.path.splitext(fname)[0]}",
                "label": "unasserted" if unasserted else label,
                "path": os.path.join(d, fname),
                "source": f"tests/calibration_corpus/{subdir}",
                "note": "generated-video frame (unasserted corpus extra)" if unasserted else "",
            })

    if include_remote:
        for asset in h.load_detector_assets("image"):
            assets.append({
                "id": asset["id"],
                "label": asset.get("label", "unknown"),
                "url": asset["url"],
                "tier_expect": asset.get("tier_expect"),
                "source": asset.get("source", "detector_assets.json"),
                "note": "remote image URL",
            })
    return assets


def scan(detector: h.Detector, asset: dict, flags: dict, timeout: int):
    payload = dict(flags)
    if asset.get("url"):
        payload["image_url"] = asset["url"]
    else:
        payload["image_base64"] = h.b64_data_uri(asset["path"])
    return detector.post("/predict/image/deep", payload, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    h.add_common_args(ap)
    ap.add_argument("--remote-images", action="store_true",
                    help="also scan the image assets registered in tests/detector_assets.json "
                         "(remote URLs; needs network)")
    args = ap.parse_args()

    assets = h.filter_by_ids(collect_assets(args.remote_images), args.ids)
    if not assets:
        print("No image assets selected.")
        return 2

    detector = h.Detector(args.live, args.key)
    flags = h.payload_flags(args)
    records = []
    h.print_header("image", len(assets), detector)

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
            rec = h.make_record(
                asset["id"],
                expected=asset["label"],
                source=asset["source"],
                scores={
                    "score": verdict.get("score"),
                    "tier": tier,
                    "conf": verdict.get("confidence"),
                },
                verdict=h.tier_verdict(asset["label"], tier, asset.get("tier_expect")),
                note=asset.get("note", ""),
                elapsed_s=elapsed,
                extra={
                    "top_reasons": verdict.get("reasons", []),
                    "breakdown": verdict.get("breakdown"),
                    "metadata_source": verdict.get("metadata_source"),
                    "character_match": verdict.get("character_match"),
                },
            )
        records.append(rec)
        h.log_record(rec)

    return h.print_summary("image", records, detector, args.out)


if __name__ == "__main__":
    sys.exit(h.run_main(main))
