"""
Offline evaluation of the heuristic (pure-logic) StoryScope engine.

Measures how much classification accuracy the rule-based extractor retains
relative to the paper's full LLM extraction, using the released 61,575-story
feature matrix and the *shipped* model + pure-Python scorer (no xgboost
needed).

Three scenarios, all scored by the same trained model:

  full       every feature present as released (upper bound - LLM extraction)
  masked     heuristic-covered features as released, everything else -> n/a
             (what production does: the rule-based extractor leaves
             judgment features as n/a, which the classifier handles natively)
  noisy-0.6  covered features correct 60% of the time, random category
             otherwise; uncovered -> n/a (realistic middle estimate: the
             rules are decent proxies but noisier than an LLM)
  zero-signal covered features replaced by their majority training category
             (lower bound: the heuristic contributes no signal at all)

The real heuristic sits between ``masked`` and ``zero-signal``: it does emit
noisy estimates for the covered features, but they are not as accurate as the
LLM's values. ``masked`` is the headline number; ``noisy-0.6`` is a
realistic middle estimate; ``zero-signal`` shows the floor.

Also prints what fraction of the model's split nodes sit in heuristic-covered
columns (how much of the model's predictive weight the rules can reach).

Usage:
    python -m storyscope.eval_heuristic [--data storyscope/data/storyscope_features.parquet]

Runtime deps (evaluation only): pandas, pyarrow, numpy, scikit-learn.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, average_precision_score, f1_score

from .encoding import NONE_CATEGORY, build_encoder
from .features import _best_match
from .heuristic import COVERED_FEATURES
from .scorer import XGBoostModel
from .taxonomy import Taxonomy

BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / "data" / "storyscope_features.parquet"
TAXONOMY_PATH = BASE_DIR / "data" / "taxonomy.json"
MODEL_PATH = BASE_DIR / "data" / "model_full.json"


def load_data(data_path: Path) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, Taxonomy]:
    taxonomy = Taxonomy.from_json(TAXONOMY_PATH)
    df = pd.read_parquet(data_path)
    if "source" in df.columns and "author" not in df.columns:
        df = df.rename(columns={"source": "author"})

    # Keep only prompts with all six sources present (paper's matched-prompt filter).
    n_sources = df["author"].nunique()
    counts = df.groupby("prompt_id")["author"].nunique()
    matched = counts[counts == n_sources].index
    df = df[df["prompt_id"].isin(matched)].copy()
    y = (df["author"] != "human").astype(np.int64).values
    return df, y, df["prompt_id"].values, taxonomy


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
    """Vectorized one-hot encoding identical to training-time encode_matrix."""
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


def mask_uncovered(X: np.ndarray, encoder, covered: frozenset) -> np.ndarray:
    """Set every non-covered feature's columns to its 'n/a' category column."""
    Xm = X.copy()
    for fid, offset in encoder._offsets.items():
        if fid in covered:
            continue
        cats = encoder.categories[fid]
        if "n/a" in cats:
            cols = [offset + j for j in range(len(cats))]
            Xm[:, cols] = 0.0
            Xm[:, offset + cats.index("n/a")] = 1.0
        else:
            cols = [offset + j for j in range(len(cats))]
            Xm[:, cols] = 0.0
    return Xm


def noisy_covered(X: np.ndarray, encoder, covered: frozenset, p: float = 0.6, seed: int = 0) -> np.ndarray:
    """Covered features keep their true category with prob p, else a random one."""
    rng = np.random.default_rng(seed)
    Xn = X.copy()
    for fid, offset in encoder._offsets.items():
        cats = encoder.categories[fid]
        ncats = len(cats)
        cols = [offset + j for j in range(ncats)]
        keep = rng.random(X.shape[0]) < p
        for row in range(X.shape[0]):
            Xn[row, cols] = 0.0
            if fid in covered:
                if keep[row]:
                    true_col = int(np.argmax(X[row, cols]))
                    Xn[row, offset + true_col] = 1.0
                else:
                    r = int(rng.integers(0, ncats))
                    Xn[row, offset + r] = 1.0
            elif "n/a" in cats:
                Xn[row, offset + cats.index("n/a")] = 1.0
    return Xn


def zero_signal(X: np.ndarray, encoder, covered: frozenset) -> np.ndarray:
    """Covered features -> their majority training category; rest -> n/a."""
    Xz = X.copy()
    for fid, offset in encoder._offsets.items():
        cats = encoder.categories[fid]
        cols = [offset + j for j in range(len(cats))]
        Xz[:, cols] = 0.0
        if fid in covered:
            # most common category in the training column (column with max sum)
            best = int(np.argmax(X[:, cols].sum(axis=0)))
            Xz[:, offset + best] = 1.0
        elif "n/a" in cats:
            Xz[:, offset + cats.index("n/a")] = 1.0
    return Xz


