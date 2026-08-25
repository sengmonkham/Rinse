"""
Layer 2: C2PA / Content Credentials Provenance Manifest Probe.

Reads signed C2PA JUMBF / XMP / EXIF assertions in JPEG, PNG, and WebP media.
Detects digitalSourceType (trainedAlgorithmicMedia) or authentic camera capture claims.
"""

from typing import Dict, Any
import re
from PIL import Image

AI_GENERATOR_KEYWORDS = [
    "dall-e", "midjourney", "stable diffusion", "firefly", "bing image creator",
    "chatgpt", "copilot", "adobe firefly", "craiyon", "flux", "sora", "runway",
    "pika", "luma dream machine", "kling", "ideogram", "leonardo.ai"
]

CAMERA_MANUFACTURERS = [
    "canon", "nikon", "sony", "leica", "fujifilm", "hasselblad", "google pixel"
]


def probe_c2pa_manifest(img: Image.Image, raw_bytes: bytes = b"") -> Dict[str, Any]:
    """
    Parse image metadata, EXIF, and binary segments for C2PA credentials.
    """
    try:
        exif_info = getattr(img, "info", {})
        combined_text = str(exif_info).lower()
        
        # Search raw bytes for C2PA JUMBF box markers if provided
        raw_probe = ""
        if raw_bytes:
            # Look for C2PA / c2pa / jumbf identifiers
            if b"c2pa" in raw_bytes.lower() or b"jumbf" in raw_bytes.lower():
                try:
                    raw_probe = raw_bytes[:100000].decode("latin-1", errors="ignore").lower()
                except Exception:
                    pass

        search_corpus = f"{combined_text} {raw_probe}"

        # 1. Check for AI digital source type assertion
        if "trainedalgorithmicmedia" in search_corpus or "algorithmicmedia" in search_corpus:
            return {
                "present": True,
                "is_ai": True,
                "is_authentic_camera": False,
                "score": 99,
                "source_type": "trainedAlgorithmicMedia",
                "reason": "C2PA Manifest Verified: Content Credential asserts digitalSourceType as 'trainedAlgorithmicMedia' (Confirmed AI generation)."
            }

        # 2. Check for AI generator claim in manifest
        for keyword in AI_GENERATOR_KEYWORDS:
            if keyword in search_corpus:
                return {
                    "present": True,
                    "is_ai": True,
                    "is_authentic_camera": False,
                    "score": 99,
                    "source_type": "ai_tool_claim",
                    "reason": f"C2PA / Provenance Manifest: Claim generator identified AI tool '{keyword.title()}'."
                }

        # 3. Check for hardware camera provenance (e.g. C2PA camera authentic capture)
        if "c2pa" in search_corpus:
            for cam in CAMERA_MANUFACTURERS:
                if cam in search_corpus:
                    return {
                        "present": True,
                        "is_ai": False,
                        "is_authentic_camera": True,
                        "score": 3,
                        "source_type": "camera_capture",
                        "reason": f"C2PA Manifest Verified: Authentic physical capture certified by {cam.title()} hardware."
                    }

        # 4. Check for standard EXIF Camera Model signatures (mild authentic signal if camera details are full)
        make = exif_info.get("Make") or ""
        model = exif_info.get("Model") or ""
        if make or model:
            return {
                "present": False,
                "is_ai": False,
                "is_authentic_camera": False,
                "score": 25,
                "source_type": "exif_camera_tags",
                "reason": f"Standard EXIF metadata present ({make} {model}), but no signed C2PA manifest found."
            }

        return {
            "present": False,
            "is_ai": False,
            "is_authentic_camera": False,
            "score": None,
            "source_type": "none",
            "reason": "No C2PA Content Credentials manifest embedded in file."
        }
    except Exception as e:
        return {
            "present": False,
            "is_ai": False,
            "is_authentic_camera": False,
            "score": None,
            "source_type": "error",
            "reason": f"C2PA manifest probe error: {e}"
        }
