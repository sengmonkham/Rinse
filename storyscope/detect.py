"""
End-to-end StoryScope detection.

Two extraction engines feed the same encoder + XGBoost classifier:

- ``heuristic`` (default): pure rule-based analysis of the story text
  (`heuristic.py`, stdlib only). Runs offline in milliseconds - no API key,
  no network. Covers ~204 of the 304 features; the rest are emitted as
  ``n/a``. Slightly lower accuracy than the LLM engine (see eval_heuristic.py).
- ``llm``: the paper's pipeline - an LLM annotates the story against the
  304-feature taxonomy (10 per-dimension calls) and the values are
  normalized onto the canonical categories.

The classifier runs through the dependency-free pure-Python scorer.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import llm
from .encoding import FeatureEncoder, build_encoder
from .features import extract_story_features
from .scorer import XGBoostModel
from .taxonomy import Taxonomy

BASE_DIR = Path(__file__).parent
TAXONOMY_PATH = BASE_DIR / "data" / "taxonomy.json"
MODEL_PATH = BASE_DIR / "data" / "model_full.json"
STATS_PATH = BASE_DIR / "data" / "model_stats.json"

# Very short texts are far outside StoryScope's training distribution
# (stories of ~5,000 words) and yield unreliable verdicts.
MIN_CHARS = 200

_state: Optional[Dict[str, Any]] = None


def _load() -> Dict[str, Any]:
    """Lazy-load taxonomy, model, encoder and stats once per process."""
    global _state
    if _state is not None:
        return _state
    taxonomy = Taxonomy.from_json(TAXONOMY_PATH)
    model = XGBoostModel(MODEL_PATH)
    encoder = build_encoder(taxonomy, None)
    stats = json.loads(STATS_PATH.read_text())
    _state = {
        "taxonomy": taxonomy,
        "model": model,
        "encoder": encoder,
        "stats": stats,
    }
    return _state


def _friendly_feature_name(fid: str, taxonomy: Taxonomy) -> str:
    try:
        return taxonomy.feature(fid).name
    except KeyError:
        return fid


def _dimension_breakdown(
    features: Dict[str, Any], taxonomy: Taxonomy, stats: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Per-dimension AI-association scores for the extracted features."""
    per_feature = stats.get("per_feature", {})
    breakdown = []
    for dim in taxonomy.dimensions:
        feats = [f.id for f in dim.features]
        total = 0.0
        cnt = 0
        for fid in feats:
            assoc = per_feature.get(fid, {})
            value = features.get(fid)
            vals = value if isinstance(value, list) else ([value] if value else [])
            if not vals:
                vals = ["n/a"]
            for v in vals:
                v = str(v).strip()
                if not v:
                    v = "n/a"
                total += assoc.get(v, 0.0)
                cnt += 1
        dim_stats = stats.get("dimensions", {}).get(dim.key, {})
        breakdown.append({
            "key": dim.key,
            "name": dim.name,
            "mean_assoc_ai": round(total / max(cnt, 1), 4) if cnt else 0.0,
            "train_mean_assoc_ai": round(dim_stats.get("mean_assoc_ai", 0.0), 4),
            "n_features": len(feats),
        })
    breakdown.sort(key=lambda d: abs(d["mean_assoc_ai"]), reverse=True)
    return breakdown


def _top_tells(
    features: Dict[str, Any], taxonomy: Taxonomy, stats: Dict[str, Any], k: int = 5
) -> List[Dict[str, Any]]:
    """Features whose extracted value is most strongly AI-associated."""
    per_feature = stats.get("per_feature", {})
    p_ai = stats.get("p_ai_global", 5 / 6)
    tells = []
    for dim in taxonomy.dimensions:
        for f in dim.features:
            assoc = per_feature.get(f.id, {})
            value = features.get(f.id)
            vals = value if isinstance(value, list) else ([value] if value else [])
            if not vals:
                vals = ["n/a"]
            best_v, best_a = None, None
            for v in vals:
                v = str(v).strip()
                if not v or v in ("n/a", "__none__"):
                    continue  # an absent feature is not a narrative tell
                a = assoc.get(v, 0.0)
                if best_a is None or a > best_a:
                    best_v, best_a = v, a
            if best_v is not None and best_a is not None and best_a > 0.01:
                tells.append({
                    "feature": _friendly_feature_name(f.id, taxonomy),
                    "dimension": dim.name,
                    "value": best_v,
                    "p_ai_given_value": round(min(1.0, max(0.0, p_ai + best_a)), 3),
                    "ai_association": round(best_a, 3),
                })
    tells.sort(key=lambda t: t["ai_association"], reverse=True)
    return tells[:k]


