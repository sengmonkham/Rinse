"""
Narrative feature extraction.

Faithful port of the paper's `apply_features` stage: for each of the 10
NarraBench dimensions an LLM call asks a literary analyst to annotate the
story against the taxonomy's features; results are fuzzy-normalized onto
the canonical value lists. 10 calls per story, run concurrently.

Attribution: adapted from jenna-russell/storyscope (MIT), arXiv:2604.03136.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from . import llm
from .taxonomy import Dimension, Feature, Taxonomy

MISSING = "n/a"

# Max characters of story sent per LLM call (the paper truncates at 280k).
MAX_STORY_CHARS = 280_000
# Parallel LLM calls for the 10 dimensions of one story.
DEFAULT_DIM_WORKERS = 5


# ---------------------------------------------------------------------------
# Value normalization
# ---------------------------------------------------------------------------

def _normalize_str(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _best_match(raw_value: str, allowed: List[str]) -> str:
    """Fuzzy-match a raw LLM value to the closest canonical taxonomy value."""
    if not allowed:
        return raw_value
    raw_norm = _normalize_str(raw_value)

    for canonical in allowed:
        if _normalize_str(canonical) == raw_norm:
            return canonical

    raw_num = re.match(r"^(\d+)", raw_norm)
    if raw_num:
        num = raw_num.group(1)
        for canonical in allowed:
            c_num = re.match(r"^(\d+)", _normalize_str(canonical))
            if c_num and c_num.group(1) == num:
                return canonical

    for canonical in allowed:
        c_norm = _normalize_str(canonical)
        if raw_norm.startswith(c_norm) or c_norm.startswith(raw_norm):
            return canonical

    raw_tokens = set(raw_norm.split("_"))
    best_score, best_canonical = 0.0, None
    for canonical in allowed:
        c_tokens = set(_normalize_str(canonical).split("_"))
        if not c_tokens:
            continue
        overlap = len(raw_tokens & c_tokens)
        score = overlap / max(len(raw_tokens), len(c_tokens))
        if score > best_score:
            best_score, best_canonical = score, canonical
    if best_score >= 0.5 and best_canonical is not None:
        return best_canonical

    return raw_value


def normalize_features(features: Dict[str, Any], taxonomy: Taxonomy) -> Dict[str, Any]:
    """Snap raw LLM output values to canonical taxonomy values."""
    normalized: Dict[str, Any] = {}
    for fid, raw_val in features.items():
        try:
            ftype = taxonomy.feature(fid).type
        except KeyError:
            continue
        allowed = [str(v) for v in taxonomy.feature(fid).values]

        # Note: "none" is NOT treated as missing here — several taxonomy features
        # legitimately use "none" as a canonical value (e.g. REV_SUS_001 ordinal).
        if raw_val is None or str(raw_val).strip().lower() in ("n/a", "na"):
            normalized[fid] = MISSING
        elif ftype == "multi_select":
            vals = raw_val if isinstance(raw_val, list) else re.split(r"[|,]", str(raw_val))
            matched = [_best_match(str(v), allowed) for v in vals if str(v).strip()]
            seen, deduped = set(), []
            for m in matched:
                key = _normalize_str(m)
                if key and key not in seen:
                    seen.add(key)
                    deduped.append(m)
            normalized[fid] = deduped if deduped else MISSING
        elif ftype == "scale":
            s = str(raw_val).strip()
            num_match = re.match(r"^(\d+)", s)
            normalized[fid] = int(num_match.group(1)) if num_match else _best_match(s, allowed)
        else:
            normalized[fid] = _best_match(str(raw_val), allowed)
    return normalized


# ---------------------------------------------------------------------------
# Per-dimension prompt building (verbatim from the paper)
# ---------------------------------------------------------------------------

def build_dimension_prompt(dimension: Dimension, story_text: str) -> str:
    feature_specs: List[str] = []
    for f in dimension.features:
        values_str = ", ".join(str(v) for v in f.values[:10])
        if len(f.values) > 10:
            values_str += f" (+ {len(f.values) - 10} more)"
        feature_specs.append(f"**{f.id}** [{f.type}]: {f.question}")
        feature_specs.append(f"  → Values: {values_str}")
        if f.condition:
            feature_specs.append(f"  → Condition: {f.condition}")
    features_block = "\n".join(feature_specs)

    if len(story_text) > MAX_STORY_CHARS:
        story_text = story_text[:MAX_STORY_CHARS] + "\n\n[... story truncated ...]"

    return f"""You are a literary analyst specializing in {dimension.name.lower()}.

