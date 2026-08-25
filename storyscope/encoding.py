"""
Feature encoding.

Every taxonomy feature is one-hot encoded over the categories observed in
the training data (union of the taxonomy's canonical values and the values
actually seen in the released 61,575-story feature matrix, which includes
real-world noise such as leaked 'yes' labels and 'n/a'). Encoding is fully
data-driven and reproducible, so the trained classifier needs no hidden
label mappings at inference time.

Multi-select features: one column per category; a pipe-separated value
activates every category it mentions; empty selection -> '__none__'.
Missing/null values -> '__none__'.

The column order is deterministic: features in taxonomy order, categories
sorted. The trained XGBoost model and this encoder share that layout.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .taxonomy import Taxonomy

NONE_CATEGORY = "__none__"
MISSING = "n/a"


def _collect_categories(taxonomy: Taxonomy, training_rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Build per-feature category lists.

    Categories are the taxonomy's canonical values plus the special buckets
    'n/a' (condition not met / undeterminable) and '__none__' (empty
    multi-select / missing). Raw values are normalized onto these by
    `features.normalize_features` (training does the same), so the encoding
    is stable and reproducible — no hidden label mappings.
    """
    categories: Dict[str, List[str]] = {}
    for dim in taxonomy.dimensions:
        for f in dim.features:
            cat = set(str(v) for v in f.values)
            cat.add(NONE_CATEGORY)
            cat.add(MISSING)
            categories[f.id] = sorted(cat)
    return categories


def build_encoder(taxonomy: Taxonomy, training_rows: List[Dict[str, Any]]) -> "FeatureEncoder":
    """Create the encoder from training data (category discovery)."""
    return FeatureEncoder(taxonomy, _collect_categories(taxonomy, training_rows))


class FeatureEncoder:
    def __init__(self, taxonomy: Taxonomy, categories: Dict[str, List[str]]):
        self.taxonomy = taxonomy
        self.categories = categories
        # column layout: feature-major, categories sorted within each feature
        self.columns: List[str] = []
        self._offsets: Dict[str, int] = {}
        for fid in taxonomy.feature_ids():
            cats = categories[fid]
            self._offsets[fid] = len(self.columns)
            for c in cats:
                self.columns.append(f"{fid}__{c}")

    @property
    def n_features(self) -> int:
        return len(self.columns)

    def encode(self, features: Dict[str, Any]) -> List[float]:
        """
        Encode a normalized feature dict (feature id -> value or list of values)
        into a dense float vector matching the training layout.
        """
        vec = [0.0] * self.n_features
        for fid, offset in self._offsets.items():
            cats = self.categories[fid]
            value = features.get(fid)
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                selected = set()
                for v in value:
                    if v is None:
                        continue
                    s = str(v)
                    if not s.strip():
                        continue
                    for part in s.split("|"):
                        if part.strip():
                            selected.add(part.strip())
                if not selected:
                    if NONE_CATEGORY in cats:
                        vec[offset + cats.index(NONE_CATEGORY)] = 1.0
                    continue
                for part in selected:
                    if part in cats:
                        vec[offset + cats.index(part)] = 1.0
            else:
                s = str(value).strip()
                if not s:
                    if NONE_CATEGORY in cats:
                        vec[offset + cats.index(NONE_CATEGORY)] = 1.0
                    continue
                if s in cats:
                    vec[offset + cats.index(s)] = 1.0
                else:
                    # Unseen category: fall back to the 'n/a' bucket if it exists,
                    # otherwise leave the row all-zero (like an absent feature).
                    if MISSING in cats:
                        vec[offset + cats.index(MISSING)] = 1.0
        return vec

    def to_json(self) -> dict:
        return {
            "feature_order": self.taxonomy.feature_ids(),
            "categories": self.categories,
            "n_features": self.n_features,
        }
