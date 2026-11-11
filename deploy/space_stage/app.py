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

Serve: python app.py

Why Server mode: a bare FastAPI app run with `uvicorn app:app` starts fine but
is killed by the ZeroGPU runtime, which only recognises an app that comes up
through Gradio's own launch path (`@spaces.GPU` detection). `gr.Server` is
Gradio's FastAPI subclass whose `.launch()` enters that path, so the Flask API,
the mounted UI and the keepalive all live on one Gradio-launched ASGI app.
"""

from __future__ import annotations

import os
import re
import time

import spaces  # MUST be imported before torch / any CUDA-touching import

import gradio as gr
from a2wsgi import WSGIMiddleware
from fastapi.middleware.cors import CORSMiddleware

import server as rinse  # noqa: E402  (loads the full Flask app + all layers)

# ---------------------------------------------------------------------------
# FastAPI shell. Route order matters: Starlette matches routes in
# registration order and a "/" mount matches EVERYTHING, so the Gradio UI
# UI mount (a specific prefix) MUST be registered before the Flask catch-all at
# "/". The UI lives at /ui because /gradio_api belongs to Gradio itself in
# Server mode (its launch readiness probe hits /gradio_api/startup-events).
# ---------------------------------------------------------------------------
# gr.Server (not FastAPI) so .launch() below goes through Gradio's launch path.
# Only these sites may call the API from a browser; loopback stays for local
# development. server.py enforces the same list inside the Flask app - this
# copy exists because the ASGI shell answers preflights before Flask is reached.
ALLOWED_ORIGINS = [
    "https://getrinse.tech",
    "https://app.getrinse.tech",
]
ALLOWED_ORIGIN_REGEX = r"^http://(?:localhost|127\.0\.0\.1)(?::\d+)?$"
_ALLOWED_ORIGIN_RE = re.compile(ALLOWED_ORIGIN_REGEX)


class SiteCORS:
    """Outermost CORS gate.

    Gradio installs its own CustomCORSMiddleware, which treats any non-localhost
    host as trusted and therefore echoes *any* Origin back with
    ``Access-Control-Allow-Origin``. That made this Space advertise itself as
    open to every website (its preflight answered 200 for arbitrary origins)
    even though the Flask gate inside then rejected the request. This wrapper
    runs outside Gradio's stack: unknown origins get no CORS grant at all and
    their preflights are refused, while the allowlisted sites get their own
    origin echoed back.
    """

    def __init__(self, app):
        self.app = app

    @staticmethod
    def allowed(origin: str) -> bool:
        return origin in ALLOWED_ORIGINS or bool(
            _ALLOWED_ORIGIN_RE.match(origin or "")
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope["headers"]
        }
        origin = headers.get("origin", "")

        if not origin:
            await self.app(scope, receive, send)
            return

        if not self.allowed(origin):
            preflight = (
                scope["method"] == "OPTIONS"
                and "access-control-request-method" in headers
            )
            if preflight:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [(b"content-length", b"0")],
                    }
                )
                await send({"type": "http.response.body", "body": b""})
                return

            async def _strip(message):
                # Drop the grant Gradio's middleware added; the body (usually
                # Flask's 403) still reaches the caller, it just cannot be read
                # cross-origin.
                if message["type"] == "http.response.start":
                    message["headers"] = [
                        (k, v)
                        for k, v in message.get("headers", [])
                        if not k.decode("latin-1").lower().startswith("access-control-")
                    ]
                await send(message)

            await self.app(scope, receive, _strip)
            return

        async def _grant(message):
            if message["type"] == "http.response.start":
                kept = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.decode("latin-1").lower()
                    not in ("access-control-allow-origin", "access-control-allow-credentials")
                ]
                kept.append((b"access-control-allow-origin", origin.encode("latin-1")))
                kept.append((b"vary", b"Origin"))
                message["headers"] = kept
            await send(message)

        await self.app(scope, receive, _grant)


class GuardedServer(gr.Server):
    """gr.Server whose entire ASGI stack sits behind SiteCORS.

    The stack is wrapped on the first request instead of after launch(), so the
    guard applies however the runtime starts the app - the Space's Gradio hot
    reload path does not necessarily run this module's __main__ block, and a
    post-launch assignment was silently skipped there.
    """

    _cors_guarded = False

    async def __call__(self, scope, receive, send):
        if not self._cors_guarded:
            stack = self.middleware_stack
            if stack is None:
                stack = self.build_middleware_stack()
            self.middleware_stack = stack = SiteCORS(stack)
            self._cors_guarded = True
            print(
                "SiteCORS guard active - allowed origins:",
                ", ".join(ALLOWED_ORIGINS),
                flush=True,
            )
        await self.middleware_stack(scope, receive, send)


fastapp = GuardedServer(title="RINSE AI-media detector")
fastapp.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@fastapp.get("/")
def _root_info():
    """Landing probe: 200 at the Space root with pointers to UI and API."""
    return {
        "service": "RINSE AI-media detector",
        "cors_guard": "sitecors-v1",
        "ui": "/ui/",
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

# Demo UI on its own prefix (the Flask API is mounted at "/" later, in the
# __main__ block, once Gradio's own routes exist).
# ssr_mode=False is REQUIRED on the Hub. The Space runtime sets
# GRADIO_SSR_MODE=true, and mount_gradio_app then starts a Node SSR server on
# port 7860 (gradio 6 starts it with server_port=7860 when ssr_mode resolves
# true) *before* uvicorn binds anything, so the app dies at boot with
# "[Errno 98] error while attempting to bind on address ('0.0.0.0', 7860):
# address already in use". The demo UI is a couple of Markdown panels - SSR buys
# nothing here - so pin it off rather than depend on the runtime env.
app = gr.mount_gradio_app(fastapp, demo, path="/ui", ssr_mode=False)
if __name__ == "__main__":
    port = int(os.environ.get("PORT") or os.environ.get("GRADIO_SERVER_PORT") or 7860)

    # ORDER MATTERS. launch() registers Gradio's own routes (/gradio_api/...)
    # on this app and THEN probes /gradio_api/startup-events. A catch-all
    # Mount("/") registered before it would swallow those routes (404), and SSR
    # would start a Node server on this same port before uvicorn binds it
    # (GRADIO_SSR_MODE=true is what the Space exports).
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        ssr_mode=False,
        prevent_thread_lock=True,
    )

    # Now that Gradio's routes exist, put the Flask API on the root path.
    # a2wsgi.WSGIMiddleware adapts WSGI to ASGI - mounting the Flask app raw
    # fails with "Flask.__call__() takes 3 positional arguments but 4 were given".
    app.mount("/", WSGIMiddleware(rinse.app), name="rinse-flask-api")

    # The uvicorn thread is non-daemon-blocking; keep the process alive.
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
