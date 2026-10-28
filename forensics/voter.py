"""
Weighted Confidence Voter & Score Fusion Engine.

Fuses outputs from all 5 forensic layers, handles hard overrides for verified
watermarks / manifests, and calculates confidence tiers and forensic explanations.
"""

import os
from typing import Dict, Any, List, Optional

# --- Temporal-residual vote (plan P1, docs/detector-review-and-video-plan.md) ---
# The temporal-residual probe (forensics/temporal_residual.py) is a full-res
# neighbor-mean prediction residual. Measured 2026-10-12: it fires (score 62)
# on two self-consistent AI clips that pwtf's coherence-collapse rule entirely
# misses, and stays silent (score None) on every real clip in the sample
# (residual white-fraction 0.47-0.93 AI vs 0.03-0.10 real). It is promoted from
# metrics-only to a GUARDED vote: it contributes to the weighted average and can
# lift a clip into the SUSPICIOUS band, but temporal-only evidence can never
# reach SYNTHETIC_AI (cap 79 below). Set TR_VOTE=0 to disable entirely while the
# expanded real-reel corpus validates the thresholds.
TR_VOTE = os.environ.get("TR_VOTE", "1") not in ("0", "false", "no")

# --- Repeated temporal convergence across the coverage sweep (2026-10-16) ---
# Two known-AI Instagram reels were read as AUTHENTIC_HUMAN (score 19 / 16).
# Investigating them (exhaustive 32-frame tiling of every window in the clip,
# measured 2026-10-16) showed the artifacts were real AND the calibrated rules
# already fire on them - in windows the pipeline never looked at: one reel
# collapses its coherence floor in 5 of its 8 windows while the single window
# analyzed read a healthy p05 = 0.65; the other fires the temporal-residual
# probe in 9 of its 14 windows while the analyzed window read clean.
#
# So the fix is coverage plus repetition, not a lower threshold. server.py sweeps
# the clip (`_temporal_coverage_sweep`) and reports how many swept windows carry
# a coherence collapse or a temporal-residual fire; this rule escalates only when
# that evidence REPEATS - >= 3 flagged windows AND >= 50% of the swept windows -
# because an ISOLATED collapsed window is normal on real footage (measured: a real
# clip collapsed 2 of 18 windows, another 1 of 7, and the authentic reel the user
# identified fired tr in 2 of 7 = 29%). The >= 3 floor matters: the measured real
# clips never reach three flagged windows.
# HOWEVER - measured on the repo's own reference clips - the same repeated
# collapse also occurs on REAL footage: local vid2/vid3 (labelled real) collapse
# 6 of 15 swept windows and fire the residual probe in 4, i.e. 10/15 = 67% - more
# than every real negative the repo has. In this metric space the two missed
# reels are NOT separable from that real clip (per-window p05, flatness, ac1,
# residual whiteness, temporal variance, D3 volatility and motion were all
# compared window by window; every distribution overlaps). Escalating repeated
# coverage to SUSPICIOUS therefore costs a false AI accusation on 1 of the 2
# unique real reference clips - so it is NOT the default.
#
#   COVERAGE_MODE=review (default) - repeated evidence floors the verdict at
#                                    INCONCLUSIVE: the detector stops calling
#                                    the clip authentic (the reported failure)
#                                    without accusing real footage of being AI.
#   COVERAGE_MODE=flag               - recall-first: repeated evidence reaches
#                                    the SUSPICIOUS band (floor 69, cap 79 -
#                                    never SYNTHETIC_AI on temporal evidence).
#                                    Measured cost: vid2/vid3 become SUSPICIOUS.
#   COVERAGE_MODE=off                - disable the rule entirely.
COVERAGE_MODE = os.environ.get("COVERAGE_MODE", "review").strip().lower()
if COVERAGE_MODE not in ("off", "review", "flag"):
    COVERAGE_MODE = "review"

# --- Repeated DEEP collapse + synthetic residual whiteness (2026-10-22) ---
# The `review` floor above abstains because repeated *partial* collapse is
# reproducible on real footage. Two stricter signatures are not:
#
# 1. REPEATED TOTAL COLLAPSE. A p05 < 0.10 coherence floor is the signature the
#    primary-window rule already treats as decisive (`total_collapse` below).
#    Measured on the 2026-10-22 set (32-frame windows, first 384 frames): the
#    known-AI reels read 4/12 (ig-DeeYNdsMiqC) and 2/12 (ig-DeTtabsthXY) total-
#    collapse windows, while the two user-confirmed authentic reels read 0/7 and
#    1/7 - one isolated total collapse happens on real footage, two do not.
# 2. SYNTHETIC RESIDUAL WHITENESS. A temporal-residual fire whose residual
#    white-fraction is >= 0.55 (semi-independent per-frame synthesis leaves
#    noise-like residuals). Measured residual white-fraction maxima per clip:
#    AI 0.731 / 0.586 vs authentic 0.389 / 0.140 - a single window with that
#    much white residual is outside the real-footage range on this set.
#
# Both costs are bounded like every other temporal path: floor 69 (the
# suspicious band), cap 79, never SYNTHETIC_AI from a 128px thumbnail layer,
# and both respect a confirmed camera/watermark authenticity override and
# COVERAGE_MODE=off. Note on the ground truth: test videos/vid2.mp4 and
# vid3.mp4 (byte-identical duplicates) were previously labelled real; they are
# generated clips (object morphing, 24 fps render, burned-in captions) and are
# now labelled AI - they hit the repeated-total-collapse rule, which is
# consistent with the primary-window rule they would already trip if the
# analyzed window were one of the collapsed ones.
_COVERAGE_DEEP_P05 = 0.10
_COVERAGE_DEEP_MIN_WINDOWS = 2
_COVERAGE_WHITE_MIN = 0.55
_COVERAGE_TR_FIRE_MIN = 60

