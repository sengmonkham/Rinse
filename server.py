import os
import hmac
import tempfile
import base64
from urllib.parse import urlparse

import requests
from PIL import Image, ImageFilter

# numpy is optional; used only by _pixel_forensics for accelerated stats.
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False

try:
    from flask import Flask, request, jsonify
    from flask_cors import CORS
except ImportError:
    print("\n" + "="*80)
    print("WARNING: Flask and Flask-CORS are required to run this server.")
    print("Please run: pip install flask flask-cors requests pillow")
    print("="*80 + "\n")
    raise

# Try to import detectzoo
DETECTZOO_AVAILABLE = False
detector = None

try:
    from detectzoo import load_detector
    # Load image detector. 'cnnspot' (280MB) is default. Can be set to 'univfd' (1.7GB) via environment variable.
    model_name = os.environ.get("MODEL_NAME", "cnnspot")
    print(f"Loading DetectZoo '{model_name}' model (device: cpu)...")
    detector = load_detector(model_name, device="cpu")
    DETECTZOO_AVAILABLE = True
    print("DetectZoo successfully loaded!")
except Exception as e:
    print("\n" + "="*80)
    print("WARNING: DetectZoo could not be loaded or initialized.")
    print(f"Error: {e}")
    print("To install DetectZoo, run: pip install detectzoo")
    print("The server will run in fallback simulation mode for testing purposes.")
    print("="*80 + "\n")

app = Flask(__name__)
# Enable CORS for Chrome Extensions and Standalone browser previews
CORS(app, resources={r"/*": {"origins": "*"}})

# Optional bearer-token auth: set API_KEY (or BEARER_TOKEN) to require it
API_KEY = os.environ.get("API_KEY") or os.environ.get("BEARER_TOKEN") or ""
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB cap for uploaded/downloaded images


def _check_auth():
    """If an API key is configured, require a matching Bearer token."""
    if not API_KEY:
        return True
    expected = f"Bearer {API_KEY}"
    provided = request.headers.get("Authorization", "")
    return hmac.compare_digest(provided, expected)


def _dhash(img, hash_size=8):
    """64-bit difference hash (perceptual). Stable across resizes and mild recompression."""
    gray = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    px = gray.tobytes()  # mode "L": one byte per pixel, no Pillow deprecation warning
    bits = []
    for row in range(hash_size):
        base = row * (hash_size + 1)
        for col in range(hash_size):
            bits.append(1 if px[base + col] > px[base + col + 1] else 0)
    return int("".join(str(b) for b in bits), 2)


def _hamming(a, b):
    return bin(a ^ b).count("1")


# Perceptual fingerprints of famous AI-generated meme artwork (64-bit dHash).
# A match (Hamming distance <= 10 of 64 bits) means "same artwork, resized/recompressed".
# To add another known asset, compute the dhash of its canonical image and add it here.
KNOWN_AI_ARTWORK_FINGERPRINTS = {
    "tung-tung-sahur": {
        "label": "Tung Tung Tung Sahur cover art (viral AI-generated meme character)",
        "dhash": 0x64a425353458d269,
    },
    "ai-generated-receipt": {
        "label": "Viral AI-generated receipt artwork (Webflow CDN)",
        "dhash": 0x232b2b2f230f2b27,
    },
}


