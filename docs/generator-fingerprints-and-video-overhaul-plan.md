# Plan: Generator-Level Fingerprints (Midjourney & Co.) + Video Detection Overhaul

Status: **PLAN ONLY — not implemented.**
Target repo: RINSE (`server.py`, `forensics/*`, new support modules).
Related: `docs/brainrot-characters-and-scan-cache-plan.md` (cache + character recognition — separate effort, shares the eval harness).

---

# Part A — Generator-level fingerprinting

Goal: move from "this is AI-generated" to **"this is AI-generated, and it looks like Midjourney"** — with evidence, confidence, and zero false attributions.

## A0. Reality check (what is actually knowable)

| Signal | Reliability | When available |
|---|---|---|
| C2PA manifest `claim_generator` | **Deterministic** — trust it | OpenAI images, Adobe Firefly, some Google. **Midjourney strips it** on most exports |
| IPTC `digitalSourceType` XMP | Deterministic | Same set as C2PA |
| EXIF `Software` / URL-host patterns | Weak hint | Inconsistent, forgeable |
| Per-generator spectral signatures | Statistical hint (never proof) | Works on native-resolution, lightly-recompressed images |
| Invisible watermarks (SynthID, Stable Signature, Tree-Ring) | Strong **if you have the detector/keys** | SynthID needs Google's classifier (not public); Tree-Ring/Stable Signature feasible for open SD models only |
| Per-generator trained heads | Statistical hint | Requires curated training data per generator |

Design rule: **attribution is a hint, never a verdict.** Only provenance metadata (C2PA/IPTC) may hard-escalate (it already does via `probe_c2pa_manifest`). Everything else feeds `generator_hint` with confidence and corroborating evidence.

## A1. Phase A1 — Provenance deep-parse (highest ROI, days of work)

Today `forensics/c2pa.py` greps a 5-keyword list against manifest JSON. Upgrade to a proper provenance reader:

1. **Parse, don't grep**: use `exiftool` (already a common deploy dep) or the `c2pa-python` binding to extract:
   - C2PA `claim_generator` + `claim_generator_info` (name, version)
   - XMP `IPTC:DigitalSourceType` (`trainedAlgorithmicMedia`, `compositeSynthetic`, etc.)
   - XMP `photoshop:Credit` / `xmp:CreatorTool` (frequent generator leaks: "Midjourney", "DALL·E", "Stable Diffusion web UI")
   - EXIF `Software`, `ImageDescription`, `UserComment`
2. **Expand the generator registry** into a data file (`forensics/generators.json`): each entry `{ id, label, family, aliases, c2pa_ids, url_hosts, notes }`. Seed: Midjourney, DALL·E / GPT-4o images, Stable Diffusion (+ WebUI/ComfyUI/Invoke), Flux, Firefly, Ideogram, Leonardo, Grok/Aurora, Imagen, Recraft, Kling/Runway/Luma/Pika (video, reused later).
3. **URL/host intelligence** (cheap, extension-friendly): maintain `url_hosts` per generator — e.g. `oaidalleapiprodscus.blob.core.windows.net` (DALL·E), `cdn.jsdelivr.net/gh/...` no, `s.mj.run` / MJ CDN patterns, `filesystem.site`, Replicate delivery hosts. Applied to `image_url` inputs **only** (never to uploaded files). Signal class: weak hint → reported, tiny score contribution.
4. Output shape (additive):

```python
"provenance": {
  "claim_generator": "Adobe Firefly v3",     # or null
  "digital_source_type": "trainedAlgorithmicMedia",
  "software_tags": ["Midjourney v6.1"],
  "host_hint": "midjourney-cdn",             # or null
  "verdict": "confirmed_ai" | "likely_ai" | "camera_claimed" | "none"
}
```

`confirmed_ai` keeps the existing hard-override behavior (c2pa ≥ 90 already does this). Everything else never escalates alone.

