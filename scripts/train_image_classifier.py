#!/usr/bin/env python3
"""Train the dataset-trained image layer on the local ``Dataset/`` corpus.

Two calibrated heads, because the two AI families need different features:

* ``render`` - CLIP ViT-B/32 embeddings + linear head. Brainrot renders vs the
  real-photo corpus. This is the head that fixes the reported failure (viral
  brainrot images read as camera photos by CNNSpot).
* ``photo`` - cheap pixel statistics (forensics/image_features.py) + linear
  head. The photoreal ``Ai_generated_dataset`` vs the real-photo corpus.

Both heads are exported to ``forensics/models/image_classifier.json`` as
scaler + coefficients; inference (forensics/learned_image.py) is numpy only.

Measured held-out performance (full corpus, GroupKFold over sources):
  render head  AUC 0.9955, 96.2% recall at 1.9% FPR (p>=0.95)
  photo head   AUC 0.8454, 55.6% recall at 1.2% FPR (p>=0.90)

Held-out evaluation is grouped: a "source" is one AI/real category, or a
contiguous block of brainrot filenames (consecutive frames from one clip are
near-duplicates, so a random split would leak them across folds). Metrics are
therefore measured on unseen categories / unseen clip blocks, not memorised
images.

Usage:
    .venv/bin/python scripts/train_image_classifier.py
    .venv/bin/python scripts/train_image_classifier.py --limit-brainrot 2000
    .venv/bin/python scripts/train_image_classifier.py --refresh
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET = ROOT / "Dataset"
BRAINROT = DATASET / "brainrot images"
AI_DIR = DATASET / "ai vs real images" / "Ai_generated_dataset"
REAL_DIR = DATASET / "ai vs real images" / "real_dataset"
MODEL_PATH = ROOT / "forensics" / "models" / "image_classifier.json"
STATS_CACHE = ROOT / "cache" / "image_classifier_features.npz"
CLIP_CACHE = ROOT / "cache" / "image_classifier_clip.npz"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
BRAINROT_BLOCKS = 8
# Strong L2. Measured on the full 5,000-frame brainrot corpus: C=0.1 lets the
# head memorise camera/category quirks (12.8% real FPR at p>=0.85); C=0.02
# keeps 98.2% recall at 8.7% and 96.2% at 1.9%. The calibrated score mapping
# only escalates at p>=0.955, i.e. the ~2% FPR operating point.
HEAD_C = 0.02

# The photoreal head is the hardest: its two classes are "photoreal AI" vs
# "real stock photos", which overlap far more than brainrot-vs-real. A stronger
# C is needed so the head can fit modern photoreal exemplars; measured
# GroupKFold AUC ~0.80 at C=0.1 (vs ~0.78 at C=0.02) and it is the only head
# that separates the "images it cant detect" exemplars. The runtime caps its
# score at SUSPICIOUS to keep a photoreal mistake out of the SYNTHETIC tier.
PHOTOREAL_C = 0.1


def _extract_stats_one(path: str) -> list[float] | None:
    try:
        from forensics.image_features import extract_features, feature_names
        with Image.open(path) as img:
            img.load()
            feats = extract_features(img)
        return [feats[n] for n in feature_names()]
    except Exception:
        return None


def collect_entries(limit_brainrot: int) -> list[dict]:
    entries: list[dict] = []
    if BRAINROT.is_dir():
        files = sorted(p for p in BRAINROT.iterdir() if p.suffix.lower() in EXTS)
        if limit_brainrot and len(files) > limit_brainrot:
            step = len(files) / limit_brainrot
            files = [files[int(i * step)] for i in range(limit_brainrot)]
        n = len(files)
        for i, p in enumerate(files):
            entries.append({
                "path": str(p), "label": 1, "group": "brainrot",
                "source": f"brainrot-block-{i * BRAINROT_BLOCKS // max(n, 1)}",
            })
    for group, label, base in (("ai", 1, AI_DIR), ("real", 0, REAL_DIR)):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix.lower() not in EXTS:
                continue
            entries.append({
                "path": str(p), "label": label, "group": group,
                "source": f"{group}/{p.parent.name}",
            })
    return entries


def _load_cached(cache_path: Path, entries: list[dict]):
    if not cache_path.exists():
        return None
    data = np.load(cache_path, allow_pickle=True)
    cached = {str(p): row for p, row in zip(data["paths"], data["X"])}
    if any(e["path"] not in cached for e in entries):
        return None
    return np.asarray([cached[e["path"]] for e in entries], dtype=np.float64)


def load_stats(entries: list[dict], jobs: int, refresh: bool) -> np.ndarray:
    if not refresh:
        X = _load_cached(STATS_CACHE, entries)
        if X is not None:
            print(f"Loaded cached pixel-statistics features ({X.shape}).")
            return X
    print(f"Extracting pixel-statistics features for {len(entries)} images...")
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        vecs = list(pool.map(_extract_stats_one, [e["path"] for e in entries], chunksize=16))
    keep = [i for i, v in enumerate(vecs) if v is not None]
    if len(keep) != len(vecs):
        entries[:] = [entries[i] for i in keep]
        vecs = [vecs[i] for i in keep]
    X = np.asarray(vecs, dtype=np.float64)
    STATS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(STATS_CACHE, paths=np.asarray([e["path"] for e in entries]), X=X)
    print(f"  {X.shape} in {time.time() - t0:.0f}s")
    return X


def load_clip(entries: list[dict], refresh: bool) -> np.ndarray:
    if not refresh:
        E = _load_cached(CLIP_CACHE, entries)
        if E is not None:
            print(f"Loaded cached CLIP embeddings ({E.shape}).")
            return E
    from forensics.learned_image import clip_embedding

    print(f"Extracting CLIP ViT-B/32 embeddings for {len(entries)} images...")
    t0 = time.time()
    rows = []
    for i, e in enumerate(entries, 1):
        try:
            with Image.open(e["path"]) as img:
                img.load()
                emb = clip_embedding(img)
        except Exception:
            emb = None
        if emb is None:
            raise SystemExit(
                "CLIP embeddings unavailable - install open-clip-torch and let it "
                "download the ViT-B-32/openai weights, then rerun."
            )
        rows.append(emb)
        if i % 500 == 0:
            print(f"  {i}/{len(entries)} ({time.time() - t0:.0f}s)", flush=True)
    E = np.asarray(rows, dtype=np.float64)
    CLIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CLIP_CACHE, paths=np.asarray([e["path"] for e in entries]), X=E)
    print(f"  {E.shape} in {time.time() - t0:.0f}s")
    return E


def _head_model(C: float = HEAD_C):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        StandardScaler(),
        LogisticRegression(C=C, class_weight="balanced", max_iter=6000),
    )


def evaluate_head(X: np.ndarray, y: np.ndarray, sources: np.ndarray, C: float = HEAD_C) -> dict:
    """Grouped 5-fold OOF predictions + operating-point metrics."""
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold

    oof = np.zeros(len(y), dtype=np.float64)
    for tr, te in GroupKFold(n_splits=min(5, len(set(sources)))).split(X, y, groups=sources):
        model = _head_model(C).fit(X[tr], y[tr])
        oof[te] = model.predict_proba(X[te])[:, 1]

    pos, neg = oof[y == 1], oof[y == 0]
    metrics = {"grouped_auc": round(float(roc_auc_score(y, oof)), 4)}
    for budget in (0.01, 0.05, 0.10):
        threshold = float(np.quantile(neg, 1.0 - budget))
        metrics[f"tpr_at_fpr_{int(budget * 100)}"] = round(float(np.mean(pos >= threshold)), 4)
    for th in (0.70, 0.85, 0.95):
        metrics[f"recall_at_{th}"] = round(float(np.mean(pos >= th)), 4)
        metrics[f"fpr_at_{th}"] = round(float(np.mean(neg >= th)), 4)
        metrics[f"precision_at_{th}"] = round(
            float(np.sum((oof >= th) & (y == 1)) / max(np.sum(oof >= th), 1)), 4
        )
    return {"metrics": metrics, "oof": oof}


def export_head(model, feature_names=None) -> dict:
    scaler = model.named_steps["standardscaler"]
    clf = model.named_steps["logisticregression"]
    head = {
        "scaler_mean": [float(v) for v in scaler.mean_],
        "scaler_scale": [float(v) for v in scaler.scale_],
        "coef": [float(v) for v in clf.coef_[0]],
        "intercept": float(clf.intercept_[0]),
    }
    if feature_names is not None:
        head["feature_names"] = list(feature_names)
    return head


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--limit-brainrot", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    from forensics.image_features import feature_names
    from forensics.learned_image import probability_to_score

    entries = collect_entries(args.limit_brainrot)
    by_group: dict[str, int] = {}
    for e in entries:
        by_group[e["group"]] = by_group.get(e["group"], 0) + 1
    print(f"Corpus: {by_group}")

    X_stats = load_stats(entries, args.jobs, args.refresh)
    X_clip = load_clip(entries, args.refresh)
    y = np.asarray([e["label"] for e in entries])
    groups = np.asarray([e["group"] for e in entries])
    sources = np.asarray([e["source"] for e in entries])
    names = feature_names()

    render_mask = np.isin(groups, ["brainrot", "real"])
    photo_mask = np.isin(groups, ["ai", "real"])
    photoreal_mask = np.isin(groups, ["ai", "real"])

    print("Evaluating render head (CLIP, brainrot vs real)...")
    render = evaluate_head(X_clip[render_mask], y[render_mask], sources[render_mask])
    print(f"  {render['metrics']}")
    print("Evaluating photo head (pixel stats, ai-dataset vs real)...")
    photo = evaluate_head(X_stats[photo_mask], y[photo_mask], sources[photo_mask])
    print(f"  {photo['metrics']}")
    print("Evaluating photoreal head (CLIP, ai-dataset vs real)...")
    photoreal = evaluate_head(
        X_clip[photoreal_mask], y[photoreal_mask], sources[photoreal_mask], C=PHOTOREAL_C
    )
    print(f"  {photoreal['metrics']}")

    # Combined operating profile on the whole corpus, using the same calibrated
    # probability -> score mapping the runtime layer uses. Real images appear in
    # both heads, so their score is the max of the two held-out probabilities.
    render_prob = np.full(len(entries), np.nan)
    render_prob[render_mask] = render["oof"]
    photo_prob = np.full(len(entries), np.nan)
    photo_prob[photo_mask] = photo["oof"]
    combined = np.fmax(render_prob, photo_prob)
    scored = np.isfinite(combined)
    scores = np.asarray([probability_to_score(p) for p in combined[scored]])
    y_scored = y[scored]
    g_scored = groups[scored]
    print("\nCombined score operating points (held-out):")
    combined_metrics = {}
    for cutoff in (62, 69, 80):
        called = scores >= cutoff
        rec_brainrot = float(called[g_scored == "brainrot"].mean()) if (g_scored == "brainrot").any() else 0.0
        rec_ai = float(called[g_scored == "ai"].mean()) if (g_scored == "ai").any() else 0.0
        fpr = float(called[y_scored == 0].mean())
        combined_metrics[f"score_ge_{cutoff}"] = {
            "brainrot_recall": round(rec_brainrot, 4),
            "ai_dataset_recall": round(rec_ai, 4),
            "real_fpr": round(fpr, 4),
        }
        print(f"  score>={cutoff}: brainrot recall {rec_brainrot:.1%}, "
              f"ai-dataset recall {rec_ai:.1%}, real FPR {fpr:.1%}")

    print("\nTraining final heads on all data...")
    render_model = _head_model().fit(X_clip[render_mask], y[render_mask])
    photo_model = _head_model().fit(X_stats[photo_mask], y[photo_mask])
    photoreal_model = _head_model(PHOTOREAL_C).fit(X_clip[photoreal_mask], y[photoreal_mask])

    payload = {
        "version": 2,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "heads": {
            "render": {
                "features": "clip_vit_b32_openai",
                **export_head(render_model),
                "metrics": render["metrics"],
            },
            "photo": {
                "features": "pixel_stats_v1",
                "feature_names": names,
                **export_head(photo_model),
                "metrics": photo["metrics"],
            },
            "photoreal": {
                "features": "clip_vit_b32_openai",
                **export_head(photoreal_model),
                "metrics": photoreal["metrics"],
                "score_cap": 79,
            },
        },
        "corpus": by_group,
        "combined_metrics": combined_metrics,
        "notes": (
            "Trained on Dataset/: brainrot + Ai_generated_dataset (incl. "
            "photoreal/ exemplars) = AI, real_dataset = real photos. Held-out "
            "metrics use GroupKFold over sources (categories / contiguous "
            "brainrot clip blocks). Three heads: render (CLIP, brainrot), photo "
            "(pixel stats, ai-dataset), photoreal (CLIP, ai-dataset, score-capped "
            "at 79). Inference is numpy-only in forensics/learned_image.py."
        ),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {MODEL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
