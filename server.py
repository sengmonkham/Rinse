import os
import io
import json
import hashlib
import hmac
import time
import shutil
import tempfile
import subprocess
import base64
import atexit
import queue
import threading
from urllib.parse import urlparse

import numpy as np
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
    from flask import Flask, request, jsonify, Response
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

# Only the RINSE web app and this machine may call the API. Browser requests
# carry an Origin/Referer; the site's server-side /api/scan proxy has neither,
# so it is allowed only with the bearer token. /health stays public so
# platform probes and the web warm-up ping can reach a sleeping Space.
ALLOWED_WEB_HOSTS = {
    "getrinse.tech",
    "app.getrinse.tech",
}
ALLOWED_ORIGIN_PATTERNS = [
    r"https?://(?:app\.)?getrinse\.tech(?::\d+)?",
    r"http://localhost(?::\d+)?",
    r"http://127\.0\.0\.1(?::\d+)?",
]
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGIN_PATTERNS}})


def _origin_host(value: str) -> str:
    try:
        return (urlparse(value).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


@app.before_request
def _restrict_clients():
    """Deny browsers and clients that are not the RINSE site or this machine."""
    if request.path in ("/health", "/v1/health"):
        return None

    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if origin:
        if _origin_host(origin) in ALLOWED_WEB_HOSTS:
            return None
        return jsonify({"error": "Forbidden origin."}), 403

    # No browser origin: local development, or an authenticated server-side
    # call from the site. A proxied request (X-Forwarded-For present) never
    # counts as local, even if the platform's proxy connects over loopback.
    remote = (request.remote_addr or "").strip()
    is_local = (
        not request.headers.get("X-Forwarded-For")
        and (remote in ("127.0.0.1", "::1") or remote.startswith("127."))
    )
    if is_local:
        return None
    if _check_auth():
        return None
    return jsonify({"error": "Forbidden: allowed origin or bearer token required."}), 403

# Optional bearer-token auth: set API_KEY (or BEARER_TOKEN) to require it
API_KEY = os.environ.get("API_KEY") or os.environ.get("BEARER_TOKEN") or ""
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB cap for uploaded/downloaded images
MAX_VIDEO_BYTES = 150 * 1024 * 1024  # 150 MB cap for uploaded/downloaded videos
MAX_VIDEO_FRAMES = 32               # contiguous frames per analyzed shot window

# ---------------------------------------------------------------------------
# Shot-aware video sampling
#
# The temporal layers (PwTF-DVD, temporal coherence) require CONTIGUOUS frames
# at (near) native frame rate. Uniformly-spaced samples stretched across a
# whole reel alias real motion into the high temporal bins and span scene cuts
# - calibrated on Instagram reels, that fabricated HIGHER temporal-artifact
# readings on a real clip than on a generated one (see forensics/temporal.py).
# So we decode at native fps, split the clip into camera shots, and analyze a
# contiguous window inside the most content-rich shot.
# ---------------------------------------------------------------------------

def _detect_shot_boundaries(frames_bgr, max_probe=600):
    """Detect hard cuts via mean absolute grayscale difference on downscaled
    frames. Returns a list of (start, end) index ranges per shot, keeping only
    shots with >= 32 frames (the minimum analyzable window)."""
    import cv2 as cv
    cuts = [0]
    prev = None
    step = max(1, len(frames_bgr) // max_probe)
    for idx in range(0, len(frames_bgr), step):
        small = cv.resize(frames_bgr[idx], (64, 64))
        g = cv.cvtColor(small, cv.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        if prev is not None and float(np.mean(np.abs(g - prev))) > 0.16:
            cuts.append(idx)
        prev = g
    shots = []
    for a, b in zip(cuts, cuts[1:] + [len(frames_bgr)]):
        if b - a >= MAX_VIDEO_FRAMES:
            shots.append((a, b))
    return shots or ([(0, len(frames_bgr))] if len(frames_bgr) >= MAX_VIDEO_FRAMES else [])


# ---------------------------------------------------------------------------
# Temporal coverage sweep (2026-10-16)
#
# The primary analysis follows the calibrated shot-aware rule: one contiguous
# window inside the richest shot, plus the strongest-pwtf shot's window. That
# rule assumes the artifact is present in the shot we picked - and it can be
# wrong: measured on two known-AI reels that the detector read as AUTHENTIC,
# the artifacts were real and the EXISTING rules already fire on them, in
# windows the pipeline never looked at (a 9 s single-shot reel collapses its
# coherence floor in 5 of its 8 windows while the one window analyzed read a
# healthy p05 = 0.65).
#
# The sweep closes that blind spot: it tiles the clip into consecutive windows
# (bounded frame range and window count) and measures how much of the clip
# carries the temporal artifact. It deliberately does NOT feed the escalation
# paths the primary window drives - an isolated collapsed window is normal on
# real footage (measured: 2 of 18 windows on a real clip, 1 of 7 on another) -
# so only REPEATED convergence across the sweep escalates (see voter.py).
# Streaming: one tile is held in memory at a time. Never raises.
# Cost bounded deliberately: the sweep is temporal work on top of the primary
# analysis, and the residual probe runs at full resolution. Measured worst case
# on a 720x1280 15 s reel: ~13 tiles added ~40 s to a ~25 s scan. The defaults
# (<= 8 tiles over the first 384 frames = 12.8 s at 30 fps) keep every clip in
# the calibration set correctly classified while roughly halving that cost; both
# are env-overridable for a server that wants finer coverage.
_COVERAGE_MAX_FRAMES = int(os.environ.get("VIDEO_COVERAGE_MAX_FRAMES", "384"))
_COVERAGE_MAX_WINDOWS = int(os.environ.get("VIDEO_COVERAGE_MAX_WINDOWS", "8"))
_COVERAGE_COLLAPSE_P05 = 0.25   # same collapse threshold the pwtf escalation uses
_COVERAGE_TR_MIN = 60           # temporal_residual fire threshold
# A p05 this deep is the 'total collapse' the voter treats as decisive when it
# happens once in the analyzed window; repeated occurrences across the sweep are
# scored by voter.py (see its _COVERAGE_DEEP_P05 note).
_COVERAGE_DEEP_P05 = 0.10
# Residual-white-fraction floor above which a temporal-residual fire is the
# synthetic-whiteness signature (authentic reels measured <= 0.42).
_COVERAGE_WHITE_MIN = 0.55


def _score_coverage_tile(frames, tr_mod):
    """Score one sweep tile with the SAME layers/thresholds the verdict uses."""
    s_pwtf = analyze_pixel_temporal_frequency(frames)
    pm = s_pwtf.get("metrics") or {}
    p05 = pm.get("coherence_p05")
    pwtf_score = s_pwtf.get("score")
    s_tr = tr_mod.analyze_temporal_residual(frames) if tr_mod._NP_AVAILABLE else {}
    tr_score = s_tr.get("score")
    tr_metrics = s_tr.get("metrics") or {}
    white = tr_metrics.get("residual_white_frac")
    # Residual energy and hot share are reported so the voter can tell FLICKER
    # (noise-like residual with a mostly-quiet frame) from MOTION (residual
    # covering nearly the whole frame). Without them the voter only saw
    # whiteness, which real fast motion produces too.
    energy = tr_metrics.get("residual_energy_mean")
    hot = tr_metrics.get("residual_hot_frac")
    collapse = bool(
        pwtf_score is not None and pwtf_score >= 60
        and p05 is not None and p05 < _COVERAGE_COLLAPSE_P05
    )
    tr_fire = bool(tr_score is not None and tr_score >= _COVERAGE_TR_MIN)
    return {
        "pwtf_score": pwtf_score,
        "p05": p05,
        "tr_score": tr_score,
        "white": white,
        "energy": energy,
        "hot": hot,
        "collapse": collapse,
        # Deeper than the escalation's 0.25 collapse band - voter.py scores
        # repetition of this one (see _COVERAGE_DEEP_P05).
        "deep_collapse": bool(
            pwtf_score is not None and pwtf_score >= 60
            and p05 is not None and p05 < _COVERAGE_DEEP_P05
        ),
        "tr_fire": tr_fire,
        "flagged": bool(collapse or tr_fire),
    }


def _temporal_coverage_sweep(video_bytes, skip_starts=()):
    """Tile the clip into consecutive windows and count how many show temporal
    generation evidence (coherence collapse or a temporal-residual fire).

    Returns a compact aggregate + per-window records, or {} when the sweep
    cannot run (no decoder, no bytes). Never raises into the verdict path.
    """
    try:
        import cv2 as cv
        from forensics import temporal_residual as tr_mod
    except Exception:  # noqa: BLE001
        return {}
    if not video_bytes:
        return {}

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp = f.name
        cap = cv.VideoCapture(tmp)
        if not cap.isOpened():
            return {}

        # Tile starts across the bounded range, thinned evenly to the window cap
        # and skipping tiles that overlap the primary analysis windows.
        tiles = [
            s for s in range(0, max(0, _COVERAGE_MAX_FRAMES - MAX_VIDEO_FRAMES + 1), MAX_VIDEO_FRAMES)
            if all(abs(s - int(p)) >= MAX_VIDEO_FRAMES // 2 for p in skip_starts)
        ]
        if len(tiles) > _COVERAGE_MAX_WINDOWS > 1:
            step = (len(tiles) - 1) / (_COVERAGE_MAX_WINDOWS - 1)
            tiles = sorted({tiles[int(round(i * step))] for i in range(_COVERAGE_MAX_WINDOWS)})
        if not tiles:
            return {}

        records = []
        idx = 0
        for start in tiles:
            while idx < start:
                if not cap.grab():
                    break
                idx += 1
            if idx < start:
                break  # clip ended early
            buf = []
            while idx < start + MAX_VIDEO_FRAMES:
                if not cap.grab():
                    break
                got, frame = cap.retrieve()
                idx += 1
                if got and frame is not None:
                    buf.append(Image.fromarray(cv.cvtColor(frame, cv.COLOR_BGR2RGB)))
            if len(buf) >= MAX_VIDEO_FRAMES // 2:
                rec = _score_coverage_tile(buf, tr_mod)
                records.append({"start": start, **rec})
        cap.release()

        if not records:
            return {}
        flagged = sum(1 for r in records if r["flagged"])
        return {
            "frames_tiled": min(_COVERAGE_MAX_FRAMES, idx),
            "analyzed": len(records),
            "flagged": flagged,
            "collapse_windows": sum(1 for r in records if r["collapse"]),
            "deep_collapse_windows": sum(1 for r in records if r["deep_collapse"]),
            "tr_windows": sum(1 for r in records if r["tr_fire"]),
            "white_windows": sum(
                1 for r in records
                if r["tr_fire"] and r.get("white") is not None
                and float(r["white"]) >= _COVERAGE_WHITE_MIN
            ),
            "flagged_frac": round(flagged / len(records), 3),
            # Clip-level residual means (see _score_coverage_tile): the voter's
            # sustained-flicker rule needs the average, not one window.
            "white_mean": round(
                sum(float(r["white"]) for r in records if r.get("white") is not None)
                / max(1, sum(1 for r in records if r.get("white") is not None)), 4
            ) if any(r.get("white") is not None for r in records) else None,
            "hot_mean": round(
                sum(float(r["hot"]) for r in records if r.get("hot") is not None)
                / max(1, sum(1 for r in records if r.get("hot") is not None)), 4
            ) if any(r.get("hot") is not None for r in records) else None,
            "windows": records,
        }
    except Exception as e:  # noqa: BLE001
        print(f"Temporal coverage sweep failed: {e}")
        return {}
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _extract_video_shot_windows(video_bytes, max_window=MAX_VIDEO_FRAMES, max_windows=3):
    """Decode the video and extract up to `max_windows` CONTIGUOUS native-frame-
    rate windows (each `max_window` frames) from the most content-rich shots.

    Memory-safe: the decoder passes each grabbed frame straight to the shot
    detector (or the current window builder) and drops it immediately, so peak
    memory stays at O(active windows), not O(whole video).

    Returns (windows, frame_interval_seconds, info_dict); windows is a list of
    frame lists, or ([], None, error_dict) when decoding fails. Requires
    OpenCV - the only backend that can grab dense contiguous native-rate
    frames, which the temporal layers need.
    """
    try:
        import cv2 as cv
    except ImportError:
        return [], None, {
            "error": "Video temporal analysis requires opencv-python-headless, which is not installed on this server.",
            "hint": "Install one with: pip install opencv-python-headless"
        }

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp = f.name
        cap = cv.VideoCapture(tmp)
        if not cap.isOpened():
            return [], None, {"error": "Could not open the video file for decoding."}
        native_fps = cap.get(cv.CAP_PROP_FPS) or 0.0
        if not native_fps or native_fps <= 0 or native_fps > 240:
            native_fps = 30.0
        frame_interval = 1.0 / native_fps
        
        # Limit total frames to prevent memory issues with very long videos
        max_total_frames = 300  # Analyze at most 300 frames (~10 sec at 30fps)

        # Pass 1: stream-grab every frame, remember only 64x64 thumbnails for
        # shot-boundary detection (O(thumbnails) memory).
        thumbs = []
        total_frames = 0
        frame_limit = min(max_total_frames, 600)  # At most 600 thumbnails or frame limit
        while True:
            ok = cap.grab()
            if not ok:
                break
            total_frames += 1
            if len(thumbs) < frame_limit:
                got, frame = cap.retrieve()
                if got and frame is not None:
                    thumbs.append(cv.resize(frame, (64, 64)))
        cap.release()
        if total_frames < max_window:
            return [], None, {"error": "Video has fewer decodable frames than the minimum analysis window."}

        # Shot boundaries from the thumbnail stream.
        cuts = [0]
        prev = None
        for i, small in enumerate(thumbs):
            g = cv.cvtColor(small, cv.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            if prev is not None and float(np.mean(np.abs(g - prev))) > 0.16:
                cuts.append(i)
            prev = g
        shots = []
        for a, b in zip(cuts, cuts[1:] + [total_frames]):
            if b - a >= max_window:
                shots.append((a, b))
        if not shots:
            shots = [(0, total_frames)]
        shots.sort(key=lambda s: s[1] - s[0], reverse=True)

        # Windows: start 20% into each of the top shots (skips fade-ins),
        # deduplicated so heavily-overlapping windows are not re-analyzed.
        planned = []
        for a, b in shots:
            start = a + min(int((b - a) * 0.2), b - a - max_window)
            if all(abs(start - p0) >= max_window // 2 for p0, _ in planned):
                planned.append((start, a))
            if len(planned) >= max_windows:
                break

        # Pass 2: stream-grab again, keeping only the planned windows in memory.
        windows = []
        window_shot_id = []
        active = {}
        idx = 0
        cap = cv.VideoCapture(tmp)
        while True:
            ok = cap.grab()
            if not ok:
                break
            for wi, (start, _) in enumerate(planned):
                if start <= idx < start + max_window:
                    got, frame = cap.retrieve()
                    if got and frame is not None:
                        if wi not in active:
                            active[wi] = []
                            window_shot_id.append(wi)
                        active[wi].append(frame)
            idx += 1
        cap.release()

        out = []
        for wi in sorted(active):
            frames = [Image.fromarray(cv.cvtColor(f, cv.COLOR_BGR2RGB)) for f in active[wi]]
            out.append(frames)
        info = {
            "native_fps": round(native_fps, 2),
            "total_frames": total_frames,
            "shots_detected": len(shots),
            "windows_analyzed": len(out),
            # Start indices of the primary windows: the coverage sweep skips
            # these tiles so its counts never double-count the primary evidence.
            "window_starts": [start for start, _ in planned],
        }
        if out:
            # Provenance on the first window's first frame for the verdict.
            out[0][0]._rinse_shot_info = info
        return out, frame_interval, info
    except Exception as e:
        return [], None, {"error": f"Video decode failed: {e}"}
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

# Video frame extraction backends. ffmpeg (subprocess) is tried first, then
# OpenCV (opencv-python-headless) as a fallback; the endpoint reports an honest
# 503 when neither is installed instead of pretending to analyze the file.
_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")
_FFMPEG_WORKS = False
if _FFMPEG:
    try:
        _probe = subprocess.run([_FFMPEG, "-version"], capture_output=True, timeout=10)
        _FFMPEG_WORKS = _probe.returncode == 0
    except Exception:
        _FFMPEG_WORKS = False


# ---------------------------------------------------------------------------
# Social-platform video resolution (yt-dlp, optional)
#
# Social pages (Instagram Reels, TikTok, YouTube, ...) serve HTML; a plain HTTP
# fetch cannot resolve the underlying clip. yt-dlp handles 300+ platforms and
# is used to resolve such links to a direct media file before downloading.
# Optional dependency: without it the endpoint keeps the honest 415 error.
# ---------------------------------------------------------------------------

try:
    import yt_dlp  # type: ignore
    _YTDLP_AVAILABLE = True
except ImportError:
    yt_dlp = None  # type: ignore[assignment]
    _YTDLP_AVAILABLE = False

_SOCIAL_VIDEO_HOSTS = (
    "instagram.com", "instagr.am", "tiktok.com", "youtube.com", "youtu.be",
    "facebook.com", "fb.watch", "x.com", "twitter.com", "twitch.tv",
    "vimeo.com", "reddit.com", "redd.it", "imgur.com", "snapchat.com",
)

# Caption + page context of the most recently yt-dlp-resolved video
# (module-level so the video deep path can pass it to the AI-metadata probe;
# single-threaded handoff is acceptable because each request reads it right
# after its own resolve call).
_LAST_VIDEO_CAPTION = ""
_LAST_VIDEO_PAGE_INFO: dict = {}


def _looks_like_social_page(url):
    """True when the URL host is a known social platform."""
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in _SOCIAL_VIDEO_HOSTS)


def _ytdlp_provenance(page_info: dict) -> tuple:
    """Build provenance text channels for the AI-metadata layer from a
    yt-dlp info dict captured during the video resolve.

    Returns (source_caption, page_context) where:
      source_caption  the POST'S OWN caption / title / description - the page's
                      own label for this specific asset. This keeps the existing
                      strong semantics: a generator name here scores 75 -> voter
                      escalation.
      page_context    surrounding account / page context (channel, uploader,
                      webpage URL / basename). Context only: a strong tool name
                      here counts as one weak vote, never a synthetic-band verdict
                      on its own (a channel named after a tool is not proof a
                      specific post is AI - but it is weak provenance signal).

    The split mirrors the image path's alt_text vs page_context discipline so
    the reason text stays honest about which channel produced a marker.
    """
    title = page_info.get("title", "")
    description = page_info.get("description", "")
    channel = page_info.get("channel") or page_info.get("uploader", "")
    webpage_url = page_info.get("webpage_url", "")
    basename = page_info.get("webpage_url_basename", "")

    # Source caption: the post's own label for this asset. Title + description
    # already include the caption text and any on-post hashtags.
    caption = " ".join(p for p in (title, description) if p).strip()

    # Page context: surrounding account / page text. A channel named after a
    # tool is weak evidence about origin, not a claim about this specific asset.
    context_parts = [p for p in (channel, webpage_url, basename) if p]
    page_context = " ".join(context_parts).strip()

    return caption, page_context


def _classify_ytdlp_error(err: str) -> str:
    """Classify a yt-dlp failure into an actionable category. The API error
    should carry the MOST informative of the attempted selectors' errors, not
    the last one (measured: a YouTube bot-wall produced [SSL: UNEXPECTED_EOF]
    -> 'Sign in to confirm you're not a bot' -> 'Requested format is not
    available', and the last one blames the format selector when the real
    problem is the bot-wall)."""
    lowered = err.lower()
    if "sign in to confirm" in lowered or "confirm you\u2019re not a bot" in lowered or "not a bot" in lowered:
        return "botwall"
    if "cookies" in lowered and ("confirm" in lowered or "sign in" in lowered):
        return "botwall"
    if "requested format is not available" in lowered:
        return "format"
    if "login required" in lowered or "private video" in lowered or "age" in lowered and "restricted" in lowered:
        return "auth"
    if "unavailable" in lowered or "removed" in lowered or "does not exist" in lowered or "404" in lowered:
        return "gone"
    if "ssl" in lowered or "connection reset" in lowered or "timed out" in lowered or "eof" in lowered:
        return "transient"
    return "other"


def _ytdlp_download(url):
    """Download a video from a social-platform page URL via yt-dlp.

    yt-dlp resolves the page to the underlying clip and performs the download
    itself, which carries the required headers, cookies, and (with ffmpeg)
    HLS/DASH handling - a plain requests.get on the resolved CDN URL is not
    enough. Tries a layered chain of format selectors (pre-merged -> ffmpeg
    merge -> video-only -> last resort) with an optional browser-cookies
    fallback for platforms that bot-wall anonymous requests.

    Returns (video_bytes, error_string); exactly one of the two is non-None.
    """
    if not _YTDLP_AVAILABLE:
        return None, (
            "This URL points to a social platform page (Instagram Reel, TikTok, "
            "YouTube, ...), which serves HTML instead of a video file. Install "
            "yt-dlp on the server to resolve these links automatically: "
            "pip install -U yt-dlp"
        )

    # Source provenance probe (read-only; failures are non-fatal). We capture
    # the yt-dlp info dict once so the video-deep path can mine more provenance
    # channels than just the title+description caption (channel/uploader, page
    # URL, hashtags, thumbnail filename hints) for the AI-metadata layer
    # (forensics/ai_metadata.py). Creators routinely declare the generator tool
    # somewhere on the page, not only in the caption.
    page_info = {}
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                               "noplaylist": True, "socket_timeout": 15,
                               "extract_flat": False}) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("_type") == "playlist":
                entries = info.get("entries") or []
                if entries:
                    info = entries[0]
            if info:
                page_info = {
                    "title": str(info.get("title") or "").strip(),
                    "description": str(info.get("description") or "").strip(),
                    "channel": str(info.get("channel") or info.get("uploader") or "").strip(),
                    "uploader": str(info.get("uploader") or "").strip(),
                    "webpage_url": str(info.get("webpage_url") or "").strip(),
                    "webpage_url_basename": str(info.get("webpage_url_basename") or "").strip(),
                    "id": str(info.get("id") or "").strip(),
                    "tags": info.get("tags"),
                }
    except Exception as e:  # noqa: BLE001
        print(f"[yt-dlp] page provenance probe failed for {url}: {e}")
        page_info = {}

    # Format strategy: the pixel/temporal layers are what the verdict is built
    # on, so a pre-merged A+V file is preferred but not required - the audio
    # layer (forensics/audio_track.py) analyzes whatever audio stream the
    # resolved file carries and abstains honestly when there is none. The
    # selectors are tried in order of preference; each is a fallback chain
    # itself so a platform that lacks one container still downloads:
    #   1. pre-merged A+V mp4 (Instagram, most direct sites)
    #   2. A+V MERGE via ffmpeg when available (YouTube DASH serves separated
    #      tracks; modern YouTube pages offer no pre-merged file at all, so
    #      "best" fails with "Requested format is not available" unless a
    #      merge is allowed - this is the fix for that error)
    #   3. video-only stream (no audio, no merge needed - works everywhere,
    #      fine for a frames-only forensic pipeline)
    #   4. last resort: any single format yt-dlp can pick ("b" = best
    #      pre-merged OR fallback to bestvideo per yt-dlp semantics)
    ffmpeg_ok = bool(_FFMPEG and _FFMPEG_WORKS)
    formats_to_try = [
        "best[ext=mp4]/best",                                  # pre-merged A+V
        ("bv*+ba/b" if ffmpeg_ok else None),                   # A+V merge (needs ffmpeg)
        "bestvideo[ext=mp4]/bestvideo",                        # video-only
        "b",                                                   # last resort
    ]
    formats_to_try = [f for f in formats_to_try if f]

    # Optional browser-cookies fallback: platforms (YouTube above all)
    # bot-wall anonymous datacenter/home IPs with "Sign in to confirm you're
    # not a bot". Exporting the user's own browser cookies is the platform-
    # documented workaround. The cookie specs can be forced/configured via
    # YTDLP_COOKIES_FROM_BROWSER="chrome" / "chrome:Profile 1" (comma- or
    # semicolon-separated list allowed) or YTDLP_COOKIES_FILE=/path/file.txt
    # (Netscape cookie export); when neither is set, common local browser
    # profiles are probed as a last resort. Cookie access can pop OS-level
    # auth dialogs (macOS Keychain), so it is strictly a fallback pass.
    cookie_specs = [None]
    env_browser = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    env_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if env_file:
        cookie_specs.append(env_file)
    if env_browser:
        for part in env_browser.replace(";", ",").split(","):
            spec = part.strip()
            if not spec:
                continue
            browser, _, profile = spec.partition(":")
            cookie_specs.append((browser.strip().lower(), profile.strip() or None))
    else:
        for browser, profile in (("chrome", "Default"), ("chrome", None), ("firefox", None), ("safari", None)):
            cookie_specs.append((browser, profile))

    last_err = None
    best_err_kind = None
    _KIND_RANK = {"botwall": 0, "auth": 0, "gone": 0, "format": 1, "other": 2, "transient": 3}

    def _attempt(fmt: str, cookie_spec):
        """One download attempt. Returns (video_bytes, '') on success, else
        (None, error_string)."""
        tmpdir = tempfile.mkdtemp(prefix="rinse_ytdlp_")
        opts = {
            "format": fmt,
            "outtmpl": os.path.join(tmpdir, "source.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,           # keep the server log readable
            "noplaylist": True,
            "socket_timeout": 30,
            "max_filesize": MAX_VIDEO_BYTES,
            "retries": 2,
        }
        if cookie_spec:
            if isinstance(cookie_spec, str):
                opts["cookiefile"] = cookie_spec       # Netscape-format export
            else:
                opts["cookiesfrombrowser"] = cookie_spec  # (browser, profile)
        if ffmpeg_ok and _FFMPEG:
            # Some server processes don't inherit a PATH that contains ffmpeg
            # (launchd, secret/CI runners, docker-minimal images). Point
            # yt-dlp at the verified binary explicitly so the merge selector
            # can run.
            opts["ffmpeg_location"] = _FFMPEG
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info and info.get("_type") == "playlist":
                    entries = info.get("entries") or []
                    if entries:
                        info = entries[0]
            if info and info.get("duration") and info.get("duration") > 600:
                return None, "Video is longer than 10 minutes; download the clip and upload the file instead."
            files = [
                os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
                if os.path.isfile(os.path.join(tmpdir, f))
            ]
            if not files:
                return None, "yt-dlp reported success but wrote no media file."
            best = max(files, key=os.path.getsize)
            if os.path.getsize(best) > MAX_VIDEO_BYTES:
                return None, f"Video download too large ({os.path.getsize(best) // (1024 * 1024)}MB, limit 150MB)."
            with open(best, "rb") as f:
                return f.read(), ""
        except Exception as e:  # noqa: BLE001
            return None, str(e)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # Pass 1: anonymous. Pass 2 (only when everything failed): with cookies.
    for cookie_spec in cookie_specs:
        for fmt in formats_to_try:
            data, err = _attempt(fmt, cookie_spec)
            if data is not None:
                if cookie_spec:
                    label = cookie_spec if isinstance(cookie_spec, str) else cookie_spec[0]
                    print(f"[yt-dlp] download with {label} cookies succeeded for {url}")
                # Expose the captured page info for the metadata layer (module
                # global; the video deep path reads it right after its own
                # resolve). Single-threaded handoff is acceptable.
                global _LAST_VIDEO_PAGE_INFO
                _LAST_VIDEO_PAGE_INFO = page_info
                return data, None
            kind = _classify_ytdlp_error(err)
            if last_err is None or _KIND_RANK.get(kind, 2) < _KIND_RANK.get(best_err_kind, 2):
                last_err = err
                best_err_kind = kind
        # A bot-wall ends the current pass immediately: retrying other format
        # selectors cannot fix an IP-level block.
        if last_err and best_err_kind == "botwall" and len(formats_to_try) > 1:
            break

    # The most common real-world failure is an outdated yt-dlp: platforms
    # change constantly and old extractors lose access to every format (the
    # user-visible error is usually "Requested format is not available").
    # Make the fix self-serviceable in the server log and the API error.
    ytdlp_ver = getattr(getattr(yt_dlp, "version", None), "__version__", "unknown")
    kind = _classify_ytdlp_error(last_err or "")
    if kind == "botwall":
        advice = (
            "The platform is bot-walling this server's IP ('Sign in to confirm you're not a bot'). "
            "Fixes: set YTDLP_COOKIES_FROM_BROWSER=chrome (or export cookies to a file and set "
            "YTDLP_COOKIES_FILE) on the server, retry later, or download the clip and upload it directly."
        )
    elif kind == "format":
        advice = (
            f"The most common fix is updating yt-dlp (this server runs {ytdlp_ver}): pip install -U yt-dlp. "
            "If it is current, the post is likely private/login-walled - download and upload the file."
        )
    else:
        advice = (
            "If the post is private, age-restricted, or the platform requires a login, "
            "download the clip and upload the file instead."
        )
    print(f"[yt-dlp {ytdlp_ver}] download failed for {url} ({kind}): {last_err}")
    return None, (
        f"Could not download the video from this link: {last_err}. {advice}"
    )


def _video_decoder_available():
    """True when either ffmpeg works or opencv is importable."""
    if _FFMPEG and _FFMPEG_WORKS:
        return True
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False

SERVER_START_TIME = time.time()  # for /health uptime reporting


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
# NOTE: superseded by the generated fingerprints/db.py + forensics/characters.py
# matcher (two-of-three hashing) when available — this dict remains as fallback.
KNOWN_AI_ARTWORK_FINGERPRINTS = {
    "tung-tung-sahur": {
        "label": "Tung Tung Tung Sahur cover art (viral AI-generated meme character)",
        "dhash": 0x64a425353458d269,
    },
    "tung-tung-sahur-news-still": {
        "label": "Tung Tung Tung Sahur news/video still (viral AI-generated meme character)",
        "dhash": 0x4a4b0b2e2d2e3e3e,
    },
    "ai-generated-receipt": {
        "label": "Viral AI-generated receipt artwork (Webflow CDN)",
        "dhash": 0x232b2b2f230f2b27,
    },
}

# --- Character fingerprint matcher (generated DB + two-of-three hashing) ---
# fingerprints/db.py is generated by scripts/build_fingerprints.py from
# fingerprints/canon/<character>/ images + legacy seeds. When present it
# replaces the legacy loop above; otherwise we fall back to it.
_CHARACTERS_AVAILABLE = False
characters_mod = None
try:
    from forensics import characters as characters_mod  # noqa: E402

    if getattr(characters_mod, "FINGERPRINTS", None):
        _CHARACTERS_AVAILABLE = True
        print(
            f"Character fingerprints loaded: {len(characters_mod.FINGERPRINTS)} entries "
            f"(build {getattr(__import__('fingerprints.db', fromlist=['x']), 'FINGERPRINT_DB_BUILD', 'unknown')})"
        )
except Exception as e:  # noqa: BLE001
    print(f"Character matcher unavailable, using legacy fingerprint loop: {e}")

# --- Scan cache (SQLite, exact + near-duplicate layers) --------------------
# Optional at runtime: if the module or the DB can't initialize, scans simply
# run uncached. Enabled with SCAN_CACHE=1 (default on).
_CACHE_ENABLED = os.environ.get("SCAN_CACHE", "1") not in ("0", "false", "no")
scan_cache = None
if _CACHE_ENABLED:
    try:
        from forensics import scan_cache as scan_cache  # noqa: E402,F811

        scan_cache.cache_stats()  # force schema init + fail fast if unusable
        print(f"Scan cache enabled at {scan_cache.DB_PATH}")
    except Exception as e:  # noqa: BLE001
        print(f"Scan cache unavailable, running uncached: {e}")
        _CACHE_ENABLED = False

# --- Scan log (SQLite, one row per scan) ------------------------------------
# Same fail-open policy as the cache: if the log can't initialize, scans still
# run - they just aren't recorded. SCAN_LOG=0 turns it off deliberately.
scan_log = None
try:
    from forensics import scan_log as scan_log  # noqa: E402,F811

    if scan_log.ENABLED:
        scan_log.stats()  # force schema init + fail fast if the DB is unusable
        print(
            f"Scan log enabled at {scan_log.DB_PATH} "
            f"(retention {scan_log.RETENTION_DAYS}d, human {scan_log.HUMAN_RETENTION_DAYS}d)"
        )
    else:
        print("Scan log disabled (SCAN_LOG=0).")
except Exception as e:  # noqa: BLE001
    print(f"Scan log unavailable, scans won't be recorded: {e}")
    scan_log = None


def _collage_tile_stats(img, grid=4, work=512, color_bits=4):
    """Per-tile busyness statistics of a partitioned image (Phase 4a).

    A dense AI collage packs many INDEPENDENT renders uniformly - every cell
    of a grid is busy and color-rich alike - while a real photo of similar
    overall density has a subject and surroundings: its emptiest region (sky,
    background wall, table) is far quieter than the subject region.

    The image is resized to `work`x`work`, split into a `grid`x`grid
    partition, and each tile gets: edge-pixel share (gradient > 24/255) and
    a quantized unique-color count (top `color_bits` bits per RGB channel).

    Returns {} when numpy is unavailable or the image is too small, else:
        edge_cv          std/mean of per-tile edge density (uniformity of
                         busyness; a uniform collage is near 0)
        edge_mean        mean per-tile edge density
        min_tile_colors  quantized palette of the EMPTIEST tile
        max_tile_colors  quantized palette of the busiest tile
    """
    if not _NUMPY_AVAILABLE:
        return {}
    try:
        a = np.asarray(
            img.convert("RGB").resize((work, work), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
        luma = a.mean(axis=2)
        edge = np.zeros_like(luma)
        edge[:, :-1] += np.abs(np.diff(luma, axis=1))
        edge[:-1, :] += np.abs(np.diff(luma, axis=0))

        ts = work // grid
        tile_edge, tile_colors = [], []
        quant = (a.astype(np.uint8) >> (8 - color_bits))
        for r in range(grid):
            for c in range(grid):
                te = edge[r * ts:(r + 1) * ts, c * ts:(c + 1) * ts]
                tile_edge.append(float((te > 24.0).mean()))
                tq = quant[r * ts:(r + 1) * ts, c * ts:(c + 1) * ts]
                tile_colors.append(float(len(np.unique(tq.reshape(-1, 3), axis=0))))
        e = np.asarray(tile_edge)
        c = np.asarray(tile_colors)
        return {
            "edge_cv": float(e.std() / (e.mean() + 1e-6)),
            "edge_mean": float(e.mean()),
            "min_tile_colors": float(c.min()),
            "max_tile_colors": float(c.max()),
        }
    except Exception:
        return {}


def _pixel_forensics_img(img):
    """Color-structure forensics for flat cel-shaded / 3D-render character art.

    AI character art (toon renders, meme art) differs drastically from camera
    photos: very few distinct colors, high saturation, low edge variance, and
    large perfectly-flat regions. Returns stats + a conservative score boost,
    or None when the analysis can't run. Accepts a PIL Image directly (used
    for video frames); _pixel_forensics() wraps it for file paths.
    """
    if not _NUMPY_AVAILABLE:
        return None
    try:
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

        # 3. Edge statistics (Laplacian-like). Edge DENSITY (fraction of
        # strong-edge pixels) is the robust tell for AI toon/3D renders:
        # real saturated photos (macro florals, fruit) are covered in
        # texture edges, while renders have clean outlines with flat fills
        # between them - even after JPEG recompression. Raw edge VARIANCE
        # is fragile here because compression noise on small news/video
        # stills inflates it, so it is not used as a gate.
        edges = np.asarray(img.convert("L").filter(ImageFilter.FIND_EDGES)).astype(np.float32)
        edge_var = float(edges.var())
        edge_density = float((edges > 60).mean())

        # 4. Flat-region ratios (8x8 patches). Two thresholds: std < 3
        # captures perfectly flat fills; std < 8 additionally captures the
        # smooth gradient shading typical of 3D renders (which a strict
        # flat test misses).
        luma = np.asarray(img.convert("L")).astype(np.float32)
        flat = 0
        smooth8 = 0
        patches = 0
        patch_stds = []
        step = 8
        for y in range(0, hh - step, step):
            for x in range(0, ww - step, step):
                patches += 1
                patch_std = luma[y:y + step, x:x + step].std()
                patch_stds.append(patch_std)
                if patch_std < 3.0:
                    flat += 1
                if patch_std < 8.0:
                    smooth8 += 1
        flat_ratio = flat / max(patches, 1)
        smooth8_ratio = smooth8 / max(patches, 1)
        # Texture floor: how much micro-texture the LEAST-textured quarter of
        # the image carries. Camera photos keep sensor/grain noise everywhere
        # (even smooth backgrounds), renders/composites do not.
        patch_std_p25 = float(np.percentile(np.asarray(patch_stds), 25)) if patch_stds else 0.0

        # 5. Document-render signature (AI-generated receipts, tickets, documents)
        # Dense text images are gated out of the photo/art heuristics above. AI
        # generators render them with two tells a camera can't reproduce:
        #   - a perfectly smooth, texture-free background around the page
        #     (real photos/scans always show grain, shadows or a cluttered scene)
        #   - soft, anti-aliased type (real print has crisp high-contrast edges)
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

        # Synthetic flat-render signature (cel-shaded / 3D-render character art,
        # e.g. viral AI meme characters like Tung Tung Tung Sahur).
        #
        # A strict AND over every feature misses this class: news/video stills of
        # renders are small, heavily JPEG-compressed screenshots, which inflates
        # raw edge variance far past any sensible threshold (measured 1390 on a
        # Tung Tung Sahur still) while every other tell still points at AI art.
        # So the signature is a SATURATION GATE + scored soft signals instead:
        #   gate:   mean saturation > 0.50 (camera photos rarely exceed this;
        #           saturated macro florals/fruit DO, but they fail the edge
        #           density signal below because real texture is everywhere)
        #   signal: few distinct colors (< 700) - flat render palettes
        #   signal: sparse edges (edge_density < 0.10) - clean outlines, not
        #           photographic texture (macro flower 0.15, fruit 0.14, plate
        #           0.22 all excluded; tung still 0.06 passes)
        #   signal: smooth shaded regions (smooth8_ratio 0.30-0.65) - large
        #           gradient-shaded areas typical of 3D renders, but not an
        #           empty/blank image (bokeh portrait 0.72, sunset 1.0 excluded)
        # 3/3 signals -> strong boost; 2/3 -> moderate boost.
        boost = 0
        reason = None
        if sat_mean > 0.50:
            signals = 0
            if unique_colors < 700:
                signals += 1
            if edge_density < 0.10:
                signals += 1
            if 0.30 < smooth8_ratio < 0.65:
                signals += 1
            if signals == 3:
                boost = 80
                reason = (
                    f"Synthetic render signature: cel-shaded/3D-render palette "
                    f"({unique_colors} distinct colors, saturation {sat_mean:.2f}, "
                    f"sparse edges at {edge_density * 100:.1f}% density, "
                    f"{smooth8_ratio * 100:.0f}% smooth shaded regions). "
                    f"AI toon/character art shows this exact color profile; "
                    f"camera photos - even saturated macro shots - keep dense "
                    f"texture edges instead."
                )
            elif signals == 2:
                boost = 60
                reason = (
                    f"Synthetic render signature (moderate): saturated image with "
                    f"a limited palette ({unique_colors} colors, saturation "
                    f"{sat_mean:.2f}) and partially smooth shading "
                    f"({smooth8_ratio * 100:.0f}% smooth regions, edge density "
                    f"{edge_density * 100:.1f}%) - consistent with AI toon/3D-render "
                    f"character art, uncommon for camera photos."
                )

        # Muted-palette render signature (saturation 0.30-0.50).
        #
        # The saturated gate above structurally misses AI art with desaturated
        # grade (moody editorial illustrations, muted toon renders - measured
        # sat 0.35 on a Fortnite-brainrot news image, 0.45 on a Guardian AI
        # still). Simply lowering the gate to 0.30 is NOT safe: real sunsets,
        # bokeh portraits and food plates live at 0.24-0.49 too, and a real
        # sunset is a near-twin of AI reel frames in every one of the signals
        # below (measured: sunset sat 0.25 / colors 372 / edge 0.092 /
        # smooth8 0.50 vs an AI reel frame 0.25 / 471 / 0.033 / 0.51).
        #
        # The muted band separates on BOUNDED features instead - AI renders
        # land in a middle ground (moderate palette, sparse-but-present
        # outlines, gradient fills, a texture floor with *some* grain) that
        # the risky real photos miss on most axes (calibration corpus,
        # 2026-09-27: 10 real photos + 7 AI assets):
        #   muted AI:      fortnite  colors 613 edge 0.038 smooth8 0.44 p25 4.4
        #                  guardian  colors 954 edge 0.082 smooth8 0.38 p25 5.3
        #   real, in band: food_salad  colors 1521 edge 0.150 smooth8 0.23 p25 8.4
        #                  bokeh_portrait colors 471 edge 0.019 smooth8 0.72 p25 1.3
        #   real, sunset (band-adjacent, sat 0.25): p25 4.6 but edge 0.092 with
        #   smooth8 0.50 would pass - hence the saturation floor stays at 0.30.
        elif 0.30 <= sat_mean <= 0.50:
            muted_signals = 0
            if 350 <= unique_colors <= 1100:
                muted_signals += 1
            if 0.020 <= edge_density <= 0.115:
                muted_signals += 1
            if 0.30 <= smooth8_ratio <= 0.55:
                muted_signals += 1
            if 1.8 <= patch_std_p25 <= 7.5:
                muted_signals += 1
            if muted_signals >= 4:
                boost = 70
                reason = (
                    f"Synthetic render signature (muted palette): desaturated "
                    f"image (saturation {sat_mean:.2f}) with a bounded render "
                    f"palette ({unique_colors} colors), sparse clean outlines "
                    f"(edge density {edge_density * 100:.1f}%), gradient-shaded "
                    f"fills ({smooth8_ratio * 100:.0f}% smooth regions) and a "
                    f"texture floor of {patch_std_p25:.1f} - the middle-ground "
                    f"profile of AI illustration/3D-render art. Real photos in "
                    f"this saturation band are either far busier (food/texture "
                    f"shots) or far cleaner (bokeh/flat-sky shots) on every axis."
                )
            elif muted_signals == 3:
                boost = 60
                reason = (
                    f"Synthetic render signature (muted palette, moderate): "
                    f"desaturated image (saturation {sat_mean:.2f}) with a "
                    f"bounded palette ({unique_colors} colors), partially smooth "
                    f"shading ({smooth8_ratio * 100:.0f}% smooth regions, edge "
                    f"density {edge_density * 100:.1f}%, texture floor "
                    f"{patch_std_p25:.1f}) - consistent with muted AI toon/render "
                    f"art, uncommon for camera photos."
                )

        # Dense saturated multi-character collage signature (e.g. the viral
        # 'all Italian brainrot characters' poster grid).
        #
        # Measured separation problem: the poster is the OPPOSITE of the
        # flat-render signatures above - hyper-saturated (sat 0.53), hyper-
        # dense (1558 colors, edge density 0.215), which photo-realistic busy
        # shots approach (food_salad: 1521 colors, edge 0.150; strawberries:
        # 766 colors, edge 0.176). The stable separator across the corpus is
        # the JOINT condition: only the poster combines very high saturation
        # AND very high edge density AND a huge palette. Every real photo in
        # the 11-image calibration corpus misses at least one axis by a wide
        # margin (max real edge density 0.176, max real colors 1591 - and
        # that plate image sits at sat 0.24, far below the gate).
        #
        # PHASE 4a TILE-UNIFORMITY STRUCTURE (measured 2026-09-27, 4x4 grid,
        # per-tile edge density CV + minimum per-tile quantized palette):
        # a collage is many INDEPENDENT character renders packed uniformly,
        # so every tile is busy and color-rich alike; a real photo has a
        # subject and surroundings. Corpus margins (poster vs closest real
        # challengers):
        #   poster        edge-CV 0.22, emptiest tile 342 colors, e_mean 0.284
        #   strawberries  edge-CV 0.37, emptiest tile 197 colors, e_mean 0.227
        #   food_salad    edge-CV 0.66, emptiest tile  54 colors, e_mean 0.161
        #   every other real photo: CV 0.47-1.78, emptiest tile <= 197 colors
        #
        #   70 (strong, pf_strong floor): dense+sat+palette gate AND every
        #   tile busy (CV <= 0.30) AND the emptiest tile still rich (>= 280
        #   quantized colors). Strawberries misses BOTH tile axes (CV 0.37,
        #   c_min 197); food_salad/parrot/food_plate miss the base gate.
        #   60 (moderate, weighted average only): base gate alone - the
        #   previous behavior, kept for collages with uneven tiles.
        # INDEPENDENT check (not an elif): the saturated gate above consumes
        # every sat > 0.50 image - the poster lands there with 0/3 signals
        # and boost 0, so this signature only fires when the flat-render
        # signature did NOT fire.
        if (
            boost == 0
            and sat_mean >= 0.50
            and edge_density >= 0.17
            and unique_colors >= 1100
        ):
            tiles = _collage_tile_stats(img)
            if (
                tiles
                and tiles["edge_cv"] <= 0.30
                and tiles["min_tile_colors"] >= 280
                and tiles["edge_mean"] >= 0.15
            ):
                boost = 70
                reason = (
                    f"Dense render-collage signature (strong): hyper-saturated "
                    f"({sat_mean:.2f} mean saturation) image with an extremely "
                    f"dense palette ({unique_colors} colors), dense outlines "
                    f"(edge density {edge_density * 100:.1f}%) and a UNIFORM "
                    f"tile grid - every cell of a 4x4 partition is equally busy "
                    f"(edge-density CV {tiles['edge_cv']:.2f}, emptiest cell "
                    f"still {tiles['min_tile_colors']:.0f} quantized colors). "
                    f"AI multi-character render collages/meme grids pack many "
                    f"independent renders uniformly; real photos with this "
                    f"overall density have a clear subject - their emptiest "
                    f"region (sky/background) collapses on both axes."
                )
            else:
                boost = 60
                reason = (
                    f"Dense render-collage signature (moderate): hyper-saturated "
                    f"({sat_mean:.2f} mean saturation) image with an extremely "
                    f"dense palette ({unique_colors} colors) and dense outlines "
                    f"(edge density {edge_density * 100:.1f}%) - the profile of "
                    f"AI multi-character render collages/meme grids. Real photos "
                    f"that approach it on one axis (busy food shots, dense "
                    f"floral macros) miss another by a wide margin."
                )

        # Known-AI-character fingerprint match (two-of-three perceptual
        # hashing with crop fallback — see forensics/characters.py and
        # docs/brainrot-characters-and-scan-cache-plan.md). Falls back to the
        # legacy single-dHash loop when the generated DB is unavailable.
        match_label = None
        character_match = None
        if _CHARACTERS_AVAILABLE:
            cm = characters_mod.match_character(img)
            if cm:
                character_match = cm
                match_label = cm["label"]
                # Only exact/likely matches hard-force the verdict; a "weak"
                # match is reported but never escalates the score.
                if cm["match_strength"] in ("exact", "likely"):
                    match_label = (
                        f"{cm['label']} [confirmed]"
                        if cm["match_strength"] == "exact"
                        else cm["label"]
                    )
                else:
                    match_label = None
        else:
            img_dhash = _dhash(img)
            for entry in KNOWN_AI_ARTWORK_FINGERPRINTS.values():
                if _hamming(img_dhash, entry["dhash"]) <= 10:
                    match_label = entry["label"]
                    break

        return {
            "unique_colors": unique_colors,
            "sat_mean": sat_mean,
            "edge_var": edge_var,
            "edge_density": edge_density,
            "flat_ratio": flat_ratio,
            "smooth8_ratio": smooth8_ratio,
            "patch_std_p25": patch_std_p25,
            "boost": boost,
            "reason": reason,
            "doc_boost": doc_boost,
            "doc_reason": doc_reason,
            "match_label": match_label,
            "character_match": character_match,
        }
    except Exception as e:
        print(f"Pixel forensics unavailable: {e}")
        return None


def _pixel_forensics(img_path):
    """Open an image file and run _pixel_forensics_img on it. Kept for callers
    that hold a path (image deep path); video frames pass the decoded PIL image
    straight into _pixel_forensics_img."""
    if not _NUMPY_AVAILABLE:
        return None
    try:
        with Image.open(img_path) as img:
            return _pixel_forensics_img(img)
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

from forensics import (
    probe_synthid_watermark,
    probe_c2pa_manifest,
    probe_ai_metadata,
    analyze_frequency_domain,
    analyze_neural_and_heatmap,
    analyze_video_temporal_coherence,
    analyze_pixel_temporal_frequency,
    fuse_ensemble_verdict,
)
from forensics.d3 import analyze_second_order_dynamics
from forensics import spai
from forensics.learned_image import analyze_learned_image
from forensics import rppg as _rppg
from forensics import temporal_residual as _tr
from forensics import audio_track as _audio
from forensics import capture_origin as _capture_origin
from forensics import camera_physics as _camera_physics
from forensics import embedding_consistency as _embedding
from storyscope import dna_detect


def _decode_frames_from_base64(frames_b64, cap: int = 30):
    """Decode a list of base64 frame payloads (data URLs or raw b64) into PIL RGB images."""
    loaded_frames = []
    if frames_b64 and isinstance(frames_b64, list):
        for item in frames_b64[:cap]:
            try:
                if isinstance(item, str) and "," in item:
                    item = item.split(",", 1)[1]
                b = base64.b64decode(item)
                loaded_frames.append(Image.open(io.BytesIO(b)).convert("RGB"))
            except Exception:
                pass
    return loaded_frames


def _extract_video_frames_ffmpeg(video_bytes, n_frames=MAX_VIDEO_FRAMES):
    """Sample n uniformly-spaced frames from a video (raw bytes) with ffmpeg.
    Returns a list of PIL RGB images (possibly empty). Uses a single pass with
    the fps filter so sampling stays cheap even on long clips."""
    if not (_FFMPEG and _FFMPEG_WORKS):
        return []
    frames = []
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp = f.name

        duration = None
        if _FFPROBE:
            try:
                probe = subprocess.run(
                    [_FFPROBE, "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", tmp],
                    capture_output=True, text=True, timeout=20,
                )
                if probe.returncode == 0 and probe.stdout.strip():
                    duration = float(probe.stdout.strip())
            except Exception:
                duration = None
        if not duration or duration <= 0:
            duration = 10.0  # undecodable duration: assume 10s, still sample
        interval = max(0.05, duration / max(n_frames, 1))

        run = subprocess.run(
            [_FFMPEG, "-v", "error", "-i", tmp, "-vf", f"fps=1/{interval:.6f}",
             "-frames:v", str(n_frames), "-f", "image2pipe", "-vcodec", "mjpeg",
             "-q:v", "4", "-"],
            capture_output=True, timeout=180,
        )
        if run.returncode != 0 or not run.stdout:
            return []

        # Split the concatenated JPEG stream on SOI (FF D8) / EOI (FF D9) markers.
        data = run.stdout
        start = 0
        while start < len(data):
            soi = data.find(b"\xff\xd8", start)
            if soi == -1:
                break
            eoi = data.find(b"\xff\xd9", soi + 2)
            if eoi == -1:
                break
            try:
                frames.append(Image.open(io.BytesIO(data[soi:eoi + 2])).convert("RGB"))
            except Exception:
                pass
            start = eoi + 2
        return frames[:n_frames]
    except Exception as e:
        print(f"ffmpeg video frame extraction failed: {e}")
        return []
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _extract_video_frames_cv2(video_bytes, n_frames=MAX_VIDEO_FRAMES):
    """Sample n uniformly-spaced frames from a video (raw bytes) with OpenCV.
    Fallback used when ffmpeg is unavailable; opencv-python-headless wheels
    bundle their own decoders so no system ffmpeg is required."""
    try:
        import cv2 as cv
    except ImportError:
        return []
    frames = []
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp = f.name
        cap = cv.VideoCapture(tmp)
        try:
            total = int(cap.get(cv.CAP_PROP_FRAME_COUNT))
            if total <= 0:
                return []
            indices = sorted(set(
                int(i * (total - 1) / max(n_frames - 1, 1))
                for i in range(min(n_frames, total))
            ))
            for idx in indices:
                cap.set(cv.CAP_PROP_POS_FRAMES, idx)
                ok, frame = cap.read()
                if ok and frame is not None:
                    frames.append(Image.fromarray(cv.cvtColor(frame, cv.COLOR_BGR2RGB)))
        finally:
            cap.release()
        return frames[:n_frames]
    except Exception as e:
        print(f"OpenCV video frame extraction failed: {e}")
        return []
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _extract_video_frames(video_bytes, n_frames=MAX_VIDEO_FRAMES):
    """Try ffmpeg first, then OpenCV, then give up (caller reports the error)."""
    frames = _extract_video_frames_ffmpeg(video_bytes, n_frames)
    if frames:
        return frames
    return _extract_video_frames_cv2(video_bytes, n_frames)


def _load_video_frames(data):
    """Resolve a video payload into (window_list, frame_interval, info, error).

    window_list is a list of CONTIGUOUS native-frame-rate frame windows
    (required by the temporal forensics layers); frame_interval is the real
    per-frame spacing in seconds (None for client-extracted frames without an
    interval); info carries sampling provenance. error is None on success and a
    (jsonify(...), status) tuple otherwise. Errors are honest: HTML pages from
    social platforms get a clear 415 (plus a precise yt-dlp error when
    resolution fails) instead of a silently fabricated score.

    Accepts, in priority order: video_base64 (raw file upload), video_url
    (direct .mp4/.webm/.mov link, or a social-platform page link resolved via
    yt-dlp when installed), frames_base64 (client-extracted frames, ideally
    contiguous with a frame_interval_seconds field).
    """
    video_bytes = None
    video_b64 = data.get("video_base64") or ""
    if video_b64:
        if len(video_b64) > MAX_VIDEO_BYTES * 4 // 3 + 4096:
            return [], None, None, (jsonify({"error": "Video payload too large (150MB limit)."}), 413)
        try:
            payload = video_b64.split(",", 1)[-1] if "," in video_b64 else video_b64
            video_bytes = base64.b64decode(payload)
            if not video_bytes:
                return [], None, None, (jsonify({"error": "Empty video payload."}), 400)
        except Exception as e:
            return [], None, None, (jsonify({"error": f"Invalid video_base64: {e}"}), 400)

    video_url = data.get("video_url") or ""
    if video_bytes is None and video_url:
        parsed = urlparse(video_url)
        if parsed.scheme not in ("http", "https"):
            return [], None, None, (jsonify({"error": "Invalid video_url: only http(s) sources are allowed."}), 400)
        # Known social platforms (YouTube, Instagram, TikTok, X, ...): skip the
        # plain fetch entirely. These hosts reset or bot-wrangle non-browser
        # clients (YouTube literally closes the connection), so a plain
        # requests.get fails with an exception or a bot-wall HTML before
        # yt-dlp ever runs - and yt-dlp handles direct CDN links fine anyway.
        if _looks_like_social_page(video_url):
            if not _YTDLP_AVAILABLE:
                return [], None, None, (jsonify({
                    "error": "This URL points to a social platform (YouTube, Instagram, TikTok, ...), "
                              "which requires yt-dlp on the server to resolve (pip install -U yt-dlp). "
                              "Alternatively download the video and upload the file, or paste a "
                              "direct .mp4/.webm/.mov file URL."
                }), 415)
            video_bytes, dl_err = _ytdlp_download(video_url)
            if video_bytes is None:
                return [], None, None, (jsonify({"error": dl_err}), 415)
        else:
            headers = {"User-Agent": "RINSEAuthenticityDetector/2.0"}
            try:
                resp = requests.get(video_url, headers=headers, timeout=20, stream=True)
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if not resp.ok:
                    status = 502 if resp.status_code >= 500 else resp.status_code
                    resp.close()
                    return [], None, None, (jsonify({"error": f"Failed to download video URL (HTTP {resp.status_code})."}), status)
                if "text/html" in ctype or "application/xhtml" in ctype:
                    resp.close()
                    # An HTML page from an unknown host: try yt-dlp if it is
                    # installed (it covers 300+ sites), otherwise keep the
                    # honest advisory.
                    if _YTDLP_AVAILABLE:
                        video_bytes, dl_err = _ytdlp_download(video_url)
                        if video_bytes is None:
                            return [], None, None, (jsonify({"error": dl_err}), 415)
                    else:
                        return [], None, None, (jsonify({
                            "error": "The URL points to a web page (HTML), not a direct video file. "
                                      "Social platforms (Instagram Reels, TikTok, YouTube, Facebook, X) serve "
                                      "page HTML that requires yt-dlp to resolve (pip install -U yt-dlp). "
                                      "Alternatively download the video and upload the file, or paste a "
                                      "direct .mp4/.webm/.mov file URL."
                        }), 415)
                else:
                    # Direct media file: stream it in with a size cap.
                    chunks = []
                    total = 0
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > MAX_VIDEO_BYTES:
                            resp.close()
                            return [], None, None, (jsonify({"error": "Video download too large."}), 413)
                        chunks.append(chunk)
                    video_bytes = b"".join(chunks)
            except requests.RequestException as e:
                # A non-social host that reset the connection: if yt-dlp is
                # available, give it one shot (it can handle sites the plain
                # fetch cannot), otherwise report the failure honestly.
                if _YTDLP_AVAILABLE:
                    video_bytes, dl_err = _ytdlp_download(video_url)
                    if video_bytes is None:
                        return [], None, None, (jsonify({"error": dl_err}), 415)
                else:
                    return [], None, None, (jsonify({"error": f"Failed to download video URL: {e}"}), 502)

    if video_bytes is not None:
        windows, frame_interval, info = _extract_video_shot_windows(video_bytes)
        if "error" in info:
            err_body = {"error": info["error"]}
            if info.get("hint"):
                err_body["hint"] = info["hint"]
            return [], None, None, (jsonify(err_body), 503)
        if not windows:
            return [], None, None, (jsonify({"error": "No analyzable contiguous shot windows found in the video."}), 422)
        # Hand the resolved container bytes back to the caller so the audio
        # layer decodes the audio track from the SAME download instead of a
        # second fetch. Private key: popped in _run_video_deep, never
        # serialized into a verdict. Deliberately NOT used by the container
        # metadata scan - a yt-dlp download is a remux whose container tags
        # belong to the downloader, not the uploader, so that layer keeps
        # reading only originally-uploaded bytes (video_base64).
        info["_raw_video_bytes"] = video_bytes
        return windows, frame_interval, info, None

    frames_b64 = data.get("frames_base64") or []
    client_frames = _decode_frames_from_base64(frames_b64)
    interval = data.get("frame_interval_seconds")
    try:
        interval = float(interval) if interval is not None else None
    except (TypeError, ValueError):
        interval = None
    has_valid_interval = bool(client_frames) and interval is not None and 0 < interval <= 0.5
    if client_frames and not has_valid_interval:
        # Client frames without a valid interval are treated as a sparse
        # gallery: temporal layers stay inactive, spatial layers still run.
        interval = None
    return [client_frames] if client_frames else [], (interval if has_valid_interval else None), None, None


def _analyze_video_frames(loaded_frames, mode="video_deep", frame_interval_seconds=None, video_source="server",
                          video_bytes=None, source_caption="", page_context="", audio_bytes=None,
                          coverage=None):
    """
    Run the full video forensic ensemble over one or more contiguous frame
    windows: temporal layers on every window + spatial layers on the first and
    strongest-pwtf window's middle frame + PwTF-DVD pixel-wise temporal
    frequency (ICCV 2025). Returns a verdict dict.

    loaded_frames: a LIST of frame windows (each a list of PIL frames). Multiple
    windows are analyzed independently and the strongest temporal evidence wins
    - AI artifacts are often localized to one scene, so a single window can
    miss them entirely (measured: window position flipped a verdict).

    frame_interval_seconds: real per-frame spacing of the windows. When None
    (sparse client frames without an interval), the temporal layers report
    inactive instead of voting on aliased garbage - by design.
    video_source: "server" (native-rate contiguous windows) or "client".
    video_bytes: raw video file bytes (enables the container-metadata scan of
    the AI-provenance layer; None for client-frame payloads).
    audio_bytes: raw container bytes the audio layer decodes its track from.
    On server-side payloads this is the same download the frames came from
    (uploaded file or resolved URL), so no second fetch is needed; None for
    client-frame payloads, where the audio layer abstains honestly.
    source_caption: optional post caption / page title from the resolver -
    provenance evidence for the AI-metadata layer (strong channel: a generator
    name here scores 75 -> voter escalation).
    page_context: optional surrounding account / page context (channel,
    uploader, page URL) from the resolver - context-only weak channel, never a
    synthetic-band verdict on its own.
    """
    windows = [w for w in (loaded_frames or []) if w]
    if not windows:
        raise ValueError("No usable video frames were provided.")

    per_window_pwtf = []
    per_window_temporal = []
    per_window_d3 = []
    per_window_rppg = []
    per_window_tr = []
    per_window_cap = []
    per_window_cam = []
    per_window_emb = []
    window_details = []

    # Pass 1 - temporal layers on EVERY window; strongest evidence wins. Both
    # layers require a valid frame interval: without one the frames are a
    # sparse gallery, the temporal FFT would be sampling noise, and the
    # layers must stay out of the fusion. The per-frame score-trajectory
    # chart is built from the first window only (one chart per verdict).
    for win_idx, win in enumerate(windows):
        s_temporal = analyze_video_temporal_coherence(
            win, frame_interval_seconds=frame_interval_seconds,
            compute_frame_scores=(win_idx == 0),
        )
        if frame_interval_seconds:
            s_pwtf = analyze_pixel_temporal_frequency(win)
        else:
            s_pwtf = {
                "score": None, "probability": None, "label": "Inactive",
                "reasons": ["PwTF-DVD inactive: no valid frame interval - temporal "
                             "frequency analysis on non-contiguous frames is sampling noise."],
                "metrics": {}, "spectrum_bins": 0, "frames_analyzed": len(win), "active": False,
            }
        per_window_temporal.append(s_temporal)
        per_window_pwtf.append(s_pwtf)
        # D3 second-order dynamics (ICCV 2025): metrics-only layer - in
        # pixel/patch space the volatility statistic does not separate real
        # motion from generation (calibrated in forensics/eval_d3.py), so it
        # reports measurements and reasons but never votes (score=None).
        s_d3 = analyze_second_order_dynamics(
            win, frame_interval_seconds=frame_interval_seconds,
        )
        per_window_d3.append(s_d3)
        s_rppg = _rppg.analyze_video_rppg(win, frame_interval_seconds) if frame_interval_seconds else {
            "score": None, "active": False, "applies": False,
            "pulse_present": False, "pulse_score": 12,
            "estimated_hr": None, "band_energy": 0.0,
            "spectral_concentration": 0.0, "reasons": ["rPPG inactive: no valid frame interval."],
            "not_applicable_reason": "non_contiguous_frames",
        }
        per_window_rppg.append(s_rppg)
        # Temporal residual probe (full-res, neighbor-mean predictor).
        # Runs on every window; metrics are reported per window and threaded to
        # the fusion as a metrics-only signal until calibration is solid. The vote
        # threshold is deliberately conservative (high energy AND spatially
        # unstructured residual) so real motion does not flip reels.
        s_tr = _tr.analyze_temporal_residual(win) if _tr._NP_AVAILABLE else {
            "score": None, "active": False, "reasons": ["Temporal residual probe unavailable."], "metrics": {},
        }
        per_window_tr.append(s_tr)
        # Capture-origin probe (native resolution). The ONLY layer that does not
        # work on the 128px grayscale thumbnail: it measures whether the clip is
        # a rendered image sequence (exactly flat fills + byte-identical image
        # rows), which sensor read noise makes impossible on camera footage.
        s_cap = _capture_origin.analyze_capture_origin(win)
        per_window_cap.append(s_cap)
        # Camera-physics probe (native resolution, metrics-only). Measures the
        # photon-transfer curve / fixed-pattern noise / residual spectrum that a
        # camera sensor imposes and a diffusion render does not. It does NOT vote
        # yet - calibration (scripts/probe_camera_physics.py, 2026-11-11) showed
        # no single statistic separates real from photoreal-AI with a defensible
        # margin on the 7-real-clip corpus - so it surfaces measurements only.
        s_cam = _camera_physics.analyze_camera_physics(win)
        per_window_cam.append(s_cam)
        # Embedding-consistency probe (DINOv2 one-class, the photoreal-diffusion
        # signal). Measures how far each frame sits from a bank of REAL-clip
        # embeddings. Votes SUSPICIOUS (capped 79) when the distance is clearly
        # outside the measured real range - the only signal that separated the 8
        # hyper-real Higgsfield clips from the 7 confirmed-real clips (real max
        # 0.642 vs hyper-real min 0.678, calibrated 2026-11-11).
        s_emb = _embedding.analyze_embedding_consistency(win)
        per_window_emb.append(s_emb)
        window_details.append({
            "frames": len(win),
            "temporal_score": s_temporal.get("score"),
            "pwtf_score": s_pwtf.get("score"),
            "d3_score": s_d3.get("score"),
            "rppg_score": s_rppg.get("score"),
            "rppg_applies": s_rppg.get("applies"),
            "rppg_pulse_present": s_rppg.get("pulse_present"),
            "rppg_estimated_hr": s_rppg.get("estimated_hr"),
            "pwtf_p05_coherence": (s_pwtf.get("metrics") or {}).get("coherence_p05"),
            "d3_volatility": (s_d3.get("metrics") or {}).get("volatility"),
            "spatial_layers_run": False,
            "tr_score": s_tr.get("score"),
            "tr_metrics": s_tr.get("metrics"),
            "tr_reasons": s_tr.get("reasons"),
            "capture_origin_score": s_cap.get("score"),
            "capture_origin_metrics": s_cap.get("metrics"),
            "camera_physics_score": s_cam.get("score"),
            "camera_physics_metrics": s_cam.get("metrics"),
            "embedding_score": s_emb.get("score"),
            "embedding_metrics": s_emb.get("metrics"),
        })

    # Pass 2 - spatial layers (plan v2 Phase 1.5). These used to run ONLY on
    # the first window's middle frame (`if not s1:` guard) - a real blind
    # spot: a regenerated scene in a later shot window was never seen by any
    # spatial layer. They now also run on the strongest-pwtf window (top-2
    # subset of the plan's every-window option, bounding spatial latency),
    # with temporal-first ordering so the selection can use pwtf evidence.
    # The AI-provenance metadata scan is window-independent and runs once.
    s_meta = probe_ai_metadata(raw_bytes=video_bytes or b"", kind="video",
                               source_caption=source_caption, page_context=page_context)

    # Audio track (docs/audio-and-lip-sync-plan.md phase A0). Decoded from the
    # SAME bytes the frames came from - no second download - and reported on a
    # SEPARATE axis: this layer never votes on the video tier, because a
    # synthetic voice over real footage is an audio-AI finding, not a deepfake
    # video (a real clip with a TTS voiceover must not read SYNTHETIC_AI). It
    # abstains honestly when there are no bytes (client-extracted frames carry
    # no container audio) or no audio stream, and never fabricates a reading.
    s_audio = _audio.analyze_audio_track(audio_bytes if audio_bytes is not None else video_bytes)

    active_pwtf_idxs = [
        i for i, s in enumerate(per_window_pwtf)
        if s.get("active") and s.get("score") is not None
    ]
    spatial_idxs = {0}
    if active_pwtf_idxs:
        spatial_idxs.add(max(active_pwtf_idxs, key=lambda i: per_window_pwtf[i]["score"]))

    per_window_spatial = {}
    for idx in sorted(spatial_idxs):
        win = windows[idx]
        mid_frame = win[len(win) // 2]
        w1 = probe_synthid_watermark(mid_frame)
        w2 = probe_c2pa_manifest(mid_frame)
        # include_grid_peaks=False: the GAN-grid rule is H.264-blind on
        # video frames (every decoded frame rings periodically at 512x512
        # - measured ~10 on both real and generated reels).
        w3 = analyze_frequency_domain(mid_frame, include_grid_peaks=False)
        w4 = analyze_neural_and_heatmap(
            "", mid_frame, allow_flat_render_vote=False, include_heatmap=False
        )
        w5 = spai.detect(mid_frame)

        # Pixel forensics: ONLY the known-AI-artwork perceptual fingerprint
        # is allowed to vote on video frames - the flat-render/document
        # signatures detect saturated cartoon/animation STYLE, not
        # generation (calibrated: the flat-render boost fired on 31/61
        # frames of a real hand-drawn animation reel and 0/23 frames of a
        # generated photorealistic clip). A match is carried by the synthid
        # 99 override; the neural layer is never injected a 0 score when it
        # was inactive (a fingerprint match alone leaves it inactive - the
        # override carries that verdict).
        pf_hits = []
        if len(win) >= 3:
            for probe_frame in (win[0], mid_frame, win[-1]):
                pf = _pixel_forensics_img(probe_frame)
                if not pf:
                    continue
                if pf["match_label"]:
                    w1["score"] = 99
                    pf_hits.append(f"Perceptual fingerprint match on video frame: {pf['match_label']}")

        per_window_spatial[idx] = {
            "synthid": w1, "c2pa": w2, "frequency": w3, "neural": w4, "spai": w5,
            "pf_hits": pf_hits,
        }
        window_details[idx]["spatial_layers_run"] = True

    spatial_order = sorted(per_window_spatial)

    def _max_spatial(key):
        vals = [per_window_spatial[i][key].get("score") for i in spatial_order]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None

    # C2PA scores are CLAIMS, not detectors: 99 = confirmed AI manifest,
    # 3 = certified camera capture, 25 = plain EXIF tags, None = absent. A
    # low score is evidence FOR authenticity, so windows aggregate by claim
    # decisiveness (AI > camera > EXIF > none) - a blind max would mask an
    # authentic-capture claim whenever any other window reported absent.
    c2pa_scores = [per_window_spatial[i]["c2pa"].get("score") for i in spatial_order]
    c2pa_present = [v for v in c2pa_scores if v is not None]
    if c2pa_present:
        if 99 in c2pa_present:
            c2pa_score = 99
        elif 3 in c2pa_present:
            c2pa_score = 3
        else:
            c2pa_score = max(c2pa_present)
    else:
        c2pa_score = None

    def _dedup_reasons(lines):
        out, seen = [], set()
        for line in lines:
            if line and line not in seen:
                seen.add(line)
                out.append(line)
        return out

    def _layer_reasons(key):
        return _dedup_reasons(
            [r for i in spatial_order for r in per_window_spatial[i][key].get("reasons", [])]
        )

    pf_reasons = _dedup_reasons(
        [h for i in spatial_order for h in per_window_spatial[i]["pf_hits"]]
    )

    # Representative window for the visual extras (heatmap overlay, SPAI
    # metrics): the analyzed window with the strongest neural reading, so the
    # overlay corresponds to the frame that actually drove the verdict.
    rep_idx = max(
        spatial_order,
        key=lambda i: (per_window_spatial[i]["neural"].get("score") if per_window_spatial[i]["neural"].get("score") is not None else -1),
    )
    rep = per_window_spatial[rep_idx]

    # Strongest-evidence selection for the temporal layers: max score across
    # windows (a real clip scores low everywhere; a locally-regenerated clip
    # scores high in the affected window).
    active_pwtf = [s["score"] for s in per_window_pwtf if s.get("active") and s.get("score") is not None]
    pwtf_score = max(active_pwtf) if active_pwtf else None
    best_pwtf = max(per_window_pwtf, key=lambda s: (s.get("score") if s.get("score") is not None else -1))
    active_temporal = [s["score"] for s in per_window_temporal if s.get("active") and s.get("score") is not None]
    temporal_score = max(active_temporal) if active_temporal else None
    best_temporal = max(per_window_temporal, key=lambda s: (s.get("score") if s.get("score") is not None else -1))
    # D3 is metrics-only: the strongest window's metrics are surfaced, but no
    # score is ever selected (the layer emits None by design).
    best_d3 = max(
        per_window_d3,
        key=lambda s: (s.get("metrics") or {}).get("volatility", -1.0),
    ) if per_window_d3 else None
    best_rppg = max(
        per_window_rppg,
        key=lambda s: (s.get("pulse_score") if s.get("active") else -1),
    ) if per_window_rppg else None

    best_tr = None
    if per_window_tr:
        best_tr = max(per_window_tr, key=lambda s: (s.get("score") or -1))

    # Strongest capture-origin window (a rendered scene can occupy one shot of
    # an otherwise-camera clip; a real clip abstains in every window).
    active_cap = [s["score"] for s in per_window_cap if s.get("score") is not None]
    cap_score = max(active_cap) if active_cap else None
    best_cap = (
        max(per_window_cap, key=lambda s: (s.get("score") if s.get("score") is not None else -1))
        if per_window_cap else None
    )

    # Camera-physics probe: metrics-only, so there is no score to select. Surface
    # the window with the strongest texture-smoothness reading (the statistic
    # that came closest to separating in calibration) for the verdict payload.
    best_cam = (
        max(per_window_cam, key=lambda s: (s.get("metrics") or {}).get("tex_ac1", -1.0))
        if per_window_cam else None
    )

    # Embedding-consistency probe: strongest-window score wins (a regenerated
    # scene can occupy one shot of an otherwise-camera clip).
    active_emb = [s["score"] for s in per_window_emb if s.get("score") is not None]
    emb_score = max(active_emb) if active_emb else None
    best_emb = (
        max(per_window_emb, key=lambda s: (s.get("score") if s.get("score") is not None else -1))
        if per_window_emb else None
    )

    verdict = fuse_ensemble_verdict(
        layers={
            "synthid": _max_spatial("synthid"),
            "c2pa": c2pa_score,
            "metadata": s_meta["score"],
            "frequency": _max_spatial("frequency"),
            "neural": _max_spatial("neural"),
            "spai": _max_spatial("spai"),
            "temporal": temporal_score,
            "pwtf": pwtf_score,
            "rppg": best_rppg.get("score") if best_rppg else None,
            "tr": best_tr.get("score") if best_tr else None,
            "capture_origin": cap_score,
            "embedding": emb_score,
        },
        layer_reasons={
            "synthid": _dedup_reasons(
                [per_window_spatial[i]["synthid"].get("reason") for i in spatial_order]
            ),
            "c2pa": _dedup_reasons(
                [per_window_spatial[i]["c2pa"].get("reason") for i in spatial_order]
            ),
            "metadata": [s_meta["reason"]] if s_meta.get("reason") and s_meta.get("score") is not None else [],
            "frequency": _layer_reasons("frequency"),
            "neural": _layer_reasons("neural") + pf_reasons,
            "spai": _layer_reasons("spai"),
            "temporal": best_temporal.get("reasons", []) if temporal_score is not None else [],
            "pwtf": best_pwtf.get("reasons", []) if pwtf_score is not None else [],
            "d3": best_d3.get("reasons", []) if best_d3 else [],
            "rppg": _dedup_reasons(
                [r for s in per_window_rppg for r in s.get("reasons", []) or []]
            ) if per_window_rppg and any(s.get("active") for s in per_window_rppg) else [],
            "tr": _dedup_reasons(
                [r for s in per_window_tr for r in s.get("reasons", []) or []]
            ) if per_window_tr and any(s.get("active") for s in per_window_tr) else [],
            "capture_origin": _dedup_reasons(
                [r for s in per_window_cap for r in s.get("reasons", []) or []]
            ) if per_window_cap else [],
            "camera_physics": _dedup_reasons(
                [r for s in per_window_cam for r in s.get("reasons", []) or []]
            ) if per_window_cam else [],
            "embedding": _dedup_reasons(
                [r for s in per_window_emb for r in s.get("reasons", []) or []]
            ) if per_window_emb else [],
            # Audio is reported, never scored: these lines document what the
            # audio layer found (and why it abstained when it did) so audio
            # evidence is never silently ignored.
            "audio": _dedup_reasons(s_audio.get("reasons", []) or []),
        },
        is_video=True,
        extra_data={
            "mode": mode,
            "video_source": video_source,
            "frame_interval_seconds": round(frame_interval_seconds, 5) if frame_interval_seconds else None,
            "frames_analyzed": sum(len(w) for w in windows),
            "windows_analyzed": len(windows),
            "window_details": window_details,
            **getattr(windows[0][0], "_rinse_shot_info", {}),
            "frame_scores": (per_window_temporal[0] or {}).get("frame_scores", []),
            "temporal_flicker_energy": best_temporal.get("temporal_flicker_energy", 0.0),
            "motion_residual_variance": best_temporal.get("motion_residual_variance", 0.0),
            "temporal_active": best_temporal.get("active", False),
            "metadata_source": s_meta.get("source"),
            "metadata_markers": s_meta.get("markers", [])[:5],
            "neural_submodels": rep["neural"].get("submodels", {}),
            "pf_hits": _dedup_reasons(
                [h for i in spatial_order for h in per_window_spatial[i].get("pf_hits", [])]
            ) or None,
            "heatmap_grid": rep["neural"].get("heatmap_grid"),
            "heatmap_overlay_base64": rep["neural"].get("heatmap_overlay_base64"),
            "spai_metrics": rep["spai"].get("metrics", {}),
            "pwtf_metrics": best_pwtf.get("metrics", {}),
            "pwtf_spectrum_bins": best_pwtf.get("spectrum_bins", 0),
            "pwtf_frames_analyzed": best_pwtf.get("frames_analyzed", 0),
            "rppg_applies": best_rppg.get("applies") if best_rppg else None,
            "rppg_pulse_present": best_rppg.get("pulse_present") if best_rppg else None,
            "rppg_estimated_hr": best_rppg.get("estimated_hr") if best_rppg else None,
            "rppg_band_energy": best_rppg.get("band_energy") if best_rppg else None,
            "rppg_spectral_concentration": best_rppg.get("spectral_concentration") if best_rppg else None,
            "rppg_not_applicable_reason": best_rppg.get("not_applicable_reason") if best_rppg else None,
            "rppg_active": best_rppg.get("active") if best_rppg else None,
            "rppg_reasons": best_rppg.get("reasons", []) if best_rppg else [],
            "pwtf_coherence_p05": (best_pwtf.get("metrics") or {}).get("coherence_p05"),
            "pwtf_hotspot_fraction": (best_pwtf.get("metrics") or {}).get("hotspot_fraction"),
            "pwtf_anomaly_concentration": (best_pwtf.get("metrics") or {}).get("anomaly_concentration"),
            "pwtf_hotspot_cluster": (best_pwtf.get("metrics") or {}).get("hotspot_cluster"),
            "pwtf_residual_ac1": (best_pwtf.get("metrics") or {}).get("residual_ac1"),
            "pwtf_spectral_flatness": (best_pwtf.get("metrics") or {}).get("spectral_flatness"),
            "d3_metrics": (best_d3.get("metrics") or {}) if best_d3 else {},
            "d3_active": False,  # metrics-only layer; never a vote
            "straighten_metrics": (best_d3.get("straighten_metrics") or {}) if best_d3 else {},
            "tr_score": best_tr.get("score") if best_tr else None,
            "tr_active": best_tr.get("active", False) if best_tr else False,
            "tr_metrics": (best_tr.get("metrics") or {}) if best_tr else {},
            "tr_reasons": best_tr.get("reasons", []) if best_tr else [],
            "camera_physics_metrics": (best_cam.get("metrics") or {}) if best_cam else {},
            "camera_physics_reasons": (best_cam.get("reasons", []) if best_cam else []),
            "embedding_score": emb_score,
            "embedding_metrics": (best_emb.get("metrics") or {}) if best_emb else {},
            "embedding_reasons": (best_emb.get("reasons", []) if best_emb else []),
            # Temporal coverage sweep (see _temporal_coverage_sweep): how much of
            # the clip - beyond the primary shot window - shows a coherence-floor
            # collapse or a temporal-residual fire. Reported per window, and used
            # by the voter only when the evidence REPEATS across the clip
            # (an isolated collapse window is normal on real footage).
            "temporal_coverage": coverage or {},
            # Audio-track block (phase A0; metrics-only, separate axis - see the
            # s_audio note above). Its score is always None, so it cannot move
            # the video verdict; A1/A3 add av_sync + synthetic-speech siblings.
            "audio": s_audio,
        },
    )
    return verdict


def _decode_proxy_original_url(url):
    """Decode the original image URL embedded in a search-engine image-proxy URL.

    Search-result proxies (e.g. https://imgs.search.brave.com/<sig>/rs:fit:.../
    g:ce/aHR0cHM6Ly9...) carry the source URL base64url-encoded in the last path
    segment. The proxy hosts hotlink-block non-browser clients (403 for any
    server-side fetch), while the original source usually allows it — so a
    failed proxy download is retried against the decoded original.
    Returns the original http(s) URL, or None when the URL is not a recognizable
    proxy pattern or the payload does not decode.
    """
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if host != "imgs.search.brave.com":
            return None
        segments = [s for s in parsed.path.split("/") if s]
        if not segments:
            return None
        b64 = segments[-1]
        if len(b64) < 16:
            return None
        # base64url with missing padding
        decoded = base64.urlsafe_b64decode((b64 + "=" * (-len(b64) % 4)).encode("ascii")).decode("utf-8", "strict")
        if decoded.startswith("http://") or decoded.startswith("https://"):
            return decoded
    except Exception:
        return None
    return None


def _download_image_bytes(url, timeout=15):
    """Stream an image URL to bytes with a size cap. Raises on failure."""
    headers = {"User-Agent": "RINSEAuthenticityDetector/2.0"}
    resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
    if not resp.ok:
        resp.close()
        raise requests.HTTPError(f"HTTP {resp.status_code} for {url}")
    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            resp.close()
            raise ValueError("Image download too large.")
        chunks.append(chunk)
    resp.close()
    return b"".join(chunks)


def _load_image_bytes(data):
    """Extract/download the raw image bytes WITHOUT decoding them.

    The exact cache key is `sha256(namespace + raw_bytes)`, so a cached scan
    only needs the bytes. Keeping this separate from the PIL decode lets the
    endpoints answer a hit before paying base64 decode + PNG decode + a temp
    file write (measured ~14 ms for a 0.4MB PNG on the dev machine).

    Returns: (raw_bytes, error_tuple).
    """
    image_url = data.get("image_url")
    image_base64 = data.get("image_base64")

    if not image_url and not image_base64:
        return None, (jsonify({"error": "No image source provided. Set 'image_url' or 'image_base64'."}), 400)

    if image_base64 and len(image_base64) > MAX_IMAGE_BYTES * 2:
        return None, (jsonify({"error": "Image payload too large."}), 413)

    try:
        if image_base64:
            if "," in image_base64:
                image_base64 = image_base64.split(",")[1]
            raw_bytes = base64.b64decode(image_base64)
            if len(raw_bytes) > MAX_IMAGE_BYTES:
                return None, (jsonify({"error": "Image payload exceeds 20MB limit."}), 413)
            return raw_bytes, None

        parsed = urlparse(image_url)
        if parsed.scheme not in ("http", "https"):
            return None, (jsonify({"error": "Invalid image URL: only http(s) sources are allowed."}), 400)
        # Hotlink-protected proxies (Brave image search etc.) reject any
        # server-side fetch with 403, while the original source usually
        # allows it. When the proxy URL embeds the original source URL
        # (base64url in the path), try the original first, then the proxy
        # URL as given. A failure of every candidate raises to the outer
        # handler, which reports the error honestly.
        candidates = []
        decoded_original = _decode_proxy_original_url(image_url)
        if decoded_original:
            candidates.append(decoded_original)
        candidates.append(image_url)

        last_err = None
        for candidate in candidates:
            try:
                # Source-fetch cache: the same meme URL is often scanned by many
                # users; skip the network download when we fetched it recently.
                if scan_cache is not None:
                    cached = scan_cache.get_fetch(candidate)
                    if cached is not None:
                        return cached, None
                raw_bytes = _download_image_bytes(candidate)
                if scan_cache is not None:
                    scan_cache.store_fetch(candidate, raw_bytes)
                return raw_bytes, None
            except Exception as e:
                last_err = e
        raise last_err if last_err else RuntimeError("Image download failed.")
    except Exception as e:
        return None, (jsonify({"error": f"Failed to load image: {str(e)}"}), 400)


def _decode_image_bytes(raw_bytes):
    """Decode raw image bytes into a PIL RGB image plus a temp-file path.

    Returns: (img, temp_file_path). Raises on undecodable bytes.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
        f.write(raw_bytes)
        temp_file = f.name
    try:
        img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
        return img, temp_file
    except Exception:
        try:
            os.remove(temp_file)
        except Exception:
            pass
        raise


def _load_image_from_payload(data):
    """
    Safely extract PIL Image, raw bytes, and optional temp file from JSON payload.
    Returns: (img, raw_bytes, temp_file_path, error_tuple)
    """
    raw_bytes, err = _load_image_bytes(data)
    if err is not None:
        return None, None, None, err
    try:
        img, temp_file = _decode_image_bytes(raw_bytes)
        return img, raw_bytes, temp_file, None
    except Exception as e:
        return None, None, None, (jsonify({"error": f"Failed to load image: {str(e)}"}), 400)


# ---------------------------------------------------------------------------
# Scan cache helpers (exact sha256 + near-dup dHash reuse; see plan §3)
# ---------------------------------------------------------------------------

def _serve_exact_hit(hit: dict):
    """Add the fields a cache hit reports, exactly like a normal lookup."""
    age_s = int(time.time() - hit.pop("_cached_at", time.time()))
    hit["cached"] = "exact"
    if age_s >= 0:
        hit["cache_age_s"] = age_s
    return hit


def _image_exact_hit(raw_bytes: bytes, key_namespace: str, no_cache: bool = False):
    """Exact cache lookup that needs only the raw bytes - no PIL decode.

    Used before `_decode_image_bytes` so a repeat scan never pays the 10-15 ms
    decode (plus temp-file write) for a verdict we already have.
    """
    if not _CACHE_ENABLED or no_cache or scan_cache is None:
        return None
    key = hashlib.sha256(
        key_namespace.encode("utf-8") + b"\x00" + raw_bytes
    ).hexdigest()
    hit = scan_cache.get_verdict_exact(key)
    return _serve_exact_hit(hit) if hit is not None else None


def _cache_lookup_or_run(
    raw_bytes: bytes,
    kind: str,
    run_fn,
    dhash_img=None,
    no_cache: bool = False,
    key_namespace: str = None,
    exact_prechecked: bool = False,
):
    """Exact/near-dup cache lookup; on miss runs the pipeline and stores.

    run_fn must return (verdict_dict, http_status) — plain dicts, not Flask
    responses (the endpoint jsonifies the result). The verdict dict gains a
    top-level "cached" field: False (fresh), "exact", or "near".
    Returns (verdict_dict, http_status).
    """
    if not _CACHE_ENABLED or no_cache or scan_cache is None:
        resp, status = run_fn()
        if isinstance(resp, dict):
            resp["cached"] = False
        return resp, status

    # Key = sha256(namespace + NUL + raw bytes): fast/deep/video scans of the
    # same content get separate entries. `kind` stays 'image'/'video' (the SQL
    # layer filters on it); the near-dup layer deliberately matches across
    # scan depths — decisive verdicts only (plan §3.2).
    ns = key_namespace or kind
    key = hashlib.sha256(ns.encode("utf-8") + b"\x00" + raw_bytes).hexdigest()

    # Layer 1: exact bytes. The image endpoints already checked this before
    # decoding, so they skip the duplicate lookup on a miss.
    if not exact_prechecked:
        hit = scan_cache.get_verdict_exact(key)
        if hit is not None:
            return _serve_exact_hit(hit), 200

    # Layer 2: near-duplicate (dHash) — decisive verdicts only
    if dhash_img is not None:
        try:
            dh = _dhash(dhash_img)
            near = scan_cache.get_verdict_near(dh)
            if near is not None:
                payload, similar_key = near
                age_s = int(time.time() - payload.pop("_cached_at", time.time()))
                payload["cached"] = "near"
                payload["similar_to"] = similar_key
                if age_s >= 0:
                    payload["cache_age_s"] = age_s
                return payload, 200
        except Exception as e:  # noqa: BLE001
            print(f"Cache near-lookup failed (running full scan): {e}")

    # Miss — run the real pipeline.
    resp, status = run_fn()

    # Only cache successful verdicts (and store them WITHOUT the "cached"
    # marker; hits re-add "cached": "exact"/"near" on retrieval).
    if status == 200 and isinstance(resp, dict) and "score" in resp:
        try:
            dh = _dhash(dhash_img) if dhash_img is not None else None
            # Stamp the stored verdict so cache_age_s can be reported on hit.
            stored = dict(resp)
            stored["_cached_at"] = time.time()
            scan_cache.store_verdict(key, kind, stored, dh)
        except Exception as e:  # noqa: BLE001
            print(f"Cache store failed: {e}")

    if isinstance(resp, dict):
        resp["cached"] = False
    return resp, status


def _no_cache_requested(data: dict) -> bool:
    return bool(data.get("no_cache"))


_SCAN_LOG_QUEUE: "queue.Queue[dict]" = queue.Queue(maxsize=4096)
_SCAN_LOG_WORKER: threading.Thread | None = None
_SCAN_LOG_LOCK = threading.Lock()


def _scan_log_worker() -> None:
    """Drain queued scan rows off the request path.

    SQLite has one writer, so doing a synchronous INSERT + commit per scan
    serialises every request behind the log under load. The response no
    longer waits for the row to hit disk; `/scans/*` can lag by milliseconds.
    """
    while True:
        kwargs = _SCAN_LOG_QUEUE.get()
        try:
            if scan_log is not None:
                scan_log.log_scan(**kwargs)
        except Exception as e:  # noqa: BLE001
            print(f"Scan log write failed (scan unaffected): {e}")
        finally:
            _SCAN_LOG_QUEUE.task_done()


def _flush_scan_log(timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while _SCAN_LOG_QUEUE.unfinished_tasks and time.time() < deadline:
        time.sleep(0.02)


def _start_scan_log_worker() -> None:
    global _SCAN_LOG_WORKER
    if _SCAN_LOG_WORKER is not None:
        return
    with _SCAN_LOG_LOCK:
        if _SCAN_LOG_WORKER is not None:
            return
        atexit.register(_flush_scan_log)
        thread = threading.Thread(
            target=_scan_log_worker, name="scan-log-writer", daemon=True
        )
        thread.start()
        _SCAN_LOG_WORKER = thread


def _record_scan(
    kind: str,
    source: str,
    verdict,
    status: int = 200,
    *,
    cached=None,
    excerpt: str | None = None,
    content=None,
    source_url: str | None = None,
    started: float | None = None,
) -> None:
    """Queue one scan-log row. Best-effort: never affects the response.

    `content` is hashed on the request thread but not retained; the row itself
    is written by a background thread so a slow disk or a busy SQLite writer
    cannot add latency to a scan.
    """
    if scan_log is None:
        return
    try:
        forwarded = request.headers.get("X-Forwarded-For") or request.remote_addr
        digest = None
        if isinstance(content, bytes) and content:
            digest = hashlib.sha256(content).hexdigest()
        elif isinstance(content, str) and content:
            digest = hashlib.sha256(content.encode("utf-8", "ignore")).hexdigest()
        row = dict(
            kind=kind,
            verdict=verdict if isinstance(verdict, dict) else None,
            source=source,
            status=status,
            cached=cached,
            excerpt=excerpt,
            content_sha256=digest,
            content_chars=len(content) if isinstance(content, (bytes, str)) else None,
            source_url=source_url,
            ip=forwarded,
            user_agent=request.headers.get("User-Agent"),
            latency_ms=(time.time() - started) * 1000 if started else None,
        )
        _start_scan_log_worker()
        try:
            _SCAN_LOG_QUEUE.put_nowait(row)
        except queue.Full:
            # Under extreme load, drop the log row rather than the scan.
            pass
    except Exception as e:  # noqa: BLE001
        print(f"Scan log skipped ({source}): {e}")


def _video_cache_bytes(data: dict):
    """Deterministic exact-cache key material for a video payload.

    video_base64 -> the (data-URI prefix stripped) base64 string; video_url ->
    the URL string (direct links are stable enough content addresses for the
    cache's 30-day TTL); frames_base64 -> the joined frame strings. Returns
    None when the payload carries no recognizable video source. Video caching
    is exact-key only — no perceptual near-dup layer (plan §3.4).
    """
    video_b64 = data.get("video_base64") or ""
    if video_b64:
        payload = video_b64.split(",", 1)[-1] if "," in video_b64 else video_b64
        return payload.encode("utf-8", "ignore")
    video_url = data.get("video_url") or ""
    if video_url:
        return ("url:" + video_url).encode("utf-8", "ignore")
    frames = data.get("frames_base64")
    if isinstance(frames, list) and frames:
        return "\n".join(str(f) for f in frames).encode("utf-8", "ignore")
    return None


def _run_video_deep(data):
    """Full video deep pipeline; returns (verdict_dict, http_status)."""
    window_list, frame_interval, info, video_err = _load_video_frames(data)
    if video_err:
        err_resp, err_status = video_err
        return err_resp.get_json(), err_status

    # Container bytes the audio layer decodes from: the same download/upload the
    # frames came from (popped so the private key never reaches a verdict).
    audio_bytes = (info or {}).pop("_raw_video_bytes", None)

    # Raw bytes for the container-metadata scan: video_base64 decodes them
    # again cheaply; URL/frames payloads have none (the resolver already
    # captured the source caption for URL payloads).
    video_bytes = None
    video_b64 = data.get("video_base64") or ""
    if video_b64:
        try:
            payload = video_b64.split(",", 1)[-1] if "," in video_b64 else video_b64
            video_bytes = base64.b64decode(payload)
        except Exception:
            video_bytes = None
    caption = str(data.get("source_caption") or "")
    page_context = str(data.get("page_context") or "")
    if not caption and not page_context and (data.get("video_url") or ""):
        caption, page_context = _ytdlp_provenance(_LAST_VIDEO_PAGE_INFO)

    # Temporal coverage sweep: only meaningful for contiguous native-rate
    # server-side windows (client frame galleries have no reliable interval).
    coverage = {}
    if frame_interval is not None:
        coverage = _temporal_coverage_sweep(
            audio_bytes if audio_bytes is not None else video_bytes,
            (info or {}).get("window_starts") or (),
        )

    # If single image provided as fallback
    if not window_list:
        img, _, temp_file, err = _load_image_from_payload(data)
        if err:
            err_resp, err_status = err
            return err_resp.get_json(), err_status
        window_list = [[img]]
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

    try:
        return _analyze_video_frames(
            window_list,
            mode="video_deep",
            frame_interval_seconds=frame_interval,
            video_source="server" if frame_interval is not None else "client",
            video_bytes=video_bytes,
            source_caption=caption,
            page_context=page_context,
            audio_bytes=audio_bytes,
            coverage=coverage,
        ), 200
    except Exception as e:
        print(f"Video analysis error: {e}")
        return {
            "score": 50,
            "confidence": "LOW",
            "tier": "INCONCLUSIVE",
            "reasons": [f"Video deep forensic analysis error: {str(e)}"],
            "short_label": "No clear alteration or AI artifacts detected",
            "alteration": {"label": "unlikely", "score": 12, "short_label": "No clear alteration evidence", "reasons": [f"Video deep forensic analysis error: {str(e)}"]},
            "ai_artifact": {"label": "unlikely", "score": 12, "short_label": "No clear AI-artifact evidence", "reasons": [f"Video deep forensic analysis error: {str(e)}"]},
        }, 500


def _video_context_cache_key(data: dict, caption: str, page_context: str) -> str:
    """Stable suffix for the video-deep cache namespace derived from the
    provenance channels actually used for the verdict.

    For URL payloads the provenance is resolved server-side from the yt-dlp
    page info (caption + page_context from _ytdlp_provenance), so the cache
    identity must include those resolved strings; otherwise two requests for
    the same video_url with different surrounding page text would incorrectly
    share a cached verdict.

    Collision-resistant: sha256 truncated to 16 hex chars; '-nocontext' when
    no provenance was used.
    """
    import hashlib as _hashlib
    parts = {
        "cap": caption,
        "ctx": page_context,
        "body_cap": str(data.get("source_caption") or ""),
        "body_ctx": str(data.get("page_context") or ""),
    }
    if not any(parts.values()):
        return "-nocontext"
    blob = "\n".join(f"{k}\x1f{v}" for k, v in sorted(parts.items()))
    return "-ctx-" + _hashlib.sha256(blob.encode("utf-8", "ignore")).hexdigest()[:16]


def _cached_video_deep(data):
    """Video deep path with exact-hash scan caching (no near-dup layer).

    The cache key is computed from the payload itself, so an exact hit skips
    the (expensive) frame download/decode entirely.
    """
    started = time.time()
    key_bytes = _video_cache_bytes(data)
    if key_bytes is None:
        resp, status = _run_video_deep(data)
        if isinstance(resp, dict):
            resp["cached"] = False
        _record_scan(
            "video", "video/deep", resp, status,
            source_url=data.get("video_url"), started=started,
        )
        return jsonify(resp), status

    resp, status = _cache_lookup_or_run(
        key_bytes, "video", lambda: _run_video_deep(data),
        dhash_img=None, no_cache=_no_cache_requested(data),
        key_namespace="video:deep" + _video_context_cache_key(
            data,
            str(data.get("source_caption") or ""),
            str(data.get("page_context") or ""),
        ),
    )
    _record_scan(
        "video", "video/deep", resp, status,
        cached=resp.get("cached") if isinstance(resp, dict) else None,
        content=key_bytes, source_url=data.get("video_url"), started=started,
    )
    return jsonify(resp), status


def _image_page_context(data: dict):
    """Extract page-declared AI-provenance context from an image payload.

    Accepts (all optional):
      alt_text      the <img> alt / title / figcaption label for THIS asset
      page_title    the document.title of the page hosting the image
      source_caption  a post caption or page text supplied by the caller
      page_url      the page (not image) URL - scanned as a LABEL source
      page_context  pre-extracted surrounding post/article text

    The caption channel keeps its existing strong semantics (a caption naming
    a generator scores 75 -> voter escalation). Alt text scores the same way:
    it is the page's own label for this specific asset. Page title + URL +
    surrounding text are CONTEXT: their weak markers count toward the
    weak-marker rule and their strong tool names add one weak vote, but they
    can never produce a synthetic-band verdict on their own (a news article
    ABOUT AI tools is not evidence its photos are AI).

    Returns (alt_text, page_context) for probe_ai_metadata, where
    page_context is the joined title + page_url + page_context + caption
    corpus (the caption ALSO rides its own dedicated channel below).
    """
    alt = str(data.get("alt_text") or "")
    caption = str(data.get("source_caption") or "")
    context_parts = [
        str(data.get("page_title") or ""),
        str(data.get("page_url") or ""),
        str(data.get("page_context") or ""),
    ]
    page_context = " ".join(p for p in context_parts if p)
    return alt, page_context


def _image_context_cache_key(data: dict) -> str:
    """Stable suffix for image cache namespaces derived from page context.

    The cached verdict depends on the pixels AND on the page context sent
    with them (a caption naming a generator changes the verdict), so the
    context must be part of the cache identity. Collision-resistant for
    context strings: sha256 truncated to 16 hex chars; '-nocontext' when no
    context was supplied.
    """
    import hashlib as _hashlib
    parts = {
        "alt": str(data.get("alt_text") or ""),
        "cap": str(data.get("source_caption") or ""),
        "title": str(data.get("page_title") or ""),
        "url": str(data.get("page_url") or ""),
        "ctx": str(data.get("page_context") or ""),
    }
    if not any(parts.values()):
        return "-nocontext"
    blob = "\n".join(f"{k}\x1f{v}" for k, v in sorted(parts.items()))
    return "-ctx-" + _hashlib.sha256(blob.encode("utf-8", "ignore")).hexdigest()[:16]


@app.route("/health", methods=["GET"])
@app.route("/v1/health", methods=["GET"])
def health():
    """Lightweight health probe used by the extension's dev tools to confirm
    backend connectivity, latency, and which detectors are live."""
    storyscope_mode = os.environ.get("STORYSCOPE_MODE", "heuristic")
    return jsonify({
        "status": "ok",
        "server": "RINSE Cloud Detector",
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - SERVER_START_TIME, 1),
        "mode": storyscope_mode,
        "llm_enabled": bool(os.environ.get("STORYSCOPE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "detectzoo_loaded": DETECTZOO_AVAILABLE,
        "characters_loaded": _CHARACTERS_AVAILABLE,
        "cache_enabled": _CACHE_ENABLED,
        "scan_log_enabled": bool(scan_log is not None and scan_log.ENABLED),
        "auth_required": bool(API_KEY),
        "layers": ["synthid", "c2pa", "frequency", "neural", "learned", "temporal", "pwtf", "d3"],
        "endpoints": [
            "/predict", "/predict/image/fast", "/predict/image/deep",
            "/predict/video/deep", "/predict/storyscope", "/predict/text/dna",
            "/cache/stats", "/cache/clear",
            "/scans/stats", "/scans/recent", "/scans/export"
        ],
        "timestamp": time.time()
    })


@app.route("/cache/stats", methods=["GET"])
def cache_stats_endpoint():
    """Aggregate scan-cache statistics (auth-gated)."""
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401
    if not _CACHE_ENABLED or scan_cache is None:
        return jsonify({"error": "Scan cache is disabled."}), 503
    try:
        return jsonify(scan_cache.cache_stats())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Cache stats failed: {e}"}), 500


@app.route("/cache/clear", methods=["POST"])
def cache_clear_endpoint():
    """Wipe all cached verdicts + fetches (auth-gated)."""
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401
    if not _CACHE_ENABLED or scan_cache is None:
        return jsonify({"error": "Scan cache is disabled."}), 503
    try:
        return jsonify(scan_cache.cache_clear())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Cache clear failed: {e}"}), 500


@app.route("/scans/stats", methods=["GET"])
def scans_stats_endpoint():
    """Scan-log statistics: totals by mode/tier, human-likely counts (auth-gated)."""
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401
    if scan_log is None or not scan_log.ENABLED:
        return jsonify({"error": "Scan log is disabled."}), 503
    try:
        return jsonify(scan_log.stats())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Scan log stats failed: {e}"}), 500


@app.route("/scans/recent", methods=["GET"])
def scans_recent_endpoint():
    """Newest logged scans (auth-gated).

    Query params:
      limit=50          rows to return (max 500)
      kind=text|image|video
      human=1           only verdicts that cleared as human / authentic
      include_text=1    include the stored text excerpt
      since=<epoch>     only scans at or after this Unix timestamp
    """
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401
    if scan_log is None or not scan_log.ENABLED:
        return jsonify({"error": "Scan log is disabled."}), 503

    kind = (request.args.get("kind") or "").lower().strip() or None
    if kind and kind not in ("text", "image", "video"):
        return jsonify({"error": "kind must be text, image, or video."}), 400
    try:
        limit = int(request.args.get("limit") or 50)
    except ValueError:
        return jsonify({"error": "limit must be an integer."}), 400
    since_raw = request.args.get("since")
    try:
        since = float(since_raw) if since_raw else None
    except ValueError:
        return jsonify({"error": "since must be a Unix timestamp."}), 400

    try:
        rows = scan_log.recent(
            limit,
            kind=kind,
            human_only=bool(request.args.get("human") in ("1", "true", "yes")),
            include_text=bool(request.args.get("include_text") in ("1", "true", "yes")),
            since=since,
        )
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Scan log read failed: {e}"}), 500
    return jsonify({"count": len(rows), "scans": rows})


@app.route("/scans/export", methods=["GET"])
def scans_export_endpoint():
    """Download matching scan-log rows as JSON Lines (auth-gated).

    This is how the log leaves a deployed instance that has no shell: run

        curl -H "Authorization: Bearer $API_KEY" \
          "$BASE/scans/export?human=1&kind=text" -o human-corpus.jsonl

    Query params mirror /scans/recent: kind, human=1, since=<epoch>,
    include_verdict=1. Unlike /scans/recent there is no row cap — the whole
    match is streamed, one JSON object per line.
    """
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401
    if scan_log is None or not scan_log.ENABLED:
        return jsonify({"error": "Scan log is disabled."}), 503

    kind = (request.args.get("kind") or "").lower().strip() or None
    if kind and kind not in ("text", "image", "video"):
        return jsonify({"error": "kind must be text, image, or video."}), 400
    since_raw = request.args.get("since")
    try:
        since = float(since_raw) if since_raw else None
    except ValueError:
        return jsonify({"error": "since must be a Unix timestamp."}), 400

    human_only = request.args.get("human") in ("1", "true", "yes")
    include_verdict = request.args.get("include_verdict") in ("1", "true", "yes")

    def stream():
        try:
            for item in scan_log.iter_rows(
                kind=kind,
                human_only=human_only,
                since=since,
                include_verdict=include_verdict,
            ):
                yield json.dumps(item, ensure_ascii=False) + "\n"
        except Exception as e:  # noqa: BLE001
            # Headers are already sent; emit a final line instead of a 500.
            print(f"Scan log export stream failed: {e}")
            yield json.dumps({"error": f"export interrupted: {e}"}) + "\n"

    stamp = time.strftime("%Y%m%d-%H%M", time.gmtime())
    return Response(
        stream(),
        mimetype="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="rinse-scans-{stamp}.jsonl"',
            "Cache-Control": "no-store",
        },
    )





@app.route("/predict/synthid/probe", methods=["GET", "POST"])
def predict_synthid_probe():
    """Layer 1 standalone probe endpoint."""
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401

    data = request.get_json() if request.is_json else request.args.to_dict()
    img, raw_bytes, temp_file, err = _load_image_from_payload(data)
    if err:
        return err

    try:
        synthid_res = probe_synthid_watermark(img)
        return jsonify(synthid_res)
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


@app.route("/predict/image/fast", methods=["POST"])
def predict_image_fast():
    """Fast path (<100ms): Evaluates Layers 1 (SynthID), 2 (C2PA), and 3 (Frequency Forensics)."""
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401

    started = time.time()
    data = request.get_json() or {}
    raw_bytes, err = _load_image_bytes(data)
    if err:
        return err

    namespace = "image:fast" + _image_context_cache_key(data)
    # Repeat scans are answered from the bytes alone: no PIL decode and no
    # temp file before the cache is consulted.
    hit = _image_exact_hit(raw_bytes, namespace, _no_cache_requested(data))
    if hit is not None:
        _record_scan(
            "image", "image/fast", hit, 200,
            cached=hit.get("cached"), content=raw_bytes,
            source_url=data.get("image_url"), started=started,
        )
        return jsonify(hit), 200

    try:
        img, temp_file = _decode_image_bytes(raw_bytes)
    except Exception as e:
        return jsonify({"error": f"Failed to load image: {str(e)}"}), 400

    def _run_fast():
        try:
            s1 = probe_synthid_watermark(img)
            s2 = probe_c2pa_manifest(img, raw_bytes=raw_bytes)
            alt_text, page_context = _image_page_context(data)
            s_meta = probe_ai_metadata(img=img, raw_bytes=raw_bytes, kind="image",
                                       source_url=(data.get("image_url") or ""),
                                       source_caption=(data.get("source_caption") or ""),
                                       alt_text=alt_text,
                                       page_context=page_context)
            s3 = analyze_frequency_domain(img)
            s5 = spai.detect(img)

            # Character fingerprint match (cheap, <1ms, runs even on the fast
            # path — a confirmed character match forces the verdict to AI).
            fast_character_match = None
            if _CHARACTERS_AVAILABLE:
                cm = characters_mod.match_character(img)
                if cm and cm["match_strength"] in ("exact", "likely"):
                    fast_character_match = cm
                    s1["score"] = 99

            verdict = fuse_ensemble_verdict(
                layers={
                    "synthid": s1["score"],
                    "c2pa": s2["score"],
                    "metadata": s_meta["score"],
                    "frequency": s3["score"],
                    "neural": None,
                    "spai": s5["score"]
                },

                layer_reasons={
                    "synthid": [s1["reason"]] if s1.get("reason") else [],
                    "c2pa": [s2["reason"]] if s2.get("reason") else [],
                    "metadata": [s_meta["reason"]] if s_meta.get("reason") and s_meta.get("score") is not None else [],
                    "frequency": s3.get("reasons", []),
                    "spai": s5.get("reasons", [])
                },
                is_video=False,
                extra_data={
                    "mode": "fast",
                    "frequency_metrics": s3.get("metrics", {}),
                    "spai_metrics": s5.get("metrics", {}),
                    "metadata_source": s_meta.get("source"),
                    "metadata_markers": s_meta.get("markers", [])[:5],
                    **({"character_match": fast_character_match} if fast_character_match else {})
                }
            )
            return verdict, 200
        finally:
            # Covers the cache-miss path; the endpoint-level finally below
            # covers cache hits (where this closure never runs). Idempotent.
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    # Temp-file cleanup must wrap the cache call too: on an exact/near cache
    # hit the closure never runs, so its inner finally would never fire.
    try:
        resp, status = _cache_lookup_or_run(
            raw_bytes, "image", _run_fast, dhash_img=img,
            no_cache=_no_cache_requested(data),
            key_namespace=namespace,
            exact_prechecked=True,
        )
        _record_scan(
            "image", "image/fast", resp, status,
            cached=resp.get("cached") if isinstance(resp, dict) else None,
            content=raw_bytes, source_url=data.get("image_url"), started=started,
        )
        return jsonify(resp), status
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


@app.route("/predict/image/deep", methods=["POST"])
@app.route("/predict", methods=["POST"])
@app.route("/v1/predict", methods=["POST"])
def predict_image_deep():
    """Deep path: Evaluates all 4 image layers (SynthID, C2PA, Frequency, Neural & ViT Patch Heatmap)."""
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401

    data = request.get_json() or {}

    # A frames_base64 / video_base64 / video_url payload means the caller sent
    # a video clip instead of a still image - run the full video deep path
    # (spatial layers on sampled frames + temporal coherence + PwTF-DVD pixel-
    # wise temporal frequency) so the standard /predict endpoint handles both
    # media types.
    frames_b64 = data.get("frames_base64") or []
    video_b64 = data.get("video_base64") or ""
    video_url = data.get("video_url") or ""
    is_video_payload = bool(
        video_b64 or video_url or (isinstance(frames_b64, list) and any(frames_b64))
    )
    if is_video_payload:
        return _cached_video_deep(data)

    started = time.time()
    raw_bytes, err = _load_image_bytes(data)
    if err:
        return err

    namespace = "image:deep" + _image_context_cache_key(data)
    # Answer an exact hit before decoding: the cache key is the bytes.
    hit = _image_exact_hit(raw_bytes, namespace, _no_cache_requested(data))
    if hit is not None:
        _record_scan(
            "image", "image/deep", hit, 200,
            cached=hit.get("cached"), content=raw_bytes,
            source_url=data.get("image_url"), started=started,
        )
        return jsonify(hit), 200

    try:
        img, temp_file = _decode_image_bytes(raw_bytes)
    except Exception as e:
        return jsonify({"error": f"Failed to load image: {str(e)}"}), 400

    def _run_deep():
        try:
            # Layer 1: SynthID
            s1 = probe_synthid_watermark(img)
            # Layer 2: C2PA
            s2 = probe_c2pa_manifest(img, raw_bytes=raw_bytes)
            # Layer 2b: AI-provenance metadata (file/container/URL markers +
            # page-declared labels: caption, alt text, page title/URL).
            alt_text, page_context = _image_page_context(data)
            s_meta = probe_ai_metadata(img=img, raw_bytes=raw_bytes, kind="image",
                                       source_url=(data.get("image_url") or ""),
                                       source_caption=(data.get("source_caption") or ""),
                                       alt_text=alt_text,
                                       page_context=page_context)
            # Layer 3: Frequency Forensics
            s3 = analyze_frequency_domain(img)
            # Layer 4: Semantic Neural Classifier & ViT Patch Heatmap
            s4 = analyze_neural_and_heatmap(
                temp_file, img, include_heatmap=bool(data.get("include_heatmap"))
            )
            # Layer 5: SPAI Spectral Analysis (CVPR 2025)
            s5 = spai.detect(img)
            # Layer 6: dataset-trained classifier (CLIP render head + pixel-
            # statistics photo head). The off-the-shelf CNNSpot layer above is
            # blind to viral brainrot renders; this layer is trained on the
            # local Dataset/ corpus. Returns score None when unavailable.
            s_learn = analyze_learned_image(img)

            # Pixel forensics & known fingerprints supplement
            pf = _pixel_forensics(temp_file) if temp_file else None
            pf_reasons = []
            pf_strong = False
            character_match = None
            if pf:
                if pf["match_label"]:
                    s1["score"] = 99
                    pf_reasons.append(f"Perceptual fingerprint match: {pf['match_label']}")
                if pf["boost"] and (s4["score"] is None or s4["score"] < pf["boost"]):
                    s4["score"] = pf["boost"]
                    pf_reasons.append(pf["reason"])
                if pf["doc_boost"] and (s4["score"] is None or s4["score"] < pf["doc_boost"]):
                    s4["score"] = pf["doc_boost"]
                    pf_reasons.append(pf["doc_reason"])
                character_match = pf.get("character_match")
                # Strong render signatures (saturated 3/3 or muted 4/4) are
                # decisive structural evidence - see the pf_strong floor in
                # forensics/voter.py. 60-boost moderate signatures stay in the
                # weighted average only.
                pf_strong = bool(pf["boost"] and pf["boost"] >= 70)

            neural_reasons = s4.get("reasons", []) + pf_reasons

            verdict = fuse_ensemble_verdict(
                layers={
                    "synthid": s1["score"],
                    "c2pa": s2["score"],
                    "metadata": s_meta["score"],
                    "frequency": s3["score"],
                    "neural": s4["score"],
                    "spai": s5["score"],
                    "learned": s_learn.get("score")
                },
                layer_reasons={
                    "synthid": [s1["reason"]] if s1.get("reason") else [],
                    "c2pa": [s2["reason"]] if s2.get("reason") else [],
                    "metadata": [s_meta["reason"]] if s_meta.get("reason") and s_meta.get("score") is not None else [],
                    "frequency": s3.get("reasons", []),
                    "neural": neural_reasons,
                    "spai": s5.get("reasons", []),
                    "learned": s_learn.get("reasons", [])
                },
                is_video=False,
                extra_data={
                    "mode": "deep",
                    "heatmap_grid": s4.get("heatmap_grid"),
                    "heatmap_overlay_base64": s4.get("heatmap_overlay_base64"),
                    "synthetic_patches_count": s4.get("synthetic_patches_count", 0),
                    "neural_submodels": s4.get("submodels", {}),
                    "frequency_metrics": s3.get("metrics", {}),
                    "spai_metrics": s5.get("metrics", {}),
                    "learned_metrics": s_learn.get("metrics", {}),
                    "metadata_source": s_meta.get("source"),
                    "metadata_markers": s_meta.get("markers", [])[:5],
                    **({"pf_strong": True} if pf_strong else {}),
                    **({"character_match": character_match} if character_match else {})
                }
            )
            return verdict, 200
        except Exception as e:
            print(f"Error handling deep prediction: {e}")
            return {
                "score": 50,
                "confidence": "LOW",
                "tier": "INCONCLUSIVE",
                "short_label": "No clear alteration or AI artifacts detected",
                "alteration": {"label": "unlikely", "score": 12, "short_label": "No clear alteration evidence", "reasons": [f"Deep forensic scan error: {str(e)}"]},
                "ai_artifact": {"label": "unlikely", "score": 12, "short_label": "No clear AI-artifact evidence", "reasons": [f"Deep forensic scan error: {str(e)}"]},
            }, 500

    # Temp-file cleanup wraps the cache call: on an exact/near cache hit the
    # closure never runs, so cleanup must happen at the endpoint level.
    try:
        resp, status = _cache_lookup_or_run(
            raw_bytes, "image", _run_deep, dhash_img=img,
            no_cache=_no_cache_requested(data),
            key_namespace=namespace,
            exact_prechecked=True,
        )
        _record_scan(
            "image", "image/deep", resp, status,
            cached=resp.get("cached") if isinstance(resp, dict) else None,
            content=raw_bytes, source_url=data.get("image_url"), started=started,
        )
        return jsonify(resp), status
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


@app.route("/predict/video/deep", methods=["POST"])
def predict_video_deep():
    """Video path: Spatial layers 1-4 on sampled frames + Layer 5 temporal
    coherence + Layer 6 PwTF-DVD pixel-wise temporal frequency (ICCV 2025).

    Accepts three payload shapes:
      { "video_base64": "<base64 of a video file>" }   - device upload; the
        server decodes frames itself (ffmpeg, or OpenCV fallback)
      { "video_url": "https://.../clip.mp4" }          - direct file link;
        social-platform links (Instagram Reels, TikTok, YouTube, ...) are
        resolved automatically when yt-dlp is installed on the server
      { "frames_base64": ["<jpeg>", ...] }             - browser-extracted frames
    """
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401

    data = request.get_json() or {}
    return _cached_video_deep(data)

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

    started = time.time()
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
        _record_scan(
            "text", "text/storyscope", result, 200,
            excerpt=text, content=text, started=started,
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:  # noqa: BLE001
        print(f"StoryScope error: {e}")
        return jsonify({"error": f"StoryScope analysis failed: {e}"}), 500


@app.route("/predict/text/dna", methods=["POST"])
def predict_text_dna():
    """DNA-DetectLLM: Zero-shot AI text detection via mutation-repair paradigm.

    Send JSON body: {"text": "..."}
    Returns a detection verdict based on how closely the text matches the
    reference model's ideal sequence (NeurIPS 2025 Spotlight).
    """
    if not _check_auth():
        return jsonify({"error": "Unauthorized: missing or invalid Bearer token."}), 401

    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text provided. Send JSON body: {\"text\": \"...\"}"}), 400

    started = time.time()
    try:
        result = dna_detect.detect(text)
        _record_scan(
            "text", "text/dna", result, 200,
            excerpt=text, content=text, started=started,
        )
        return jsonify(result)
    except Exception as e:
        print(f"DNA-DetectLLM error: {e}")
        failure = {
            "score": 50,
            "label": "Inconclusive",
            "reasons": [f"DNA-DetectLLM analysis failed: {e}"],
        }
        # A failed detector still answered a request; log it as a 500 so
        # outages are visible in the same table as the verdicts.
        _record_scan(
            "text", "text/dna", failure, 500,
            excerpt=text, content=text, started=started,
        )
        return jsonify(failure), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
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
    print(f"DNA-DetectLLM loaded (text AI-detection endpoint: /predict/text/dna).")
    print(f"SPAI spectral analyzer loaded (image AI-detection in /predict/image/deep).")
    print(f"PwTF-DVD temporal-frequency detector loaded (ICCV 2025; video AI-detection via "
          f"/predict/video/deep and /predict with frames_base64).")
    print(f"DetectZoo loaded: {DETECTZOO_AVAILABLE}")
    
    # Use threaded mode to handle concurrent requests without blocking
    # Set timeout to prevent hanging on slow downloads
    from werkzeug.serving import run_simple
    run_simple(
        "0.0.0.0",
        port,
        app.wsgi_app,
        threaded=True,
        use_reloader=False,
        use_debugger=False,
    )

