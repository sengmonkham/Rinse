# RINSE Canvas — AI Detection Playground

An infinite canvas environment for testing AI content detection. Drag text and images onto the canvas, then point and scan to detect AI-generated patterns.

## Quick Start

```bash
cd canvas-demo
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Features

- **Infinite Canvas** — Scroll to zoom, Shift+drag to pan. Grid background for spatial orientation.
- **Sample Content** — Pre-loaded AI and human-written texts + AI-themed images in the sidebar.
- **Point & Scan** — Click any item on the canvas, hit the 🔍 button to run AI detection heuristics.
- **Score Badges** — Each scanned item gets a color-coded badge (red=AI definite, orange=likely, yellow=suspicious, green=human).
- **Detailed Results** — Click a scanned item to see detection flags, reasoning, and humanization suggestions.
- **Scan All** — One-click to scan every item on the canvas at once.
- **Right-Click Menu** — Right-click any item for quick scan or delete options.

## Sample Content Included

### Texts
| Name | Type | What it detects |
|------|------|----------------|
| LinkedIn Broetry | AI | Emojis, buzzwords, bold bullets, engagement hooks, hashtags |
| Corporate Marketing | AI | Hyphenated compounds, em-dashes, "testament to", "synergy" |
| AI Emoji Slop | AI | Emoji overload, corporate hooks, hashtag salad |
| AI Personal Narrative | AI | Narrative patterns ("Back in 2021", "This led me to"), causal density |
| Human Writing (Casual) | Human | Lowercase starts, informal tone, contractions |
| Human Writing (Opinion) | Human | Natural hedging, varied sentence length, real uncertainty |

### Images
| Name | What it represents |
|------|--------------------|
| AI Neural Network Art | Purple gradient, neural nodes — typical AI aesthetic |
| AI Vibecoded Dashboard | Pink/purple v0-style SaaS dashboard |
| AI Landscape | Symmetrical DALL-E style sunset landscape |

## Demo Video Workflow

1. Open the canvas app
2. Click a few sample texts from the sidebar (mix AI and human)
3. Add an image or two
4. Click "Scan All" or scan items individually
5. Show the score badges and detailed results panel
6. Pan around the canvas to show the spatial layout

## Tech Stack

- Next.js 15 (App Router)
- TypeScript
- Tailwind CSS
- react-konva (infinite canvas with pan/zoom)
- Detection heuristics ported from RINSE Playground
