"""Measure the camera-physics probe over the labelled video corpus.

Companion to `scripts/probe_capture_origin.py` and the calibration step for
`forensics/camera_physics.py`. Prints per-clip native-resolution photon-transfer
/ fixed-pattern / residual-spectrum statistics so a threshold can only be placed
where the labelled corpus leaves a gap - and so a statistic that does not
separate is visible immediately instead of being wired into a verdict.

Usage:
    .venv/bin/python scripts/probe_camera_physics.py --label human
    .venv/bin/python scripts/probe_camera_physics.py --hyperreal
    .venv/bin/python scripts/probe_camera_physics.py --ids ig-DfA6rNyKDRU,ig-DaAd4iqhbnj

Downloads are cached in .detectzoo_data/video_cache/<id>.mp4; re-runs are free.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import probe_capture_origin as pco  # noqa: E402  (fetch + decode helpers)
from forensics import camera_physics  # noqa: E402

# The 8 hyper-realistic Higgsfield links the user supplied (2026-11-11).
HYPERREAL_IDS = [
    "ig-Dfko7WRJY9o",
    "ig-DdDKCrEKT3r",
    "ig-DeqTgBEhvAu",
    "ig-DfA6rNyKDRU",
    "ig-De1OcoyBkhZ",
    "ig-DecPhb-iBFr",
    "ig-DeWNa25MgzR",
    "ig-DeZyTL0t2Yi",
]

KEYS = (
    "noise_n_flat_px",
    "noise_slope", "noise_intercept", "noise_rsq", "noise_resid_norm",
    "noise_spearman", "noise_bright_dark",
    "fpn_ratio", "fpn_diff_corr",
    "noise_ac1_h", "noise_ac1_v",
    "tex_ac1_h", "tex_ac1_v",
)


def probe(asset_id: str, url: str) -> dict:
    data = pco.fetch(asset_id, url)
    frames = pco.frames_from_bytes(data)
    out = camera_physics.analyze_camera_physics(frames)
    return out.get("metrics") or {}


def print_table(rows: list) -> None:
    hdr = f"{'id':24}{'lab':6}" + "".join(f"{k[:14]:>16}" for k in KEYS)
    print(hdr)
    for r in sorted(rows, key=lambda r: (r["label"], r["id"])):
        cells = ""
        for k in KEYS:
            v = r.get(k)
            cells += f"{v:>16.4f}" if isinstance(v, float) else f"{'-':>16}"
        print(f"{r['id']:24}{r['label']:6}{cells}")

    print("\n=== SEPARATION (human vs AI) ===")
    humans = [r for r in rows if r["label"] == "human"]
    ais = [r for r in rows if r["label"] == "ai"]
    for k in KEYS:
        hv = [r[k] for r in humans if isinstance(r.get(k), float)]
        av = [r[k] for r in ais if isinstance(r.get(k), float)]
        if not hv or not av:
            continue
        sep = " <-- SEPARATES" if (max(hv) < min(av) or min(hv) > max(av)) else ""
        print(
            f"{k:20} human [{min(hv):9.4f}, {max(hv):9.4f}]   "
            f"ai [{min(av):9.4f}, {max(av):9.4f}]{sep}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default="", help="comma-separated asset ids")
    ap.add_argument("--label", default="", help="run every asset with this label")
    ap.add_argument("--hyperreal", action="store_true",
                    help="run the 8 hyper-realistic Higgsfield clips")
    ap.add_argument("--out", default="tests/camera_physics_probe.json")
    args = ap.parse_args()

    assets = pco.load_assets()
    todo = []
    if args.ids:
        for i in [s.strip() for s in args.ids.split(",") if s.strip()]:
            a = assets.get(i)
            if not a:
                print(f"{i}: not in the asset registry")
                continue
            todo.append((i, a["label"], a["url"]))
    if args.label:
        todo += [(k, v["label"], v["url"]) for k, v in assets.items() if v["label"] == args.label]
    if args.hyperreal:
        for i in HYPERREAL_IDS:
            a = assets.get(i)
            if not a:
                print(f"{i}: not in the asset registry")
                continue
            todo.append((i, a["label"], a["url"]))

    rows = []
    for asset_id, label, url in todo:
        try:
            metrics = probe(asset_id, url)
            rows.append({"id": asset_id, "label": label, **metrics})
            print(f"ok   {asset_id} ({label})")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {asset_id} ({label}): {e}")
            rows.append({"id": asset_id, "label": label})

    if rows:
        print()
        print_table(rows)
        out = os.path.join(ROOT, args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(rows, f, indent=2)
        print(f"\nwrote {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