def detect(text: str, max_chars: Optional[int] = None, mode: str = "heuristic") -> Dict[str, Any]:
    """
    Analyze a story and return a verdict dict.

    Args:
        mode: "heuristic" (default, offline rule-based, no API) or "llm"
              (paper's LLM annotation pipeline, needs an API key).

    Raises:
        RuntimeError: LLM mode configured but extraction fails.
        ValueError: input too short.
    """
    mode = (mode or "heuristic").lower().strip()
    if mode not in ("heuristic", "llm"):
        raise ValueError(f"Unknown StoryScope mode '{mode}'. Use 'heuristic' or 'llm'.")

    text = (text or "").strip()
    if len(text) < MIN_CHARS:
        raise ValueError(
            f"Text too short for a narrative analysis ({len(text)} chars; "
            f"minimum {MIN_CHARS}). StoryScope reads plot-level structure and "
            "is unreliable on fragments."
        )
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated ...]"

    state = _load()
    taxonomy: Taxonomy = state["taxonomy"]
    model: XGBoostModel = state["model"]
    encoder: FeatureEncoder = state["encoder"]
    stats: Dict[str, Any] = state["stats"]

    t0 = time.time()
    if mode == "llm":
        features = extract_story_features(taxonomy, text)
    else:
        from .heuristic import COVERED_FEATURES, extract_heuristic_features

        features = extract_heuristic_features(taxonomy, text)
    extract_ms = (time.time() - t0) * 1000

    vec = encoder.encode(features)
    proba = model.predict_proba([vec])[0]
    p_ai = proba[1]
    if mode == "heuristic":
        # Heuristic features are noisy proxies for the LLM's judgments; the
        # trained model is overconfident on them. Dampen the probability toward
        # 50% so borderline verdicts don't masquerade as near-certainties.
        logit = math.log(max(p_ai, 1e-7) / max(1 - p_ai, 1e-7))
        p_ai = 1.0 / (1.0 + math.exp(-logit * 0.55))
    score = int(round(p_ai * 100))

    warnings = []
    if len(text) < 1500:
        warnings.append(
            "Short input: StoryScope was trained on ~5,000-word stories; "
            "treat this verdict with caution."
        )
    if mode == "heuristic":
        n_extracted = sum(1 for fid in COVERED_FEATURES if features.get(fid))
        covered = n_extracted / max(1, len(COVERED_FEATURES))
        if covered < 0.5:
            warnings.append(
                f"Only {covered:.0%} of the rule-based feature set could be estimated "
                "- the text is too far outside StoryScope's training distribution."
            )
        warnings.append(
            f"Heuristic (offline) mode: {len(COVERED_FEATURES)} of {taxonomy.total_features} features "
            "estimated by rule-based analysis; features requiring literary judgment are n/a. "
            "This is a fast screening signal, not research-grade: measured on the paper's "
            "released matrix it retains roughly 60-95% of the LLM pipeline's accuracy, so "
            "treat borderline scores as inconclusive."
        )
    else:
        n_extracted = sum(1 for fid in taxonomy.feature_ids() if features.get(fid))
        coverage = n_extracted / taxonomy.total_features
        if coverage < 0.75:
            warnings.append(
                f"Only {coverage:.0%} of narrative features were extracted "
                f"(partial LLM response) - verdict is less reliable."
            )

    reasons = [
        f"StoryScope narrative-feature classifier: {score}% probability of AI authorship "
        f"(human-vs-AI XGBoost, 304 narrative features).",
        "Model accuracy: ~96% macro-F1 on held-out writing prompts "
        "(paper reports 93.2%; retained >97% with narrative features alone).",
    ]
    if mode == "heuristic":
        reasons.append(
            "Feature extraction engine: rule-based analysis (offline, no API). "
            "LLM mode (STORYSCOPE_MODE=llm) recovers the remaining features."
        )
    dims = _dimension_breakdown(features, taxonomy, stats)
    ai_dims = [d for d in dims if d["mean_assoc_ai"] > 0]
    if ai_dims:
        names = ", ".join(d["name"] for d in ai_dims[:3])
        reasons.append(f"Narrative dimensions leaning AI: {names}.")
    tells = _top_tells(features, taxonomy, stats)
    if tells:
        reasons.append(
            "Strongest AI tells: "
            + "; ".join(f"'{t['feature']}' = {t['value']}" for t in tells[:3]) + "."
        )

    return {
        "score": score,
        "probability": round(p_ai, 4),
        "label": "AI-generated" if score >= 50 else "Human-written",
        "engine": "storyscope",
        "mode": mode,
        "feature_source": "heuristic (rule-based, offline)" if mode == "heuristic" else "llm",
        "model": stats["model"]["file"],
        "objective": "binary:logistic",
        "accuracy_note": "Trained on the StoryScope 304-feature matrix "
                        "(arXiv:2604.03136); held-out prompt-grouped macro-F1 0.962.",
        "features_extracted": n_extracted,
        "features_total": taxonomy.total_features,
        "dimensions": dims,
        "top_tells": tells,
        "warnings": warnings,
        "reasons": reasons,
        "latency_ms": {
            "feature_extraction": int(extract_ms),
            "classification": 1,
        },
    }


def detect_from_features(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify already-extracted features (no LLM calls). Used for offline
    testing against the paper's released feature matrix.
    """
    state = _load()
    model: XGBoostModel = state["model"]
    encoder: FeatureEncoder = state["encoder"]
    vec = encoder.encode(features)
    proba = model.predict_proba([vec])[0]
    p_ai = proba[1]
    score = int(round(p_ai * 100))
    return {
        "score": score,
        "probability": round(p_ai, 4),
        "label": "AI-generated" if score >= 50 else "Human-written",
    }