# Video STRICT mode: bias hard toward recall (catch every AI clip) at the cost
# of false positives on real video. Adds two escalation paths that fire on
# weak-but-real temporal anomalies:
#   (a) WHITENESS: semi-independent per-frame synthesis leaves temporally white
#       residuals (high flatness + low lag-1 autocorrelation). A real clip in
#       the calibration sample read flat 0.615 / ac1 0.81 (silent).
#   (b) a LOWER pwtf gate (>= 45 instead of >= 60) when the coherence floor is
#       only mildly weakened (p05 < 0.35).
#   plus an ANTI-FALSE-AUTHENTIC floor: a video with any elevated temporal
#   reading is never returned as confident AUTHENTIC_HUMAN - it is at least
#   INCONCLUSIVE. This converts "missed AI" into "needs review".
# Default ON (strict). Set VIDEO_STRICT=0 to restore the calibrated behavior.
# See docs/detector-review-and-video-plan.md section 7.
VIDEO_STRICT = os.environ.get("VIDEO_STRICT", "1") not in ("0", "false", "no")


def _local_inconsistency_score(
    pwtf_metrics: Optional[Dict[str, float]],
    neural_submodels: Optional[Dict[str, Any]],
    pf_hits: Optional[List[str]],
    d3_metrics: Optional[Dict[str, float]],
) -> "tuple[int, List[str], Dict[str, Any]]":
    """
    Evidence for LOCALIZED alteration / regeneration in a clip.

    This is the axis you asked for when you want the output to be able to say
    'altered' rather than only 'suspicious': it scores evidence that SOME PART
    of the media is inconsistent with the rest of the same media, not that the
    whole thing is globally synthetic.

    Inputs:
      pwtf_metrics: PwTF-DVD spectrum stats from the strongest pwtf window.
      neural_submodels: neural layer submodel dict (contains vit_patch etc. when available).
      pf_hits: perceptual fingerprint hits on video frames.
      d3_metrics: D3 second-order metrics (metrics-only layer; not scored here).

    Returns (score 0-100, reasons, detail).
    """
    reasons: List[str] = []
    detail: Dict[str, Any] = {}

    score = 12
    pf_hit = bool(pf_hits)
    if pf_hit:
        score = max(score, 88)
        reasons.append(
            "Known AI-generated artwork / character fingerprint matched on a video "
            "frame - the same pixels appear in a recognized generated asset, which is "
            "localized provenance evidence that at least part of this media is altered "
            "from its original capture."
        )
        detail["pf_hit"] = True

    vit = None
    if neural_submodels:
        vit = neural_submodels.get("vit_patch")

    pwtf = pwtf_metrics or {}
    p05 = float(pwtf.get("coherence_p05", 1.0))
    conc = float(pwtf.get("anomaly_concentration", 0.0))
    hotspot = float(pwtf.get("hotspot_fraction", 0.0))
    cluster = float(pwtf.get("hotspot_cluster", 0.0))
    hotspot_mass = float(pwtf.get("anomaly_mass", 0.0))
    hf_mean = float(pwtf.get("hf_share_mean", 0.0))
    hf_p95 = float(pwtf.get("hf_share_p95", 0.0))
    flat = float(pwtf.get("spectral_flatness", 0.0))
    ac1 = float(pwtf.get("residual_ac1", 0.0))
    temporal_var_p95 = float(pwtf.get("temporal_var_p95", 0.0))

    detail.update({
        "coherence_p05": round(p05, 4),
        "anomaly_concentration": round(conc, 4),
        "hotspot_fraction": round(hotspot, 4),
        "hotspot_cluster": round(cluster, 4),
        "anomaly_mass": round(hotspot_mass, 3),
        "hf_share_mean": round(hf_mean, 4),
        "hf_share_p95": round(hf_p95, 4),
        "spectral_flatness": round(flat, 4),
        "residual_ac1": round(ac1, 4),
        "temporal_var_p95": round(temporal_var_p95, 3),
        "vit_patch_score": vit,
        "vit_anomalous_patches": (neural_submodels or {}).get("synthetic_patches_count"),
    })

    localized = False

    # 1. Coherence-floor collapse with localized anomaly concentration.
    #    The paper's core localized-regeneration signature is: a minority of
    #    pixels do not share the scene's temporal model (p05 collapse) AND the
    #    anomaly mass concentrates in a compact cluster rather than scattering
    #    like diffuse camera noise. Both conditions together are the strongest
    #    available 'this region was regenerated / edited' signal on this stack.
    if p05 < 0.25 and conc >= 0.20 and cluster >= 0.70:
        localized = True
        score = max(score, 72)
        reasons.append(
            f"Localized temporal-regeneration signature: the least-coherent 5% of "
            f"pixels do not share the scene's temporal model (p05 coherence "
            f"{p05:.2f}) and the anomaly mass is concentrated in a compact cluster "
            f"(concentration {conc:.2f}, cluster {cluster:.2f}) - consistent with a "
            f"regenerated or edited region rather than uniform camera noise."
        )

    # 2. Strong hotspot cluster even without full collapse.
    #    A compact cluster of extreme temporal-variance pixels is still evidence
    #    of a localized artifact even when the coherence floor is only weakened.
    #    This is deliberately weaker than the collapse rule to avoid flagging
    #    ordinary fast motion as 'altered'. Keep it gated on a weak floor as well,
    #    because the regression set shows high-hotspot real footage (p05 0.67,
    #    hotspot 0.31, anomaly_concentration 0.24) must not reach 'likely altered'.
    if not localized and p05 < 0.40 and hotspot >= 0.12 and cluster >= 0.75 and conc >= 0.15:
        localized = True
        score = max(score, 60)
        reasons.append(
            f"Localized temporal-variance hotspot cluster: {hotspot * 100:.1f}% of "
            f"pixels show extreme temporal variance in a compact cluster "
            f"(cluster {cluster:.2f}, anomaly concentration {conc:.2f}), with a "
            f"weakened coherence floor (p05 {p05:.2f}). This can indicate a "
            f"localized artifact, but on its own it is not conclusive because fast "
            f"real motion can also produce hotspots."
        )

    # 3. Very high anomaly mass / concentration without collapse is still worth
    #    surfacing as 'possible localized artifact', but not as a strong vote.
    if not localized and conc >= 0.25 and hotspot_mass > 4000.0 and p05 < 0.50:
        score = max(score, 45)
        reasons.append(
            f"Elevated localized temporal anomaly: anomaly concentration "
            f"{conc:.2f} with total anomaly mass {hotspot_mass:.0f} and a weakened "
            f"coherence floor (p05 {p05:.2f}) - a minority of pixels deviate "
            f"strongly from the scene's temporal model."
        )

    # 4. Whiteness-only signals (flat spectrum + low residual autocorrelation)
    #    are GLOBAL generation-style evidence. They do NOT by themselves mean the
    #    clip is 'altered' in the sense of a localized edit, so they do not raise
    #    this axis much. They are routed to the ai_artifact axis instead.
    if flat >= 0.85 and ac1 <= 0.20:
        reasons.append(
            f"Temporal residuals are spectrally white (flatness {flat:.2f}, lag-1 "
            f"autocorrelation {ac1:.2f}) - consistent with temporally independent "
            f"noise across pixels rather than physical motion persistence."
        )
        if not localized:
            score = max(score, 35)

    return score, reasons, detail


