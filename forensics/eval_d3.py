"""
Calibration harness for the D3 second-order dynamics layer.

    python -m forensics.eval_d3

There is no labelled in-the-wild video corpus in this repo, so (in the style
of the repo's other calibration notes) this harness synthesizes clips that
bracket the statistic's range:

  real-like   textured scene + camera motion (tripod / handheld / zoom /
              diagonal) + per-frame JPEG recompression + sensor noise - the
              codec and sensor chain keeps perturbing frame distances.
  gen-like    the SAME scene with generation-style content evolution: a fixed
              (or moving) camera while fine detail regenerates with a
              smoothly evolving phase - D3's "interpolated motion" failure
              case, both global and localized (e.g. a face region).
  static      codec noise but no motion - the layer must abstain.

For every candidate statistic the harness measures both groups and checks
whether the groups SEPARATE with a safe margin. Result (recorded 2026-09,
see the table the harness prints): in pixel/patch feature space every
variant overlaps or lands on the wrong side - which is why forensics/d3.py
is a metrics layer, not a voting layer. The D3 paper's separation comes from
SEMANTIC encoder features (XCLIP/DINOv2), unavailable in this numpy/PIL
stack.

If you change the descriptor extractor or add encoder embeddings, re-run
this harness: the moment a variant separates BOTH groups with margin >= 2x
here, it becomes a vote candidate - but calibrate on real social footage
before enabling the vote (synthetic pans are a floor, not a benchmark).
"""

from __future__ import annotations

import io
from typing import Callable, Dict, List

import numpy as np
from PIL import Image

from .d3 import (
    analyze_second_order_dynamics,
    second_order_volatility,
    MOTION_GATE,
)
from .trajectory import frame_descriptors, trajectory_metrics
from .pwtf import analyze_pixel_temporal_frequency


# ---------------------------------------------------------------------------
# Synthetic clip generation
# ---------------------------------------------------------------------------

