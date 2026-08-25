"""
RINSE Maximum-Accuracy AI Image & Video Detection Engine.
5-Layer Forensic Ensemble:
- Layer 1: SynthID Watermark Probe
- Layer 2: C2PA Content Credentials Manifest Probe
- Layer 3: Frequency-Domain Spectral & Wavelet Forensics
- Layer 4: Semantic Neural & ViT Patch Heatmap Classifier
- Layer 5: Spatio-Temporal Coherence Video Analyzer
"""

from .synthid import probe_synthid_watermark
from .c2pa import probe_c2pa_manifest
from .frequency import analyze_frequency_domain
from .neural import analyze_neural_and_heatmap
from .temporal import analyze_video_temporal_coherence
from .voter import fuse_ensemble_verdict

__all__ = [
    "probe_synthid_watermark",
    "probe_c2pa_manifest",
    "analyze_frequency_domain",
    "analyze_neural_and_heatmap",
    "analyze_video_temporal_coherence",
    "fuse_ensemble_verdict",
]