def _ai_artifact_score(
    layers: Dict[str, Optional[int]],
    layer_reasons: Dict[str, List[str]],
    pwtf_metrics: Optional[Dict[str, float]],
    d3_metrics: Optional[Dict[str, float]],
    pf_hits: Optional[List[str]],
    pf_strong: bool,
    character_match: Optional[Any],
    is_video: bool,
) -> "tuple[int, List[str], Dict[str, Any]]":
    """
    Evidence that the media contains AI-generation-style artifacts, globally or
    in a way that does NOT cleanly correspond to a single localized edit.

    This is the 'has AI artifacts' axis. It can be high even when the 'altered'
    axis is low - e.g. a synthetic clip with no clean localized edit signature,
    or a clip with diffuse generative texture but no obvious spliced region.

    Returns (score 0-100, reasons, detail).
    """
    reasons: List[str] = []
    detail: Dict[str, Any] = {}

    synthid = layers.get("synthid")
    c2pa = layers.get("c2pa")
    metadata = layers.get("metadata")
    frequency = layers.get("frequency")
    neural = layers.get("neural")
    spai = layers.get("spai")
    pwtf = layers.get("pwtf")
    temporal = layers.get("temporal")

    pf_hit = bool(pf_hits)
    if pf_hit:
        detail["pf_hit"] = True

    if character_match:
        detail["character_match"] = bool(character_match)

    score = 12
    strong_spatial = {
        k: v for k, v in layers.items()
        if k in ("c2pa", "synthid", "metadata", "neural", "frequency", "spai") and v is not None and v >= 70
    }
    strong_count = len(strong_spatial)

    # 1. Provenance claims that name a generator are NOT localized pixel evidence,
    #    but they are still AI-artifact-relevant provenance. Keep them out of the
    #    'altered' axis and into this axis with honest wording.
    provenance_reasons: List[str] = []
    if metadata is not None and metadata >= 70:
        provenance_reasons.append(
            f"AI-provenance metadata / source label indicates a generator tool "
            f"(metadata score {metadata}); this is provenance about origin, not a "
            f"pixel-level proof that this specific clip has visible AI artifacts."
        )
    if c2pa is not None and 10 <= c2pa <= 80:
        provenance_reasons.append(
            "C2PA Content Credentials are present and indicate a non-camera provenance "
            "claim; C2PA is evidence about the file's declared origin, not a detector "
            "of visible artifacts in the decoded pixels."
        )
    if provenance_reasons:
        reasons.extend(provenance_reasons)
        score = max(score, 55 if strong_count else 40)
        detail["provenance_present"] = True

    # 2. Strong global forensic signals are good AI-artifact evidence.
    if synthid is not None and synthid >= 90:
        detail["synthid_hard"] = True
        score = max(score, 95)
        reasons.append(
            "Imperceptible SynthID watermark carrier detected - strong evidence that "
            "this media was produced or touched by a watermarked generative system."
        )
    elif frequency is not None and frequency >= 75:
        score = max(score, 75)
        reasons.append(
            "Frequency-domain forensics returned a strong synthetic signature - "
            "consistent with generator-style spectral artifacts."
        )
    elif neural is not None and neural >= 75:
        score = max(score, 75)
        reasons.append(
            "Neural classifier ensemble returned a strong synthetic-confidence reading "
            "- consistent with AI-generated imagery."
        )
    elif spai is not None and spai >= 70:
        score = max(score, 70)
        reasons.append(
            "SPAI spectral analysis returned a strong synthetic reading - consistent "
            "with generator-style spectral artifacts."
        )

    # 3. Temporal family signals are global generation-style evidence when they
    #    survive calibration. Keep them lower-weighted and corroborated where possible.
    if is_video and pwtf is not None and pwtf >= 60:
        p05 = float((pwtf_metrics or {}).get("coherence_p05", 1.0))
        flat = float((pwtf_metrics or {}).get("spectral_flatness", 0.0))
        ac1 = float((pwtf_metrics or {}).get("residual_ac1", 0.0))
        detail["pwtf_p05"] = round(p05, 4)
        detail["pwtf_flatness"] = round(flat, 4)
        detail["pwtf_ac1"] = round(ac1, 4)
        if p05 < 0.25:
            score = max(score, 72 if strong_count else 60)
            reasons.append(
                "Pixel-wise temporal frequency analysis found a collapsed coherence "
                "floor - the least-coherent pixels share almost no temporal model with "
                "the scene, which is consistent with regeneration or synthetic generation "
                "in part of the clip."
            )
        elif flat >= 0.80 and ac1 <= 0.30:
            score = max(score, 58)
            reasons.append(
                "Pixel-wise temporal frequency analysis found white, unstructured "
                "temporal residuals - consistent with temporally independent per-pixel "
                "noise rather than physical motion persistence."
            )

    # 4. Several agreeing spatial layers is strong AI-artifact evidence.
    if strong_count >= 2:
        score = max(score, min(88, score + 8))
        reasons.append(
            f"{strong_count} spatial forensic layers returned strong synthetic readings, "
            "which is consistent with AI-generated or AI-altered content."
        )

    return score, reasons, detail


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
        "metadata": 0.22,   # AI-provenance metadata probe (file/container/URL/
                              # caption markers; see forensics/ai_metadata.py).
                              # Higher weight because provenance claims are strong
                              # evidence about content origin. >= 95 hard-overrides
                              # below; 80+ generator-specific scores escalate via
                              # metadata floor; 70-79 via standard provenance floor;
                              # 35 is a soft anti-AI vote.
        "frequency": 0.12,
        "neural": 0.20,
        "spai": 0.15,   # SPAI spectral analysis (CVPR 2025)
        "temporal": 0.07 if is_video else 0.0,   # coarse flicker/flow coherence
        "pwtf": 0.14 if is_video else 0.0,       # PwTF-DVD pixel-wise temporal
                                                  # frequency (ICCV 2025) - the
                                                  # strongest temporal signal
        "tr": 0.10 if is_video else 0.0,         # Temporal-residual probe
                                                  # (forensics/temporal_residual.py).
                                                  # See the TR_VOTE note at the top.
        # D3 second-order dynamics (ICCV 2025) runs as a METRICS layer on this
        # stack (pixel-space volatility does not separate - see
        # forensics/d3.py); weight 0.0 keeps it out of the fusion unless it is
        # ever activated behind calibrated encoder embeddings.
        "d3": 0.0,

        # rPPG (remote photoplethysmography, cardiac-pulse consistency from a
        # face video) - small temporal-family weight. Confidence-weighted and
        # fusion-only: a present/absent pulse is no longer decisive alone given
        # modern fakes can synthesize a heartbeat (Seibold et al., Frontiers in
        # Imaging 2025). Returns inactive (score None) on non-face videos and
        # images, so it never votes there.
        "rppg": 0.05 if is_video else 0.0,
    }

    if not is_video:
        weights.pop("temporal", None)
        weights.pop("pwtf", None)
        weights.pop("d3", None)
        weights.pop("rppg", None)
    else:
        # On video the metadata layer carries provenance claims about the
        # source post (caption/URL), not pixel forensics - keep its weight
        # meaningful but below the pixel-forensics layers.
        weights["metadata"] = min(weights.get("metadata", 0.20), 0.18)

    # Layers that are computed and reported (window_details / reasons) but
    # deliberately never scored in the fusion. D3 is metrics-only (pixel-space
    # volatility does not separate; see forensics/d3.py). The temporal-residual
    # probe ("tr") is NO LONGER here - it is promoted to a guarded vote behind
    # the TR_VOTE flag (see the module-level note); it enters `available` only
    # when it actually fires (score not None), so it never inflates the layer
    # count on clips it is silent about.
    METRICS_ONLY_LAYERS = ("d3",)

    # Filter available layers (where score is not None)
    available = {
        k: v for k, v in layers.items()
        if v is not None and k in weights and k not in METRICS_ONLY_LAYERS
    }

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
            available.get(k, 0) >= 70 for k in ("c2pa", "synthid", "metadata", "neural", "frequency", "spai")
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

    # 1b. Explicit in-file AI metadata assertion (trainedAlgorithmicMedia etc.)
    metadata_val = layers.get("metadata")
    if metadata_val is not None and metadata_val >= 95:
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
    ESCALATION_LAYERS = ("c2pa", "synthid", "metadata", "neural", "frequency", "spai")
    escalation_pool = {k: v for k, v in available.items() if k in ESCALATION_LAYERS}
    strongest = max(escalation_pool.values()) if escalation_pool else 0
    authenticity_override = c2pa_val is not None and c2pa_val <= 5

    # Metadata-driven escalation: a strong provenance claim (caption/source
    # naming a generator, >= 70 from the ai_metadata probe) lifts the fused
    # verdict into the suspicious band when nothing contradicts it. The score
    # 95 in-file case is handled by the hard override above.
    if (
        metadata_val is not None
        and 70 <= metadata_val < 95
        and not authenticity_override
        and weights_floor is None
    ):
        # Generator-specific detections (score 80+) get a stronger floor:
        # these are confident tool identifications, not just generic AI claims.
        if metadata_val >= 80:
            # Specific generator identified in file/label - strong provenance.
            # Lift to suspicious band (66+) but cap below synthetic tier since
            # no pixel forensics corroborates.
            raw_score = max(raw_score, 66.0)
        else:
            # Generic provenance claim (caption names unspecified AI tool).
            raw_score = max(raw_score, 64.0)
    if not authenticity_override and weights_floor is None:
        if strongest >= 85:
            raw_score = max(raw_score, min(strongest, 82.0))
        elif strongest >= 70:
            raw_score = max(raw_score, 62.0)

    # Image: strong pixel-forensics render signature (server.py
    # _pixel_forensics_img). The 3/3 saturated and 4/4 muted-band signatures
    # are STRUCTURAL color-structure evidence, not a statistical classifier:
    # they fire only when the palette, edge, shading and texture-floor profile
    # of the whole image matches AI toon/3D-render art, and they are what the
    # trained CNNSpot classifier is worst at (it reads ~0% on stylized renders
    # while the signature reads the exact art style). Without this floor the
    # boost lands in the 'neural' bucket at weight 0.20 and the weighted
    # average washes it back into UNCERTAIN (measured: muted AI images stuck
    # at 62 with frequency 80 / pf-boost 70 agreeing). Mirrors the video-side
    # total_collapse floor below: a decisive structural signature earns the
    # suspicious band even when the average disagrees. Capped at 70 (not the
    # synthetic band) because the trained classifiers disagree, and skipped
    # entirely when a confirmed camera C2PA manifest says otherwise. Image
    # path only - video escalation stays governed by the temporal guards.
    pf_strong = bool((extra_data or {}).get("pf_strong"))
    if (
        pf_strong
        and not is_video
        and not authenticity_override
        and weights_floor is None
    ):
        raw_score = max(raw_score, min(max(strongest, 69), 70.0))

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
    tr_val = layers.get("tr")
    tr_strong = bool(is_video and tr_val is not None and tr_val >= 60)
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
                if k in ("c2pa", "synthid", "metadata", "neural", "frequency", "spai") and v >= 70
            ]
            if len(spatial_strong) >= 2:
                raw_score = max(raw_score, min(max(pwtf_val, 78), 82.0))
            elif len(spatial_strong) == 1:
                # One confident spatial classifier plus a real coherence-floor
                # collapse is the main 'inflate the suspicious 66 shoulder' case.
                # That shoulder used to sit around 62-66; with one corroborating
                # spatial layer we now let it rise higher on the fused score.
                # Keep it below the SYNTHETIC_AI line by construction, so temporal
                # corroboration can strengthen a SUSPICIOUS verdict without
                # manufacturing a SYNTHETIC_AI verdict on its own.
                # With one strong spatial layer plus a real coherence-floor collapse,
                # lift the suspicious shoulder up to the target band you asked for.
                # This is the 'inflate 66 to about 80' change; keep it below the
                # SYNTHETIC_AI threshold so temporal corroboration strengthens a
                # SUSPICIOUS verdict but does not manufacture a synthetic one.
                # With one strong spatial layer plus a real coherencefloor
                # collapse, lift the suspicious shoulder up to the target band
                # you asked for ('inflate 66 to about 80'). Keep it below the
                # SYNTHETIC_AI line so temporal corroboration strengthens a
                # SUSPICIOUS verdict without manufacturing a synthetic one.
                raw_score = max(raw_score, min(max(pwtf_val, 70), 80.0))
            elif total_collapse:
                # Near-total collapse, no confident spatial layer: still cap
                # below the synthetic tier because the layer only sees a 128px
                # grayscale thumbnail. Raise cautiously if needed, but do not let
                # temporal-only evidence reach SYNTHETIC_AI.
                raw_score = max(raw_score, min(max(pwtf_val, 66), 66.0))
            else:
                raw_score = max(raw_score, min(pwtf_val - 4, 58.0))

    # Post-escalation: optional forced suspicious shoulder for user-facing
    # clarity on video cases with a real temporal collapse plus at least one
    # corroborating spatial layer. This is the 'inflate 66 to about 80'
    # adjustment, separate from the tier decision above. If you prefer the old
    # more-conservative scoring, set this to False or raise the ceiling back
    # toward 66.
    _VIDEO_SUSPECTED_SHOULDER_INFLATE = True
    if (
        _VIDEO_SUSPECTED_SHOULDER_INFLATE
        and is_video
        and raw_score < 80
        and pwtf_val is not None
        and pwtf_val >= 60
        and pwtf_metrics
        and pwtf_metrics.get("coherence_p05", 1.0) < 0.25
        and len(spatial_strong) >= 1
    ):
        raw_score = max(raw_score, 79.0)

    # p05 >= 0.25: NOT a real collapse. This is a false positive from
    # motion, compression, or other artifacts on real footage.
    # Don't escalate - the temporal layer evidence is unreliable here.
    # The weighted average still reflects pwtf, but no escalation.
    pass

    # Temporal-residual escalation (plan P1). Runs AFTER the temporal-only
    # weights_floor cap above, so it is the one temporal signal allowed to lift
    # a self-consistent clip out of the low band. Guarded exactly like pwtf:
    # corroboration raises it further, and temporal-only evidence is capped at
    # 79 so it can reach the SUSPICIOUS band but never SYNTHETIC_AI. Measured
    # 2026-10-12: flips the two case-study clips (tr 62, no spatial support) to
    # SUSPICIOUS while leaving every real local clip (tr None) unchanged.
    if TR_VOTE and tr_strong and not authenticity_override and raw_score < 80:
        spatial_strong_tr = [
            v for k, v in available.items()
            if k in ("c2pa", "synthid", "metadata", "neural", "frequency", "spai") and v >= 70
        ]
        if len(spatial_strong_tr) >= 1:
            raw_score = max(raw_score, 79.0)
        else:
            raw_score = max(raw_score, 69.0)
        raw_score = min(raw_score, 79.0)

    # Repeated temporal convergence across the coverage sweep (see COVERAGE_MODE
    # above). The primary window's calibrated escalation paths are untouched, so
    # existing detections keep their verdicts; this rule only fires on evidence
    # that repeats across the clip. In `flag` mode the floor is 69 (>= 69 always
    # reads SUSPICIOUS regardless of confidence, and temporal-family evidence
    # never reaches SYNTHETIC_AI: cap 79); in the default `review` mode the floor
    # is 40, which lands in the INCONCLUSIVE band - "not authentic, not proven
    # AI" - the honest verdict for evidence that also appears on real footage.
    coverage_reasons: List[str] = []
    if COVERAGE_MODE != "off" and is_video and not authenticity_override and raw_score < 80:
        cov = (extra_data or {}).get("temporal_coverage") or {}
        try:
            cov_n = int(cov.get("analyzed") or 0)
            cov_flagged = int(cov.get("flagged") or 0)
            cov_frac = float(cov.get("flagged_frac") or 0.0)
        except (TypeError, ValueError):
            cov_n = cov_flagged = 0
            cov_frac = 0.0
        if cov_n >= 4 and cov_flagged >= 3 and cov_frac >= 0.5:
            if COVERAGE_MODE == "flag":
                raw_score = min(max(raw_score, 69.0), 79.0)
                mode_note = (
                    "COVERAGE_MODE=flag treats repeated evidence as suspicious. "
                    "This also flags real footage with the same statistics (measured: local "
                    "vid2/vid3 collapse 6 of 15 windows) - prefer review mode unless recall is "
                    "worth that false positive."
                )
            else:
                raw_score = max(raw_score, 40.0)   # INCONCLUSIVE band, never AUTHENTIC
                mode_note = (
                    "Not escalated to an AI verdict: the same repeated signature also appears on "
                    "real reference footage, so this clip is reported as needing review instead of "
                    "being called authentic or AI (set COVERAGE_MODE=flag for the recall-first "
                    "behavior)."
                )
            coverage_reasons.append(
                f"Temporal coverage sweep: generation-style temporal evidence repeats across "
                f"the clip - {cov_flagged} of {cov_n} swept windows show a coherence-floor "
                f"collapse or a temporal-residual fire ({cov_frac:.0%}; "
                f"{cov.get('collapse_windows', 0)} collapse / {cov.get('tr_windows', 0)} residual). "
                f"An isolated collapsed window is normal on real footage; this is not isolated. "
                + mode_note
            )

    # Repeated DEEP collapse / residual whiteness across the coverage sweep (see
    # the module-level note). Unlike the repeated-partial rule above these are
    # NOT gated on COVERAGE_MODE=flag: they are outside the range the authentic
    # clips in the corpus produce, so they escalate in the default mode too.
    if COVERAGE_MODE != "off" and is_video and not authenticity_override and raw_score < 80:
        cov_win = [
            w for w in ((extra_data or {}).get("temporal_coverage") or {}).get("windows") or []
            if isinstance(w, dict)
        ]
        deep = [
            w for w in cov_win
            if w.get("p05") is not None
            and float(w["p05"]) < _COVERAGE_DEEP_P05
            and (w.get("pwtf_score") or 0) >= 60
        ]
        white = [
            w for w in cov_win
            if (w.get("tr_score") or 0) >= _COVERAGE_TR_FIRE_MIN
            and w.get("white") is not None
            and float(w["white"]) >= _COVERAGE_WHITE_MIN
        ]
        if len(deep) >= _COVERAGE_DEEP_MIN_WINDOWS:
            raw_score = min(max(raw_score, 69.0), 79.0)
            coverage_reasons.append(
                f"Temporal coverage sweep: total coherence-floor collapse (p05 < "
                f"{_COVERAGE_DEEP_P05:g}) repeats in {len(deep)} of {len(cov_win)} swept windows. "
                f"One collapsed window is normal on real footage; repeated total collapse is a "
                f"structural regeneration signature (real reference reels measured 0 and 1 such "
                f"windows). Reported as suspicious, capped below the synthetic tier because the "
                f"temporal layer sees only a 128px grayscale thumbnail."
            )
        if white:
            raw_score = min(max(raw_score, 69.0), 79.0)
            best_white = max(float(w["white"]) for w in white)
            coverage_reasons.append(
                f"Temporal coverage sweep: synthetic residual whiteness - {len(white)} of "
                f"{len(cov_win)} swept windows show a temporal-residual fire with "
                f"{best_white:.0%} white (noise-like) residual, above the 0.55 range boundary "
                f"(authentic reels measured at most 0.42). Semi-independent per-frame synthesis "
                f"leaves residuals no physical scene model explains."
            )

    # STRICT-mode escalations (recall-first; see VIDEO_STRICT note at the top).
    # Applied last so they can lift a clip the calibrated paths left low. They
    # can reach the SUSPICIOUS band but are capped below 80 (never SYNTHETIC_AI
    # from a weak temporal hint alone), and they respect a confirmed-camera or
    # watermark authenticity override.
    strict_whiteness = False
    if VIDEO_STRICT and is_video and not authenticity_override and raw_score < 80:
        fm = pwtf_metrics or {}
        flat_v = float(fm.get("spectral_flatness", 0.0)) if fm else 0.0
        ac1_v = float(fm.get("residual_ac1", 1.0)) if fm else 1.0
        # (a) Whiteness: temporally white residuals (semi-independent frames).
        if fm and flat_v >= 0.85 and ac1_v <= 0.35:
            strict_whiteness = True
            raw_score = max(raw_score, 66.0)
        # (b) Lowered pwtf gate on a mildly weakened coherence floor.
        if pwtf_val is not None and pwtf_val >= 45 and fm and fm.get("coherence_p05", 1.0) < 0.35:
            strict_whiteness = True
            raw_score = max(raw_score, 66.0)
        # Anti-false-authentic floor: any elevated temporal reading means the
        # video is at least INCONCLUSIVE, never a confident AUTHENTIC_HUMAN.
        if (
            (pwtf_val is not None and pwtf_val >= 25)
            or tr_strong
            or (fm and flat_v >= 0.80 and ac1_v <= 0.45)
        ):
            raw_score = max(raw_score, 40.0)
        raw_score = min(raw_score, 79.0)

    final_score = int(round(min(99, max(1, raw_score))))

    # Determine confidence tier
    active_count = len(available)
    if (synthid_val is not None and synthid_val >= 90) or (c2pa_val is not None and c2pa_val >= 90) or (
        metadata_val is not None and metadata_val >= 95
    ):
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
    elif final_score >= 62 and metadata_val is not None and metadata_val >= 70:
        # Metadata-escalated verdicts (64-68): a source-label provenance claim
        # is decisive evidence about the content's origin - not a borderline
        # pixel reading - so 62-68 with a >= 70 metadata vote reads SUSPICIOUS.
        # (66 UNCERTAIN on a caption that names the generator tool misled.)
        tier = "SUSPICIOUS"
    elif final_score >= 60 and metadata_val is not None and metadata_val >= 80:
        # Generator-specific detection (metadata 80+) with score 60-68:
        # even with lower fused score, the specific generator ID is strong
        # provenance evidence -> SUSPICIOUS, not UNCERTAIN.
        tier = "SUSPICIOUS"
    elif final_score >= 55:
        # HIGH-confidence agreement, a confirmed total coherence collapse, a
        # strong temporal-residual reading, or a strict-mode whiteness hit
        # (structural evidence, see above) all justify SUSPICIOUS in the 55-68
        # band; everything else is UNCERTAIN.
        tier = "SUSPICIOUS" if (
            confidence == "HIGH" or total_collapse or (TR_VOTE and tr_strong)
            or strict_whiteness
        ) else "UNCERTAIN"
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
    # rppg reasons are surfaced here too (applies/pulse_present readouts), and
    # so are the audio-track findings (docs/audio-and-lip-sync-plan.md phase
    # A0): audio is a SEPARATE axis with score None, so listing its lines here
    # reports the evidence without contributing a single point to the score -
    # audio evidence is surfaced, never silently ignored, and never a vote.
    all_reasons: List[str] = []
    for k in ["c2pa", "synthid", "metadata", "neural", "frequency", "spai", "pwtf", "temporal", "d3", "rppg", "audio"]:
        if k in layer_reasons and layer_reasons[k]:
            all_reasons.extend(layer_reasons[k])
    all_reasons.extend(coverage_reasons)

    # ---- Two-axis output: altered vs AI-artifact ----
    # Keep the legacy single-score fusion above for backward compatibility, but
    # also emit explicit axes so callers can say 'altered' and/or 'has AI
    # artifacts' instead of only a vague 'suspicious'.
    pwtf_metrics = (extra_data or {}).get("pwtf_metrics") if extra_data else None
    d3_metrics = (extra_data or {}).get("d3_metrics") if extra_data else None
    neural_submodels = (extra_data or {}).get("neural_submodels") if extra_data else None
    pf_hits = (extra_data or {}).get("pf_hits") if extra_data else None
    pf_strong = bool((extra_data or {}).get("pf_strong")) if extra_data else False
    character_match = (extra_data or {}).get("character_match") if extra_data else None

    alteration_score, alteration_reasons, alteration_detail = _local_inconsistency_score(
        pwtf_metrics=pwtf_metrics,
        neural_submodels=neural_submodels,
        pf_hits=pf_hits,
        d3_metrics=d3_metrics,
    )
    ai_artifact_score, ai_artifact_reasons, ai_artifact_detail = _ai_artifact_score(
        layers=layers,
        layer_reasons=layer_reasons,
        pwtf_metrics=pwtf_metrics,
        d3_metrics=d3_metrics,
        pf_hits=pf_hits,
        pf_strong=pf_strong,
        character_match=character_match,
        is_video=is_video,
    )

    def _axis_label(score: int) -> str:
        if score >= 80:
            return "yes"
        if score >= 60:
            return "likely"
        if score >= 40:
            return "possible"
        return "unlikely"

    alteration_label = _axis_label(alteration_score)
    ai_artifact_label = _axis_label(ai_artifact_score)

    # Derived human-readable short label that matches what you asked for.
    if alteration_label in ("yes", "likely") and ai_artifact_label in ("yes", "likely"):
        short_label = "Altered with AI artifacts"
    elif alteration_label in ("yes", "likely"):
        short_label = "Altered"
    elif ai_artifact_label in ("yes", "likely"):
        short_label = "Has AI artifacts"
    elif alteration_label == "possible" or ai_artifact_label == "possible":
        short_label = "Possibly altered or AI-affected"
    else:
        short_label = "No clear alteration or AI artifacts detected"

    if is_video and alteration_label in ("yes", "likely"):
        short_label = "Altered region detected"
    elif is_video and ai_artifact_label in ("yes", "likely") and alteration_label not in ("yes", "likely"):
        short_label = "Has AI artifacts"
    elif is_video and ai_artifact_label == "possible" and alteration_label not in ("yes", "likely", "possible"):
        short_label = "Possibly has AI artifacts"

    # Video headline label. Score and tier are untouched - this only scopes the
    # wording to the artifacts found IN the clip instead of claiming how the
    # clip was made. A temporal-family reading (which is what lifts most reels
    # into the 69+ band) proves neither origin nor coverage: a clip can carry
    # AI artifacts - an AI cover frame or thumbnail, an AI insert, AI upscaling -
    # while the filmed content is authentic. Calling that "AI-generated" accuses
    # the wrong thing, so the headline says what was actually detected and lets
    # the score/tier carry the strength.
    video_label = None
    if is_video:
        if tier == "SYNTHETIC_AI":
            video_label = "Video has strong AI artifacts"
        elif tier == "SUSPICIOUS":
            video_label = "Video has AI artifacts - needs review"
        if video_label is not None:
            # The headline and the one-line summary must agree: the axis
            # short_labels above describe only the pixel axes, so an escalated
            # temporal verdict would otherwise read "has AI artifacts" next to
            # "no clear AI artifacts detected".
            short_label = video_label

    result: Dict[str, Any] = {
        "score": final_score,
        "confidence": confidence,
        "tier": tier,
        "layers_active": list(available.keys()),
        "breakdown": {k: int(round(v)) for k, v in available.items()},
        "reasons": all_reasons,
        "alteration": {
            "label": alteration_label,
            "score": alteration_score,
            "short_label": ("Altered" if alteration_label in ("yes", "likely") else
                            ("Possible alteration" if alteration_label == "possible" else
                             "No clear alteration evidence")),
            "reasons": alteration_reasons,
            **alteration_detail,
        },
        "ai_artifact": {
            "label": ai_artifact_label,
            "score": ai_artifact_score,
            "short_label": ("Has AI artifacts" if ai_artifact_label in ("yes", "likely") else
                            ("Possible AI artifacts" if ai_artifact_label == "possible" else
                             "No clear AI-artifact evidence")),
            "reasons": ai_artifact_reasons,
            **ai_artifact_detail,
        },
        "short_label": short_label,
    }
    if video_label is not None:
        result["label"] = video_label

    if extra_data:
        result.update(extra_data)

    return result
