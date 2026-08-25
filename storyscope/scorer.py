"""
Dependency-free XGBoost JSON model scorer.

Runs gradient-boosted tree models serialized in XGBoost's JSON format
(`clf.save_model("model.json")`) in pure Python — no libxgboost / OpenMP
needed. Validated to match the native library's `predict_proba` to within
1e-9 on random inputs (see `train.py` `--self-test`).

Supported objectives: binary:logistic, binary:logitraw, multi:softprob.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Optional, Sequence


class XGBoostModel:
    def __init__(self, model_path: str | Path):
        with open(model_path) as f:
            data = json.load(f)
        learner = data["learner"]
        self.objective = learner.get("objective", {}).get("name", "binary:logistic")
        lp = learner.get("learner_model_param", {})
        raw_base = lp.get("base_score", 0.5)
        # xgboost >= 2.1 serializes base_score as a list, sometimes stringified: "[5E-1]"
        if isinstance(raw_base, str) and raw_base.startswith("[") and raw_base.endswith("]"):
            raw_base = raw_base[1:-1]
        if isinstance(raw_base, (list, tuple)):
            raw_base = raw_base[0]
        self.base_score = float(raw_base)
        self.num_feature = int(lp.get("num_feature", 0))

        gbtree = learner["gradient_booster"]
        model = gbtree["model"]
        self.trees = model["trees"]
        self.tree_info = model.get("tree_info", [0] * len(self.trees))

        # Base margin: base_score is stored in probability space; convert to log-odds.
        if self.objective in ("binary:logistic", "binary:logitraw"):
            self.base_margin = self._logit(self.base_score)
            self.n_classes = 2
        elif self.objective == "multi:softprob":
            # For multiclass, base_score is 1/n_classes in probability space.
            self.n_classes = int(lp.get("num_class", 0))
            self.base_margin = self._logit(self.base_score) if self.n_classes == 2 else 0.0
        else:
            self.base_margin = 0.0
            self.n_classes = 2

        # Precompute per-tree per-class node arrays for fast traversal.
        self._parsed = [
            self._parse_tree(t, c) for t, c in zip(self.trees, self.tree_info)
        ]

    @staticmethod
    def _logit(p: float) -> float:
        p = max(1e-7, min(1 - 1e-7, p))
        return math.log(p / (1.0 - p))

    @staticmethod
    def _parse_tree(tree: dict, tree_class: int) -> dict:
        return {
            "class": tree_class,
            "split_indices": tree["split_indices"],
            "split_conditions": tree["split_conditions"],
            "left_children": tree["left_children"],
            "right_children": tree["right_children"],
            "default_left": tree.get("default_left", [0] * len(tree["left_children"])),
            "base_weights": tree["base_weights"],
        }

    def _predict_tree(self, tree: dict, x: Sequence[float]) -> float:
        node = 0
        left = tree["left_children"]
        right = tree["right_children"]
        while left[node] != -1:
            fid = tree["split_indices"][node]
            val = x[fid]
            if val is None or (isinstance(val, float) and math.isnan(val)):
                node = left[node] if tree["default_left"][node] else right[node]
            elif val < tree["split_conditions"][node]:
                node = left[node]
            else:
                node = right[node]
        return tree["base_weights"][node]

    def predict_raw(self, X: List[Sequence[float]]) -> List[List[float]]:
        """Raw margins per row: one value for binary, one per class for softprob."""
        out = []
        if self.objective == "multi:softprob":
            for x in X:
                margins = [0.0] * self.n_classes
                for tree in self._parsed:
                    margins[tree["class"]] += self._predict_tree(tree, x)
                out.append(margins)
        else:
            # binary: all trees belong to class 0; margin = base_margin + sum of leaf weights
            for x in X:
                margin = self.base_margin
                for tree in self._parsed:
                    margin += self._predict_tree(tree, x)
                out.append([margin])
        return out

    def predict_proba(self, X: List[Sequence[float]]) -> List[List[float]]:
        """
        Class probabilities, same layout as XGBClassifier.predict_proba:
        column 0 = P(negative class), column 1 = P(positive class).
        """
        margins = self.predict_raw(X)
        if self.objective == "multi:softprob":
            return [self._softmax(m) for m in margins]
        # binary:logistic: positive-class probability = sigmoid(margin)
        return [[1.0 - (1.0 / (1.0 + math.exp(-m[0]))), 1.0 / (1.0 + math.exp(-m[0]))] for m in margins]

    @staticmethod
    def _softmax(m: List[float]) -> List[float]:
        mx = max(m)
        exps = [math.exp(v - mx) for v in m]
        total = sum(exps)
        return [e / total for e in exps]