Extract structured features about **{dimension.name}** from the story below.
Focus area: {dimension.description}

# FEATURES TO EXTRACT

For each feature, select the appropriate value(s) from the allowed options.

**Response format rules:**
- For "binary" features: respond with exactly "yes" or "no"
- For "categorical" features: respond with exactly ONE value from the list
- For "ordinal" features: respond with exactly ONE value from the list
- For "multi_select" features: respond with a JSON array of ALL applicable values
- For "scale" features: respond with an integer within the specified range
- ONLY use values from the provided lists
- If a feature has a condition that is not met, use "n/a"
- **Never use null or omit a key** — every feature must have a value

{features_block}

# STORY TO ANALYZE

<story>
{story_text}
</story>

# OUTPUT

Return a single JSON object with feature IDs as keys.
"""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

# Minimum fraction of taxonomy features that must be extracted before the
# classifier is allowed to produce a verdict (below this, the signal is too thin).
MIN_COVERAGE = 0.5
# Retries after the initial parallel batch. Kept at 0: per-call retries inside
# the LLM client already handle transient failures, and a sequential re-batch
# would multiply latency when a provider is rate-limiting.
DIM_RETRIES = 0


def extract_story_features(
    taxonomy: Taxonomy,
    story_text: str,
    dim_workers: int = DEFAULT_DIM_WORKERS,
) -> Dict[str, Any]:
    """Extract all taxonomy features for a story (10 parallel LLM calls).

    Fails fast with an actionable error when fewer than MIN_COVERAGE of the
    taxonomy's features could be extracted (e.g. provider rate limiting).
    """
    all_features: Dict[str, Any] = {}
    failed: List[Dimension] = []

    def process_dimension(dim: Dimension) -> tuple[str, Dict[str, Any]]:
        prompt = build_dimension_prompt(dim, story_text)
        return dim.key, llm.generate_json(prompt)

    def run_batch(dims: List[Dimension]) -> None:
        nonlocal all_features, failed
        if not dims:
            return
        with ThreadPoolExecutor(max_workers=dim_workers) as executor:
            futures = {executor.submit(process_dimension, dim): dim for dim in dims}
            for future in as_completed(futures):
                dim = futures[future]
                try:
                    _, result = future.result()
                    clean = {k: v for k, v in result.items() if not k.startswith("_")}
                    all_features.update(clean)
                except Exception:  # noqa: BLE001 - retried below
                    failed.append(dim)

    run_batch(taxonomy.dimensions)
    for _ in range(DIM_RETRIES):
        if not failed:
            break
        retry, failed = failed, []
        run_batch(retry)

    if not all_features:
        raise RuntimeError(
            "StoryScope LLM extraction returned no features. The provider may be "
            "rate-limited or the API key invalid - check the server logs and retry."
        )

    coverage = len(all_features) / taxonomy.total_features
    if coverage < MIN_COVERAGE:
        raise RuntimeError(
            f"StoryScope extracted only {coverage:.0%} of the {taxonomy.total_features} "
            f"narrative features ({len(failed)}/{len(taxonomy.dimensions)} dimensions failed). "
            f"Likely LLM rate limiting - wait a bit and retry."
        )

    return normalize_features(all_features, taxonomy)
