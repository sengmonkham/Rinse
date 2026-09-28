"""
RINSE Maximum-Accuracy AI Image & Video Detection Engine.
Forensic ensemble:
- Layer 1: SynthID Watermark Probe
- Layer 2: C2PA Content Credentials Manifest Probe
- Layer 3: Frequency-Domain Spectral & Wavelet Forensics
- Layer 4: Semantic Neural & ViT Patch Heatmap Classifier
- Layer 5: Spatio-Temporal Coherence Video Analyzer
- Layer 6: PwTF-DVD Pixel-wise Temporal Frequency Analyzer (ICCV 2025)
"""

from .synthid import probe_synthid_watermark
from .c2pa import probe_c2pa_manifest
from .ai_metadata import probe_ai_metadata
from .frequency import analyze_frequency_domain
from .neural import analyze_neural_and_heatmap
from .temporal import analyze_video_temporal_coherence
from .pwtf import analyze_pixel_temporal_frequency
from .voter import fuse_ensemble_verdict

__all__ = [
    "probe_synthid_watermark",
    "probe_c2pa_manifest",
    "probe_ai_metadata",
    "analyze_frequency_domain",
    "analyze_neural_and_heatmap",
    "analyze_video_temporal_coherence",
    "analyze_pixel_temporal_frequency",
    "fuse_ensemble_verdict",
]