## A2. Phase A2 — Spectral signature registry per generator

The core new idea: generator upscalers/decoders leave **characteristic frequency fingerprints** (GAN checkerboard for SD x4 upscalers, MJ v6's periodic lattice at 1024-multiples, diffusion spectral deficits at high radial frequencies). Build a registry the same way audio fingerprinting works:

1. **Collection** (`scripts/collect_generator_corpus.py`): for each generator, gather 200–500 native-resolution outputs of known provenance (own generations via API where possible; public datasets otherwise: MJ via community datasets, SD/Flux via HuggingFace sets, DALL·E via published samples). Store provenance in `fingerprints/generators/`.
2. **Signature extraction** (`scripts/build_generator_signatures.py`): per image compute
   - azimuthally-averaged FFT radial power profile (256 bins, normalized),
   - grid-peak spectrum (reuse `forensics/frequency.py` internals),
   - residual statistics after SPAI-style masked reconstruction (reuse `forensics/spai.py`).
   Average per generator → store centroid + covariance diagonal in `fingerprints/generator_signatures.py` (generated file, committed).
3. **Matching** (`forensics/generator_id.py`): cosine/radial-profile distance of the query against every centroid → `generator_hint = {generator, family, similarity, evidence: {radial_delta, grid_peaks}}`. **Escalation rules**:
   - similarity ≥ 0.9 AND neural ≥ 60 → boost neural toward 75 (corroboration, still under hard tiers);
   - similarity ≥ 0.9 alone → report hint, no score change;
   - similarity < 0.75 → no hint reported.
4. **Robustness**: signatures computed at multiple resolutions (native + 512 + 256 recompressed) so the registry stores resolution-conditioned centroids; recompression shifts spectra, so the matcher picks the closest condition.
5. **Eval gate** (same harness as Part B): ≥ 80% correct generator attribution at similarity ≥ 0.9 on held-out native-res images; < 1% false hints on real camera photos. **Camera-photo false hints must be ~zero** — a wrong "looks like Midjourney" on a real photo is a credibility killer.

## A3. Phase A3 — Open watermark probes

1. **Tree-Ring watermarks (SD family)**: detection is a frequency-domain ring-pattern correlation against the model's fixed initial latent. Implement for the 2–3 open SD checkpoints whose keys are public. Probe cost is low (single FFT pass). Feasible and publishable-grade — include as `watermark: {scheme: "tree-ring", model: "...", correlation, score}`. Score ≥ threshold escalates like C2PA.
2. **Stable Signature**: detectable via decoder network (public for some SD models); optional, same output shape.
3. **SynthID**: keep the existing spectral heuristic, but (a) demote it to hint-only unless metadata confirms (the spectral probe alone can false-positive on textured photos), (b) integrate Google's **SynthID Detector portal/API** when access is granted — keep an adapter stub.
4. **Meta "AI info" labels**: parse IPTC metadata Meta embeds ("Imagined with AI") — goes in the A1 registry.

## A4. Phase A4 (optional, largest) — Generator-attribution classifier head

Only after A1–A3 prove out: train a single multi-class head (families: real-camera, GAN-family, MJ, SDXL/Flux-diffusion, OpenAI, video-derived) on the collected corpus, small CNN backbone, ONNX-served like the existing neural layer. Output: per-class probabilities → contributes to `generator_hint` (family-level only, not version-level). Gate: ≥ 85% family accuracy on held-out recompressed data, else don't ship.

## A5. Response contract (additive, non-breaking)

```python
"generator_hint": {
  "generator": "midjourney", "family": "diffusion",
  "confidence": "moderate",          # high (provenance) / moderate (spectral ≥0.9) / low
  "evidence": "C2PA claim_generator 'Midjourney v6.1'" | "radial spectral profile match (sim 0.93)",
  "watermark": null | {...}
}
```

UI (rinse-web `/scan` + extension): under the verdict, a muted line — "Looks like Midjourney (spectral signature, moderate confidence)". Never shown below "low".

---

# Part B — Video detection overhaul (current weak spot)

## B0. Audited weaknesses (with receipts)

1. **Temporal resolution starvation**: `temporal.py` thumbs at **128×128 grayscale BILINEAR** (temporal.py:84–89); `pwtf.py` works at `WORK_RES = 128` (pwtf.py:52). The high-frequency pixel-wise temporal artifacts PwTF-DVD hunts are largely destroyed by a 128px gray downsample — we're running the ICCC 2025 detector far below its operating point.
2. **One spatial frame per window**: `_analyze_video_frames` runs the 5-layer spatial stack on each window's **middle frame only** → ~3 frames analyzed spatially per video. A single frame is a coin flip for the neural layer.
3. **D3 is dead weight**: `forensics/d3.py` weight = 0.0 in `voter.py` (their own eval: pixel-space volatility doesn't separate). The temporal story is currently "temporal coherence + PwTF on 128px gray" — thin.
4. **Client-frame scans bias INCONCLUSIVE**: `frames_base64` without `frame_interval_seconds` → temporal layers abstain → honest but frequent "INCONCLUSIVE" on user uploads.
5. **No latency strategy**: decode + 5 spatial layers + 2 temporal layers run serially; social-platform URLs need yt-dlp on the server.

## B1. Phase B1 — Resolution + channel starvation fix (biggest expected gain)

1. **Raise temporal working res**: 128 → **256** (make configurable `TEMPORAL_RES`; benchmark 192/256/320 on the eval set from B6). Memory: 256² × 32 frames float32 ≈ 8 MB per window — trivial. Latency: FFT stacks scale linearly in pixels; measure and pick.
2. **Add chroma to temporal layers**: generation pipelines leave chroma-specific flicker; currently we compute luma only. Extend `temporal.py`/`pwtf.py` to stack (Y + downsampled Cb/Cr) — chroma planes at half res.
3. **Resample properly**: BILINEAR → LANCZOS for the temporal stack (aliasing matters when hunting frequency artifacts).
4. Re-verify the **shot-aware sampling** thresholds still hold at higher res (the 0.16 cut threshold in `_detect_shot_boundaries` is tuned for 64px probes — keep probe at 64, unchanged).
Gate: no threshold lands without the B6 eval.

## B2. Phase B2 — Multi-frame spatial voting

1. Per window, run the spatial stack on **5 spread frames** (not just the middle): frames at 10%, 30%, 50%, 70%, 90% of the window.
2. Aggregate: median score + spread; feed the fusion a **distribution** — `neural` gets median; add `neural_spread` to extra_data; disagreement (spread > 25) caps confidence at MEDIUM.
3. Fingerprint matching (`_pixel_forensics_img`) runs on **all 5 frames** (brainrot characters in videos get caught at any frame, not the middle one).
4. Latency control: neural on 5 frames ≈ 5× neural cost; mitigate with B8 parallelism + optional 3-frame mode for `/predict` (vs `/predict/video/deep`).

## B3. Phase B3 — Replace D3 with a real learned temporal layer

D3's honest failure (pixel-space volatility doesn't separate) doesn't mean temporal dynamics carry no signal — it means *that* statistic doesn't. Build one learned temporal model:

1. **Model**: lightweight temporal transformer / 3D-CNN over frame-difference stacks at 128–256px (input: the same windows we already decode). Train on DeepfakeBench/GenVideo + collected Sora/Veo/Kling/Runway/Pika samples vs camera + social-compressed real.
2. **Output**: `temporal_learned` score joins the fusion at a calibrated weight (start 0.10, calibrate on eval).
3. **Honesty invariant preserved**: learned temporal layer, like PwTF, never escalates alone (voter's video-agreement guard stays).
4. Serve via ONNX (same as planned neural path); CPU budget ~1–2 s per window.

## B4. Phase B4 — Codec-native forensics (cheap, orthogonal, underused)

1. **Double-compression detector**: real social videos are re-encoded ≥2× (camera → platform); AI videos are usually uploaded fresh (1×). Measure via P-frame quality ladder / quantization ghosting (classic double-JPEG analog for H.264). Implement in `forensics/codec.py` operating on the decoded stream + container metadata (encoder, bitrate, GOP).
2. **Container/metadata audit**: muxer tags (`Lavf`, GPU encoder strings, absurdly clean GOPs), resolution/frame-rate conventions of known generators (Sora 720/1080 30fps, Kling patterns...). Weak hints, registry-driven (shares `generators.json` from Part A).
3. Feed as a *context* layer: reported in reasons, small weight (0.05), never decisive alone.

## B5. Phase B5 — Audio track forensics (stretch)

Generated videos usually ship synthetic or AI-produced audio. Add: extract audio track (ffmpeg) → run a small speech-synthetic detector (AASIST-class) + music-generation spectral check → `audio_hint: {ai_likely: bool, evidence}`. Reported only; never affects the visual verdict's score. Ships only if B6 eval shows ≥ 80% on synthetic audio with < 2% camera-audio FPs.

## B6. Phase B6 — Benchmark harness (the gate for everything above)

`forensics/eval_video.py` (extends the pattern of `eval_d3.py`):

1. **Real set**: 150+ clips — camera footage (phones, DSLR), PLUS social-compressed variants (Instagram/TikTok-style re-encode matrix: 720p q-high/low, crop-to-9:16, platform watermark burn-in).
2. **Generated set**: 150+ clips across Sora, Veo, Kling, Runway, Luma, Pika, MJ video, Wan — same recompression matrix.
3. **Metrics**: per-layer ROC/AP, fused ROC at current thresholds, per-generator breakdown, INCONCLUSIVE rate (target < 15% on server-side URLs), latency p50/p95 per mode.
4. **CI discipline**: `make eval-video` produces a table; every threshold change in this plan requires an attached before/after table. No vibes.

## B7. Phase B7 — Protocol + product fixes

1. **Client-frame protocol v2** (extension): require sending `frame_interval_seconds` (it knows the capture fps) + native-res frames (no pre-downscale) + frame CRCs; server validates contiguity via CRC → temporal layers activate → INCONCLUSIVE bias drops.
2. **Layer parallelism**: spatial layers are independent — `ThreadPoolExecutor` (CPU-bound, GIL-releasing via numpy/torch) → ~2–3× wall-clock cut on deep scans.
3. **Adaptive mode**: `/predict/video/deep` runs B1 temporal probe first; only runs the expensive spatial+learned stack when the temporal probe is ambiguous (30–70). Clear-cut cases return fast.

## B8. Rollout order

1. **B6 harness first** (nothing else is trustworthy without it).
2. B1 res/chroma fix + re-bench (likely the single biggest score improvement).
3. B2 multi-frame spatial voting.
4. B7.2 parallelism + B7.3 adaptive mode (pure latency).
5. B7.1 client protocol v2 (extension-side change + server validation).
6. B4 codec forensics (cheap wins).
7. B3 learned temporal layer (needs training data collection — start collection early, in parallel with step 2).
8. B5 audio (stretch).

## B9. Risks

| Risk | Mitigation |
|---|---|
| Higher res breaks calibrated thresholds | Config-gated res; eval-gated rollout; keep 128 fallback |
| Multi-frame voting slows scans | Parallelism + adaptive mode + frame-count modes |
| Learned temporal layer overfits eval | Held-out generators (train on some, exclude others entirely), recompression matrix |
| Double-compression signal inverted on platforms that re-encode AI uploads | Report-only layer; monitor per-platform in eval |
| Chroma planes unavailable (gray sources) | Graceful luma-only fallback (existing behavior) |
