"""Measure the capture-origin probe over the labelled video corpus.

This is the calibration step the layer itself refuses to skip: it prints the
per-clip native-resolution statistics so a threshold can only be placed where
the LABELLED corpus actually leaves a gap (and so a metric that does not
separate is visible immediately instead of being wired into a verdict).

Usage:
    .venv/bin/python scripts/probe_capture_origin.py --ids ig-DfA6rNyKDRU,ig-DaAd4iqhbnj
    .venv/bin/python scripts/probe_capture_origin.py --label human
    .venv/bin/python scripts/probe_capture_origin.py --files "test videos/vid1.mp4"

Downloads are cached in .detectzoo_data/video_cache/<id>.mp4, so re-running
after a code change costs nothing. Every clip is decoded with the same OpenCV
path the server uses, and the probe window matches the server's temporal window
(contiguous native-rate frames from the start of the analysed range).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from forensics import capture_origin  # noqa: E402

CACHE_DIR = os.path.join(ROOT, ".detectzoo_data", "video_cache")
ASSET_FILES = ("tests/media_test_assets.json", "tests/detector_assets.json")

WIN_START = 30        # skip the first second (intro / fade-in)
WIN_FRAMES = 48       # contiguous native-rate frames, like a temporal window
MAX_SIDE = 1280       # native unless the clip is larger than this


def load_assets() -> dict:
    assets = {}
    for rel in ASSET_FILES:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for key in ("videos", "reels", "assets"):
            for a in data.get(key) or []:
                if not isinstance(a, dict) or "id" not in a:
                    continue
                url = a.get("url") or ""
                if not url:
                    sc = a.get("shortcode")
                    if sc:
                        url = f"https://www.instagram.com/p/{sc}/"
                assets[a["id"]] = {
                    "label": a.get("label", ""),
                    "url": url,
                    "note": a.get("note", ""),
                }
    return assets


def fetch(asset_id: str, url: str) -> bytes:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{asset_id}.mp4")
    if os.path.exists(path) and os.path.getsize(path) > 20000:
        with open(path, "rb") as f:
            return f.read()
    if not url:
        raise RuntimeError("no url")
    import server  # noqa: PLC0415 - reuse the exact resolver the pipeline uses

    data, err = server._ytdlp_download(url)
    if not data:
        raise RuntimeError(err or "download failed")
    with open(path, "wb") as f:
        f.write(data)
    return data


def frames_from_bytes(data: bytes) -> list:
    """Decode the SERVED window at (near) native resolution."""
    import tempfile

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(data)
            tmp = f.name
        cap = cv2.VideoCapture(tmp)
        if not cap.isOpened():
            raise RuntimeError("decoder could not open the clip")
        frames = []
        idx = 0
        while idx < WIN_START + WIN_FRAMES:
            ok, frame = cap.read()
            if not ok:
                break
            if idx >= WIN_START:
                h, w = frame.shape[:2]
                long_side = max(h, w)
                if long_side > MAX_SIDE:
                    s = MAX_SIDE / float(long_side)
                    frame = cv2.resize(
                        frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA
                    )
                frames.append(frame)
            idx += 1
        cap.release()
        if len(frames) < capture_origin.MIN_FRAMES:
            raise RuntimeError(f"only {len(frames)} frames decoded")
        return frames
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


KEYS = (
    "flat_floor", "exact_flat_blocks", "flat_block_frac", "flat_pixel_frac",
    "dup_period", "dup_score", "row_identical", "col_identical",
    "edge_hard_share", "edge_mid_share",
    "residual_zero_frac", "residual_floor", "residual_mean",
)


def probe(asset_id: str, url: str) -> dict:
    data = fetch(asset_id, url)
    frames = frames_from_bytes(data)
    out = capture_origin.analyze_capture_origin(frames)
    return out.get("metrics") or {}


def print_table(rows: list) -> None:
    hdr = f"{'id':24}{'lab':6}" + "".join(f"{k[:13]:>14}" for k in KEYS)
    print(hdr)
    for r in sorted(rows, key=lambda r: (r["label"], r["id"])):
        cells = ""
        for k in KEYS:
            v = r.get(k)
            cells += f"{v:>14.4f}" if isinstance(v, float) else f"{'-':>14}"
        print(f"{r['id']:24}{r['label']:6}{cells}")

    print("\n=== SEPARATION (human max / min vs AI + target values) ===")
    humans = [r for r in rows if r["label"] == "human"]
    for k in KEYS:
        hv = [r[k] for r in humans if isinstance(r.get(k), float)]
        av = [r[k] for r in rows if r["label"] == "ai" and isinstance(r.get(k), float)]
        if not hv or not av:
            continue
        print(
            f"{k:20} human min {min(hv):9.4f}  max {max(hv):9.4f}   "
            f"ai min {min(av):9.4f}  max {max(av):9.4f}"
            f"{'   <-- SEPARATES' if (max(hv) < min(av) or min(hv) > max(av)) else ''}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="comma-separated asset ids")
    ap.add_argument("--label", default="", help="run every asset with this label")
    ap.add_argument("--files", default="", help="comma-separated local video paths")
    ap.add_argument("--out", default="tests/capture_origin_probe.json")
    args = ap.parse_args()

    assets = load_assets()
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
    for rel in [s.strip() for s in args.files.split(",") if s.strip()]:
        p = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        todo.append((os.path.basename(p), "local", p))

    rows = []
    for asset_id, label, url in todo:
        try:
            if label == "local":
                with open(url, "rb") as f:
                    data = f.read()
                metrics = capture_origin.analyze_capture_origin(
                    frames_from_bytes(data)
                ).get("metrics") or {}
            else:
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
