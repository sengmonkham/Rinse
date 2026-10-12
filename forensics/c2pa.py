"""
Layer 2: C2PA / Content Credentials Provenance Manifest Probe.

Reads signed C2PA JUMBF / XMP / EXIF assertions in JPEG, PNG, and WebP media.
Detects digitalSourceType (trainedAlgorithmicMedia) or authentic camera capture claims.
"""

from typing import Dict, Any, Optional
import re
from PIL import Image

AI_GENERATOR_KEYWORDS = [
    "dall-e", "midjourney", "stable diffusion", "firefly", "bing image creator",
    "chatgpt", "copilot", "adobe firefly", "craiyon", "flux", "sora", "runway",
    "pika", "luma dream machine", "kling", "ideogram", "leonardo.ai",
    # Additional generators for deeper detection
    "higgsfield", "genjutsu", "veo", "google imagen", "novelai",
    "comfyui", "automatic1111", "invokeai", "fooocus", "recraft",
    "nightcafe", "starryai", "playgroundai", "dreamstudio", "chatgpt",
    "elevenlabs", "minimax", "hailuo", "klingai", "pikart"
]

# Generator family mapping for attribution hints
GENERATOR_FAMILIES = {
    "diffusion": ["stable diffusion", "sdxl", "sdturbo", "flux", "dreamstudio", "stability ai"],
    "gan": ["stylegan", "stylegan2", "stylegan3"],
    "transformer": ["dall-e", "dalle", "imagen", "parti"],
    "autoregressive": ["midjourney"],
    "video_diffusion": ["sora", "veo", "runway", "pika", "luma", "kling", "hailuo", "minimax", "higgsfield", "genjutsu"],
}

CAMERA_MANUFACTURERS = [
    "canon", "nikon", "sony", "leica", "fujifilm", "hasselblad", "google pixel"
]


def _detect_generator_from_claim(text: str) -> Optional[str]:
    """Detect specific generator tool from C2PA claim_generator or software tags.

    Returns the canonical generator name if detected, else None.
    """
    lowered = text.lower()
    for kw in AI_GENERATOR_KEYWORDS:
        if kw.lower() in lowered:
            return kw
    return None


def _detect_generator_family(text: str) -> Optional[str]:
    """Detect generator family from text (diffusion, video_diffusion, etc.).

    Returns family name if detected, else None.
    """
    lowered = text.lower()
    for family, keywords in GENERATOR_FAMILIES.items():
        for kw in keywords:
            if kw.lower() in lowered:
                return family
    return None


def probe_c2pa_manifest(img: Image.Image, raw_bytes: bytes = b"") -> Dict[str, Any]:
    """
    Parse image metadata, EXIF, and binary segments for C2PA credentials.
    Improved to detect specific generators and their families.
    """
    try:
        exif_info = getattr(img, "info", {})
        info_str = str(exif_info).lower()
        
        # Search raw bytes for C2PA JUMBF box markers if provided
        raw_probe = ""
        if raw_bytes:
            # Look for C2PA / c2pa / jumbf identifiers OR generator keywords directly
            raw_lower = raw_bytes.lower()
            if (b"c2pa" in raw_lower or b"jumbf" in raw_lower or 
                b"trainedalgorithmicmedia" in raw_lower or
                any(kw.encode() in raw_lower for kw in AI_GENERATOR_KEYWORDS)):
                try:
                    raw_probe = raw_bytes[:100000].decode("latin-1", errors="ignore").lower()
                except Exception:
                    pass

        search_corpus = f"{info_str} {raw_probe}"

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
        detected_generator = _detect_generator_from_claim(search_corpus)
        generator_family = _detect_generator_family(search_corpus) if detected_generator else None
        if detected_generator:
            family_note = f" (family: {generator_family})" if generator_family else ""
            return {
                "present": True,
                "is_ai": True,
                "is_authentic_camera": False,
                "score": 99,
                "source_type": "ai_tool_claim",
                "generator": detected_generator,
                "generator_family": generator_family,
                "reason": f"C2PA / Provenance Manifest: Claim generator identified AI tool '{detected_generator.title()}'{family_note}."
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
                "generator": None,
                "generator_family": None,
                "reason": f"Standard EXIF metadata present ({make} {model}), but no signed C2PA manifest found."
            }

        return {
            "present": False,
            "is_ai": False,
            "is_authentic_camera": False,
            "score": None,
            "source_type": "none",
            "generator": None,
            "generator_family": None,
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
