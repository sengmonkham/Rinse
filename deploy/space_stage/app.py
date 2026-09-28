"""
RINSE AI-media detector — Hugging Face Space entry point.

What runs here (the REAL backend, not a mock):
  - The complete forensic ensemble from server.py: SynthID probe, C2PA
    provenance, AI-metadata (captions / alt text / page context), frequency
    forensics, DetectZoo (CNNSpot) neural classifier, SPAI spectral analysis,
    pixel-forensics render/collage signatures, and the PwTF-DVD temporal
    pipeline for video - mounted verbatim as REST routes on the Space root:
        GET  /health
        POST /predict
        POST /predict/image/fast | /predict/image/deep
        POST /predict/video/deep
    Same payloads, same Bearer-token auth (set the API_KEY secret), same
    verdict shape - the Chrome extension / clients work unchanged by pointing
    at this Space's URL.

  - A compact Gradio UI (Image / Video tabs) on top of the SAME detectors for
    quick manual tests.

  - ZeroGPU hardware note: this Space runs on zero-a10g because that is the
    only compute a free account can host. RINSE is deliberately CPU-only
    (DetectZoo device="cpu", numpy forensics) - the single @spaces.GPU
    function below is a NO-OP that burns no quota and exists purely to
    satisfy the ZeroGPU runtime (at least one decorated callable required).
    See https://huggingface.co/docs/hub/spaces-sdks-gradio#zerogpu.

Serve: uvicorn app:app --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import os

import spaces  # MUST be imported before torch / any CUDA-touching import

import gradio as gr
import uvicorn
from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import server as rinse  # noqa: E402  (loads the full Flask app + all layers)

# ---------------------------------------------------------------------------
# FastAPI shell. Route order matters: Starlette matches routes in
# registration order and a "/" mount matches EVERYTHING, so the Gradio UI
# mount at /gradio_api MUST be registered before the Flask mount at "/".
# ---------------------------------------------------------------------------
fastapp = FastAPI(title="RINSE AI-media detector")
fastapp.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # the Flask app applies its own CORS config inside
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapp.get("/")
def _root_info():
    """Landing probe: 200 at the Space root with pointers to UI and API."""
    return {
        "service": "RINSE AI-media detector",
        "ui": "/gradio_api/",
        "health": "/health",
        "api": ["/predict", "/predict/image/fast", "/predict/image/deep", "/predict/video/deep"],
    }


@spaces.GPU(duration=10)
def _zerogpu_keepalive() -> int:
    """No-op ZeroGPU probe.

    The ZeroGPU runtime requires at least one @spaces.GPU-decorated function.
    RINSE never touches CUDA, so this returns immediately and allocates no
    GPU time (visitors burn no quota; the Space owner pays nothing).
    """
    return 0


# ---------------------------------------------------------------------------
# Gradio demo UI - calls the REAL forensic pipeline (rinse.*), not a stub.
# ---------------------------------------------------------------------------
def _verdict_markdown(v: dict) -> str:
    breakdown = v.get("breakdown") or {}
    lines = [
        f"### Verdict: **{v.get('tier', 'INCONCLUSIVE')}**",
        f"- Score **{v.get('score')} / 100** | Confidence **{v.get('confidence')}**",
        f"- Layers active: {', '.join(v.get('layers_active', [])) or 'none'}",
        "",
        "| layer | score |",
        "|---|---|",
    ]
    for k in sorted(breakdown):
        lines.append(f"| {k} | {breakdown[k]} |")
    reasons = v.get("reasons") or []
    if reasons:
        lines += ["", "**Top evidence**"] + [f"- {r}" for r in reasons[:6]]
    return "\n".join(lines)


def scan_image(img, progress=gr.Progress()):
    """Run the full image deep ensemble on one image."""
    if img is None:
        raise gr.Error("Upload an image first.")
    import io
    import base64 as b64

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    payload = {
        "image_base64": "data:image/png;base64," + b64.b64encode(buf.getvalue()).decode(),
        "no_cache": True,
    }
    client = rinse.app.test_client()
    resp = client.post("/predict/image/deep", json=payload)
    v = resp.get_json(force=True)
    if resp.status_code != 200 or not isinstance(v, dict) or "score" not in v:
        raise gr.Error(f"Scan failed: {str(v)[:200]}")
    return _verdict_markdown(v)


def scan_video(url: str, progress=gr.Progress()):
    """Resolve a platform/direct URL server-side and run the full video path."""
    url = (url or "").strip()
    if not url:
        raise gr.Error("Paste a video URL first (YouTube/IG/TikTok or direct .mp4).")
    client = rinse.app.test_client()
    resp = client.post(
        "/predict/video/deep",
        json={"video_url": url, "no_cache": True},
    )
    v = resp.get_json(force=True)
    if resp.status_code != 200 or not isinstance(v, dict) or "score" not in v:
        raise gr.Error(f"Scan failed: {str(v)[:200]}")
    wd = v.get("window_details") or []
    extra = ""
    if wd:
        extra = f"\n- Windows analyzed: {len(wd)}; per-window pwtf: {[w.get('pwtf_score') for w in wd]}"
    return _verdict_markdown(v) + extra


with gr.Blocks(title="RINSE - AI image & video detector") as demo:
    gr.Markdown(
        "## RINSE - AI image & video detector\n"
        "Real forensic ensemble (SynthID, C2PA, AI-metadata, frequency, "
        "DetectZoo neural, SPAI, pixel-forensics signatures, PwTF-DVD temporal). "
        "Video scans take ~10-20s per clip. The full REST API is mounted on the "
        "Space root - see the docs below the app."
    )
    with gr.Tabs():
        with gr.Tab("Image"):
            with gr.Row():
                with gr.Column():
                    img_in = gr.Image(type="pil", label="Image")
                    img_btn = gr.Button("Scan image", variant="primary")
                with gr.Column():
                    img_out = gr.Markdown(label="Verdict")
            img_btn.click(scan_image, inputs=[img_in], outputs=[img_out], api_name="scan_image")
        with gr.Tab("Video URL"):
            with gr.Row():
                with gr.Column():
                    vid_in = gr.Textbox(label="Video URL (YouTube / Instagram / TikTok / direct mp4)")
                    vid_btn = gr.Button("Scan video", variant="primary")
                with gr.Column():
                    vid_out = gr.Markdown(label="Verdict")
            vid_btn.click(scan_video, inputs=[vid_in], outputs=[vid_out], api_name="scan_video")

# UI first (specific prefix), Flask API last (catch-all root).
# a2wsgi.WSGIMiddleware adapts the WSGI Flask app to ASGI - mounting the raw
# Flask app fails at request time with "Flask.__call__() takes 3 positional
# arguments but 4 were given" (Starlette passes (scope, receive, send),
# which a WSGI app cannot accept).
app = gr.mount_gradio_app(fastapp, demo, path="/gradio_api")
app.mount("/", WSGIMiddleware(rinse.app), name="rinse-flask-api")


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or os.environ.get("GRADIO_SERVER_PORT") or 7860)
    uvicorn.run(app, host="0.0.0.0", port=port)