def _pixel_forensics(img_path):
    """Color-structure forensics for flat cel-shaded / 3D-render character art.

    AI character art (toon renders, meme art) differs drastically from camera
    photos: very few distinct colors, high saturation, low edge variance, and
    large perfectly-flat regions. Returns stats + a conservative score boost,
    or None when the analysis can't run.
    """
    if not _NUMPY_AVAILABLE:
        return None
    try:
        with Image.open(img_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            max_side = 512
            if max(w, h) > max_side:
                img = img.resize(
                    (int(w * max_side / max(w, h)), int(h * max_side / max(w, h))),
                    Image.LANCZOS,
                )
            arr = np.asarray(img).astype(np.float32)
            hh, ww, _ = arr.shape

            # 1. Unique quantized colors (4 bits per channel)
            quant = (arr.reshape(-1, 3) // 16).astype(np.uint8)
            unique_colors = int(len(np.unique(quant, axis=0)))

            # 2. Mean saturation
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
            mx = np.maximum(np.maximum(r, g), b)
            mn = np.minimum(np.minimum(r, g), b)
            sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
            sat_mean = float(sat.mean())

            # 3. Edge variance (Laplacian-like)
            edges = np.asarray(img.convert("L").filter(ImageFilter.FIND_EDGES)).astype(np.float32)
            edge_var = float(edges.var())

            # 4. Flat-region ratio (8x8 patches with std < 3)
            luma = np.asarray(img.convert("L")).astype(np.float32)
            flat = 0
            patches = 0
            step = 8
            for y in range(0, hh - step, step):
                for x in range(0, ww - step, step):
                    patches += 1
                    if luma[y:y + step, x:x + step].std() < 3.0:
                        flat += 1
            flat_ratio = flat / max(patches, 1)

            # 5. Document-render signature (AI-generated receipts, tickets, documents)
            # Dense text images are gated out of the photo/art heuristics above. AI
            # generators render them with two tells a camera can't reproduce:
            #   - a perfectly smooth, texture-free background around the page
            #     (real photos/scans always show grain, shadows or a cluttered scene)
            #   - soft, anti-aliased type (real print has crisp high-contrast edges)
            edge_density = float((edges > 60).mean())
            strong_edges = float((edges > 120).mean())
            medium_edges = float(((edges > 40) & (edges <= 120)).mean())
            edge_ratio = strong_edges / max(medium_edges, 1e-6)

            bw = max(2, ww // 20)
            bh = max(2, hh // 20)
            frame = np.concatenate(
                [luma[:bh].ravel(), luma[-bh:].ravel(), luma[:, :bw].ravel(), luma[:, -bw:].ravel()]
            )
            border_std = float(frame.std())

            doc_boost = 0
            doc_reason = None
            if (
                edge_density > 0.06
                and flat_ratio < 0.35
                and border_std < 20.0
                and edge_ratio < 1.1
            ):
                doc_boost = 75
                doc_reason = (
                    f"Synthetic document render signature: text-dense image with an "
                    f"unnaturally smooth background (border variance {border_std:.1f}) "
                    f"and soft anti-aliased type (strong/medium edge ratio {edge_ratio:.2f}). "
                    f"AI generators render receipts/documents with perfectly uniform paper "
                    f"and smooth glyphs; camera photos and scans show background texture "
                    f"and crisp print."
                )

            # Synthetic flat-render signature (cel-shaded / 3D-render character art).
            # All four features are required gates: AI toon art has few colors, vivid
            # saturation, very low edge variance, and little flat texture. Each gate
            # was calibrated against real photos - a dark-table photo of a receipt
            # (saturation 0.57, edge variance 685) is excluded by the edge-variance
            # gate while genuine flat renders (edge variance < 600) still pass.
            boost = 0
            reason = None
            if (
                sat_mean > 0.50
                and unique_colors < 700
                and edge_var < 600
                and flat_ratio < 0.5
            ):
                boost = 75
                reason = (
                    f"Synthetic render signature: flat cel-shaded palette "
                    f"({unique_colors} distinct colors, saturation {sat_mean:.2f}, "
                    f"low edge variance {edge_var:.0f}, {flat_ratio * 100:.0f}% flat regions). "
                    f"Camera photos rarely show this color profile."
                )

            # Known-AI-artwork fingerprint match
            match_label = None
            img_dhash = _dhash(img)
            for entry in KNOWN_AI_ARTWORK_FINGERPRINTS.values():
                if _hamming(img_dhash, entry["dhash"]) <= 10:
                    match_label = entry["label"]
                    break

            return {
                "unique_colors": unique_colors,
                "sat_mean": sat_mean,
                "edge_var": edge_var,
                "flat_ratio": flat_ratio,
                "boost": boost,
                "reason": reason,
                "doc_boost": doc_boost,
                "doc_reason": doc_reason,
                "match_label": match_label,
            }
    except Exception as e:
        print(f"Pixel forensics unavailable: {e}")
        return None


def analyze_image_heuristics(img_path):
    """
    Fallback local metadata and noise heuristic evaluator.
    Analyzes EXIF/metadata strings and basic structural statistics.
    """
    score = 12
    reasons = []
    
    try:
        with Image.open(img_path) as img:
            # Check image format & basic specs
            width, height = img.size
            
            # Check EXIF metadata for common generator keys
            exif_data = img.info
            exif_str = str(exif_data).lower()
            
            ai_tags = [
                ("stable diffusion", "Stable Diffusion generation parameters"),
                ("midjourney", "Midjourney prompt tags"),
                ("dall-e", "DALL-E metadata footprint"),
                ("novelai", "NovelAI generation tags"),
                ("civitai", "CivitAI metadata marker"),
                ("adobe firefly", "Adobe Firefly creator signature"),
                ("parameters", "PNG generative parameter chunks")
            ]
            
            for tag, label in ai_tags:
                if tag in exif_str:
                    score = 98
                    reasons.append(f"Heuristic Signature Match: Found '{tag}' in EXIF metadata ({label})")
            
            # Basic structural heuristic (unusually perfect or extreme aspect ratios / sizes)
            if width % 64 == 0 and height % 64 == 0:
                # Many generators output sizes divisible by 64
                if score < 90:
                    score += 15
                    reasons.append("Structural signature: Image dimensions match neural generation grid blocks (divisible by 64)")
            
    except Exception as e:
        reasons.append(f"EXIF analysis incomplete: {e}")

    # Pixel-structure forensics: flat render + document render signatures + known AI artwork fingerprints
    forensics = _pixel_forensics(img_path)
    if forensics:
        if forensics["boost"]:
            score = max(score, forensics["boost"])
            reasons.append(forensics["reason"])
        if forensics["doc_boost"]:
            score = max(score, forensics["doc_boost"])
            reasons.append(forensics["doc_reason"])
        if forensics["match_label"]:
            score = 99
            reasons.append(f"Perceptual fingerprint match: {forensics['match_label']}")
        
    if not reasons:
        reasons.append("No artificial EXIF metadata or pixel distribution anomalies discovered.")
        
    return score, reasons

@app.route("/predict", methods=["POST"])
@app.route("/v1/predict", methods=["POST"])
def predict():
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401

    data = request.get_json() or {}
    image_url = data.get("image_url")
    image_base64 = data.get("image_base64")
    
    if not image_url and not image_base64:
        return jsonify({"error": "No image source provided. Set 'image_url' or 'image_base64'."}), 400

    # Reject oversized base64 payloads before decoding
    if image_base64 and len(image_base64) > MAX_IMAGE_BYTES * 2:
        return jsonify({"error": "Image payload too large."}), 413
        
    temp_file = None
    
    try:
        # Create a temporary file to store the image for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            temp_file = f.name
            
            if image_base64:
                # Handle base64 encoded image
                # Strip metadata header if present (e.g. data:image/png;base64,)
                if "," in image_base64:
                    image_base64 = image_base64.split(",")[1]
                img_bytes = base64.b64decode(image_base64)
                if len(img_bytes) > MAX_IMAGE_BYTES:
                    return jsonify({"error": "Image payload too large."}), 413
                f.write(img_bytes)
            else:
                # Only fetch http(s) sources (avoid internal-network / file targets)
                parsed = urlparse(image_url)
                if parsed.scheme not in ("http", "https"):
                    return jsonify({"error": "Invalid image URL: only http(s) sources are allowed."}), 400
                # Download image from URL with a size cap
                headers = {"User-Agent": "RINSEAuthenticityDetector/1.0"}
                resp = requests.get(image_url, headers=headers, timeout=15, stream=True)
                resp.raise_for_status()
                total = 0
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        resp.close()
                        return jsonify({"error": "Image download too large."}), 413
                    f.write(chunk)
                
        # Perform image AI detection
        if DETECTZOO_AVAILABLE and detector is not None:
            print(f"Running DetectZoo prediction on file: {temp_file}")
            result = detector.predict(temp_file)
            
            # Extract score from DetectZoo result
            # DetectZoo predict returns a standardized DetectionResult dataclass
            score = 50  # Default fallback
            if hasattr(result, "score"):
                # Typically score is normalized between 0-100 or 0-1
                score = result.score
                if score <= 1.0:
                    score = int(score * 100)
            elif hasattr(result, "probability"):
                prob = result.probability
                score = int(prob * 100) if prob <= 1.0 else int(prob)
            elif isinstance(result, dict) and "score" in result:
                score = result["score"]
                if score <= 1.0:
                    score = int(score * 100)
            elif isinstance(result, (int, float)):
                score = int(result * 100) if result <= 1.0 else int(result)
            
            reasons = [
                f"DetectZoo Model classification score: {score}% confidence",
                f"Evaluation model used: '{detector.__class__.__name__}'",
                "Anomaly mapping suggests synthetic pixel grid generation." if score >= 60 else "Pixel distribution looks authentic to human camera capture."
            ]

            # Supplement weak model verdicts with pixel-structure forensics (skip when the model is already confident)
            forensics = _pixel_forensics(temp_file) if score < 80 else None
            if forensics:
                if forensics["boost"] and score < forensics["boost"]:
                    score = forensics["boost"]
                    reasons.append(forensics["reason"])
                if forensics["doc_boost"] and score < forensics["doc_boost"]:
                    score = forensics["doc_boost"]
                    reasons.append(forensics["doc_reason"])
                if forensics["match_label"]:
                    score = 99
                    reasons.append(f"Perceptual fingerprint match: {forensics['match_label']}")
        else:
            # Fall back to simulated heuristic metrics
            print("DetectZoo offline: Running heuristic classifier...")
            score, reasons = analyze_image_heuristics(temp_file)
            reasons.append("API Server note: Running in simulation mode because PyTorch/DetectZoo is offline.")
            
        return jsonify({
            "score": min(99, max(1, score)),
            "reasons": reasons
        })
        
    except Exception as e:
        print(f"Error handling request: {e}")
        return jsonify({
            "score": 50,
            "reasons": [f"Error scanning image via Python server: {str(e)}", "Please check server console outputs."]
        }), 500
        
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# StoryScope: narrative-feature AI fiction detection
#
# Implements the detection pipeline from Russell et al. (2026),
# "StoryScope: Investigating idiosyncrasies in AI fiction" (arXiv:2604.03136):
# 304 discourse-level narrative features are extracted from the story and
# classified by an XGBoost model trained on the paper's released feature
# matrix (61,575 stories). The classifier runs through a dependency-free
# pure-Python scorer.
#
# Two extraction engines (STORYSCOPE_MODE, or per-request "mode" field):
#
#   heuristic (default): pure rule-based analysis of the text. No API key,
#       no network - runs in milliseconds. Slightly lower accuracy.
#   llm: the paper's original pipeline - an LLM annotates the story (10
#       per-dimension calls). Requires an API key.
#
# Server-side config (environment variables):
#   STORYSCOPE_MODE          heuristic (default) | llm
#   STORYSCOPE_LLM_PROVIDER  openai (default) | anthropic | gemini   (llm mode)
#   STORYSCOPE_LLM_MODEL     model id (provider default if unset)    (llm mode)
#   STORYSCOPE_LLM_API_KEY   falls back to OPENAI/ANTHROPIC/GOOGLE key (llm mode)
#   STORYSCOPE_LLM_BASE_URL  OpenAI-compatible base URL (llm mode)
#   STORYSCOPE_MAX_CHARS     optional story truncation (default 280000)

STORYSCOPE_AVAILABLE = False
STORYSCOPE_ERROR = None
try:
    from storyscope.detect import detect as storyscope_detect
    from storyscope.llm import get_config as storyscope_llm_config
    STORYSCOPE_AVAILABLE = True
except Exception as e:  # noqa: BLE001
    STORYSCOPE_ERROR = str(e)


def _storyscope_mode(request_data: dict) -> str:
    """Resolve extraction engine: per-request 'mode', else STORYSCOPE_MODE env."""
    mode = (request_data.get("mode") or os.environ.get("STORYSCOPE_MODE", "heuristic")).lower().strip()
    return mode if mode in ("heuristic", "llm") else "heuristic"


def _storyscope_ready(mode: str):
    """Return (ok, error_message). Heuristic mode needs only the package;
    llm mode additionally requires an LLM API key."""
    if not STORYSCOPE_AVAILABLE:
        return False, f"StoryScope module unavailable: {STORYSCOPE_ERROR}"
    if mode == "llm":
        try:
            storyscope_llm_config()
            return True, ""
        except Exception as e:  # noqa: BLE001
            return False, str(e)
    return True, ""


@app.route("/predict/storyscope", methods=["POST"])
def predict_storyscope():
    """AI-fiction detection via the StoryScope narrative-feature pipeline.

    Default engine is the offline rule-based extractor (no API key needed).
    Pass {"mode": "llm"} (or set STORYSCOPE_MODE=llm) for the paper's LLM
    annotation pipeline.
    """
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401

    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text provided. Send JSON body: {\"text\": \"...\"}"}), 400

    mode = _storyscope_mode(data)
    ok, err = _storyscope_ready(mode)
    if not ok:
        return jsonify({
            "error": err,
            "hint": "Heuristic mode needs no configuration. For LLM mode set "
                    "STORYSCOPE_LLM_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY / "
                    "GOOGLE_API_KEY) and STORYSCOPE_LLM_PROVIDER on the server."
        }), 503

    try:
        max_chars = data.get("max_chars") or int(os.environ.get("STORYSCOPE_MAX_CHARS", "280000"))
        result = storyscope_detect(text, max_chars=int(max_chars), mode=mode)
        print(f"StoryScope[{mode}]: text={len(text)} chars -> score={result['score']} "
              f"({result['label']}), features={result['features_extracted']}/{result['features_total']}")
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:  # noqa: BLE001
        print(f"StoryScope error: {e}")
        return jsonify({"error": f"StoryScope analysis failed: {e}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting RINSE Cloud Detector server on port {port}...")
    if API_KEY:
        print("Bearer-token authentication is enabled (API_KEY is set).")
    if STORYSCOPE_AVAILABLE:
        mode = os.environ.get("STORYSCOPE_MODE", "heuristic")
        print(f"StoryScope narrative detector loaded (text AI-detection endpoint: "
              f"/predict/storyscope, engine: {mode}).")
        if mode == "llm":
            print("  LLM feature extraction requires STORYSCOPE_LLM_API_KEY (see README).")
        else:
            print("  Offline rule-based feature extraction - no API key needed.")
    app.run(host="0.0.0.0", port=port, debug=False)
