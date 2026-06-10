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
