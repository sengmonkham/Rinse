#!/usr/bin/env python3
"""Dedicated text-detector tests.

Runs every text asset through both in-repo text detectors and prints the score
each one returns:

* ``POST /predict/storyscope`` - StoryScope, the narrative-structure XGBoost
  classifier (heuristic/offline engine unless ``STORYSCOPE_MODE=llm``).
* ``POST /predict/text/dna``   - DNA-DetectLLM, the mutation-repair statistic.

Both return a 0-100 AI probability (>= 50 = AI-generated), so the PASS/FAIL
column is driven by the primary narrative detector (StoryScope) and the DNA
score is reported alongside it.

Corpus (all in-repo, no network):

* ``storyscope/evasion_samples.py``       - texts written by hand specifically
                                            to evade these detectors (expected
                                            human)

Usage:
    .venv/bin/python tests/test_text.py
    .venv/bin/python tests/test_text.py --live http://localhost:5001 --ids text-human-written
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import media_test_common as h

def collect_assets() -> list:
    assets = []

    try:
        from storyscope import evasion_samples  # noqa: PLC0415

        for name, texts in evasion_samples.EVASION_SAMPLES.items():
            for i, text in enumerate(texts):
                suffix = f"-{i + 1}" if len(texts) > 1 else ""
                assets.append({
                    "id": f"text-evasion-{name.replace('_', '-')}{suffix}",
                    "label": "human",
                    "text": text,
                    "source": "storyscope/evasion_samples.py",
                    "note": "hand-written evasion sample",
                })
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: could not load storyscope evasion samples: {e}")

    return assets


def read_text(asset: dict) -> str:
    if asset.get("text"):
        return asset["text"]
    with open(asset["path"], "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def scan(detector: h.Detector, text: str, flags: dict, timeout: int):
    """Run both text detectors. Returns (scores, verdict_score, errors, extras)."""
    ss_status, ss = detector.post("/predict/storyscope", {"text": text, **flags}, timeout=timeout)
    dna_status, dna = detector.post("/predict/text/dna", {"text": text, **flags}, timeout=timeout)

    errors, extras = [], {}
    ss_score = ss.get("score") if ss_status == 200 and "error" not in ss else None
    dna_score = dna.get("score") if dna_status == 200 and "error" not in dna else None

    if ss_score is None:
        errors.append(f"storyscope: {ss.get('error', f'HTTP {ss_status}')}")
    if dna_score is None:
        errors.append(f"dna: {dna.get('error', f'HTTP {dna_status}')}")

    if ss_status == 200 and "error" not in ss:
        extras["storyscope_label"] = ss.get("label")
        extras["engine"] = f"{ss.get('engine')}/{ss.get('mode')}"
        extras["features"] = f"{ss.get('features_extracted')}/{ss.get('features_total')}"
        extras["top_reasons"] = ss.get("reasons", [])
    if dna_status == 200 and "error" not in dna:
        extras["dna_label"] = dna.get("label")

    scores = {"storyscope": ss_score, "dna": dna_score}
    # StoryScope is the primary narrative detector for these lengths.
    return scores, ss_score, errors, extras


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    h.add_common_args(ap)
    args = ap.parse_args()

    assets = h.filter_by_ids(collect_assets(), args.ids)
    if not assets:
        print("No text assets selected.")
        return 2

    detector = h.Detector(args.live, args.key)
    flags = h.payload_flags(args)
    records = []
    h.print_header("text", len(assets), detector)

    for asset in assets:
        try:
            text = read_text(asset)
        except Exception as e:  # noqa: BLE001
            rec = h.make_record(asset["id"], expected=asset["label"],
                                source=asset["source"], error=f"read failed: {e}")
        else:
            t0 = time.time()
            scores, primary, errors, extras = scan(detector, text, flags, args.timeout)
            rec = h.make_record(
                asset["id"],
                expected=asset["label"],
                source=asset["source"],
                scores=scores,
                verdict=h.text_verdict(asset["label"], primary) if primary is not None else None,
                error="; ".join(errors),
                note=asset.get("note", ""),
                elapsed_s=time.time() - t0,
                extra={**extras, "chars": len(text)},
            )
        records.append(rec)
        h.log_record(rec)

    return h.print_summary("text", records, detector, args.out)


if __name__ == "__main__":
    sys.exit(h.run_main(main))
