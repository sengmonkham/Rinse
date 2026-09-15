"""
Layer 4: Semantic Neural Classifier & ViT Patch Heatmap Ensemble.

Integrates CNNSpot, UnivFD (via DetectZoo), CLIP feature distribution analysis,
and a 16x16 patch-level synthetic texture detector that generates regional heatmaps.
"""

import os
import io
import base64
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


# Global cached instances
_DETECTZOO_DETECTOR = None
_CLIP_MODEL = None
_CLIP_PREPROCESS = None


def get_detectzoo_detector():
    """Lazy-load DetectZoo detector."""
    global _DETECTZOO_DETECTOR
    if _DETECTZOO_DETECTOR is None:
        try:
            from detectzoo import load_detector
            import os
            model_name = os.environ.get("MODEL_NAME", "cnnspot")
            _DETECTZOO_DETECTOR = load_detector(model_name, device="cpu")
        except Exception as e:
            print(f"DetectZoo lazy load failed: {e}")
            _DETECTZOO_DETECTOR = False
    return _DETECTZOO_DETECTOR if _DETECTZOO_DETECTOR is not False else None


def generate_patch_heatmap(img: Image.Image, grid_size: int = 16) -> Tuple[List[List[float]], str]:
    """
    Divide image into a grid_size x grid_size patch matrix (e.g. 16x16 = 256 patches)
    and score each patch as a LOCAL ANOMALY relative to the frame's own statistics.

    IMPORTANT: patch scores are NOT absolute "synthetic" probabilities. The old
    implementation scored saturation + smoothness absolutely, which flagged any
    dark-background / saturated-subject frame (i.e. virtually all social-media
    video) at 98% regardless of origin. Saturation and smoothness are style,
    not evidence. What generalizes is inconsistency: a spliced or regenerated
    region deviates from the frame's own texture/saturation norm, so each patch
    is compared against the frame-wide median instead.

    Generate 2D matrix [0.0 - 1.0] and an alpha-blended overlay image as base64 PNG.
    """
    w, h = img.size
    img_rgb = img.convert("RGB")
    arr = np.asarray(img_rgb).astype(np.float32)

    # Compute gradient magnitude and saturation maps
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)

    # Luminance gradient
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    dy, dx = np.gradient(luma)
    grad_mag = np.sqrt(dx ** 2 + dy ** 2)

    patch_w = w / grid_size
    patch_h = h / grid_size

    # ---- First pass: raw per-patch statistics ----
    raw = []  # (mean_sat, smoothness) per patch
    for row in range(grid_size):
        for col in range(grid_size):
            x1 = int(col * patch_w)
            y1 = int(row * patch_h)
            x2 = max(x1 + 1, int((col + 1) * patch_w))
            y2 = max(y1 + 1, int((row + 1) * patch_h))

            p_sat = sat[y1:y2, x1:x2]
            p_grad = grad_mag[y1:y2, x1:x2]

            mean_sat = float(p_sat.mean()) if p_sat.size > 0 else 0.0
            grad_std = float(p_grad.std()) if p_grad.size > 0 else 0.0
            grad_mean = float(p_grad.mean()) if p_grad.size > 0 else 0.0
            smoothness = max(0.0, 1.0 - (grad_std / max(grad_mean + 1.0, 1e-5)))
            raw.append((mean_sat, smoothness))

    sats = np.array([s[0] for s in raw])
    smooths = np.array([s[1] for s in raw])
    med_sat = float(np.median(sats))
    med_smooth = float(np.median(smooths))

    # ---- Second pass: anomaly relative to the frame's own norm ----
    heatmap_grid: List[List[float]] = []
    idx = 0

    # Color overlay image (RGBA)
    overlay = Image.new("RGBA", (grid_size, grid_size), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    for row in range(grid_size):
        row_scores: List[float] = []
        for col in range(grid_size):
            mean_sat, smoothness = raw[idx]
            idx += 1

            # Only deviations ABOVE the frame median flag: a patch that is
            # much smoother / more saturated than the frame's typical patch.
            rel_smooth = float(np.clip((smoothness - med_smooth) * 2.0, 0.0, 1.0))
            rel_sat = float(np.clip((mean_sat - med_sat) * 2.5, 0.0, 1.0))

            patch_score = float(np.clip(0.55 * rel_smooth + 0.45 * rel_sat, 0.02, 0.98))
            row_scores.append(round(patch_score, 3))

            # Color map: Green (consistent < 0.4) -> Yellow (0.4-0.7) -> Red (anomalous > 0.7)
            if patch_score > 0.65:
                # Red with alpha
                r_c, g_c, b_c, a_c = 239, 68, 68, int(patch_score * 160)
            elif patch_score > 0.45:
                # Amber with alpha
                r_c, g_c, b_c, a_c = 245, 158, 11, int(patch_score * 130)
            else:
                # Emerald / Transparent
                r_c, g_c, b_c, a_c = 16, 185, 129, int((1.0 - patch_score) * 110)

            overlay_draw.point((col, row), fill=(r_c, g_c, b_c, a_c))

        heatmap_grid.append(row_scores)

    # Upscale overlay to match original aspect
    overlay_resized = overlay.resize((w, h), Image.Resampling.BILINEAR)

    # Export overlay as base64 PNG
    buf = io.BytesIO()
    overlay_resized.save(buf, format="PNG")
    overlay_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    return heatmap_grid, overlay_b64


def _flat_render_signature(img: Image.Image) -> Tuple[bool, int, float]:
    """
    Whole-frame flat-render check (cel-shaded toon / 3D-render look): a very
    small distinct-color count combined with high saturation. This is the same
    offline signature the browser extension uses; it is a narrow, honest rule -
    it says nothing about photorealistic content.

    Returns (is_flat_render, distinct_colors, mean_saturation).
    """
    small = img.convert("RGB").resize((256, 256), Image.Resampling.BILINEAR)
    arr = np.asarray(small)
    buckets = ((arr[..., 0].astype(np.int32) >> 4) << 8) | \
              ((arr[..., 1].astype(np.int32) >> 4) << 4) | \
              (arr[..., 2].astype(np.int32) >> 4)
    distinct = int(np.unique(buckets).size)
    mx = arr.max(axis=2).astype(np.float32)
    mn = arr.min(axis=2).astype(np.float32)
    sat_mean = float(((mx - mn) / np.maximum(mx, 1.0)).mean())

    # Edge-density gate: renders have clean outlines over flat fills, while
    # camera photos - even smooth ones - carry sensor/texture edges everywhere
    # (mirrors the pixel-forensics heuristic). Note that near-black backgrounds
    # have HIGH saturation ratios, so saturation alone cannot gate this rule.
    edges = np.asarray(small.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    edge_density = float((edges > 60).mean())

    is_flat = distinct < 700 and sat_mean > 0.5 and edge_density < 0.12
    return is_flat, distinct, sat_mean


def analyze_neural_and_heatmap(
    img_path: str,
    img: Image.Image,
    allow_flat_render_vote: bool = True,
) -> Dict[str, Any]:
    """
    Run Layer 4 neural classifier ensemble + 16x16 patch heatmap analysis.

    The patch heatmap is a LOCAL ANOMALY map (relative to the frame's own
    statistics) used for visualization and as a minor fusion term - it is NOT
    an absolute synthetic-probability model. When the trained DetectZoo
    classifier is unavailable, the layer only votes via the narrow flat-render
    signature and otherwise reports inactive rather than fabricating a
    content-driven score (the old behavior scored every dark-background /
    saturated-subject frame - i.e. all social video - at 98%).

    For VIDEO analysis, pass allow_flat_render_vote=False: the flat-render
    signature detects saturated cartoon/animation STYLE, not generation. It
    fires on ~74% of frames of a real hand-drawn animation reel (measured)
    while never firing on photorealistic AI clips, so on video frames it only
    produces false positives. Video verdicts must come from the temporal
    layers instead.
    """
    submodels: Dict[str, Any] = {}
    reasons: List[str] = []

    # 1. DetectZoo (CNNSpot / UnivFD) - the only trained model in this layer.
    detector = get_detectzoo_detector()
    detectzoo_score = None
    if detector is not None:
        try:
            target = img if (not img_path or not os.path.exists(img_path)) else img_path
            res = detector.predict(target)
            if hasattr(res, "score"):
                raw_score = res.score
            elif hasattr(res, "probability"):
                raw_score = res.probability
            elif isinstance(res, dict) and "score" in res:
                raw_score = res["score"]
            else:
                raw_score = 0.5

            detectzoo_score = int(raw_score * 100) if raw_score <= 1.0 else int(raw_score)
            submodels["detectzoo"] = detectzoo_score
            reasons.append(f"DetectZoo ({detector.__class__.__name__}) spatial classifier: {detectzoo_score}% confidence.")
        except Exception as e:
            print(f"DetectZoo prediction failed: {e}")

    # 2. Patch anomaly heatmap (relative to the frame's own statistics).
    heatmap_grid, heatmap_b64 = generate_patch_heatmap(img, grid_size=16)
    flattened = [v for row in heatmap_grid for v in row]
    vit_patch_mean = float(np.mean(flattened))
    vit_patch_max = float(np.max(flattened))
    vit_anomalous_patches = int(sum(1 for v in flattened if v >= 0.65))

    vit_score = int(np.clip((vit_patch_mean * 70) + (vit_anomalous_patches / 2.56 * 30), 5, 95))
    submodels["vit_patch"] = vit_score
    reasons.append(
        f"Patch anomaly map: {vit_anomalous_patches}/256 patches inconsistent with the "
        f"frame's own texture norm (mean deviation {vit_patch_mean:.2f}) - regional "
        f"highlight only, not an absolute AI verdict."
    )

    # 3. Fusion. A trained classifier dominates; the anomaly map is a minor
    #    term because legitimate photos contain smooth regions (skies, studio
    #    backdrops) that any content-based rule will highlight.
    if detectzoo_score is not None:
        neural_final = int(0.75 * detectzoo_score + 0.25 * vit_score)
        return {
            "score": int(np.clip(neural_final, 5, 99)),
            "heatmap_grid": heatmap_grid,
            "heatmap_overlay_base64": heatmap_b64,
            "synthetic_patches_count": vit_anomalous_patches,
            "submodels": submodels,
            "reasons": reasons,
        }

    # No trained model available: only the narrow flat-render signature may
    # produce a vote; anything photorealistic stays out of the fusion. Video
    # frames disable this vote entirely (style != generation, see docstring).
    is_flat, distinct, sat_mean = (False, 0, 0.0)
    if allow_flat_render_vote:
        is_flat, distinct, sat_mean = _flat_render_signature(img)
    if is_flat:
        submodels["flat_render"] = 72
        reasons.append(
            f"Flat cel-shaded render palette ({distinct} distinct colors, "
            f"{round(sat_mean * 100)}% mean saturation, sparse texture edges) - "
            f"toon/3D-render AI signature."
        )
        return {
            "score": 72,
            "heatmap_grid": heatmap_grid,
            "heatmap_overlay_base64": heatmap_b64,
            "synthetic_patches_count": vit_anomalous_patches,
            "submodels": submodels,
            "reasons": reasons,
        }

    return {
        "score": None,
        "heatmap_grid": heatmap_grid,
        "heatmap_overlay_base64": heatmap_b64,
        "synthetic_patches_count": vit_anomalous_patches,
        "submodels": submodels,
        "reasons": reasons + [
            "No trained neural classifier available (DetectZoo weights not installed) - "
            "neural layer inactive for photorealistic content; remaining layers carry the verdict."
        ],
    }
