# RINSE backend - Render.com Docker deployment
#
# The full forensic ensemble (SynthID, C2PA, AI-metadata, frequency,
# DetectZoo/CNNSpot neural classifier, SPAI, pixel-forensics, PwTF-DVD
# temporal, StoryScope) as a plain Flask REST API - same endpoints and
# payloads as every other RINSE deployment target.
#
# Render runs this with:  docker run -e PORT=<port> -p <port>:<port> ...
# server.py already binds 0.0.0.0:$PORT and serves GET /health for Render's
# health-check path.

# (bookworm pinned: slim currently tracks trixie, where libglib2.0-0 was
# renamed to libglib2.0-0t64 - the apt install below expects bookworm names)
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Runtime caches on the mounted persistent disk (see render.yaml).
    SCAN_CACHE_DIR=/app/data/cache \
    TMPDIR=/app/data/tmp

WORKDIR /app

# System deps: ffmpeg (video decoding + yt-dlp HLS/DASH merges), libglib2.0-0
# (opencv-python-headless needs it even without a GUI), curl (weight bake).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python deps first so code changes never re-download the ML stack.
# CPU-only torch wheels from the official CPU index (skips ~2.5GB of CUDA
# libraries; RINSE runs everything on CPU).
# Versions mirror the local, tested venv (torch 2.14 / tv 0.29 / ta 2.11).
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.14.0 torchvision==0.29.0 torchaudio==2.11.0

COPY requirements-render.txt .
RUN pip install -r requirements-render.txt

# Backend sources (the frontend/extension is served by the Chrome build,
# not this container).
COPY server.py forensics/ storyscope/ fingerprints/ /app/

# Bake the CNNSpot weights (~280MB, blur_jpg_prob0.5.pth) into the image so
# cold boots don't re-download them from Dropbox (which rate-limits).
# detectzoo caches under CWD/.detectzoo_data/ (see
# detectzoo/datasets/_download.py get_cache_dir) and skips existing files
# (download_file's dest.exists() check).
# Best-effort: if Dropbox blocks the build IP, the build still succeeds and
# detectzoo downloads the weights on first boot instead. A partial/corrupt
# file is removed so detectzoo never trusts it (it skips existing files).
RUN mkdir -p /app/.detectzoo_data/cnnspot \
    && { curl -fsSL --retry 3 -o /app/.detectzoo_data/cnnspot/blur_jpg_prob0.5.pth \
           "https://www.dropbox.com/s/2g2jagq2jn1fd0i/blur_jpg_prob0.5.pth?dl=1" \
         && python -c "import os,sys; p='/app/.detectzoo_data/cnnspot/blur_jpg_prob0.5.pth'; sys.exit(0 if os.path.getsize(p) > 200_000_000 else 1)" \
         && echo 'CNNSpot weights baked into image' \
       || { rm -f /app/.detectzoo_data/cnnspot/blur_jpg_prob0.5.pth; \
            echo 'WARNING: CNNSpot weight bake failed; weights will download on first boot'; }; }

# Scan cache + temp files live on the persistent disk so verdicts survive
# deploys (disk is optional: the server falls back to uncached scans).
RUN mkdir -p /app/data/cache /app/data/tmp

EXPOSE 10000
CMD ["python", "server.py"]
