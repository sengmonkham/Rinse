"""
Weighted Confidence Voter & Score Fusion Engine.

Fuses outputs from all 5 forensic layers, handles hard overrides for verified
watermarks / manifests, and calculates confidence tiers and forensic explanations.
"""

from typing import Dict, Any, List, Optional


def fuse_ensemble_verdict(
    layers: Dict[str, Optional[int]],
    layer_reasons: Dict[str, List[str]],
    is_video: bool = False,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Fuse multi-layer scores into a unified verdict.

    Args:
        layers: Dict with keys 'synthid', 'c2pa', 'frequency', 'neural', 'temporal'
        layer_reasons: Dict mapping layer key to list of reason strings
        is_video: True if video stream analysis
        extra_data: Additional payloads such as heatmap, patch grid, frame scores
    """
    weights = {
        "synthid": 0.30,
        "c2pa": 0.20,
        "frequency": 0.15,
        "neural": 0.25,
        "temporal": 0.10 if is_video else 0.0,
    }

    if not is_video:
        weights.pop("temporal", None)

    # Filter available layers (where score is not None)
    available = {k: v for k, v in layers.items() if v is not None and k in weights}
    
    if not available:
        return {
            "score": 50,
            "confidence": "LOW",
            "tier": "INCONCLUSIVE",
            "layers_active": [],
            "breakdown": {},
            "reasons": ["No forensic layers were able to analyze the input media."]
        }

    total_weight = sum(weights[k] for k in available)
    if total_weight <= 0:
        total_weight = 1.0

    raw_score = sum(
        layers[k] * (weights[k] / total_weight)
        for k in available
    )

    # Hard overrides
    synthid_val = layers.get("synthid")
    c2pa_val = layers.get("c2pa")
    
    # 1. Confirmed AI watermark or manifest
    if (synthid_val is not None and synthid_val >= 90) or (c2pa_val is not None and c2pa_val >= 90):
        raw_score = max(raw_score, 92.0)

    # 2. Confirmed authentic camera C2PA signature
    if c2pa_val is not None and c2pa_val <= 5:
        raw_score = min(raw_score, 12.0)

    final_score = int(round(min(99, max(1, raw_score))))

    # Determine confidence tier
    active_count = len(available)
    if (synthid_val is not None and synthid_val >= 90) or (c2pa_val is not None and c2pa_val >= 90):
        confidence = "HIGH"
    elif active_count >= 3:
        confidence = "HIGH"
    elif active_count >= 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # Determine qualitative classification tier
    if final_score >= 80:
        tier = "SYNTHETIC_AI"
    elif final_score >= 55:
        tier = "SUSPICIOUS"
    elif final_score >= 35:
        tier = "INCONCLUSIVE"
    else:
        tier = "AUTHENTIC_HUMAN"

    # Consolidate reasons
    all_reasons: List[str] = []
    for k in ["c2pa", "synthid", "neural", "frequency", "temporal"]:
        if k in layer_reasons and layer_reasons[k]:
            all_reasons.extend(layer_reasons[k])

    result: Dict[str, Any] = {
        "score": final_score,
        "confidence": confidence,
        "tier": tier,
        "layers_active": list(available.keys()),
        "breakdown": {k: int(round(v)) for k, v in available.items()},
        "reasons": all_reasons
    }

    if extra_data:
        result.update(extra_data)

    return result
