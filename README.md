# Detoxify

Detoxify AI Content Verifier is a browser extension and dashboard designed to detect AI-generated content in text, images, and video.

## Workings and Details

The application functions by analyzing web content through a dual execution path. By default, it operates offline using heuristic algorithms to identify generative text structures, inspect image metadata signatures, and check video container flags directly in the browser. When switched to cloud mode, it sends requests to a Python API server that runs advanced deep learning classifiers, such as DetectZoo models, to perform structural pixel audits and verify media authenticity.

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
