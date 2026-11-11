#!/usr/bin/env python3
"""Evaluate the image detector on the local ``Dataset/`` corpus.

Groups:

* ``brainrot``  - Dataset/brainrot images/*.jpg      (all AI-generated)
* ``ai``        - Dataset/ai vs real images/Ai_generated_dataset/**  (AI)
* ``real``      - Dataset/ai vs real images/real_dataset/**          (photos)

Runs the same layers the /predict/image/deep endpoint fuses (SynthID, C2PA,
AI metadata, frequency, DetectZoo neural, SPAI, pixel forensics) and reports
tier distribution + ranking (AUC) per group. This is the measurement harness
for any calibration work on this corpus.

Usage:
    .venv/bin/python scripts/eval_image_dataset.py --per-group 60
    .venv/bin/python scripts/eval_image_dataset.py --per-group 0 --json /tmp/eval.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET = ROOT / "Dataset"
BRAINROT_DIR = DATASET / "brainrot images"
AI_DIR = DATASET / "ai vs real images" / "Ai_generated_dataset"
REAL_DIR = DATASET / "ai vs real images" / "real_dataset"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def collect(per_group: int) -> list[dict]:
    """Deterministically sample `per_group` files per group (0 = all)."""
    entries: list[dict] = []

    def add(group: str, label: str, paths: list[Path]):
        paths = sorted(paths)
        if per_group and len(paths) > per_group:
            step = len(paths) / per_group
            paths = [paths[int(i * step)] for i in range(per_group)]
        for p in paths:
            entries.append({"group": group, "label": label, "path": str(p)})

    if BRAINROT_DIR.is_dir():
        add("brainrot", "ai", [p for p in BRAINROT_DIR.iterdir() if p.suffix.lower() in EXTS])
    if AI_DIR.is_dir():
        add("ai", "ai", [p for p in AI_DIR.rglob("*") if p.suffix.lower() in EXTS])
    if REAL_DIR.is_dir():
        add("real", "real", [p for p in REAL_DIR.rglob("*") if p.suffix.lower() in EXTS])
    return entries


def auc(scores: list[float], labels: list[int]) -> float:
    """Rank AUC (probability an AI item ranks above a real item)."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else (0.5 if p == n else 0.0)
    return wins / (len(pos) * len(neg))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-group", type=int, default=60,
                    help="files per group (0 = all)")
    ap.add_argument("--json", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    entries = collect(args.per_group)
    if args.limit:
        entries = entries[: args.limit]

    import server  # loads DetectZoo and all forensics modules
    from forensics import (
        probe_synthid_watermark,
        probe_c2pa_manifest,
        probe_ai_metadata,
        analyze_frequency_domain,
        analyze_neural_and_heatmap,
        fuse_ensemble_verdict,
    )
    from forensics import spai
    from forensics.learned_image import analyze_learned_image

    rows = []
    t0 = time.time()
    for i, e in enumerate(entries, 1):
        try:
            with Image.open(e["path"]) as img:
                img.load()
            raw = Path(e["path"]).read_bytes()
            s1 = probe_synthid_watermark(img)
            s2 = probe_c2pa_manifest(img, raw_bytes=raw)
            s_meta = probe_ai_metadata(img=img, raw_bytes=raw, kind="image")
            s3 = analyze_frequency_domain(img)
            s4 = analyze_neural_and_heatmap(e["path"], img)
            s5 = spai.detect(img)
            s_learn = analyze_learned_image(img)
            pf = server._pixel_forensics(e["path"])
            pf_reasons = []
            pf_strong = False
            if pf:
                if pf["boost"] and (s4["score"] is None or s4["score"] < pf["boost"]):
                    s4["score"] = pf["boost"]
                    pf_reasons.append(pf["reason"])
                if pf["doc_boost"] and (s4["score"] is None or s4["score"] < pf["doc_boost"]):
                    s4["score"] = pf["doc_boost"]
                    pf_reasons.append(pf["doc_reason"])
                pf_strong = bool(pf["boost"] and pf["boost"] >= 70)

            verdict = fuse_ensemble_verdict(
                layers={
                    "synthid": s1["score"],
                    "c2pa": s2["score"],
                    "metadata": s_meta["score"],
                    "frequency": s3["score"],
                    "neural": s4["score"],
                    "spai": s5["score"],
                    "learned": s_learn.get("score"),
                },
                layer_reasons={
                    "synthid": [s1["reason"]] if s1.get("reason") else [],
                    "c2pa": [s2["reason"]] if s2.get("reason") else [],
                    "metadata": [s_meta["reason"]] if s_meta.get("reason") else [],
                    "frequency": s3.get("reasons", []),
                    "neural": s4.get("reasons", []) + pf_reasons,
                    "spai": s5.get("reasons", []),
                    "learned": s_learn.get("reasons", []),
                },
                is_video=False,
                extra_data={"mode": "eval", "pf_strong": pf_strong},
            )
            row = {
                "group": e["group"],
                "label": e["label"],
                "path": os.path.relpath(e["path"], ROOT),
                "score": verdict["score"],
                "tier": verdict["tier"],
                "confidence": verdict.get("confidence"),
                "layers": {
                    "synthid": s1["score"], "c2pa": s2["score"],
                    "metadata": s_meta["score"], "frequency": s3["score"],
                    "neural": s4["score"], "spai": s5["score"],
                    "learned": s_learn.get("score"),
                    "pf_boost": pf["boost"] if pf else None,
                    "detectzoo": (s4.get("submodels") or {}).get("detectzoo"),
                },
            }
        except Exception as exc:  # noqa: BLE001
            row = {"group": e["group"], "label": e["label"], "path": e["path"],
                   "error": str(exc)}
        rows.append(row)
        if i % 10 == 0 or i == len(entries):
            print(f"  {i}/{len(entries)}  ({time.time() - t0:.0f}s)", flush=True)

    print("\n=== Tier distribution ===")
    tiers = ("SYNTHETIC_AI", "SUSPICIOUS", "UNCERTAIN", "INCONCLUSIVE", "AUTHENTIC_HUMAN")
    for group in ("brainrot", "ai", "real"):
        sub = [r for r in rows if r["group"] == group and "error" not in r]
        if not sub:
            continue
        print(f"\n{group} (n={len(sub)}):")
        for t in tiers:
            n = sum(1 for r in sub if r["tier"] == t)
            if n:
                print(f"  {t:16s} {n:4d}  {n / len(sub):6.1%}")
        scores = [r["score"] for r in sub]
        print(f"  score: mean {np.mean(scores):.1f}  median {np.median(scores):.1f}  "
              f"p10 {np.percentile(scores, 10):.1f}  p90 {np.percentile(scores, 90):.1f}")
        called_ai = sum(1 for r in sub if r["tier"] in ("SYNTHETIC_AI", "SUSPICIOUS"))
        print(f"  called AI (SYNTHETIC+SUSPICIOUS): {called_ai / len(sub):.1%}")

    ai_rows = [r for r in rows if r["label"] == "ai" and "error" not in r]
    real_rows = [r for r in rows if r["label"] == "real" and "error" not in r]
    if ai_rows and real_rows:
        print("\n=== Ranking ===")
        for combo in (ai_rows,):
            pass
        all_scored = ai_rows + real_rows
        print(f"  AUC (all AI vs real): {auc([r['score'] for r in all_scored], [1 if r['label'] == 'ai' else 0 for r in all_scored]):.4f}")
        br = [r for r in ai_rows if r["group"] == "brainrot"]
        if br:
            print(f"  AUC (brainrot vs real): {auc([r['score'] for r in br + real_rows], [1] * len(br) + [0] * len(real_rows)):.4f}")
        gen = [r for r in ai_rows if r["group"] == "ai"]
        if gen:
            print(f"  AUC (ai-dataset vs real): {auc([r['score'] for r in gen + real_rows], [1] * len(gen) + [0] * len(real_rows)):.4f}")

    if args.json:
        Path(args.json).write_text(json.dumps({"rows": rows}, indent=2))
        print(f"\nWrote {args.json}")
    print(f"\nDone in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
