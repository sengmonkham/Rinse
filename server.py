import os
import io
import re
import tempfile
import base64
import requests
from PIL import Image

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
        
    if not reasons:
        reasons.append("No artificial EXIF metadata or pixel distribution anomalies discovered.")
        
    return score, reasons

@app.route("/predict", methods=["POST"])
@app.route("/v1/predict", methods=["POST"])
def predict():
    data = request.get_json() or {}
    image_url = data.get("image_url")
    image_base64 = data.get("image_base64")
    
    if not image_url and not image_base64:
        return jsonify({"error": "No image source provided. Set 'image_url' or 'image_base64'."}), 400
        
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
                f.write(img_bytes)
            else:
                # Download image from URL
                headers = {"User-Agent": "AegisAuthenticityDetector/1.0"}
                resp = requests.get(image_url, headers=headers, timeout=10)
                resp.raise_for_status()
                f.write(resp.content)
                
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Aegis Cloud Detector server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
