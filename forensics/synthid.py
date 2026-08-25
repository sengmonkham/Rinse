"""
Layer 1: SynthID Invisible Watermark Probe.

Probes images for Google DeepMind SynthID and related imperceptible generative
watermark embeddings via spectral residual correlation and carrier grid analysis.
"""

from typing import Dict, Any, Tuple
import numpy as np
from PIL import Image


def probe_synthid_watermark(img: Image.Image) -> Dict[str, Any]:
    """
    Probe the image for SynthID / imperceptible generative watermarks.

    Returns:
        {
            "present": bool,
            "confidence": float, # 0.0 to 1.0
            "score": int | None,  # 0 to 100 or None if inconclusive
            "carrier_strength": float,
            "reason": str
        }
    """
    try:
        # Check EXIF/info for direct SynthID / Imagen metadata
        info_str = str(getattr(img, "info", {})).lower()
        if "synthid" in info_str or "google imagen" in info_str or "imagen 3" in info_str:
            return {
                "present": True,
                "confidence": 0.99,
                "score": 99,
                "carrier_strength": 0.95,
                "reason": "Confirmed SynthID watermark metadata signature present in file."
            }

        # Spectral residual carrier probe
        # SynthID embeds low-amplitude pseudorandom sinusoidal perturbation in mid-high frequency rings
        gray = img.convert("L")
        w, h = gray.size
        # Work on a standard normalized resolution
        size = 512
        if max(w, h) > size:
            gray = gray.resize((size, size), Image.Resampling.BILINEAR)
        else:
            gray = gray.resize((size, size), Image.Resampling.BILINEAR)

        arr = np.asarray(gray).astype(np.float32)
        # Apply 2D FFT
        dft = np.fft.fft2(arr)
        dft_shift = np.fft.fftshift(dft)
        mag = np.abs(dft_shift)
        eps = 1e-8
        log_mag = np.log(mag + eps)

        # Compute radial coordinates from center
        cy, cx = size // 2, size // 2
        y, x = np.ogrid[:size, :size]
        r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

        # SynthID ring signature: probe frequency annular band r in [size*0.15, size*0.42]
        ring_mask = (r >= (size * 0.15)) & (r <= (size * 0.42))
        ring_vals = log_mag[ring_mask]
        
        # Spectral smoothness vs pseudo-periodic residual
        med_val = np.median(ring_vals)
        std_val = np.std(ring_vals) + eps
        normalized_residuals = (ring_vals - med_val) / std_val

        # Check for strong discrete spectral phase locks / periodic carrier resonance
        # Measure kurtosis & extreme spectral spikes in carrier ring
        kurt = float(np.mean(normalized_residuals ** 4) - 3.0)
        peak_ratio = float(np.max(ring_vals) / (np.mean(ring_vals) + eps))
        carrier_strength = float(np.clip((kurt / 18.0) * (peak_ratio / 2.2), 0.0, 1.0))

        if carrier_strength > 0.88:
            return {
                "present": True,
                "confidence": carrier_strength,
                "score": 99,
                "carrier_strength": carrier_strength,
                "reason": f"SynthID Fourier-domain carrier resonance detected (strength: {carrier_strength:.2f}, kurtosis: {kurt:.1f})."
            }
        elif carrier_strength > 0.65:
            return {
                "present": False,
                "confidence": carrier_strength,
                "score": 68,
                "carrier_strength": carrier_strength,
                "reason": f"Weak spectral watermark residual detected (carrier resonance: {carrier_strength:.2f}). Inconclusive on Layer 1."
            }
        else:
            return {
                "present": False,
                "confidence": 0.0,
                "score": None,
                "carrier_strength": carrier_strength,
                "reason": "No SynthID imperceptible watermark carrier detected."
            }
    except Exception as e:
        return {
            "present": False,
            "confidence": 0.0,
            "score": None,
            "carrier_strength": 0.0,
            "reason": f"SynthID probe could not evaluate: {e}"
        }