def _photo_like_base(size=512, seed=7):
    """Procedural photo-like texture: multiscale smooth luminance structure,
    fine grain, saturated patches and hard edges."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64) / size
    img = np.zeros((size, size), dtype=np.float64)
    for freq, amp in ((3, 60), (7, 35), (15, 22), (31, 14)):
        px = rng.uniform(0, 2 * np.pi)
        py = rng.uniform(0, 2 * np.pi)
        img += amp * np.sin(2 * np.pi * freq * xx + px) * \
            np.cos(2 * np.pi * freq * yy + py)
    img += rng.normal(0, 6, (size, size))
    for _ in range(6):
        cy, cx = rng.integers(60, size - 60, 2)
        r = int(rng.integers(18, 70))
        val = rng.uniform(-70, 70)
        mask = (yy * size - cy) ** 2 + (xx * size - cx) ** 2 < r * r
        img[mask] += val
    img = np.clip(img + 128, 0, 255)
    rgb = np.stack(
        [img, np.clip(img * 0.96 + 6, 0, 255), np.clip(img * 0.9 + 14, 0, 255)],
        axis=-1,
    )
    return Image.fromarray(rgb.astype(np.uint8))


def _pan_clip(base, n=32, dx=2.0, dy=0.0, jitter=0.0, jpeg_q=None,
              noise_sigma=0.0, zoom=0.0, seed=3):
    """Render a pan/zoom clip. jitter = per-frame offset random-walk amplitude
    (px); jpeg_q = per-frame JPEG recompression quality; noise_sigma = sensor
    noise added to the FULL-RES frame."""
    rng = np.random.default_rng(seed)
    size = base.size[0]
    frames = []
    jx = jy = 0.0
    for t in range(n):
        jx += rng.normal(0, jitter) if jitter else 0.0
        jy += rng.normal(0, jitter) if jitter else 0.0
        z = 1.0 + zoom * t
        a = 1.0 / z
        shift_x = dx * t + jx + size * (z - 1) / (2 * z)
        shift_y = dy * t + jy + size * (z - 1) / (2 * z)
        frame = base.transform(
            (size, size), Image.AFFINE,
            (a, 0, shift_x, 0, a, shift_y),
            resample=Image.Resampling.BILINEAR,
        )
        arr = np.asarray(frame, dtype=np.float64)
        if noise_sigma:
            arr = arr + rng.normal(0, noise_sigma, arr.shape)
        frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        if jpeg_q:
            buf = io.BytesIO()
            frame.save(buf, format="JPEG", quality=jpeg_q)
            buf.seek(0)
            frame = Image.open(buf).convert("RGB")
        frames.append(frame)
    return frames


def _morph_clip(base, n=32, jpeg_q=None, noise_sigma=0.0, seed=3,
                localized=False, radius=80, speed=0.22):
    """Generation-style content evolution: the camera is FIXED but fine detail
    regenerates with a smoothly evolving phase (interpolated texture). With
    ``localized`` only a circular patch (e.g. a face region) regenerates."""
    rng = np.random.default_rng(seed)
    size = base.size[0]
    arr0 = np.asarray(base, dtype=np.float64)[..., 0]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64) / size
    amp_scale = 1.0
    mask = None
    if localized:
        cy, cx = size * 0.5, size * 0.42
        mask = ((yy * size - cy) ** 2 + (xx * size - cx) ** 2) < radius ** 2
        amp_scale = 2.6  # keep the localized signal above the noise floor
    frames = []
    for t in range(n):
        phase = speed * t
        drift = np.zeros((size, size), dtype=np.float64)
        for freq, amp in ((15, 10), (31, 8), (47, 5)):
            px = rng.uniform(0, 2 * np.pi)
            py = rng.uniform(0, 2 * np.pi)
            drift += amp * np.sin(2 * np.pi * freq * xx + px + phase) * \
                np.cos(2 * np.pi * freq * yy + py + 0.7 * phase)
        drift = drift * mask if mask is not None else drift
        img = np.clip(arr0 + amp_scale * drift, 0, 255)
        frame = Image.fromarray(np.stack([img] * 3, axis=-1).astype(np.uint8))
        if noise_sigma:
            a = np.asarray(frame, dtype=np.float64)
            a = a + rng.normal(0, noise_sigma, a.shape)
            frame = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        if jpeg_q:
            buf = io.BytesIO()
            frame.save(buf, format="JPEG", quality=jpeg_q)
            buf.seek(0)
            frame = Image.open(buf).convert("RGB")
        frames.append(frame)
    return frames


# ---------------------------------------------------------------------------
# Candidate second-order statistics
# ---------------------------------------------------------------------------

def _gray_stack(clip, res=96):
    return np.stack([
        np.asarray(f.convert("L").resize((res, res)), dtype=np.float64)
        for f in clip
    ])


def stat_global_vol(clip) -> float:
    """Paper statistic on raw patch descriptors: std(accel)/mean(vel)."""
    F = frame_descriptors(clip, res=96)
    v = np.linalg.norm(np.diff(F, axis=0), axis=1)
    return second_order_volatility(v)


def stat_global_vol_norm(clip) -> float:
    """Scale-invariant variant: std(accel)/std(vel)."""
    F = frame_descriptors(clip, res=96)
    v = np.linalg.norm(np.diff(F, axis=0), axis=1)
    return float((v[2:] - v[:-2]).std() / (v.std() + 1e-9))


def _region_vol_profile(gray_stack, cells=8):
    edges = np.linspace(0, gray_stack.shape[1], cells + 1).astype(int)
    vols, motions = [], []
    for y0, y1 in zip(edges[:-1], edges[1:]):
        for x0, x1 in zip(edges[:-1], edges[1:]):
            trace = gray_stack[:, y0:y1, x0:x1].mean(axis=(1, 2))
            v = np.abs(np.diff(trace))
            if v.size >= 3:
                vols.append(second_order_volatility(v))
                motions.append(float(v.mean()))
    vols = np.asarray(vols); motions = np.asarray(motions)
    w = motions + 1e-9
    return float((vols * w).sum() / w.sum())


def stat_region_vol(clip) -> float:
    """Motion-weighted per-region second-order volatility."""
    return _region_vol_profile(_gray_stack(clip))


STATS: Dict[str, Callable] = {
    "global_vol std(accel)/mean": stat_global_vol,
    "global_vol_norm std/std": stat_global_vol_norm,
    "region_volatility_mean": stat_region_vol,
}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def main():
    base = _photo_like_base()
    interval = 1.0 / 30.0

    real_clips = {
        "tripod pan dx=2 jpeg80 n2": _pan_clip(base, dx=2.0, jpeg_q=80, noise_sigma=2.0),
        "slow pan dx=1 jpeg80": _pan_clip(base, dx=1.0, jpeg_q=80, noise_sigma=2.0),
        "fast pan dx=6 jpeg75": _pan_clip(base, dx=6.0, jpeg_q=75, noise_sigma=2.5),
        "handheld j0.8 jpeg70 n3": _pan_clip(base, dx=2.5, jitter=0.8, jpeg_q=70, noise_sigma=3.0, seed=11),
        "handheld j1.5 jpeg70 n3": _pan_clip(base, dx=3.0, jitter=1.5, jpeg_q=70, noise_sigma=3.0, seed=17),
        "zoom 0.004 jpeg75": _pan_clip(base, zoom=0.004, jpeg_q=75, noise_sigma=2.0, seed=5),
        "diagonal pan jpeg85": _pan_clip(base, dx=1.6, dy=1.2, jpeg_q=85, noise_sigma=1.5, seed=13),
    }
    gen_clips = {
        "morph global clean": _morph_clip(base),
        "morph global jpeg75 n2": _morph_clip(base, jpeg_q=75, noise_sigma=2.0),
        "morph local clean": _morph_clip(base, localized=True),
        "morph local jpeg75": _morph_clip(base, localized=True, jpeg_q=75, noise_sigma=2.0),
        "morph local BIG r140": _morph_clip(base, localized=True, radius=140, jpeg_q=75, noise_sigma=2.0),
    }

    print("D3 second-order dynamics calibration harness")
    print(f"(motion gate {MOTION_GATE}; direction per paper: LOW volatility = "
          f"too-smooth = generation)\n")

    print("== layer behaviour (metrics-only, never votes) ==")
    for name, clip in list(real_clips.items())[:2]:
        d3 = analyze_second_order_dynamics(clip, frame_interval_seconds=interval)
        m = d3.get("metrics") or {}
        print(f"  {name:<26} score={d3.get('score')} active={d3.get('active')} "
              f"vol={m.get('volatility')}")
    static = analyze_second_order_dynamics(
        _pan_clip(base, dx=0.0, jpeg_q=80, noise_sigma=2.0),
        frame_interval_seconds=interval,
    )
    print(f"  {'static (gate)':<26} score={static.get('score')} "
          f"active={static.get('active')} (must abstain)")
    pwtf = analyze_pixel_temporal_frequency(list(real_clips.values())[0])
    print(f"  (reference: pwtf on clip 1 scores {pwtf.get('score')})")

    print("\n== candidate statistics: real-like vs generation-like ==")
    print(f"{'statistic':<28} {'real range':>16} {'gen range':>16}  verdict")
    any_separates = False
    for stat_name, fn in STATS.items():
        rv = [fn(c) for c in real_clips.values()]
        gv = [fn(c) for c in gen_clips.values()]
        rmin, rmax = min(rv), max(rv)
        gmin, gmax = min(gv), max(gv)
        # For this statistic family: real should be ABOVE gen-like.
        sep = rmin > 2 * gmax
        margin = f"{rmin / (gmax + 1e-9):.1f}x"
        any_separates = any_separates or sep
        verdict = (f"SEPARATES ({margin})" if sep else
                   f"OVERLAP (real_min/gen_max {margin})")
        print(f"{stat_name:<28} [{rmin:6.3f},{rmax:6.3f}] "
              f"[{gmin:6.3f},{gmax:6.3f}]  {verdict}")

    print("\n== trajectory geometry (ReStraV-style metrics; informational) ==")
    tm_real = trajectory_metrics(frame_descriptors(list(real_clips.values())[0], res=96))
    tm_gen = trajectory_metrics(frame_descriptors(list(gen_clips.values())[0], res=96))
    for k in tm_real:
        print(f"  {k:<20} real {tm_real[k]:>8}   gen-like {tm_gen[k]:>8}")

    print("\n== decision check ==")
    if any_separates:
        print("PASS-WITH-NOTE: a variant separates on the synthetic corpus. "
              "Do NOT enable voting until calibrated on real social footage "
              "vs generated clips (see forensics/d3.py docstring).")
    else:
        print("PASS: no pixel-space variant separates - confirms the "
              "metrics-only decision in forensics/d3.py (the D3 result "
              "requires semantic-encoder features).")


if __name__ == "__main__":
    main()