def metrics(y: np.ndarray, p: np.ndarray) -> Dict[str, float]:
    pred = (p >= 0.5).astype(int)
    return {
        "macro_f1": float(f1_score(y, pred, average="macro")),
        "f1_ai": float(f1_score(y, pred, pos_label=1)),
        "f1_human": float(f1_score(y, pred, pos_label=0)),
        "auprc": float(average_precision_score(y, p)),
        "accuracy": float(accuracy_score(y, pred)),
    }


def split_usage(model_path: Path, encoder) -> Dict[str, Any]:
    """What fraction of the model's split nodes sit in heuristic-covered columns?"""
    with open(model_path) as f:
        data = json.load(f)
    trees = data["learner"]["gradient_booster"]["model"]["trees"]
    total = 0
    covered = 0
    by_dim: Dict[str, List[int]] = {}
    for t in trees:
        for fidx in t["split_indices"]:
            total += 1
            col = encoder.columns[fidx]
            feat_id = col.split("__")[0]
            dim = feat_id.split("_")[0].lower()
            by_dim.setdefault(dim, [0, 0])
            by_dim[dim][1] += 1
            if feat_id in COVERED_FEATURES:
                covered += 1
                by_dim[dim][0] += 1
    return {
        "total_splits": total,
        "covered_splits": covered,
        "covered_frac": covered / total if total else 0.0,
        "by_dimension": {k: {"covered": v[0], "total": v[1]} for k, v in sorted(by_dim.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DATA_PATH))
    args = parser.parse_args()

    df, y, groups, taxonomy = load_data(Path(args.data))
    print(f"Loaded {len(df)} stories, {df['prompt_id'].nunique()} prompts; "
          f"AI={int(y.sum())}, human={int((y == 0).sum())}")

    encoder = build_encoder(taxonomy, None)
    print(f"Encoder: {encoder.n_features} columns; heuristic covers "
          f"{len(COVERED_FEATURES)}/{taxonomy.total_features} features "
          f"({len(COVERED_FEATURES) / taxonomy.total_features:.0%})")

    print("Encoding matrix (this takes a minute)...")
    X_full = encode_matrix(df, taxonomy, encoder)
    model = XGBoostModel(MODEL_PATH)
    print(f"Model: {model.num_feature} features (encoder matches: "
          f"{model.num_feature == encoder.n_features})")

    X_masked = mask_uncovered(X_full, encoder, COVERED_FEATURES)
    X_noisy = noisy_covered(X_full, encoder, COVERED_FEATURES, p=0.6)
    X_zero = zero_signal(X_full, encoder, COVERED_FEATURES)

    results = {}
    for name, X in (("full", X_full), ("masked", X_masked), ("noisy-0.6", X_noisy), ("zero-signal", X_zero)):
        p = np.asarray(model.predict_proba(X.tolist()))[:, 1]
        results[name] = metrics(y, p)
        m = results[name]
        print(f"\n{name:12s} macro-F1 {m['macro_f1']:.4f} | AUPRC {m['auprc']:.4f} "
              f"| acc {m['accuracy']:.4f} | F1(human) {m['f1_human']:.4f} | F1(AI) {m['f1_ai']:.4f}")

    full, masked, noisy, zero = (
        results["full"], results["masked"], results["noisy-0.6"], results["zero-signal"]
    )
    print("\nRetention vs full extraction:")
    print(f"  masked      (covered features as released, rest n/a): "
          f"{masked['macro_f1'] / full['macro_f1']:.1%} macro-F1, "
          f"{masked['auprc'] / full['auprc']:.1%} AUPRC, "
          f"{masked['accuracy'] / full['accuracy']:.1%} accuracy")
    print(f"  noisy-0.6   (covered features 60% accurate, rest n/a):  "
          f"{noisy['macro_f1'] / full['macro_f1']:.1%} macro-F1, "
          f"{noisy['auprc'] / full['auprc']:.1%} AUPRC")
    print(f"  zero-signal (covered features contribute no signal):    "
          f"{zero['macro_f1'] / full['macro_f1']:.1%} macro-F1, "
          f"{zero['auprc'] / full['auprc']:.1%} AUPRC")

    usage = split_usage(MODEL_PATH, encoder)
    print(f"\nModel split usage: {usage['covered_frac']:.0%} of "
          f"{usage['total_splits']} split nodes sit in heuristic-covered columns")


if __name__ == "__main__":
    main()
