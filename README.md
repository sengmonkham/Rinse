# RINSE

RINSE (Remove Inauthentic Noise) is a browser extension and dashboard designed to detect AI-generated content in text, images, and video.

## Workings and Details

The application functions by analyzing web content through a dual execution path. By default, it operates offline using heuristic algorithms to identify generative text structures, inspect image metadata signatures, and check video container flags directly in the browser. When switched to cloud mode, it sends requests to a Python API server that runs advanced deep learning classifiers, such as DetectZoo models, to perform structural pixel audits and verify media authenticity. For narrative text, cloud mode also runs **StoryScope**, a research-grade detector that reads plot-level structure instead of wording.

## Getting Started

### Web Application and Extension
1. Install dependencies: npm install
2. Start the dev server: npm run dev
3. Build the project: npm run build
4. Load the build: Open chrome://extensions, enable developer mode, and load the dist folder.

### Python API Server
To connect the extension or sandbox to deep learning models:
1. Install requirements: pip install flask flask-cors requests pillow detectzoo
2. Start the server: python server.py
3. Toggle to Cloud Mode in the settings panel to route scanning requests through this backend.

## StoryScope: narrative-structure AI fiction detection

StoryScope (implemented from Russell et al. 2026, [arXiv:2604.03136](https://arxiv.org/abs/2604.03136)) detects AI-written fiction by reading **narrative structure** — plot shape, character agency, temporal structure, theme handling — instead of surface style that models can paper over. The published 304-feature taxonomy (10 NarraBench dimensions) and the LLM extraction prompts are used as released; an XGBoost classifier is trained on the paper's own 61,575-story feature matrix and scored through a dependency-free pure-Python model reader.

**Accuracy (trained on the paper's released features, prompt-grouped held-out folds):**

| Model | Macro-F1 | AUPRC | Accuracy |
|---|---|---|---|
| Full (304 features) | **0.962** | 0.999 | 0.979 |
| Narrative only (style dropped) | 0.943 | 0.998 | 0.969 |

The narrative-only variant retains **98%** of full-model performance — reproducing the paper's "narrative features retain >97%" finding. The paper reports 93.2% macro-F1 on its held-out test split.

Two extraction engines feed the same classifier — see below.

### How it works

1. The story text is turned into the 304 taxonomy features (plot, agents, temporal structure, revelation, style, ...) by one of two engines:
   - **LLM engine** (`STORYSCOPE_MODE=llm`): the paper's pipeline — an LLM literary analyst annotates the story (10 per-dimension calls). Most accurate; needs an API key.
   - **Heuristic engine** (`STORYSCOPE_MODE=heuristic`, **default**): pure rule-based analysis of the text (stdlib only) — no API key, no network, ~10 ms per story. Covers 204 of the 304 features with word-list/statistic proxies; features that need literary judgment are left as `n/a`.
2. Values are normalized onto the taxonomy's canonical categories and one-hot encoded (categories derived from the training data, so no hidden label mappings).
3. The XGBoost binary classifier (human vs AI) scores the vector; the API returns the AI probability plus a per-dimension breakdown and the strongest narrative tells, e.g. "Thematic explicitness = high", "Conflict resolution = tidy" — the patterns the paper found most predictive.

### Offline heuristic engine (no API key)

**Heuristic is the default.** It reads the same narrative tells the paper identified (plot structure, character agency, temporal shape, thematic explicitness, dialogue proportion, style statistics) using ~90 hand-built text statistics and word lists — no LLM, no API, no slowdown. Run it with the server configured as-is, or call the endpoint directly.

**Honest accuracy bounds** — measured on the paper's released 61,575-story feature matrix with the shipped model (see `python -m storyscope.eval_heuristic`):

| Scenario | Macro-F1 | AUPRC | Accuracy |
|---|---|---|---|
| Full LLM extraction (in-sample upper bound) | 0.999 | 1.000 | 0.9996 |
| Heuristic coverage, covered features as released | **0.958** | 0.999 | 0.976 |
| Heuristic covered features ~60% accurate (middle estimate) | 0.600 | 0.966 | — |
| Heuristic covered features contribute no signal (floor) | 0.455 | 0.833 | — |

Heuristic mode retains **96% of full-model macro-F1 when its estimates are right**, and 84% of the model's split nodes sit in features the heuristic can reach. Real-world performance sits between the middle estimate and the upper bound — treat heuristic verdicts as a **fast screening signal, not research-grade**: borderline scores are inconclusive, and short texts (well under the ~5,000-word training length) are unreliable. For high-stakes checks, switch to `STORYSCOPE_MODE=llm`.

### Server configuration

```bash
# Extraction engine: heuristic (default, offline, no key) | llm
STORYSCOPE_MODE=heuristic

# --- LLM engine only ---
# Provider: openai (default) | anthropic | gemini
STORYSCOPE_LLM_PROVIDER=openai
STORYSCOPE_LLM_MODEL=gpt-4o-mini        # provider default if unset
STORYSCOPE_LLM_API_KEY=sk-...           # falls back to OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY
# Optional, for OpenAI-compatible endpoints (DeepSeek, OpenRouter, vLLM, ...):
STORYSCOPE_LLM_BASE_URL=https://api.openai.com/v1
```

Endpoint: `POST /predict/storyscope` with body `{"text": "...", "mode": "heuristic"}` (`mode` is optional; defaults to `STORYSCOPE_MODE`). The Playground text sandbox calls it automatically when set to Cloud Detector mode. The response includes `"mode"` and `"feature_source"` so clients can tell which engine produced the verdict.

### Retraining (optional)

The shipped classifier was trained from `storyscope/data/storyscope_features.parquet` (the paper's released per-story feature matrix). To retrain:

```bash
pip install xgboost pandas pyarrow scikit-learn   # training only
python -m storyscope.train --self-test            # cross-validates, saves model + stats
```

On macOS, xgboost needs the OpenMP runtime (`brew install libomp`) — the shipped model and server do **not**.

### Attribution

StoryScope's taxonomy, extraction prompts and dataset are by Jenna Russell, Rishanth Rajendhran, Chau Minh Pham, Mohit Iyyer and John Wieting (University of Maryland / Google DeepMind), released under MIT. This implementation ports the extraction pipeline and retrains the classifier on the released feature matrix.

## Deployment Guide

### Chrome Extension Deployment

To load and test the extension locally:
1. Run the build script to generate production assets:
   ```bash
   npm run build
   ```
2. Open Google Chrome and go to `chrome://extensions`.
3. Turn on Developer mode using the switch in the top right corner.
4. Click the Load unpacked button in the top left corner.
5. Select the `dist` folder located in your project directory.

To publish the extension to the public:
1. Compress the contents of the `dist` directory into a ZIP archive.
2. Upload this ZIP archive to the Chrome Developer Dashboard to publish it on the Chrome Web Store.

### Python API Server Deployment (Hugging Face Spaces)

Because deep learning models and PyTorch require significant memory (more than the 512MB limit provided on free tiers of services like Render or Koyeb), Hugging Face Spaces is recommended. It offers a free CPU tier with 16GB of RAM.

Follow these steps to deploy:
1. Create a Hugging Face account and navigate to Spaces.
2. Create a new Space, choose a name, and select Docker as the SDK (use the Blank template). Set hardware to CPU basic (Free) and visibility to Public.
3. Upload your `server.py` file, your `.detectzoo_data` directory containing the model weights, and create the following configuration files in the root of your Space:

#### requirements.txt
```text
flask
flask-cors
requests
pillow
torch --extra-index-url https://download.pytorch.org/whl/cpu
detectzoo
```

#### Dockerfile
```dockerfile
FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY .detectzoo_data/ /app/.detectzoo_data/
COPY server.py .

ENV PORT=7860
EXPOSE 7860

CMD ["python", "server.py"]
```

4. Once the Space build completes and shows a green Running status, your API is live.
5. In your extension settings dashboard, set the API URL to:
   `https://<your-username>-<your-space-name>.hf.space/predict`
