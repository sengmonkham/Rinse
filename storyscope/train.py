"""
Train the StoryScope binary (human vs AI) classifier.

Reproduces the paper's classification setup on its released feature matrix:
~61,300 stories (10,216 prompts x human + 5 LLMs) annotated with the 304
narrative features. Uses the same algorithm family (XGBoost) and the repo's
documented hyperparameters (max_depth=8, reg_lambda=2.0, human_weight=5.0),
with prompt-level grouping so the same writing prompt never spans train and
validation.

Usage:
    python -m storyscope.train [--data storyscope/data/storyscope_features.parquet]
                               [--out storyscope/data] [--self-test] [--narrative]

Notes:
- Native xgboost is required to RUN training (the paper's model family).
- The trained model is saved as XGBoost JSON; at inference it is scored by
  the dependency-free pure-Python scorer in scorer.py (--self-test verifies
  exact agreement with the native library).
- On macOS without a system OpenMP install, xgboost needs libomp; the
  scorer used by server.py does NOT.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, average_precision_score, f1_score
from sklearn.model_selection import GroupKFold
from xgboost import XGBClassifier

from .encoding import NONE_CATEGORY, build_encoder
from .features import _best_match
from .taxonomy import Taxonomy

DATA_PATH = Path(__file__).parent / "data" / "storyscope_features.parquet"
TAXONOMY_PATH = Path(__file__).parent / "data" / "taxonomy.json"
MODEL_PATH = Path(__file__).parent / "data" / "model_full.json"
STATS_PATH = Path(__file__).parent / "data" / "model_stats.json"

# Paper's repo documents n_estimators=420; its shipped model used 300 trees.
# We use 300 for both cross-validation and the shipped model.
CV_ESTIMATORS = 300
FINAL_ESTIMATORS = 300
HYPERPARAMS = dict(
    max_depth=8,
    reg_lambda=2.0,
    eval_metric="logloss",
    random_state=42,
    tree_method="hist",
)


def load_data(data_path: Path) -> Tuple[pd.DataFrame, Taxonomy]:
    taxonomy = Taxonomy.from_json(TAXONOMY_PATH)
    df = pd.read_parquet(data_path)
    if "source" in df.columns and "author" not in df.columns:
        df = df.rename(columns={"source": "author"})

    # Keep only prompts with all six sources present (paper's matched-prompt filter).
    n_sources = df["author"].nunique()
    counts = df.groupby("prompt_id")["author"].nunique()
    matched = counts[counts == n_sources].index
    df = df[df["prompt_id"].isin(matched)].copy()
    return df, taxonomy


def _snap_value(raw: str, allowed: List[str], is_multi: bool) -> Any:
    """Normalize one raw cell value onto canonical taxonomy categories."""
    s = raw.strip()
    if not s or s in ("n/a", "na"):
        return "n/a"
    if is_multi:
        parts = [p.strip() for p in s.split("|") if p.strip()]
        matched = [p for p in (_best_match(p, allowed) for p in parts) if p in allowed]
        return matched if matched else "n/a"
    matched = _best_match(s, allowed)
    return matched if matched in allowed else "n/a"


def encode_matrix(df: pd.DataFrame, taxonomy: Taxonomy, encoder) -> np.ndarray:
    """
    Vectorized one-hot encoding of the training matrix.

    Per feature: fuzzy-match each *unique* raw value onto canonical categories
    (identical to inference-time normalization), then one-hot via get_dummies.
    Multi-select values (pipe-separated / lists) explode into per-category counts.
    """
    n = len(df)
    X = np.zeros((n, encoder.n_features), dtype=np.float32)
    for fid, offset in encoder._offsets.items():
        cats = encoder.categories[fid]
        col = df[fid]
        s = col.astype(str).where(col.notna(), "")
        uniq = sorted(s.unique().tolist())
        is_multi = taxonomy.feature(fid).type == "multi_select"
        mapping = {u: _snap_value(u, [str(v) for v in taxonomy.feature(fid).values], is_multi) for u in uniq}
        snapped = s.map(mapping)

        if is_multi:
            exploded = snapped.explode().dropna()
            exploded = exploded[exploded != "n/a"]
            if not exploded.empty:
                dummies = pd.get_dummies(exploded).groupby(level=0).sum()
            else:
                dummies = None
        else:
            dummies = pd.get_dummies(snapped)
        if dummies is None:
            continue
        for j, cat in enumerate(cats):
            if cat in dummies.columns:
                X[:, offset + j] = dummies[cat].reindex(range(n), fill_value=0).values
    return X


def fit_model(X: np.ndarray, y: np.ndarray, groups: np.ndarray, n_estimators: int = CV_ESTIMATORS):
    sample_weight = np.where(y == 0, 5.0, 1.0)  # upweight minority human class
    clf = XGBClassifier(**HYPERPARAMS, n_estimators=n_estimators)
    clf.fit(X, y, sample_weight=sample_weight)
    return clf


def cross_validate(X: np.ndarray, y: np.ndarray, groups: np.ndarray, n_folds: int = 5) -> Dict[str, Any]:
    gkf = GroupKFold(n_splits=n_folds)
    fold_metrics = []
    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups)):
        clf = fit_model(X[train_idx], y[train_idx], groups[train_idx])
        p = clf.predict_proba(X[test_idx])[:, 1]
        pred = (p >= 0.5).astype(int)
        fold_metrics.append({
            "fold": fold + 1,
            "n_train": int(len(train_idx)),
            "n_test": int(len(test_idx)),
            "macro_f1": float(f1_score(y[test_idx], pred, average="macro")),
            "f1_ai": float(f1_score(y[test_idx], pred, pos_label=1)),
            "f1_human": float(f1_score(y[test_idx], pred, pos_label=0)),
            "auprc": float(average_precision_score(y[test_idx], p)),
            "accuracy": float(accuracy_score(y[test_idx], pred)),
        })
        print(
            f"  fold {fold + 1}: macro-F1 {fold_metrics[-1]['macro_f1']:.4f} | "
            f"AUPRC {fold_metrics[-1]['auprc']:.4f} | acc {fold_metrics[-1]['accuracy']:.4f}"
        )
    mean = {k: float(np.mean([m[k] for m in fold_metrics])) for k in
            ("macro_f1", "f1_ai", "f1_human", "auprc", "accuracy")}
    return {"folds": fold_metrics, "mean": mean}


def build_stats(df: pd.DataFrame, labels: np.ndarray, taxonomy: Taxonomy) -> Dict[str, Any]:
    """Training-time stats (vectorized) used for explanations at inference."""
    n = len(labels)
    p_ai_global = float(labels.mean())
    label_series = pd.Series(labels, index=df.index, name="_ai")

    # Per-feature, per-category P(AI | category) via groupby (fast on 61k rows).
    per_feature: Dict[str, Dict[str, float]] = {}
    for dim in taxonomy.dimensions:
        for f in dim.features:
            s = df[f.id].astype(str).where(df[f.id].notna(), "")
            if f.type == "multi_select":
                exploded = s.str.split("|").explode().dropna()
                exploded = exploded[exploded.str.strip() != ""]
                if exploded.empty:
                    per_feature[f.id] = {}
                    continue
                merged = pd.DataFrame({"_v": exploded}).join(label_series)
                merged["_v"] = merged["_v"].str.strip()
            else:
                merged = pd.DataFrame({"_v": s}).join(label_series)
                merged["_v"] = merged["_v"].replace("", NONE_CATEGORY)
            grouped = merged.groupby("_v")["_ai"].agg(["mean", "count"])
            per_feature[f.id] = {
                str(v): float(row["mean"] - p_ai_global) for v, row in grouped.iterrows()
            }

    # Per-dimension mean association across a story's feature values.
    dimension_stats = {}
    for dim in taxonomy.dimensions:
        acc = pd.Series(0.0, index=df.index)
        cnt = pd.Series(0.0, index=df.index)
        for f in dim.features:
            assoc = per_feature.get(f.id, {})
            s = df[f.id].astype(str).where(df[f.id].notna(), "")
            if f.type == "multi_select":
                exploded = s.str.split("|").explode().dropna()
                exploded = exploded[exploded.str.strip() != ""]
                vals = exploded.str.strip()
            else:
                vals = s.replace("", NONE_CATEGORY)
            mapped = vals.map(assoc).fillna(0.0)
            acc = acc.add(mapped.groupby(mapped.index).sum(), fill_value=0.0)
            cnt = cnt.add(mapped.groupby(mapped.index).count(), fill_value=0.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            dim_assoc = (acc / cnt).fillna(0.0)
        dimension_stats[dim.key] = {
            "name": dim.name,
            "n_features": len(dim.features),
            "mean_assoc_ai": float(dim_assoc.mean()),
        }

    return {
        "p_ai_global": p_ai_global,
        "n_stories": int(n),
        "n_ai": int((labels == 1).sum()),
        "n_human": int((labels == 0).sum()),
        "per_feature": per_feature,
        "dimensions": dimension_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DATA_PATH))
    parser.add_argument("--out", default=str(MODEL_PATH.parent))
    parser.add_argument("--self-test", action="store_true", help="Verify pure-Python scorer vs native xgboost")
    parser.add_argument("--narrative", action="store_true",
                        help="Also cross-validate the narrative-only variant (style dimension dropped)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading data...")
    df, taxonomy = load_data(Path(args.data))
    print(f"  {len(df)} stories, {df['prompt_id'].nunique()} prompts, "
          f"sources: {sorted(df['author'].unique())}")

    y = (df["author"] != "human").astype(np.int64).values
    print(f"  labels: AI={int((y == 1).sum())}, human={int((y == 0).sum())}")

    print("Building encoder + encoding matrix...")
    encoder = build_encoder(taxonomy, None)
    X = encode_matrix(df, taxonomy, encoder)
    print(f"  {encoder.n_features} encoded columns, X={X.shape}")
    groups = df["prompt_id"].values

    print("Cross-validating (5-fold, prompt-grouped)...")
    cv = cross_validate(X, y, groups)
    print(f"  MEAN: macro-F1 {cv['mean']['macro_f1']:.4f} | AUPRC {cv['mean']['auprc']:.4f} "
          f"| accuracy {cv['mean']['accuracy']:.4f}")

    # Optional narrative-only variant (exclude Style dimension) to mirror the paper's
    # "narrative features retain >97% of full-model performance" finding.
    cv_narr = None
    if args.narrative:
        style_ids = [feat.id for dim in taxonomy.dimensions if dim.key == "style" for feat in dim.features]
        narr_mask = [not (c.split("__")[0] in style_ids) for c in encoder.columns]
        if any(not m for m in narr_mask):
            X_narr = X[:, narr_mask]
            print("Cross-validating narrative-only variant (style dropped, 3 folds)...")
            cv_narr = cross_validate(X_narr, y, groups, n_folds=3)
            print(f"  NARRATIVE-ONLY MEAN: macro-F1 {cv_narr['mean']['macro_f1']:.4f} | "
                  f"AUPRC {cv_narr['mean']['auprc']:.4f} | "
                  f"retention {cv_narr['mean']['macro_f1'] / cv['mean']['macro_f1'] * 100:.1f}% of full macro-F1")

    print("Fitting final model on all data...")
    final = fit_model(X, y, groups, n_estimators=FINAL_ESTIMATORS)

    model_path = out_dir / "model_full.json"
    final.save_model(str(model_path))
    print(f"  saved {model_path} ({model_path.stat().st_size / 1e6:.1f} MB)")

    print("Building stats...")
    stats = build_stats(df, y, taxonomy)
    stats["encoder"] = encoder.to_json()
    stats["cv"] = cv
    stats["narrative_only_cv"] = cv_narr
    stats["narrative_only"] = {
        "enabled": cv_narr is not None,
        "excluded_dimensions": ["style"],
    }
    stats["hyperparameters"] = {**HYPERPARAMS, "n_estimators": FINAL_ESTIMATORS, "human_weight": 5.0}
    stats["model"] = {"file": model_path.name, "objective": "binary:logistic",
                      "base_score": 0.5, "label_encoding": "1 = AI, 0 = human"}
    stats_path = out_dir / "model_stats.json"
    stats_path.write_text(json.dumps(stats, indent=1))
    print(f"  saved {stats_path}")

    if args.self_test:
        self_test(str(model_path), encoder)

    print(f"Done in {time.time() - t0:.1f}s")


def self_test(model_path: str, encoder) -> None:
    """Compare the pure-Python scorer against native xgboost on random inputs."""
    from .scorer import XGBoostModel

    native = XGBClassifier()
    native.load_model(model_path)
    pure = XGBoostModel(model_path)

    rng = np.random.default_rng(42)
    X = rng.random((2000, encoder.n_features), dtype=np.float32)
    # Add missing-value rows (NaN in random columns) to exercise default branches.
    nan_rows = rng.random((500, encoder.n_features), dtype=np.float32)
    mask = rng.random((500, encoder.n_features)) < 0.15
    nan_rows[mask] = np.nan
    X = np.vstack([X, nan_rows])

    native_p = native.predict_proba(X)
    pure_p = np.asarray(pure.predict_proba(X.tolist()))
    diff = np.max(np.abs(native_p - pure_p))
    print(f"SELF-TEST: max |native - pure-python| over {len(X)} rows = {diff:.3e}")
    if diff > 1e-6:
        raise SystemExit(f"SELF-TEST FAILED: max diff {diff} > 1e-6")
    print("SELF-TEST PASSED: pure-Python scorer matches native xgboost")


if __name__ == "__main__":
    main()
