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
        "synthid": 0.25,
        "c2pa": 0.20,
        "frequency": 0.12,
        "neural": 0.20,
        "spai": 0.15,   # SPAI spectral analysis (CVPR 2025)
        "temporal": 0.07 if is_video else 0.0,   # coarse flicker/flow coherence
        "pwtf": 0.14 if is_video else 0.0,       # PwTF-DVD pixel-wise temporal
                                                  # frequency (ICCV 2025) - the
                                                  # strongest temporal signal
        # D3 second-order dynamics (ICCV 2025) runs as a METRICS layer on this
        # stack (pixel-space volatility does not separate - see
        # forensics/d3.py); weight 0.0 keeps it out of the fusion unless it is
        # ever activated behind calibrated encoder embeddings.
        "d3": 0.0,
    }

    if not is_video:
        weights.pop("temporal", None)
        weights.pop("pwtf", None)
        weights.pop("d3", None)

    # Filter available layers (where score is not None)
    available = {k: v for k, v in layers.items() if v is not None and k in weights}

    # Video-mode escalation guard: the temporal layers (pwtf/temporal) analyze
    # compressed, downscaled 128px thumbnails, so a lone high temporal reading
    # must never escalate the fused score on its own (the classic failure was
    # identical '62 / SUSPICIOUS' verdicts for an AI reel and a real one, both
    # driven by junk single-layer readings). Video verdicts need agreement:
    # either the temporal ensemble agrees with a spatial layer, or a
    # watermark/manifest/fingerprint speaks. Spatial-only escalation is fine.
    if is_video:
        temporal_layers = {k for k in ("temporal", "pwtf", "d3") if k in available}
        spatial_confident = any(
            available.get(k, 0) >= 70 for k in ("c2pa", "synthid", "neural", "frequency", "spai")
        )
        if temporal_layers and not spatial_confident:
            only_temporal_strong = all(
                available[k] < 70 for k in available if k not in temporal_layers
            )
            if only_temporal_strong:
                # Keep the temporal evidence out of the escalation path; the
                # weighted average still reflects it, capped at 55 below.
                weights_floor = 55.0
            else:
                weights_floor = None
        else:
            weights_floor = None
    else:
        weights_floor = None
    
    # The SynthID probe only emits a score below 90 for an *uncalibrated*
    # spectral soft vote (metadata-confirmed watermarks score >= 90). Soft
    # votes get a much smaller fusion weight so that a lossy-re-encode
    # resonance cannot dominate the ensemble.
    eff_weights = dict(weights)
    if "synthid" in available and available["synthid"] < 90:
        eff_weights["synthid"] = 0.08

    if not available:
        return {
            "score": 50,
            "confidence": "LOW",
            "tier": "INCONCLUSIVE",
            "layers_active": [],
            "breakdown": {},
            "reasons": ["No forensic layers were able to analyze the input media."]
        }

    total_weight = sum(eff_weights[k] for k in available)
    if total_weight <= 0:
        total_weight = 1.0

    raw_score = sum(
        layers[k] * (eff_weights[k] / total_weight)
        for k in available
    )

    # Hard overrides. NOTE: with the recalibrated SynthID probe, "synthid >= 90"
    # only happens on explicit file metadata, and c2pa >= 90 only on an explicit
    # trainedAlgorithmicMedia / AI-generator manifest, so this override is no
    # longer reachable from spectral noise.
    synthid_val = layers.get("synthid")
    c2pa_val = layers.get("c2pa")
    
    # 1. Confirmed AI watermark or manifest
    if (synthid_val is not None and synthid_val >= 90) or (c2pa_val is not None and c2pa_val >= 90):
        raw_score = max(raw_score, 92.0)

    # 2. Confirmed authentic camera C2PA signature
    if c2pa_val is not None and c2pa_val <= 5:
        raw_score = min(raw_score, 12.0)

    # 3. Strong-evidence escalation.
    # A plain weighted average lets a single overconfident (or blind-spot-hit)
    # layer bury a highly confident forensic signature - e.g. clear GAN grid
    # peaks / spectral deficits (frequency >= 75) scored against CNNSpot models
    # that are known to fail on small recompressed thumbnails. When any layer
    # is strongly confident the media is synthetic AND no hard authenticity
    # override fired above, floor the fused score into at least the suspicious
    # band instead of letting the average wash it out.
    # Escalation may only be driven by the well-understood forensic layers:
    # the temporal layers see only a 24-frame / 128px grayscale thumbnail, so
    # a strong reading there raises the fused score through the weighted
    # average instead of forcing a verdict on its own.
    ESCALATION_LAYERS = ("c2pa", "synthid", "neural", "frequency", "spai")
    escalation_pool = {k: v for k, v in available.items() if k in ESCALATION_LAYERS}
    strongest = max(escalation_pool.values()) if escalation_pool else 0
    authenticity_override = c2pa_val is not None and c2pa_val <= 5
    if not authenticity_override and weights_floor is None:
        if strongest >= 85:
            raw_score = max(raw_score, min(strongest, 82.0))
        elif strongest >= 70:
            raw_score = max(raw_score, 62.0)

    # Video temporal-only escalation cap (see the guard above).
    if weights_floor is not None:
        raw_score = min(raw_score, weights_floor)

    # Video: structural temporal evidence. On the recalibrated pwtf scorer a
    # score >= 60 is ONLY reachable via the coherence-floor collapse (p05 <
    # 0.20, optionally hotspot-confirmed) - the paper's core localized-
    # regeneration signature, which real motion does not produce (calibrated:
    # real reels kept p05 >= 0.31 across every shot window). That is structural,
    # not statistical, so it lifts the fused verdict into the suspicious band,
    # capped below the synthetic tier because the layer sees only a 128px
    # grayscale thumbnail.
    #
    # FALSE POSITIVE GUARD: The PwTF score alone is NOT sufficient evidence for
    # a SUSPICIOUS verdict on video. Real Instagram/TikTok reels with motion or
    # compression can trigger PwTF >= 60, but the calibration data shows:
    #   - Real reels: p05 coherence >= 0.31 across all shots
    #   - Generated clips: p05 coherence collapsed to ~0.00
    # So we require BOTH pwtf >= 60 AND p05 < 0.25 (not 0.30, not 0.35) to
    # escalate. Anything else is a false positive from motion/compression.
    pwtf_val = layers.get("pwtf")
    pwtf_metrics = (extra_data or {}).get("pwtf_metrics") if extra_data else None
    # A TOTAL coherence-floor collapse (p05 < 0.10) sits far below anything
    # real footage produces (calibrated: real reels keep p05 >= 0.31 across
    # every shot window; generated regions collapse to ~0.00). This deep
    # structural signature is decisive on its own: measured case - a
    # confirmed-AI Short with p05 = 0.00 and no confident spatial layer stuck
    # at 58 UNCERTAIN. It earns the suspicious band floor even without
    # spatial corroboration, and counts as decisive evidence for the tier
    # rule below regardless of confidence downgrades.
    total_collapse = bool(
        is_video
        and pwtf_val is not None
        and pwtf_val >= 60
        and pwtf_metrics
        and pwtf_metrics.get("coherence_p05", 1.0) < 0.10
    )
    if is_video and pwtf_val is not None and pwtf_val >= 60 and not authenticity_override:
        # Check if the coherence floor is ACTUALLY collapsed (p05 < 0.25)
        # vs just weak (p05 0.25-0.50) which happens on real footage with motion.
        if pwtf_metrics and pwtf_metrics.get("coherence_p05", 1.0) < 0.25:
            # Real coherence floor collapse - this IS a regeneration signature.
            #
            # Escalation strength scales with corroboration (measured: known-AI
            # reels with a genuine collapse were stuck at exactly 58 while the
            # spatial layers independently agreed, reading as 'UNCERTAIN' on
            # content that is plainly synthetic):
            #   - collapse + >= 2 spatial layers at 70+  -> up to 82 (synthetic band)
            #   - collapse + >= 1 spatial layer at 70+   -> up to 75 (suspicious+)
            #   - collapse alone (no spatial agreement)  -> up to 58 (unchanged:
            #     the layer only sees a 128px grayscale thumbnail, so a lone
            #     temporal reading must stay out of the decisive bands)
            spatial_strong = [
                v for k, v in available.items()
                if k in ("c2pa", "synthid", "neural", "frequency", "spai") and v >= 70
            ]
            if len(spatial_strong) >= 2:
                raw_score = max(raw_score, min(max(pwtf_val, 78), 82.0))
            elif len(spatial_strong) == 1:
                # One confident spatial classifier (e.g. CNNSpot at 70+) plus
                # a total coherence collapse is at least SUSPICIOUS: measured
                # case scored neural 76 with p05 = 0.00 and landed at 68
                # UNCERTAIN (unbadged) - too weak for that evidence.
                raw_score = max(raw_score, min(max(pwtf_val, 70), 75.0))
            elif total_collapse:
                # Near-total collapse, no confident spatial layer: the
                # structural signature alone earns the suspicious band floor
                # (66), never higher - the layer still only sees a 128px
                # grayscale thumbnail.
                raw_score = max(raw_score, min(max(pwtf_val, 66), 66.0))
            else:
                raw_score = max(raw_score, min(pwtf_val - 4, 58.0))
        else:
            # p05 >= 0.25: NOT a real collapse. This is a false positive from
            # motion, compression, or other artifacts on real footage.
            # Don't escalate - the temporal layer evidence is unreliable here.
            # The weighted average still reflects pwtf, but no escalation.
            pass

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

    # Layers disagree sharply about synthetic origin (one very high, another
    # very low): downgrade confidence so the UI communicates uncertainty even
    # when the escalated score lands in a decisive tier. An extreme spread
    # (>= 70) downgrades twice.
    confident_scores = [v for v in available.values() if v is not None]
    if len(confident_scores) >= 2:
        spread = max(confident_scores) - min(confident_scores)
        if spread >= 70 and confidence == "MEDIUM":
            confidence = "LOW"
        elif spread >= 55 and confidence == "HIGH":
            confidence = "MEDIUM"

    # Cross-window temporal agreement (video): the temporal layers run per
    # shot window and the strongest window wins. Generation artifacts are
    # usually localized to ONE scene, but a verdict escalated from a single
    # window while every other window reads clean is much weaker evidence
    # than the same score with corroboration - downgrade confidence when the
    # temporal-family evidence is a single-window outlier.
    if is_video and confidence in ("HIGH", "MEDIUM"):
        window_details = (extra_data or {}).get("window_details") or []
        if len(window_details) >= 2:
            per_window_temporal = [
                max(
                    (w.get("temporal_score") or 0),
                    (w.get("pwtf_score") or 0),
                    (w.get("d3_score") or 0),
                )
                for w in window_details
            ]
            strong_windows = sum(1 for s in per_window_temporal if s >= 55)
            if strong_windows == 1 and max(per_window_temporal) >= 60:
                confidence = "LOW" if confidence == "MEDIUM" else "MEDIUM"

    # Determine qualitative classification tier. The 55-68 band with non-HIGH
    # confidence is deliberately labeled UNCERTAIN rather than SUSPICIOUS:
    # the escalated-but-unconfirmed readings that land there (lone strong
    # layer, single-window temporal evidence, layer disagreement) are exactly
    # the cases where a decisive-sounding "SUSPICIOUS" misled users. A HIGH-
    # confidence 55-68 (several agreeing layers) still reads SUSPICIOUS, and
    # 69-79 always reads SUSPICIOUS regardless of confidence (escalations
    # into that band are corroboration-backed by construction).
    #
    # An 'authentic' verdict additionally REQUIRES positive temporal evidence
    # on video: when the temporal layers could not run (sparse client frames
    # without a valid frame interval - the temporal layers abstain by
    # design), a low spatial-only score must read INCONCLUSIVE, never
    # AUTHENTIC_HUMAN. Calibrated failure: a YouTube Short fetched through
    # the browser-extraction path scored 19 'AUTHENTIC_HUMAN' on spatial
    # layers alone while the temporal ensemble - the only layers that can
    # actually see generation - never voted.
    temporal_ran = any(
        k in available for k in ("temporal", "pwtf")
    ) or bool((extra_data or {}).get("temporal_active")) if is_video else True
    if final_score >= 80:
        tier = "SYNTHETIC_AI"
    elif final_score >= 69:
        tier = "SUSPICIOUS"
    elif final_score >= 55:
        # HIGH-confidence agreement or a confirmed total coherence collapse
        # (structural evidence, see above) both justify SUSPICIOUS in the
        # 55-68 band; everything else is UNCERTAIN.
        tier = "SUSPICIOUS" if (confidence == "HIGH" or total_collapse) else "UNCERTAIN"
    elif final_score >= 35:
        tier = "INCONCLUSIVE"
    elif is_video and not temporal_ran and not (
        c2pa_val is not None and c2pa_val <= 5
    ) and not (
        synthid_val is not None and synthid_val >= 90
    ):
        # Spatial-only video scan without a hard authenticity override:
        # honest abstention instead of a false 'authentic'.
        tier = "INCONCLUSIVE"
    else:
        tier = "AUTHENTIC_HUMAN"

    # Consolidate reasons - watermark/manifest/spatial forensics first; the
    # temporal layers last, since on video they are supplementary evidence.
    all_reasons: List[str] = []
    for k in ["c2pa", "synthid", "neural", "frequency", "spai", "pwtf", "temporal", "d3"]:
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
