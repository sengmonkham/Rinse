"""
Capture-origin probe: NATIVE-RESOLUTION camera-vs-render evidence.

Why this layer exists
---------------------
Every temporal layer in this stack (PwTF-DVD, temporal-residual, D3, rPPG)
sees a 128x128 GRAYSCALE thumbnail. That downscale is deliberate - it is what
makes the coherence-floor statistic resolution-calibrated and cheap - but it
throws away precisely the evidence that separates a camera capture from a
rendered image sequence:

  * a camera has a LENS: optics band-limit the image, so edges are anti-aliased
    and gradients are spread over several pixels (soft edge population);
  * a camera has a SENSOR: no two pixels are ever exactly equal, even in a flat
    wall or a still frame - read noise guarantees a non-zero residual floor;
  * a camera has MULTI-PIXEL OPTICS + NOISE, so two adjacent ROWS of an image are
    never byte-identical across their whole width.

A rendered clip (pixel-art or photoreal diffusion) can have none of these: flat
fills are exactly flat, a frame generated at low resolution and nearest-neighbour
upscaled repeats exact pixel blocks, and a temporally static generated region
produces EXACTLY zero inter-frame residual.

Measured calibration (2026-11-11, `scripts/probe_capture_origin.py`) is the only
authority for the score mapping below; until it has run over the labelled corpus
this layer is METRICS-ONLY (`score` is None) and must not vote. Several
plausible-looking statistics were ALREADY measured and rejected as totally
non-discriminating on this corpus, so do not re-add them:

  * `static_pixel_fraction` from pwtf.py - a confirmed-HUMAN clip reads 0.2598,
    higher than either problematic AI clip (0.1186 / 0.0585);
  * the wavelet high-frequency deficit in frequency.py - it fires on EVERY real
    photo too (real range 0.0002-0.0045, i.e. always below its 0.008 gate);
  * SPAI reconstruction similarity / spectral heterogeneity - the real clips
    (0.951-0.974 similarity) bracket both targets (0.953 / 0.961).

CPU-only, numpy, no weights, no network.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

MIN_FRAMES = 3

# --- Calibrated pixel-art / rendered-sequence gate (measured 2026-11-11) ---
# `scripts/probe_capture_origin.py` over 5 confirmed-real Instagram clips plus
# the local references and 9 known-AI clips gave these ranges:
#
#   statistic            human (5 clips)        AI pixel-art clip
#   exact_flat_blocks    0.0483 - 0.1849        0.9368   (5.1x the human max)
#   flat_pixel_frac      0.1618 - 0.2954        0.9494   (3.2x)
#   row_identical        0.0000 - 0.0226        0.6966   (30x)
#
# A camera cannot produce any of these: read noise makes flat fills inexact
# and two whole image rows are never byte-identical. A rendered image sequence
# with large exactly-flat fills (pixel art, flat-shaded animation) does all
# three. The conjunction is required - each statistic alone reaches 0.29-0.34
# on real clips with big dark/flat regions after H.264 quantisation.
#
# What this gate deliberately does NOT catch: photoreal diffusion video. The
# Higgsfield clip measured exact_flat_blocks 0.1145 / flat_pixel_frac 0.2459 /
# row_identical 0.0052, i.e. INSIDE the human range on all three - it has real
# rendered texture and real motion, so it is not a flat-fill render.
_PIXEL_ART_EXACT_FLAT_MIN = 0.60
_PIXEL_ART_FLAT_PIXEL_MIN = 0.60
_PIXEL_ART_ROW_IDENTICAL_MIN = 0.10

# Blocks are 8x8 to match the luma coding block of H.264, so codec blocking
# stays INSIDE a block (it is removed with the block mean) instead of being
# counted as camera texture.
BLOCK = 8

# Edge magnitude buckets (on the 0-255 luma difference scale). A lens spreads a
# step edge over several pixels, so real footage carries a large INTERMEDIATE
# population; a rendered image jumps 0 -> 255 with nothing in between.
HARD_EDGE = 40.0
MID_EDGE = 10.0
SOFT_EDGE = 2.0


def _to_gray(frame: Any) -> np.ndarray:
    """uint8 grayscale, accepting PIL frames or OpenCV BGR/gray arrays."""
    if isinstance(frame, Image.Image):
        return np.asarray(frame.convert("L"), dtype=np.uint8)
    a = np.asarray(frame)
    if a.ndim == 3:
        if a.shape[2] == 4:
            a = a[..., :3]
        # OpenCV convention: BGR. The stack only ever hands over BGR or gray.
        a = 0.114 * a[..., 0] + 0.587 * a[..., 1] + 0.299 * a[..., 2]
    return np.clip(a, 0, 255).astype(np.uint8)


def _block_mad(g: np.ndarray, block: int = BLOCK) -> np.ndarray:
    """Per-block mean absolute deviation from the block mean.

    Using the block MEAN as the predictor is what makes this robust to the
    encoder: an 8x8 DCT block that the codec quantised to a DC-only block
    yields mad == 0 no matter what the source was, and ringing inside a block
    shows up as deviation. This is why the metric is a *floor* (a low
    percentile) rather than an average: we want the smoothest content, where a
    camera's read noise cannot be removed by any amount of compression.
    """
    h, w = g.shape
    h -= h % block
    w -= w % block
    if h < block or w < block:
        return np.zeros(1, dtype=np.float32)
    b = (
        g[:h, :w]
        .astype(np.float32)
        .reshape(h // block, block, w // block, block)
        .transpose(0, 2, 1, 3)
        .reshape(-1, block * block)
    )
    mu = b.mean(axis=1, keepdims=True)
    return np.abs(b - mu).mean(axis=1)


def _frame_stats(g: np.ndarray) -> Dict[str, float]:
    """Single-frame render-vs-camera statistics."""
    gf = g.astype(np.float32)

    # --- flat-region residual floor -------------------------------------
    mad = _block_mad(g)
    flat_floor = float(np.percentile(mad, 10))
    exact_flat = float(np.mean(mad == 0.0))
    flat_block_frac = float(np.mean(mad < 0.25))

    # --- exact duplication (nearest-neighbour upscale / flat fills) ------
    eq1 = float(np.mean(g[:, :-1] == g[:, 1:]))
    eqk = {
        k: float(np.mean(g[:, :-k] == g[:, k:]))
        for k in (2, 4, 8, 16)
        if g.shape[1] > k + 1
    }
    best_k, best_eq = 1, eq1
    for k in (2, 4, 8, 16):
        if eqk.get(k, 0.0) > best_eq:
            best_k, best_eq = k, eqk[k]
    row_identical = float(np.mean(np.all(g[:-1] == g[1:], axis=1)))
    col_identical = float(np.mean(np.all(g[:, :-1] == g[:, 1:], axis=0)))

    # A pixel whose four neighbours are all exactly equal to it sits inside a
    # perfectly flat fill - impossible in a camera frame after quantisation.
    c = g[1:-1, 1:-1]
    flat_px = float(np.mean(
        (c == g[:-2, 1:-1]) & (c == g[2:, 1:-1])
        & (c == g[1:-1, :-2]) & (c == g[1:-1, 2:])
    ))

    # --- lens / anti-aliasing edge population ---------------------------
    gx = np.abs(np.diff(gf, axis=1))
    gy = np.abs(np.diff(gf, axis=0))
    m = min(gx.shape[0], gy.shape[0])
    n = min(gx.shape[1], gy.shape[1])
    mag = np.sqrt(gx[:m, :n] ** 2 + gy[:m, :n] ** 2)
    hard = float(np.mean(mag >= HARD_EDGE))
    mid = float(np.mean((mag >= MID_EDGE) & (mag < HARD_EDGE)))
    soft = float(np.mean((mag >= SOFT_EDGE) & (mag < MID_EDGE)))
    denom = hard + mid + soft + 1e-9
    edge_hard_share = hard / denom
    # Share of edge energy that carries an INTERMEDIATE step - the optical
    # signature of a lens (blur/AA) rather than a hard render boundary.
    edge_mid_share = mid / (hard + mid + 1e-9)

    return {
        "flat_floor": flat_floor,
        "exact_flat_blocks": exact_flat,
        "flat_block_frac": flat_block_frac,
        "eq_lag1": eq1,
        "dup_period": float(best_k),
        "dup_score": float(best_eq),
        "row_identical": row_identical,
        "col_identical": col_identical,
        "flat_pixel_frac": flat_px,
        "edge_hard_share": edge_hard_share,
        "edge_mid_share": edge_mid_share,
        "edge_hard": hard,
        "edge_mid": mid,
    }


def _temporal_stats(g0: np.ndarray, g1: np.ndarray) -> Dict[str, float]:
    """Inter-frame residual statistics for one consecutive frame pair.

    A camera frame pair always differs everywhere by at least read/compression
    noise. A generated clip whose region is temporally static differs by
    EXACTLY zero in that region, and a clip generated from a still image warped
    by a slow camera move leaves a residual far below the noise floor.
    """
    r = g1.astype(np.int16) - g0.astype(np.int16)
    absr = np.abs(r)
    zero_frac = float(np.mean(r == 0))
    mad = _block_mad(absr.astype(np.uint8))
    return {
        "residual_zero_frac": zero_frac,
        "residual_floor": float(np.percentile(mad, 10)),
        "residual_mean": float(absr.mean()),
    }


def analyze_capture_origin(frames: List[Any]) -> Dict[str, Any]:
    """Measure render-vs-camera signatures over a contiguous frame window.

    Args:
        frames: contiguous frames (PIL images or OpenCV BGR arrays) at native
            resolution. A downscaled stack defeats the purpose of the layer.

    Returns a dict with `score` (None = metrics-only), `active`, `metrics`,
    `reasons` and `detail`. Never raises.
    """
    try:
        grays = [_to_gray(f) for f in frames if f is not None]
        if len(grays) < MIN_FRAMES:
            return {
                "score": None,
                "active": False,
                "metrics": {},
                "reasons": [
                    f"Capture-origin probe inactive: {len(grays)} usable frame(s), "
                    f"needs at least {MIN_FRAMES}."
                ],
                "detail": {},
            }

        # Frame statistics on an evenly spread subset (a window can be 32-48
        # frames; content repeats, so 8 frames is enough and keeps latency low).
        idx = sorted({
            int(round(i * (len(grays) - 1) / 7.0)) for i in range(8)
        })
        per_frame = [_frame_stats(grays[i]) for i in idx]
        metrics: Dict[str, float] = {}
        for k in per_frame[0]:
            metrics[k] = float(np.mean([f[k] for f in per_frame]))

        # Temporal statistics on consecutive pairs inside the same window.
        pairs = [_temporal_stats(grays[i], grays[i + 1]) for i in range(len(grays) - 1)]
        for k in pairs[0]:
            metrics[k] = float(np.mean([p[k] for p in pairs]))

        metrics["frames"] = float(len(grays))
        metrics["resolution"] = float(grays[0].shape[0] * grays[0].shape[1])

        reasons = [
            f"Capture-origin probe (native resolution {grays[0].shape[1]}x{grays[0].shape[0]}, "
            f"{len(grays)} frames): flat-region residual floor {metrics['flat_floor']:.2f}, "
            f"edge hard share {metrics['edge_hard_share']:.3f}, intermediate edge share "
            f"{metrics['edge_mid_share']:.3f}, exactly-flat 8x8 blocks "
            f"{metrics['exact_flat_blocks']:.3f}, flat pixels {metrics['flat_pixel_frac']:.3f}, "
            f"identical rows {metrics['row_identical']:.3f}, zero inter-frame residual "
            f"{metrics['residual_zero_frac']:.3f}.",
        ]

        # Rendered pixel-art / flat-fill sequence. Only the calibrated
        # conjunction votes (see the gate note at the top of the module).
        score: Optional[int] = None
        active = False
        exact_flat = metrics["exact_flat_blocks"]
        flat_px = metrics["flat_pixel_frac"]
        row_id = metrics["row_identical"]
        if (
            metrics["frames"] >= 8
            and exact_flat >= _PIXEL_ART_EXACT_FLAT_MIN
            and flat_px >= _PIXEL_ART_FLAT_PIXEL_MIN
            and row_id >= _PIXEL_ART_ROW_IDENTICAL_MIN
        ):
            active = True
            # Strength = how far the clip sits past the gate, normalised by the
            # measured headroom (gate -> the pixel-art values above). Graded so
            # two rendered clips do not both report the same number.
            strength = min(
                1.0,
                max(
                    0.0,
                    0.5 * (exact_flat - _PIXEL_ART_EXACT_FLAT_MIN) / 0.34
                    + 0.3 * (flat_px - _PIXEL_ART_FLAT_PIXEL_MIN) / 0.35
                    + 0.2 * (row_id - _PIXEL_ART_ROW_IDENTICAL_MIN) / 0.60,
                ),
            )
            score = int(round(70.0 + 9.0 * strength))
            reasons.append(
                f"Rendered image sequence at native resolution: {exact_flat:.0%} of 8x8 "
                f"blocks are EXACTLY flat ({flat_px:.0%} of pixels sit inside a perfectly "
                f"uniform neighbourhood) and {row_id:.0%} of image rows are byte-identical "
                f"to the next row. Camera footage cannot produce this - sensor read noise "
                f"guarantees a non-zero residual floor in flat areas and two whole rows are "
                f"never identical - so the frames were rendered on an exact pixel grid "
                f"(pixel-art / flat-shaded animation) rather than captured by a lens. "
                f"Calibrated: confirmed-real clips measured at most {0.1849:.0%} / "
                f"{0.2954:.0%} / {0.0226:.0%} on the same statistics. This proves the frames "
                f"were RENDERED, not captured: it is not by itself proof of an AI generator "
                f"(hand-made pixel-art animation is also a rendered grid), which is why the "
                f"score stops at the suspicious band."
            )
        else:
            reasons.append(
                "No rendered-sequence signature: flat fills, row duplication and block "
                "exactness sit inside the range measured on confirmed-real camera footage, "
                "so the native-resolution layer has no evidence either way and abstains "
                "(it cannot detect photoreal diffusion video - see the module note)."
            )

        return {
            "score": score,
            "active": active,
            "metrics": {k: round(v, 6) for k, v in metrics.items()},
            "reasons": reasons,
            "detail": {"frames_sampled": len(idx), "pairs": len(pairs)},
        }
    except Exception as e:  # noqa: BLE001 - metrics layer must never break a verdict
        return {
            "score": None,
            "active": False,
            "metrics": {},
            "reasons": [f"Capture-origin probe unavailable: {e}"],
            "detail": {},
        }
