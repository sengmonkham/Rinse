// RINSE - Content Script for Webpage DOM Injection

// Global state for scanning
let scanResults = {
  text: [],
  images: [],
  videos: [],
  score: 100,
  scannedAt: null,
  vibecoded: {
    isVibecoded: false,
    reasons: [],
    hasPurpleGradient: false,
    hasBubbleHeader: false
  }
};

let scanInProgress = false;
let sideDrawerElement = null;
let laserScannerElement = null;
let floatingTooltipElement = null;

// Sensitivity from settings (10-90), used to tune the text flagging threshold
let scanSensitivity = 50;

// Extension enabled state — when false, scanning and badges are suppressed
let extensionEnabled = true;

// Keep extensionEnabled in sync with chrome.storage.local so that
// toggling from the popup works even if the sendMessage delivery fails.
try {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.extensionEnabled) {
      extensionEnabled = changes.extensionEnabled.newValue !== false;
    }
  });
} catch (e) {
  // Not in an extension context
}

// Hover-Hotkey variables
let hoveredElement = null;
let mouseX = 0;
let mouseY = 0;

// Dynamic style sheet injection
const injectStyles = () => {
  if (document.getElementById("aegis-styles")) return;

  const style = document.createElement("style");
  style.id = "aegis-styles";
  style.textContent = `
    /* RINSE Badge Styling */
    .aegis-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 6px;
      margin: 0 4px;
      border-radius: 4px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      cursor: pointer;
      user-select: none;
      vertical-align: middle;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      border: 1px solid transparent;
      z-index: 9999;
    }
    
    .aegis-badge-ai {
      background: rgba(220, 38, 38, 0.15) !important;
      color: #F87171 !important;
      border-color: rgba(220, 38, 38, 0.4) !important;
      box-shadow: 0 0 8px rgba(220, 38, 38, 0.2);
    }
    
    .aegis-badge-ai:hover {
      background: rgba(220, 38, 38, 0.3) !important;
      box-shadow: 0 0 12px rgba(220, 38, 38, 0.4);
      transform: scale(1.05);
    }
    
    .aegis-badge-suspected {
      background: rgba(245, 158, 11, 0.15) !important;
      color: #FBBF24 !important;
      border-color: rgba(245, 158, 11, 0.4) !important;
      box-shadow: 0 0 8px rgba(245, 158, 11, 0.2);
    }
    
    .aegis-badge-suspected:hover {
      background: rgba(245, 158, 11, 0.3) !important;
      box-shadow: 0 0 12px rgba(245, 158, 11, 0.4);
      transform: scale(1.05);
    }

    /* Highlighted Elements */
    .aegis-highlight-ai {
      position: relative;
      background-color: rgba(220, 38, 38, 0.05) !important;
      border-left: 3px solid #EF4444 !important;
      padding-left: 6px !important;
    }

    .aegis-highlight-suspected {
      position: relative;
      background-color: rgba(245, 158, 11, 0.05) !important;
      border-left: 3px solid #F59E0B !important;
      padding-left: 6px !important;
    }

    .aegis-image-highlight-ai {
      outline: 4px solid #EF4444 !important;
      outline-offset: -4px !important;
      box-shadow: 0 0 12px rgba(220, 38, 38, 0.4) !important;
    }

    .aegis-image-highlight-suspected {
      outline: 4px solid #F59E0B !important;
      outline-offset: -4px !important;
      box-shadow: 0 0 12px rgba(245, 158, 11, 0.4) !important;
    }

    body.aegis-hide-ai-active .aegis-highlight-ai,
    body.aegis-hide-ai-active .aegis-highlight-suspected,
    body.aegis-hide-ai-active .aegis-badge,
    body.aegis-hide-ai-active .aegis-image-overlay-text {
      display: none !important;
    }

    body.aegis-hide-ai-active .aegis-image-highlight-ai,
    body.aegis-hide-ai-active .aegis-image-highlight-suspected {
      display: none !important;
    }

    body.aegis-hide-ai-active .aegis-media-overlay-badge {
      display: none !important;
    }

    body.aegis-hide-image-overlays .aegis-image-highlight-ai,
    body.aegis-hide-image-overlays .aegis-image-highlight-suspected {
      outline: none !important;
      box-shadow: none !important;
    }

    body.aegis-hide-image-overlays .aegis-media-overlay-badge,
    body.aegis-hide-image-overlays .aegis-image-overlay-text {
      display: none !important;
    }

    .aegis-hover-focus {
      outline: 2px dashed #06B6D4 !important;
      outline-offset: 2px !important;
      box-shadow: 0 0 15px rgba(6, 182, 212, 0.3) !important;
      transition: all 0.2s ease;
    }

    .aegis-media-overlay-badge {
      position: absolute;
      top: 8px;
      left: 8px;
      z-index: 10000;
    }
    
    /* HUD Control Panel */
    .aegis-hud {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 999999;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }
    
    .aegis-hud:hover {
      transform: scale(1.08) rotate(90deg);
      border-color: rgba(6, 182, 212, 0.4);
      box-shadow: 0 0 20px rgba(6, 182, 212, 0.3), 0 8px 32px rgba(0, 0, 0, 0.4);
    }

    .aegis-hud svg {
      width: 24px;
      height: 24px;
      stroke: #06B6D4;
      stroke-width: 2;
      fill: none;
      transition: all 0.3s;
    }

    /* Laser Scanner Overlay */
    .aegis-laser-scanner {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 4px;
      background: linear-gradient(90deg, rgba(6, 182, 212, 0) 0%, rgba(6, 182, 212, 1) 50%, rgba(6, 182, 212, 0) 100%);
      box-shadow: 0 0 15px rgba(6, 182, 212, 0.8), 0 0 30px rgba(6, 182, 212, 0.5);
      z-index: 999998;
      pointer-events: none;
      animation: aegis-laser-scan 3s ease-in-out infinite;
      display: none;
    }

    @keyframes aegis-laser-scan {
      0% { top: 0%; opacity: 0; }
      5% { opacity: 1; }
      95% { opacity: 1; }
      100% { top: 100%; opacity: 0; }
    }

    /* Floating Diagnostic Drawer */
    .aegis-drawer {
      position: fixed;
      top: 0;
      right: -420px;
      width: 380px;
      height: 100%;
      background: transparent !important;
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-left: 1px solid rgba(255, 255, 255, 0.1);
      box-shadow: -10px 0 40px rgba(0, 0, 0, 0.5);
      z-index: 9999999;
      transition: right 0.4s cubic-bezier(0.16, 1, 0.3, 1);
      color: #E2E8F0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      padding: 24px;
      box-sizing: border-box;
    }

    .aegis-drawer.open {
      right: 0;
    }

    .aegis-drawer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      padding-bottom: 16px;
      margin-bottom: 20px;
    }

    .aegis-drawer-title {
      font-size: 18px;
      font-weight: 700;
      color: #F8FAFC;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .aegis-drawer-close {
      background: none;
      border: none;
      color: #94A3B8;
      cursor: pointer;
      font-size: 20px;
      padding: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
      transition: background 0.2s;
    }

    .aegis-drawer-close:hover {
      background: rgba(255, 255, 255, 0.05);
      color: #F8FAFC;
    }

    .aegis-drawer-content {
      flex: 1;
      overflow-y: auto;
    }

    .aegis-card {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
    }

    .aegis-risk-meter {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 20px;
    }

    .aegis-risk-bar-container {
      width: 100%;
      height: 8px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 4px;
      overflow: hidden;
    }

    .aegis-risk-bar {
      height: 100%;
      border-radius: 4px;
      transition: width 0.8s ease-in-out;
    }

    .aegis-risk-red {
      background: linear-gradient(90deg, #EF4444, #DC2626);
      box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
    }
    
    .aegis-risk-yellow {
      background: linear-gradient(90deg, #F59E0B, #EAB308);
      box-shadow: 0 0 8px rgba(245, 158, 11, 0.5);
    }

    .aegis-metric-row {
      display: flex;
      justify-content: space-between;
      margin-bottom: 8px;
      font-size: 13px;
    }

    .aegis-metric-label {
      color: #94A3B8;
    }

    .aegis-metric-value {
      font-weight: 600;
      color: #F8FAFC;
    }

    .aegis-snippet {
      font-size: 13px;
      line-height: 1.5;
      color: #CBD5E1;
      background: rgba(0,0,0,0.2);
      padding: 10px;
      border-radius: 6px;
      border-left: 2px solid rgba(255,255,255,0.2);
      margin-top: 10px;
      word-break: break-word;
    }
    
    .aegis-log-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #64748B;
      margin-bottom: 8px;
      font-weight: 700;
    }

    /* Floating Cursor Tooltip Bubble */
    .aegis-floating-tooltip {
      position: absolute;
      width: 280px;
      background: transparent !important;
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5) !important;
      color: #E2E8F0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 12px;
      z-index: 99999999;
      pointer-events: auto;
      opacity: 0;
      transform: scale(0.95) translateY(5px);
      transition: opacity 0.2s ease, transform 0.2s ease;
    }

    .aegis-floating-tooltip.show {
      opacity: 1;
      transform: scale(1) translateY(0);
    }

    .aegis-tooltip-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      padding-bottom: 6px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }

    /* Topbar notification warning for vibecoded websites */
    .aegis-vibecoded-topbar {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      background: #ffffff !important;
      border-bottom: 2px solid #cbd5e1 !important;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05) !important;
      z-index: 999999999 !important;
      color: #0f172a !important;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      padding: 12px 24px !important;
      box-sizing: border-box !important;
      display: flex !important;
      justify-content: space-between !important;
      align-items: center !important;
      gap: 16px !important;
      backdrop-filter: blur(10px) !important;
      -webkit-backdrop-filter: blur(10px) !important;
      transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1) !important;
      transform: translateY(-100%);
    }
    
    .aegis-vibecoded-topbar.show {
      transform: translateY(0) !important;
    }
    
    .aegis-vibecoded-close {
      background: #f1f5f9 !important;
      border: 1px solid #cbd5e1 !important;
      color: #0f172a !important;
      cursor: pointer !important;
      font-size: 11px !important;
      font-weight: 700 !important;
      padding: 6px 12px !important;
      border-radius: 6px !important;
      transition: background 0.2s !important;
      flex-shrink: 0 !important;
    }
    
    .aegis-vibecoded-close:hover {
      background: #e2e8f0 !important;
    }
  `;
  document.head.appendChild(style);
};

// ──────────────────────────────────────────────────────────────────────────────
// Video URL Detection (mirrors the backend/canvas-demo detectAIVideo logic)
// ──────────────────────────────────────────────────────────────────────────────

/** Parse video URL and extract platform/source info */
const parseVideoUrl = (url) => {
  if (!url) return { source: "unknown", id: null, url };

  // YouTube patterns
  const ytMatch = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})/);
  if (ytMatch) return { source: "youtube", id: ytMatch[1], url };

  // Bare YouTube ID
  const bareId = url.match(/^([a-zA-Z0-9_-]{11})$/);
  if (bareId) return { source: "youtube", id: bareId[1], url };

  // Instagram patterns
  const igMatch = url.match(/instagram\.com\/reel\/([a-zA-Z0-9_-]+)/);
  if (igMatch) return { source: "instagram", id: igMatch[1], url };

  const igPostMatch = url.match(/instagram\.com\/p\/([a-zA-Z0-9_-]+)/);
  if (igPostMatch) return { source: "instagram", id: igPostMatch[1], url };

  const igTvMatch = url.match(/instagram\.com\/tv\/([a-zA-Z0-9_-]+)/);
  if (igTvMatch) return { source: "instagram", id: igTvMatch[1], url };

  // TikTok patterns
  const tikMatch = url.match(/tiktok\.com\/.*\/video\/(\d+)/);
  if (tikMatch) return { source: "tiktok", id: tikMatch[1], url };

  const tikShortMatch = url.match(/tiktok\.com\/@[^\/]+\/video\/(\d+)/);
  if (tikShortMatch) return { source: "tiktok", id: tikShortMatch[1], url };

  // Vimeo
  const vmMatch = url.match(/vimeo\.com\/(\d+)/);
  if (vmMatch) return { source: "vimeo", id: vmMatch[1], url };

  return { source: "unknown", id: null, url };
};

/** Check if video URL contains AI video platform indicators */
const checkAiVideoHosts = (url) => {
  const flags = [];
  let score = 0;
  const lower = url.toLowerCase();

  const aiVideoHosts = [
    { host: "sora", label: "OpenAI Sora" },
    { host: "runwayml", label: "Runway ML" },
    { host: "runway", label: "Runway" },
    { host: "pika-ai", label: "Pika Labs" },
    { host: "pika", label: "Pika" },
    { host: "lumaai", label: "Luma Dream Machine" },
    { host: "lumalabs", label: "Luma Labs" },
    { host: "kaiber", label: "Kaiber" },
    { host: "deforum", label: "Deforum (Stable Diffusion)" },
    { host: "stable-video-diffusion", label: "Stable Video Diffusion" },
    { host: "zeroscope", label: "ZeroScope" },
    { host: "moondream", label: "MoonDream" },
    { host: " KlingAI", label: "Kling AI" },
    { host: "hailuo", label: "Hailuo AI" },
    { host: "minimax", label: "MiniMax" },
  ];

  for (const { host, label } of aiVideoHosts) {
    if (lower.includes(host)) {
      score = Math.max(score, 85);
      flags.push(`AI video platform: ${label}`);
    }
  }

  // Known AI video generation terms in URL
  const aiVideoTerms = [
    { pattern: /gen(-|_)?video/i, label: "generative video" },
    { pattern: /ai(-|_)?generated/i, label: "AI-generated marker" },
    { pattern: /synthetic(-|_)?media/i, label: "synthetic media" },
    { pattern: /deep(-|_)?fake/i, label: "deepfake indicator" },
    { pattern: /stable(-|_)?diff/i, label: "Stable Diffusion" },
    { pattern: /midjourney/i, label: "Midjourney" },
    { pattern: /dall(-|_)?e/i, label: "DALL-E" },
    { pattern: /\bgenAIC|\bai-video|\bcontent-ai/i, label: "domain suggests AI content" },
  ];

  for (const { pattern, label } of aiVideoTerms) {
    if (pattern.test(lower)) {
      score = Math.max(score, 70);
      flags.push(`URL contains: ${label}`);
    }
  }

  return { score, flags };
};

/** Get YouTube thumbnail URL from video ID */
const getYouTubeThumbnail = (videoId, quality = "default") => {
  const qualityMap = { default: "default.jpg", medium: "mqdefault.jpg", high: "hqdefault.jpg" };
  return `https://img.youtube.com/vi/${videoId}/${qualityMap[quality]}`;
};

/** Detect AI-generated videos by URL analysis */
const detectAIVideo = (url) => {
  const flags = [];
  let score = 0;

  const parsed = parseVideoUrl(url);
  const urlLower = url.toLowerCase();

  // 1. Check AI video hosts/terms
  const aiHostCheck = checkAiVideoHosts(url);
  score += aiHostCheck.score;
  flags.push(...aiHostCheck.flags);

  // 2. Platform-specific analysis
  if (parsed.source === "youtube" && parsed.id) {
    flags.push("YouTube video detected");
    flags.push(`Video ID: ${parsed.id}`);
    flags.push(`Thumbnail: ${getYouTubeThumbnail(parsed.id)}`);
    score = Math.max(score, 10); // YouTube is neutral
  } else if (parsed.source === "instagram" && parsed.id) {
    flags.push("Instagram video/reel detected");
    flags.push(`Media ID: ${parsed.id}`);
    score = Math.max(score, 15); // Instagram is slightly suspicious (lots of AI content)
  } else if (parsed.source === "vimeo" && parsed.id) {
    flags.push("Vimeo video detected");
    score = Math.max(score, 10);
  } else if (parsed.source === "unknown") {
    flags.push("Unrecognized video URL format");
    score = Math.max(score, 25); // Unknown sources are suspicious

    // Check if it might be a direct video file
    if (/\\\.(mp4|webm|ogg|mov|avi|mkv)/i.test(url)) {
      flags.push("Direct video file URL");
      flags.push("Cannot verify source authenticity");
      score = Math.max(score, 30);
    }
  }

  // 3. Check for short URL services that hide the real source
  const shorteners = ["bit.ly", "tinyurl", "t.co", "buff.ly", "ow.ly", "qr.io", "rb.gy", "shorturl.at"];
  if (shorteners.some((s) => urlLower.includes(s))) {
    flags.push("URL uses shortener service — actual source hidden");
    score += 20;
  }

  // 4. TikTok detection (often has AI-generated content)
  if (parsed.source === "tiktok" || /tiktok\.com/i.test(url)) {
    flags.push("TikTok video detected");
    flags.push("TikTok has high volume of AI-generated content");
    score = Math.max(score, 25);
    if (parsed.id) {
      flags.push(`Video ID: ${parsed.id}`);
    }
  }

  const tier =
    score >= 80 ? "AI_DEFINITE" :
    score >= 55 ? "AI_LIKELY" :
    score >= 30 ? "SUSPICIOUS" : "AUTHENTIC";

  return {
    score: Math.min(99, score),
    tier,
    flags: flags.length > 0 ? flags : ["No AI indicators found in video URL"]
  };
};

// Check if a URL points to an AI generative domain/tool
const isAIGenerativeUrl = (urlStr) => {
  if (!urlStr) return false;
  const lowerUrl = urlStr.toLowerCase();

  // Specific domains/keywords
  const aiKeywords = ["chatgpt", "claude", "deepseek", "gemini", "openai", "midjourney", "suno", "elevenlabs", "copilot", "perplexity", "v0.dev"];
  for (const kw of aiKeywords) {
    if (lowerUrl.includes(kw)) {
      return true;
    }
  }

  // General "anything with AI" in domain
  try {
    const urlObj = new URL(urlStr);
    const host = urlObj.hostname;
    if (host.endsWith(".ai") ||
      host.includes("ai.") ||
      host.includes(".ai-") ||
      host.startsWith("ai-") ||
      host.includes("-ai-") ||
      host.endsWith("-ai") ||
      /\bai\b/.test(host)) {
      return true;
    }
  } catch (e) {
    if (lowerUrl.includes(".ai") || lowerUrl.includes("/ai/")) {
      return true;
    }
  }

  return false;
};

// Check if a string contains typical AI buzzwords, emojis, lists, or hyphen compounds
const analyzeTextHeuristics = (text) => {
  const cleanText = text.trim();
  if (cleanText.length < 15) return null; // Very short text — need at least a sentence

  let score = 0;
  const reasons = [];

  // ── SHORT-TEXT AI DETECTION ──────────────────────────────────────────
  // Patterns that identify AI-generated text even in very short snippets
  // (15-200 chars) where narrative classifiers can't operate.
  if (cleanText.length < 200) {
    // A1. Overly polished greeting + formal structure in short text
    //     Real short messages are casual; AI short messages are formal.
    const shortFormalGreeting = /^(Dear|Hello|Hi there|Greetings|Good (morning|afternoon|evening)),?\s/i.test(cleanText);
    const shortFormalClosing = /(Best regards|Sincerely|Kind regards|Thank you|Cheers),?\s*$/i.test(cleanText);
    if (shortFormalGreeting && shortFormalClosing && cleanText.length < 300) {
      score += 30;
      reasons.push("Short-Text AI: Formal greeting + formal closing in short text — AI mimics email structure even in brief messages");
    }

    // A2. Perfect grammar + no contractions in casual context
    const hasNoContractions = !/\b(can't|won't|don't|isn't|aren't|wasn't|weren't|hasn't|haven't|hadn't|couldn't|wouldn't|shouldn't|I'm|I've|I'd|I'll|we're|we've|we'd|we'll|they're|they've|they'd|they'll|that's|there's|here's|let's|what's|who's|how's)\b/i.test(cleanText);
    const hasFullFormNegations = /\b(do not|does not|did not|cannot|could not|would not|should not|will not|have not|has not|had not|is not|are not|was not|were not)\b/i.test(cleanText);
    const wordCount = cleanText.split(/\s+/).length;
    if (hasNoContractions && hasFullFormNegations && wordCount >= 5 && wordCount <= 50) {
      score += 25;
      reasons.push("Short-Text AI: Full-form negations without contractions in short text — AI over-formalizes brief messages");
    }

    // A3. Buzzword density in short text
    const shortBuzzwords = /\b(leverage|synerg(y|ize)|streamline|optimize|enhance|revolutionize|transform|innovate|empower|unleash|unlock|elevate|accelerate|holistic|paradigm|ecosystem|seamless|cutting.edge|game.changing|best.in.class|world.class|industry.leading)\b/gi;
    const buzzMatches = cleanText.match(shortBuzzwords) || [];
    if (buzzMatches.length >= 2 && wordCount <= 50) {
      score += 25;
      reasons.push(`Short-Text AI: ${buzzMatches.length} corporate buzzwords in ${wordCount} words — AI loads short text with marketing jargon`);
    }

    // A4. Sentence-level uniformity in short text
    const shortSentences = cleanText.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0);
    if (shortSentences.length >= 2 && shortSentences.length <= 6) {
      const sLens = shortSentences.map(s => s.split(/\s+/).length);
      const avg = sLens.reduce((a, b) => a + b, 0) / sLens.length;
      const maxDev = Math.max(...sLens.map(l => Math.abs(l - avg)));
      if (maxDev < avg * 0.2 && avg >= 5) {
        score += 20;
        reasons.push("Short-Text AI: Uniform sentence lengths in short text — humans vary more even in brief messages");
      }
    }

    // A5. No typos, no informal markers
    const hasInformalMarkers = /\b(lol|omg|btw|tbh|imo|imo|ngl|smh|fwiw|fyi|idk|brb|ttyl|gotta|wanna|gonna|kinda|sorta|dunno|y'all|ain't)\b/i.test(cleanText);
    const hasTypo = /\b(teh|hte|adn|nad|fo|ot|taht|thn|bcuase|beacuse|alot|definately|occured|recieve|seperate|accomodate)\b/i.test(cleanText);
    if (!hasInformalMarkers && !hasTypo && wordCount >= 8 && wordCount <= 40 && !cleanText.includes('\n')) {
      score += 15;
      reasons.push("Short-Text AI: Perfect grammar with no informal markers in short text — suspiciously polished");
    }

    // A6. Formulaic short AI patterns
    const formulaicShort = [
      { pattern: /\bI'd be happy to\b/i, label: "Formulaic AI offer: 'I'd be happy to'" },
      { pattern: /\bHere'?s? (a |an |the )?(summary|overview|breakdown|list)\b/i, label: "Formulaic AI structure: 'Here's a [noun]'" },
      { pattern: /\bLet me (help|assist|explain|clarify|show)\b/i, label: "Formulaic AI offer: 'Let me [verb]'" },
      { pattern: /\bCertainly[!]?\s/i, label: "AI affirmative: 'Certainly!'" },
      { pattern: /\bGreat question[!]?\s/i, label: "AI deflection: 'Great question!'" },
      { pattern: /\bHere (are|is) (the |some |a )?\d+\b/i, label: "AI list format: 'Here are [N]...'" },
      { pattern: /\bIn (summary|conclusion|essence),?\b/i, label: "AI conclusion marker" },
      { pattern: /\bWould you like me to\b/i, label: "AI offer: 'Would you like me to'" },
    ];
    let formulaicHits = 0;
    formulaicShort.forEach(item => {
      if (item.pattern.test(cleanText)) {
        formulaicHits++;
        reasons.push(`Short-Text AI: ${item.label}`);
      }
    });
    if (formulaicHits >= 1) {
      score += 20 * formulaicHits;
    }

    // A7. Emoji-only or emoji-heavy short text
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2700}-\u{27BF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}]/gu;
    const emojis = cleanText.match(emojiRegex) || [];
    const nonEmojiWords = cleanText.replace(emojiRegex, '').trim().split(/\s+/).filter(w => w.length > 0).length;
    if (emojis.length >= 3 && nonEmojiWords <= 10) {
      score += 20;
      reasons.push(`Short-Text AI: ${emojis.length} emojis with only ${nonEmojiWords} words — AI-generated reaction content`);
    }
  }

  // 1. Emoji density and AI/corporate patterns
  // Emojis: Spaceship (🚀), Sparkles (✨), Brain (🧠), Lightbulb (💡), Target (🎯), Briefcase (💼), Handshake (🤝), fire (🔥), chart (📈)
  const corporateEmojis = [
    { char: "🚀", label: "Spaceship emoji (hype indicator)" },
    { char: "✨", label: "Sparkles emoji (standard AI aesthetic)" },
    { char: "💼", label: "Briefcase emoji (corporate post indicator)" },
    { char: "🤝", label: "Handshake emoji (generic connection post)" },
    { char: "🧠", label: "Brain emoji (AI intelligence pitch)" },
    { char: "💡", label: "Lightbulb emoji (typical solution pitch)" },
    { char: "🎯", label: "Target emoji (corporate marketing format)" },
    { char: "📈", label: "Chart emoji (growth pitch)" },
    { char: "🔥", label: "Fire emoji (hype descriptor)" }
  ];

  let emojiScore = 0;
  let matchedEmojis = [];
  corporateEmojis.forEach(emoji => {
    const regex = new RegExp(emoji.char, "g");
    const count = (cleanText.match(regex) || []).length;
    if (count > 0) {
      emojiScore += 15 * Math.min(count, 2);
      matchedEmojis.push(emoji.char);
      reasons.push(`Emoji detected: ${emoji.char} - ${emoji.label}`);
    }
  });

  if (matchedEmojis.length > 2) {
    emojiScore += 10;
    reasons.push("Multiple corporate/hype emojis (highly generative layout signature)");
  }

  // 2. Bold bullet lists headers (**Title:** description) - Typical GPT formatting
  // Matches structural outlines like: "* **Key Factor:** This is..."
  const boldBulletPattern = /(\*|-|\d+\.)\s+\*\*[^*]+\*\*:/g;
  const boldBulletMatches = cleanText.match(boldBulletPattern);
  if (boldBulletMatches) {
    const count = boldBulletMatches.length;
    score += 20 * Math.min(count, 3);
    reasons.push(`Generative formatting template: Bolded list headers (e.g. **Title**: details) (x${count})`);
  } else {
    // Check if plain bold headers followed by colons exist
    const plainBoldHeader = /\*\*[^*]+\*\*:/g;
    const plainMatches = cleanText.match(plainBoldHeader);
    if (plainMatches && plainMatches.length > 1) {
      score += 15;
      reasons.push("Overuse of bold inline headings with colons");
    }
  }

  // 3. Hyphenated descriptive compounds
  // e.g., cutting-edge, result-oriented, thought-provoking, state-of-the-art, game-changing, decision-making, value-added, end-to-end, real-time, user-friendly, cost-effective
  const targetHyphens = [
    { term: "cutting-edge", label: "descriptive compound ('cutting-edge')" },
    { term: "state-of-the-art", label: "descriptive compound ('state-of-the-art')" },
    { term: "game-changing", label: "descriptive compound ('game-changing')" },
    { term: "thought-provoking", label: "descriptive compound ('thought-provoking')" },
    { term: "decision-making", label: "process compound ('decision-making')" },
    { term: "user-friendly", label: "descriptive compound ('user-friendly')" },
    { term: "cost-effective", label: "descriptive compound ('cost-effective')" },
    { term: "value-added", label: "business compound ('value-added')" },
    { term: "result-oriented", label: "descriptive compound ('result-oriented')" },
    { term: "end-to-end", label: "structure compound ('end-to-end')" },
    { term: "real-time", label: "process compound ('real-time')" }
  ];

  targetHyphens.forEach(item => {
    const regex = new RegExp(`\\b${item.term}\\b`, "gi");
    const matches = cleanText.match(regex);
    if (matches) {
      score += 15 * matches.length;
      reasons.push(`Hyphenated descriptor: '${item.term}' (${item.label})`);
    }
  });

  // Generic dash check between word letters: e.g. "word-word"
  // Counts overall hyphenated descriptive compound density
  const generalHyphenRegex = /[a-zA-Z]+-[a-zA-Z]+/g;
  const generalHyphens = cleanText.match(generalHyphenRegex) || [];
  // If we have high density of hyphenated words (e.g. more than 3 hyphens in a short text segment)
  if (generalHyphens.length >= 3) {
    const uniqueHyphens = [...new Set(generalHyphens.map(s => s.toLowerCase()))];
    // Filter out common simple hyphens if any, but general density in AI summaries is very high
    score += 10;
    reasons.push(`High density of hyphenated word compounds (${uniqueHyphens.length} unique)`);
  }

  // Em-dash & En-dash transition checks: "—" or "–"
  // Highly characteristic of machine summaries separating side notes
  const dashRegex = /[\u2014\u2013]/g;
  const dashCount = (cleanText.match(dashRegex) || []).length;
  if (dashCount > 0) {
    score += 20 * Math.min(dashCount, 2);
    reasons.push(`Generative punctuation: Detected Em-dash or En-dash ('—' / '–') as clause separator`);
  }

  // 4. Overused AI Corporate Speak & Buzzwords
  const aiBuzzwords = [
    { term: /as an ai language model/i, points: 50, label: "AI model disclaimer boilerplate" },
    { term: /\bdelve\b/i, points: 20, label: "Unusual vocabulary preference ('delve')" },
    { term: /\btapestry\b/i, points: 20, label: "Unusual metaphor choice ('tapestry')" },
    { term: /\btestament to\b/i, points: 15, label: "Repetitive writing pattern ('testament to')" },
    { term: /\bsynergy\b/i, points: 15, label: "Corporate buzzword ('synergy')" },
    { term: /\belevate\b/i, points: 15, label: "AI transition word ('elevate')" },
    { term: /\bfoster\b/i, points: 12, label: "AI transition word ('foster')" },
    { term: /\bseamlessly\b/i, points: 12, label: "AI descriptive buffer ('seamlessly')" },
    { term: /\brevolutionize\b/i, points: 15, label: "Hype pitch verb ('revolutionize')" },
    { term: /\buncover\b/i, points: 10, label: "AI transition word ('uncover')" },
    { term: /\bimportant to note\b/i, points: 10, label: "Structural transition phrase" },
    { term: /\bin conclusion\b/i, points: 10, label: "Generic conclusion format" },
    { term: /\buncomfortable truth\b/i, points: 20, label: "AI copywriting template cliché" },
    { term: /\bno longer optional\b/i, points: 15, label: "AI pitch transition boilerplate" },
    { term: /\bunderestimate this\b/i, points: 15, label: "AI copywriting hook formula" }
  ];

  aiBuzzwords.forEach(item => {
    const matches = cleanText.match(item.term);
    if (matches) {
      score += item.points * matches.length;
      const termStr = item.term.toString().replace(/\\b|\/gi|\/i|\//g, "");
      reasons.push(`AI Buzzword/Phrase: '${termStr}' - ${item.label}`);
    }
  });

  // 5. LinkedIn/AI Hook: Robot, alert, or corporate emoji in the first line
  const lines = cleanText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
  if (lines.length > 0) {
    const firstLine = lines[0];
    const containsQuestion = firstLine.includes('?');
    const containsEmoji = /[\u{1F300}-\u{1F9FF}\u{2700}-\u{27BF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}]/u.test(firstLine);
    if (containsQuestion && containsEmoji) {
      emojiScore += 30;
      reasons.push("AI Hook Style: Text starts with a rhetorical question containing an emoji");
    }

    // Check for robot, alert, or corporate emojis in the first line specifically
    const targetEmojis = /🤖|🌐|💻|📢|🚀|✨|💡|🎯|📈|💼|🤝|🚨|⚠️|✅|❌|🔍|📊|😵|🔥|💥|🌟|⚡|👇/u;
    if (targetEmojis.test(firstLine)) {
      emojiScore += 45;
      reasons.push("AI Hook Style: First line starts with or contains a robot, warning, or corporate emoji");
    }
  }

  // 5b. Paragraphs starting with emojis (typical AI list/bullet spacing structure)
  const emojiStartLines = lines.filter(line => /^(🤖|🌐|💻|📢|🚀|✨|💡|🎯|📈|💼|🤝|🚨|⚠️|✅|❌|🔍|📊|😵|🔥|💥|🌟|⚡|👇)/u.test(line));
  if (emojiStartLines.length >= 2) {
    emojiScore += 30;
    reasons.push(`AI Formatting Structure: Multiple paragraphs start with corporate/robot emojis (x${emojiStartLines.length})`);
  }

  // Capping emoji score if no primary LLM emojis are present
  const hasLlmEmojis = /🚀|✅|✨|💡/u.test(cleanText);
  if (!hasLlmEmojis && emojiScore > 20) {
    emojiScore = 20;
    reasons.push("Emoji score capped at 20 (no primary LLM emojis like 🚀, ✅, ✨, or 💡 present)");
  }
  score += emojiScore;

  // 6. Concluding call to engagement question
  if (lines.length > 2) {
    const lastLine = lines[lines.length - 1];
    const isEngagementQuestion = lastLine.endsWith('?') || (lastLine.includes('?') && lastLine.length < 120);
    if (isEngagementQuestion) {
      score += 20;
      reasons.push("AI Closing: Text concludes with an engagement driving question");
    }
  }

  // 7. General Bullet points check (normal humans don't use bullet points very often)
  const bulletLines = lines.filter(line => /^(•|-|\*|→|▪|▫|◦|■|□|✔|✓|\d+\.)\s+/.test(line));
  if (bulletLines.length >= 2) {
    score += Math.min(bulletLines.length * 15, 45);
    reasons.push(`AI Formatting Structure: Text contains structured bullet points (x${bulletLines.length})`);
  }

  // 8. Generative case study metrics transition: "from X hours/days to Y/zero"
  const metricPattern = /from\s+\d+\s+(hour|day|week|month)s?\s+(down\s+)?to\s+(\d+|zero)/gi;
  const metricMatches = cleanText.match(metricPattern);
  if (metricMatches) {
    score += 25;
    reasons.push(`AI Narrative Metric Pattern: Overused metric reduction template ('from X hours to Y/zero')`);
  }

  // 9. AI Copywriting / Broetry Cadence Analysis
  const paragraphs = cleanText.split(/\n\s*\n/).map(p => p.trim()).filter(p => p.length > 0);
  if (paragraphs.length >= 4) {
    let singleSentenceCount = 0;
    let ultraShortCount = 0;
    paragraphs.forEach(p => {
      const sentences = p.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0);
      if (sentences.length === 1) {
        singleSentenceCount++;
      }
      const words = p.split(/\s+/).filter(w => w.length > 0);
      if (words.length >= 1 && words.length <= 4) {
        ultraShortCount++;
      }
    });

    const singleRatio = singleSentenceCount / paragraphs.length;
    if (singleRatio >= 0.70) {
      score += 35;
      reasons.push(`AI Copywriting Layout: High density of isolated single-sentence paragraphs (${Math.round(singleRatio * 100)}% of blocks)`);
    }

    if (ultraShortCount >= 3) {
      score += 25;
      reasons.push(`AI Copywriting Layout: Multiple choppy, ultra-short lines (1-4 words) used for dramatic pacing`);
    }

    // 10. Rhetorical Repetitive Starters (Anaphora)
    const firstWords = paragraphs
      .map(p => p.split(/\s+/)[0])
      .filter(w => w && w.length > 1)
      .map(w => w.toLowerCase().replace(/[^a-z]/g, ''));
    
    const wordFreq = {};
    firstWords.forEach(w => {
      wordFreq[w] = (wordFreq[w] || 0) + 1;
    });

    let maxRepetition = 0;
    let repeatedWord = "";
    for (const w in wordFreq) {
      if (wordFreq[w] > maxRepetition) {
        maxRepetition = wordFreq[w];
        repeatedWord = w;
      }
    }

    if (maxRepetition >= 3 && ["your", "the", "proof", "build", "this", "clean", "good"].includes(repeatedWord)) {
      score += 25;
      reasons.push(`AI Copywriting Hook: Anaphora layout detected (multiple blocks start with repetitive word '${repeatedWord}')`);
    }
  }

  // 11. General AI Narrative / Personal Essay Patterns
  // Catches AI-generated personal narratives, application essays, and reflective
  // prose that lack the typical LinkedIn/corporate markers but still exhibit
  // mechanical smoothness characteristic of LLM output.

  // A. AI Transition Phrase Overuse — LLMs favor structured connectors to bridge
  //    ideas. Humans use them occasionally; AI over-uses them.
  const aiTransitions = [
    { pattern: /\bThis led me to\b/gi, label: "'This led me to' (formulaic causal bridge)" },
    { pattern: /\bBecause of this\b/gi, label: "'Because of this' (formulaic causal bridge)" },
    { pattern: /\bThat whole experience taught me\b/gi, label: "'That whole experience taught me' (template reflection)" },
    { pattern: /\btaught me a big lesson\b/gi, label: "'taught me a big lesson' (template reflection)" },
    { pattern: /\bcompletely changed my\b/gi, label: "'completely changed my' (formulaic transformation)" },
    { pattern: /\bI do not want\b/gi, label: "'I do not want' (formal contraction in personal register)" },
    { pattern: /\bmy passion was always there\b/gi, label: "'my passion was always there' (AI resolution cliché)" },
    { pattern: /\bwalked away from\b/gi, label: "'walked away from' (formulaic distancing)" },
    { pattern: /\btruly matter\b/gi, label: "'truly matter' (AI intensifier phrase)" },
    { pattern: /\bBack in \d{4}\b/gi, label: "'Back in [year]' (formulaic temporal opener)" },
    { pattern: /\btricked me\b/gi, label: "'tricked me' (overly dramatic causal attribution)" },
    { pattern: /\bthe thing I loved doing most\b/gi, label: "'the thing I loved doing most' (template phrasing)" },
    { pattern: /\bjust could not stay away\b/gi, label: "'just could not stay away' (formulaic turning point)" },
    { pattern: /\bI want to make.*stronger.*easier\b/gi, label: "'I want to make...stronger...easier' (template mission statement)" },
    { pattern: /\bno one else gets tricked\b/gi, label: "'no one else gets tricked' (template mission closure)" },
    { pattern: /\bthe way I did\b/gi, label: "'the way I did' (template reflective closure)" },
  ];
  let transitionHits = 0;
  aiTransitions.forEach(item => {
    const matches = cleanText.match(item.pattern);
    if (matches) {
      transitionHits += matches.length;
      reasons.push(`AI Narrative Transition: ${item.label} (x${matches.length})`);
    }
  });
  if (transitionHits >= 3) {
    score += 10 * Math.min(transitionHits, 6);
    reasons.push(`AI Narrative Transitions: ${transitionHits} formulaic connector phrases detected — LLMs over-use structured causal bridges to link ideas`);
  }

  // B. Causal Connector Density — AI text chains cause-effect statements with
  //    high frequency ('because', 'led to', 'so', 'taught me', 'resulted in').
  const causalWords = cleanText.toLowerCase().match(/\b(because|therefore|thus|hence|consequently|led to|resulted in|taught me|made me|caused me|this led|so I|so it)\b/g) || [];
  const textSentences = cleanText.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0);
  const causalDensity = causalWords.length / Math.max(1, textSentences.length);
  if (causalDensity > 0.25 && textSentences.length >= 3) {
    score += 20;
    reasons.push(`AI Narrative Structure: High causal connector density (${causalWords.length} connectors across ${textSentences.length} sentences) — AI chains cause-effect at an unnatural rate`);
  } else if (causalDensity > 0.15 && textSentences.length >= 5) {
    score += 10;
    reasons.push(`AI Narrative Structure: Elevated causal connector density (${causalWords.length} connectors)`);
  }

  // C. Uniform Sentence Length (Burstiness) — Human writing alternates short
  //    punchy sentences with longer complex ones. AI tends toward uniform length.
  if (textSentences.length >= 4) {
    const wc = textSentences.map(s => s.split(/\s+/).length);
    const wordAvg = wc.reduce((a, b) => a + b, 0) / wc.length;
    const maxDev = Math.max(...wc.map(w => Math.abs(w - wordAvg)));
    const uniformity = maxDev / Math.max(1, wordAvg);
    if (uniformity < 0.25) {
      score += 20;
      reasons.push(`AI Narrative Cadence: Highly uniform sentence length (max deviation ${Math.round(uniformity * 100)}% from mean) — human writing varies sentence length dramatically`);
    } else if (uniformity < 0.35) {
      score += 10;
      reasons.push(`AI Narrative Cadence: Moderately uniform sentence length (max deviation ${Math.round(uniformity * 100)}% from mean)`);
    }
  }

  // D. Template-like Emotional Progression — AI narratives follow a predictable
  //    emotional arc: setup(fear/doubt) → struggle → return → resolution → mission.
  const arcPhases = [
    { pattern: /\b(scared|afraid|worried|doubt|fear|anxious|nervous)\b/gi, phase: "fear" },
    { pattern: /\b(walked away|moved on|gave up|left|turned away|stepped away)\b/gi, phase: "departure" },
    { pattern: /\b(could not stay|came back|returned|started again|couldn't stay away|drew me back)\b/gi, phase: "return" },
    { pattern: /\b(passion was always|always there|never left|always loved|deep down)\b/gi, phase: "rediscovery" },
    { pattern: /\b(changed my|transformed|lesson|taught me|big lesson)\b/gi, phase: "lesson" },
    { pattern: /\b(no one else|don't want anyone|prevent|stop|make sure)\b/gi, phase: "mission" },
  ];
  const phasesFound = arcPhases.filter(p => { p.pattern.lastIndex = 0; return p.pattern.test(cleanText); }).map(p => p.phase);
  if (phasesFound.length >= 4) {
    score += 25;
    reasons.push(`AI Narrative Arc: ${phasesFound.length}-phase template emotional arc detected (${phasesFound.join(' → ')}) — AI generates textbook problem→struggle→return→mission arcs`);
  } else if (phasesFound.length >= 3) {
    score += 12;
    reasons.push(`AI Narrative Arc: ${phasesFound.length}-phase emotional arc detected (${phasesFound.join(' → ')}) — common in AI-generated personal narratives`);
  }

  // E. Overly Smooth Sentence Openers — Humans vary sentence beginnings; AI
  //    often uses pronoun-heavy, subject-first openings (I, My, This, That).
  if (textSentences.length >= 5) {
    const openers = textSentences.map(s => {
      const w = s.split(/\s+/)[0]?.toLowerCase().replace(/[^a-z]/g, '');
      return w || '';
    }).filter(w => w.length > 0);
    const pronounOpeners = openers.filter(w => ['i', 'my', 'this', 'that', 'still', 'however', 'because'].includes(w));
    const pronounRatio = pronounOpeners.length / openers.length;
    if (pronounRatio > 0.6) {
      score += 15;
      reasons.push(`AI Narrative Voice: ${Math.round(pronounRatio * 100)}% of sentences open with pronouns or formulaic starters (I/My/This/That/Still/However) — humans vary openings more`);
    }
  }

  // F. Perfect Grammar with Formal Register in Personal Text — AI-generated
  //    personal narratives often use full contractions ('do not' vs 'don't')
  //    and avoid contractions entirely in informal contexts.
  const fullFormNegations = cleanText.match(/\b(do not|does not|did not|cannot|could not|would not|should not|will not|have not|has not|had not|was not|were not|is not|are not)\b/gi) || [];
  const contractionMatches = cleanText.match(/\b(don't|doesn't|didn't|can't|couldn't|wouldn't|shouldn't|won't|haven't|hasn't|hadn't|wasn't|weren't|isn't|aren't|I'm|I've|I'd|I'll)\b/gi) || [];
  const isPersonalNarrative = /\bI (was|am|have|had|started|began|felt|wanted|loved|decided|learned|built|chose)\b/i.test(cleanText);
  if (isPersonalNarrative && fullFormNegations.length >= 3 && contractionMatches.length <= fullFormNegations.length) {
    score += 15;
    reasons.push(`AI Narrative Register: ${fullFormNegations.length} full-form negations ('do not', 'did not', etc.) vs ${contractionMatches.length} contractions — AI over-formalizes personal narrative text`);
  }

  // G. AI Phishing / Scam Email Patterns — AI-generated phishing emails and
  //    scam messages use specific urgency/fear tactics and formulaic praise that
  //    differ from human-written spam (which is often poorly written).
  const phishingPatterns = [
    { pattern: /\bspecial reward\b/gi, points: 15, label: "Scam lure: 'special reward'" },
    { pattern: /\bcash prize\b/gi, points: 15, label: "Scam lure: 'cash prize'" },
    { pattern: /\bselected (you|from)\b/gi, points: 12, label: "Scam lure: 'selected you/from'" },
    { pattern: /\bhard work and contributions\b/gi, points: 12, label: "Scam lure: generic praise template" },
    { pattern: /\bnot a joke and it is not a trick\b/gi, points: 18, label: "Scam tell: redundant legitimacy assertion" },
    { pattern: /\bnot a trick\b/gi, points: 12, label: "Scam tell: 'not a trick' defensiveness" },
    { pattern: /\bact fast\b/gi, points: 15, label: "Scam urgency: 'act fast'" },
    { pattern: /\bonly (open|available) for a short time\b/gi, points: 15, label: "Scam urgency: artificial time pressure" },
    { pattern: /\bjust need to confirm\b/gi, points: 10, label: "Scam call-to-action: minimizes effort" },
    { pattern: /\bonly take(s)? (two|2|a couple) minutes?\b/gi, points: 10, label: "Scam call-to-action: trivializes effort" },
    { pattern: /\bclick the link below\b/gi, points: 15, label: "Scam call-to-action: link click pressure" },
    { pattern: /\bfill out the form\b/gi, points: 10, label: "Scam call-to-action: form filling" },
    { pattern: /\byour name came up\b/gi, points: 12, label: "Scam lure: impersonal selection claim" },
    { pattern: /\bchosen from a small group\b/gi, points: 12, label: "Scam lure: exclusivity appeal" },
    { pattern: /\bwe want to give this to you\b/gi, points: 12, label: "Scam lure: unsolicited gift framing" },
    { pattern: /\bconfirm your details\b/gi, points: 12, label: "Scam call-to-action: personal data request" },
    { pattern: /\bsend you the full details\b/gi, points: 10, label: "Scam lure: deferred information" },
    { pattern: /\bwe are excited to\b/gi, points: 8, label: "Scam tone: forced enthusiasm" },
    { pattern: /\blook(s)? forward to\b/gi, points: 8, label: "Scam tone: formulaic closing" },
    { pattern: /\bwell known company\b/gi, points: 12, label: "Scam lure: vague authority appeal" },
    { pattern: /\bindustry leaders\b/gi, points: 10, label: "Scam lure: prestige appeal" },
    { pattern: /\byour potential\b/gi, points: 10, label: "Scam lure: flattery appeal" },
    { pattern: /\bprivate event\b/gi, points: 10, label: "Scam lure: exclusivity appeal" },
    { pattern: /\breward includes\b/gi, points: 10, label: "Scam lure: benefit enumeration" },
    { pattern: /\breply to this email\b/gi, points: 10, label: "Scam call-to-action: email reply pressure" },
    { pattern: /\bthe selection team\b/gi, points: 12, label: "Scam tell: anonymous authority signature" },
  ];

  let phishingScore = 0;
  let phishingHits = 0;
  phishingPatterns.forEach(item => {
    const matches = cleanText.match(item.pattern);
    if (matches) {
      phishingScore += item.points * matches.length;
      phishingHits += matches.length;
      reasons.push(`AI Phishing Pattern: ${item.label} (x${matches.length})`);
    }
  });
  // Phishing patterns are highly specific — multiple hits strongly indicate AI-generated scam content
  if (phishingHits >= 3) {
    score += phishingScore;
  } else if (phishingHits === 2) {
    score += Math.min(phishingScore, 25);
  } else if (phishingHits === 1) {
    score += Math.min(phishingScore, 15);
  }

  // H. Conversational AI Text Patterns — Catches AI-generated text that avoids
  //    typical LLM buzzwords but still exhibits mechanical smoothness.
  //    This catches phishing emails, scam letters, and plain AI prose.

  // Overly formal register in short personal/business text
  const formalPatterns = [
    { pattern: /\bI am writing to (tell|inform|let you know)\b/gi, points: 12, label: "Overly formal opener: 'I am writing to...'" },
    { pattern: /\bPlease reply to this\b/gi, points: 8, label: "Formulaic closing: 'Please reply to this'" },
    { pattern: /\bWe think you deserve\b/gi, points: 10, label: "Formulaic praise: 'We think you deserve'" },
    { pattern: /\bWe see your potential\b/gi, points: 10, label: "Formulaic flattery: 'We see your potential'" },
    { pattern: /\bThis is not a\b/gi, points: 5, label: "Defensive framing: 'This is not a...'" },
    { pattern: /\bBest regards,?\b/gi, points: 5, label: "Formulaic email closing: 'Best regards'" },
    { pattern: /\bPlease (reply|respond|confirm|click|fill|provide)\b/gi, points: 5, label: "Formulaic request: 'Please [action]'" },
    { pattern: /\bif you have any questions\b/gi, points: 8, label: "Formulaic offer: 'if you have any questions'" },
    { pattern: /\bwe (are|will|have)\b/gi, points: 3, label: "Corporate 'we' voice (institutional impersonal)" },
  ];

  let formalScore = 0;
  let formalHits = 0;
  formalPatterns.forEach(item => {
    const matches = cleanText.match(item.pattern);
    if (matches) {
      formalScore += item.points * matches.length;
      formalHits += matches.length;
      reasons.push(`AI Conversational Pattern: ${item.label} (x${matches.length})`);
    }
  });
  // High formal pattern density in short text indicates AI generation
  const wordCount = cleanText.split(/\s+/).length;
  if (formalHits >= 3) {
    score += formalScore;
  } else if (formalHits === 2 && wordCount < 500) {
    score += Math.min(formalScore, 20);
  }

  // I. Plain-text AI Cadence — Even without buzzwords, AI text exhibits
  //    predictable sentence structure. Check for repetitive sentence starters
  //    and uniform paragraph length in non-corporate text.
  if (textSentences.length >= 4 && wordCount >= 100) {
    const starters = textSentences.map(s => {
      const words = s.split(/\s+/).slice(0, 3).join(' ').toLowerCase();
      return words;
    });
    const starterFreq = {};
    starters.forEach(s => { starterFreq[s] = (starterFreq[s] || 0) + 1; });
    let maxStarterRepeat = 0;
    for (const k in starterFreq) {
      if (starterFreq[k] > maxStarterRepeat) maxStarterRepeat = starterFreq[k];
    }
    if (maxStarterRepeat >= 3) {
      score += 15;
      reasons.push(`AI Text Pattern: Repetitive sentence opening structure (${maxStarterRepeat}x same 3-word start)`);
    }
  }

  // Track whether social-engineering patterns fired — if so, we suppress the
  //  humanScoreReduction because those 'human indicators' (lowercase sentences,
  //  lowercase 'i', casual tone) are exactly what humanized phishing deliberately
  //  uses to appear authentic.
  let socialEngineeringDetected = false;

  // N. Humanized Phishing Detection — Catches phishing/scam emails that have
  //    been rewritten to bypass naive AI detectors. Even when humanized with
  //    personality, specific details, and varied sentence structure, these emails
  //    retain core social-engineering patterns that differ from legitimate
  //    business communication.

  // N1. Urgency + Benefit Combo — The core social engineering tactic: promise
  //     something valuable with artificial time pressure. Legitimate event
  //     invitations rarely combine "money" with "deadline" in the same email.
  const hasBenefit = /\b(stipend|money|cash|prize|reward|payment|honorarium|compensation)\b/i.test(cleanText);
  const hasUrgency = /\b(act fast|deadline|only (open|available)|spots? left|time is running|limited (time|spots?|space)|closing soon|final (day|call)|last chance|by friday|end of (the week|this week)|48 hours|before it.?s? (too late|gone))\b/i.test(cleanText);
  if (hasBenefit && hasUrgency) {
    score += 20;
    socialEngineeringDetected = true;
    reasons.push("Humanized Phishing: Combines benefit promise (money/reward) with artificial urgency — classic social engineering combo rarely seen in legitimate emails");
  }

  // N2. Unrequested Opportunity with CTA — A stranger emails you offering
  //     something valuable and asks you to fill out a form or click a link.
  //     Legitimate business emails from known contacts don't need to justify
  //     their own existence ("this is not a joke").
  const hasCTA = /\b(fill out|click the|follow the link|sign up|register|submit|apply|confirm your|verify your|provide your|link below|form (linked|at the|below)|takes (a |about a )?minute)\b/i.test(cleanText);
  const hasUnsolicited = /\b(your name came up|stopped on your name|you (were|have been) (selected|chosen|picked|nominated|shortlisted)|we (found|noticed|discovered) you|your (profile|work|profile came|name came|name (was|is))|pulled up.*your name|reached? out to you)\b/i.test(cleanText);
  if (hasCTA && hasUnsolicited) {
    score += 18;
    socialEngineeringDetected = true;
    reasons.push("Humanized Phishing: Unsolicited opportunity combined with a call-to-action (form/link) — hallmark of social engineering emails");
  }

  // N3. Pre-emptive Trust Building — Legitimate emails don't need to insist
  //     they're real. Phishing emails often include trust-defusing phrases.
  const trustBuilding = [
    { pattern: /\b(nothing creepy\b|not (a )?(joke|trick|scam|spam))/gi, label: "Pre-emptive trust assertion" },
    { pattern: /\b(i (actually|genuinely|really) (read|check|respond))/gi, label: "Over-proactive responsiveness claim" },
    { pattern: /\b(this is (my )?(personal|real|actual))/gi, label: "Identity authenticity claim" },
    { pattern: /\b(don'?t (ask|worry|fret)|nothing (weird|creepy|strange))\b/gi, label: "Suspicion deflection" },
  ];
  let trustHits = 0;
  trustBuilding.forEach(item => {
    if (item.pattern.test(cleanText)) {
      trustHits++;
      reasons.push(`Humanized Phishing: ${item.label} — legitimate senders don't preemptively defend against suspicion`);
    }
  });
  if (trustHits >= 2) {
    score += 15;
  }

  // N4. Vague Authority + Deferred Details — The sender references an
  //     authority figure (boss, colleague) but can't provide specifics about
  //     the opportunity, budget, or logistics. "I don't know" repeated about
  //     key details is a phishing hallmark (prevents fact-checking).
  const vagueAuthority = /\b(my (boss|manager|director|colleague|coworker|team lead)|she'?s? (handling|managing|in charge of|controlling))\b/i.test(cleanText);
  const deferredDetails = [
    /\b(i (don'?t know|have no idea|can'?t (remember|recall|confirm|say)))/gi,
    /\b(don'?t (ask|quote) me)/gi,
    /\b(i (would|'?ll?) have to (check|verify|look|ask))/gi,
    /\b(she'?s? (said|mentioned) (that )?(it (might|could|would) be|around))/gi,
  ];
  let deferredHits = 0;
  deferredDetails.forEach(p => { deferredHits += (cleanText.match(p) || []).length; });
  if (vagueAuthority && deferredHits >= 2) {
    score += 15;
    reasons.push(`Humanized Phishing: Defers to unnamed authority and can't confirm key details (${deferredHits} uncertainty statements) — prevents recipient from fact-checking`);
  }

  // N5. Excessive Self-Deprecation as Social Lubricant — Humanized phishing
  //     emails overuse self-deprecation to build false rapport and disarm
  //     suspicion. Real business emails are brief and don't apologize for
  //     their own length.
  const selfDeprecation = [
    /\b(i'?m (terrible|bad|awful|the worst) at (writing|emails?|being concise|communicating))/gi,
    /\b(sorry (this is|if (this is|it'?s) )?(so |really )?(long|verbose|a lot))/gi,
    /\b(my (girlfriend|boyfriend|partner|wife|husband|friend) (says|told|tells) (me|i))/gi,
    /\b(i (keep )?(meaning to|meant to|was (going to|supposed to)))/gi,
  ];
  let selfDepHits = 0;
  selfDeprecation.forEach(p => { selfDepHits += (cleanText.match(p) || []).length; });
  if (selfDepHits >= 2) {
    score += 12;
    reasons.push(`Humanized Phishing: ${selfDepHits} self-deprecating / rapport-building phrases — overuse of social lubricant to disarm suspicion`);
  }

  // N6. Perfect Narrative Embedded in Email Format — The email tells a
  //     complete story with named characters, specific locations, and a
  //     chronological arc. Real business emails are transactional, not
  //     narrative. This catches "humanized" phishing that wraps the scam
  //     in a story to bypass pattern detectors.
  const namedCharacters = cleanText.match(/\b[A-Z][a-z]+ (said|told|asked|showed|handed|pulled|reminded|mentioned|wanted|organized|booked|finalized)/g) || [];
  const specificLocations = cleanText.match(/\b(street|avenue|road|boulevard|plaza|drive|lane|floor|building|room|venue|coworking|office)\b/gi) || [];
  const dialogueQuotes = cleanText.match(/"[^"]{10,}"/g) || [];
  if (namedCharacters.length >= 2 && dialogueQuotes.length >= 2) {
    score += 18;
    reasons.push(`Humanized Phishing: Email contains a narrative with ${namedCharacters.length} named characters and ${dialogueQuotes.length} dialogue quotes — legitimate business emails are transactional, not story-driven`);
  }

  // N7. Form/Link + Scarcity Combo — Asking someone to fill out a form while
  //     simultaneously claiming limited availability is the signature of
  //     social engineering. The form is the payload delivery mechanism.
  const hasForm = /\b(google form|form|link below|link at the|click the link|sign-up|registration form|form linked|form is linked)\b/i.test(cleanText);
  const hasScarcity = /\b(\d+ (of|out of|spots?|seats?|places?|slots?) left|room for|only (a few|\d+)|filling (fast|up)|limited (availability|spots?|space)|\d+ (already )?(confirmed|filled|taken)|headcount|finalize.*(headcount|catering|number)|by (friday|monday|end of))\b/i.test(cleanText);
  if (hasForm && hasScarcity) {
    score += 15;
    socialEngineeringDetected = true;
    reasons.push("Humanized Phishing: Combines form/link request with scarcity claim — social engineering payload delivery with artificial pressure");
  }

  // N8. Reluctant Sender Frame — "I was asked to send this" / "here I am"
  //     creates false authenticity. Real reluctant senders just don't send.
  const reluctantFrame = /\b(here I am|she (said|told) me to|i (was (told|asked|instructed) to|had to|needed to)|someone (told|asked|made) me|making me do this|she (made|forced|asked|told) me)/i.test(cleanText);
  if (reluctantFrame) {
    score += 10;
    socialEngineeringDetected = true;
    reasons.push("Humanized Phishing: 'Reluctant sender' frame — the sender claims they were told/forced to send this, creating false authenticity");
  }

  // N9. Email That Tells Its Own Origin Story — Legitimate business emails
  //     are transactional: state purpose, ask for action. They don't narrate
  //     how they came to be written. When an email explains its own genesis
  //     (who found the name, how the list was made, what happened at the
  //     meetup), it's a humanization tactic wrapping social engineering.
  const originStory = [
    /\b(it (started|began|came about) (when|because|at|from|with))/gi,
    /\b(she (said|told|showed|handed|pulled|pointed))/gi,
    /\b(he (said|told|showed|handed|pulled|pointed))/gi,
    /\b(afterward|meanwhile|after that|before that|then she|then he)/gi,
    /\b(subscriber list|mailing list|email list|csv file|spreadsheet)/gi,
  ];
  let originHits = 0;
  originStory.forEach(p => { originHits += (cleanText.match(p) || []).length; });
  if (originHits >= 3) {
    score += 20;
    socialEngineeringDetected = true;
    reasons.push(`Humanized Phishing: Email narrates its own origin story (${originHits} origin phrases) — legitimate emails are transactional, not self-referential`);
  }

  // N10. Multi-Character Coordination Narrative — Multiple named people
  //      coordinating to reach the recipient constructs a false provenance
  //      chain. Real invitations don't explain their selection process.
  const coordinationVerbs = cleanText.match(/\b[A-Z][a-z]+ (said|told|asked|showed|handed|pulled|reminded|mentioned|wanted|organized|booked|finalized|pushed|reorganized|moved|confirmed)\b/g) || [];
  const uniqueNames = [...new Set(coordinationVerbs.map(m => m.split(/\s+/)[0]))];
  if (uniqueNames.length >= 3 && originHits >= 2) {
    score += 15;
    socialEngineeringDetected = true;
    reasons.push(`Humanized Phishing: ${uniqueNames.length}-person coordination narrative (${uniqueNames.join(', ')}) — false provenance chain`);
  }

  // Capitalization & Grammar Checks (Human Indicators)
  let humanScoreReduction = 0;
  
  // A. Check if sentences start with a lowercase letter
  const sentences = cleanText.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0);
  let lowerCaseStarts = 0;
  sentences.forEach(s => {
    const firstCharMatch = s.match(/[a-zA-Z]/);
    if (firstCharMatch) {
      const firstChar = firstCharMatch[0];
      if (firstChar === firstChar.toLowerCase()) {
        lowerCaseStarts++;
      }
    }
  });
  if (lowerCaseStarts > 0) {
    humanScoreReduction += 25 * Math.min(lowerCaseStarts, 2);
    reasons.push(`Human indicator: Sentences starting with lowercase letter (x${lowerCaseStarts})`);
  }

  // B. Check for lowercase 'i' pronouns (i, i'm, i'd, i've, i'll)
  const lowercaseIPattern = /\b(i|i'm|i'd|i've|i'll)\b/g;
  const lowercaseIMatches = cleanText.match(lowercaseIPattern);
  if (lowercaseIMatches) {
    humanScoreReduction += 15 * Math.min(lowercaseIMatches.length, 2);
    reasons.push(`Human indicator: Lowercase 'i' pronoun usage (x${lowercaseIMatches.length})`);
  }

  // C. Check for missing terminal punctuation
  const hasTerminalPunctuation = /[.!?]$/.test(cleanText);
  if (cleanText.length > 20 && !hasTerminalPunctuation) {
    humanScoreReduction += 15;
    reasons.push("Human indicator: Casual punctuation (missing terminal period/question/exclamation)");
  }

  if (humanScoreReduction > 0) {
    // When social engineering patterns are detected, the 'human indicators'
    //  (lowercase sentences, casual 'i', missing punctuation) are likely
    //  deliberate humanization tactics — reduce their penalty significantly.
    if (socialEngineeringDetected) {
      score = Math.max(1, score - Math.floor(humanScoreReduction * 0.15));
      reasons.push("Note: 'Human indicators' (casual tone, lowercase) suppressed — likely deliberate humanization to bypass detection");
    } else {
      score = Math.max(1, score - humanScoreReduction);
    }
  }

  // Cap score at 99
  const finalScore = Math.min(score, 99);

  // Sensitivity-driven flag threshold: higher sensitivity flags more aggressively
  const flagThreshold = Math.max(5, Math.min(30, 32 - scanSensitivity * 0.25));
  if (finalScore >= flagThreshold) {
    return {
      score: finalScore,
      reasons: reasons,
      text: cleanText.substring(0, 150) + (cleanText.length > 150 ? "..." : "")
    };
  }

  return null;
};

// Scan an image against the backend. ALL image analysis runs server-side —
// this function never scores an image locally. When the backend is not
// reachable the promise resolves with a connected:false result carrying the
// "not connected" explanation instead of a fabricated score.
const inspectImageMetadata = async (imgUrl) => {
  if (!imgUrl) return null;

  // Resolve relative URLs to absolute. The backend only accepts http(s) URLs;
  // relative paths like '/images/photo.jpg' cause a 400 rejection.
  let absoluteUrl = imgUrl;
  if (!imgUrl.startsWith("http://") && !imgUrl.startsWith("https://") && !imgUrl.startsWith("data:")) {
    try {
      absoluteUrl = new URL(imgUrl, window.location.href).href;
    } catch (e) {
      return null;
    }
  }

  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage({ action: "fetchImageMetadata", url: absoluteUrl }, (response) => {
        if (chrome.runtime.lastError) {
          resolve({
            score: null,
            unscanned: true,
            reasons: ["Not connected to the internet — the detection backend could not be reached."],
            url: imgUrl
          });
          return;
        }
        if (response && response.status === "backend_offline") {
          resolve({
            score: null,
            unscanned: true,
            connected: false,
            reasons: [response.error || "Not connected to the internet — the detection backend is unreachable."],
            url: imgUrl
          });
        } else if (response && response.status === "error") {
          resolve({
            score: null,
            unscanned: true,
            reasons: [response.error || "The backend could not analyze this image."],
            url: imgUrl
          });
        } else if (response && response.status === "success" && response.found) {
          resolve({
            score: response.score,
            tier: response.tier,
            confidence: response.confidence,
            reasons: response.reasons,
            url: imgUrl
          });
        } else {
          resolve(null);
        }
      });
    } catch (err) {
      resolve({
        score: null,
        unscanned: true,
        reasons: ["Not connected to the internet — the detection backend could not be reached."],
        url: imgUrl
      });
    }
  });
};

// DOM-context signals ONLY (alt text / captions / URL markers visible on the
// page). This performs no image analysis: it never inspects pixels, metadata
// or headers — every actual image scan happens on the backend via
// inspectImageMetadata. These are page-declared labels, not forensic results.
const inspectImageDOMContext = (img) => {
  if (!img) return null;
  
  const reasons = [];
  let score = 0;

  const alt = (img.alt || '').trim();
  const title = (img.title || '').trim();
  const src = img.src || '';

  // Expanded keyword regex to cover more systems
  const aiKeywordRegex = /(\bai[- ]generated\b|generative|midjourney|dall-e|dalle|stable[- ]diffusion|flux[-.]1|adobe[- ]firefly|deepai|leonardo[- ]ai|civitai|flux[- ]ai|created (with|by) ai|made (with|by) ai)/i;

  // AI attribution declared by the page itself (alt text, title attribute).
  // The backend never sees these page-local labels, so they are surfaced here
  // as context — they are the page's own claims, not a scan result.
  if (alt && aiKeywordRegex.test(alt)) {
    score = Math.max(score, 98);
    reasons.push(`AI attribution in alt text (page-declared, not a scan): "${alt}"`);
  }
  if (title && aiKeywordRegex.test(title)) {
    score = Math.max(score, 98);
    reasons.push(`AI attribution in title attribute (page-declared, not a scan): "${title}"`);
  }

  const figure = img.closest('figure');
  if (figure) {
    const figcaption = figure.querySelector('figcaption');
    if (figcaption) {
      const capText = (figcaption.innerText || figcaption.textContent || '').trim();
      if (aiKeywordRegex.test(capText)) {
        score = Math.max(score, 95);
        reasons.push(`AI attribution in image caption: "${capText}"`);
      }
    }
  }
  
  let sibling = img.nextElementSibling;
  while (sibling && (sibling.tagName === 'SPAN' || sibling.tagName === 'P' || sibling.tagName === 'DIV' || sibling.tagName === 'SMALL')) {
    const text = (sibling.innerText || sibling.textContent || '').trim();
    if (text.length < 150 && aiKeywordRegex.test(text)) {
      score = Math.max(score, 95);
      reasons.push(`AI attribution in neighboring text: "${text}"`);
      break;
    }
    sibling = sibling.nextElementSibling;
  }
  
  const classStr = (img.className && typeof img.className === 'string') ? img.className : '';
  const idStr = img.id || '';
  if (/(\bai[-_]image\b|generative|synth[-_]image)/i.test(classStr)) {
    score = Math.max(score, 85);
    reasons.push(`Class styling signature indicates generative assets: '${classStr}'`);
  }
  if (/(\bai[-_]image\b|generative|synth[-_]image)/i.test(idStr)) {
    score = Math.max(score, 85);
    reasons.push(`Element identifier indicates generative assets: '${idStr}'`);
  }

  // Page-declared URL markers only. The backend already inspects the actual
  // image (metadata, pixels, forensics) — this is context about where the
  // asset is hosted, visible in the page source itself. Skipped for data:/
  // blob: sources, which are not URLs and were already sent to the backend.
  if (!src.startsWith("data:") && !src.startsWith("blob:")) {
  const lowerSrc = src.toLowerCase();

  // Social media post context checker (e.g. Twitter/X articles, Reddit posts, LinkedIn updates)
  const postContainer = img.closest('article, [class*="post"], [class*="tweet"], [id*="post"], [id*="tweet"], [data-testid="post-container"], [class*="feed-shared-update"], [data-view-name*="feed-item"], [class*="update-v2"]');
  if (postContainer) {
    const postText = (postContainer.innerText || postContainer.textContent || '').toLowerCase();

    // Check for hashtags or explicit AI mentions in the post text
    const postKeywords = [
      "ai generated", "ai-generated", "midjourney", "dall-e", "dalle", 
      "stable diffusion", "stable-diffusion", "generative ai", "flux.1", 
      "flux 1", "flux ai", "made with ai", "created with ai", "generated by ai", 
      "ai art", "ai-art", "aiart", "#ai", "#midjourney", "#dalle", 
      "#stablediffusion", "#aiart", "generated using ai", "ai illustration",
      "synthetic media", "synthesized image", "deepseek", "gemini-generated",
      "artificial intelligence", "#generativeai", "#aiartcommunity", "created by ai"
    ];
    
    for (const kw of postKeywords) {
      if (postText.includes(kw)) {
        score = Math.max(score, 95);
        reasons.push(`AI keyword/hashtag in containing post: "${kw}"`);
        break;
      }
    }
  }

  // Expanded CDN & host domains
  const aiKeywords = [
    "midjourney", "stability", "dalle", "generated.photos", "firefly", "copilot", 
    "leonardo", "synth", "generative", "replicate.delivery", "civitai", "flux-ai", 
    "leonardo-cdn", "lexica.art", "playgroundai", "bing.com/images/create"
  ];
  for (const kw of aiKeywords) {
    if (lowerSrc.includes(kw)) {
      score = Math.max(score, 92);
      reasons.push(`External CDN Host contains AI generative directory keywords: '${kw}'`);
    }
  }

  // Midjourney and generic generator filename signature check
  const uuidRegex = /([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i;
  const isMidjourneyPattern = lowerSrc.includes("_grid_") || lowerSrc.includes("_v6_") || lowerSrc.includes("_v5_");
  if (uuidRegex.test(src) && (isMidjourneyPattern || lowerSrc.includes("discordapp") || lowerSrc.includes("prompt"))) {
    score = Math.max(score, 90);
    reasons.push("Image filename matches generative platform ID signature pattern (UUID + platform tag)");
  }
  }

  if (score > 0) {
    return {
      score: score,
      reasons: reasons
    };
  }
  return null;
};

// Trigger local scan on context menu or hotkey
const triggerLocalScan = async (element) => {
  if (!element) return;
  injectStyles();

  // Flash highlighting border
  element.classList.add("aegis-hover-focus");
  setTimeout(() => {
    element.classList.remove("aegis-hover-focus");
  }, 1000);

  // A. Check if current domain is an AI generative workbench (ChatGPT, Claude, Gemini, DeepSeek, etc.)
  if (isAIGenerativeUrl(window.location.href)) {
    showDiagnosticFloatingTooltip({
      score: 99,
      reasons: [
        `Active tab is running on a known AI generative workbench: '${window.location.hostname}'`,
        "Safety score set to 0% (100% AI generated / AI interface workspace)."
      ],
      title: "HOST INTEGRITY AUDIT",
      details: `Domain: ${window.location.hostname}`
    }, mouseX, mouseY);
    return;
  }

  // B. Check if element is a link or inside a link pointing to an AI generative portal
  const anchor = element.closest("a");
  if (anchor && anchor.href) {
    if (isAIGenerativeUrl(anchor.href)) {
      showDiagnosticFloatingTooltip({
        score: 99,
        reasons: [
          `Destination hyperlink points to an AI generative engine/portal: '${anchor.href}'`,
          "Safety score forced to 0% (100% AI-related destination)."
        ],
        title: "HYPERLINK INTEGRITY AUDIT",
        details: `Href: ${anchor.href.substring(0, 35)}...`
      }, mouseX, mouseY);
      return;
    }
  }

  // 1. Image checks — all actual analysis happens on the backend. DOM-context
  // labels (page-declared AI attributions) may supplement the server verdict,
  // but never replace it. Offline images are reported as "not connected".
  if (element.tagName === "IMG") {
    showFloatingScannerTooltip("Analyzing image via backend...", mouseX, mouseY);
    let imgResult = await inspectImageMetadata(element.src);
    if (imgResult && imgResult.score === null) {
      // Backend unreachable or request failed — say so, no fabricated score.
      showDiagnosticFloatingTooltip({
        score: 0,
        reasons: imgResult.reasons,
        title: "IMAGE VERIFICATION — OFFLINE",
        details: "Detection backend not connected. No local scan is performed."
      }, mouseX, mouseY);
      return;
    }
    if (!imgResult) {
      imgResult = inspectImageDOMContext(element);
    } else {
      const domResult = inspectImageDOMContext(element);
      if (domResult) {
        imgResult.score = Math.max(imgResult.score, domResult.score);
        imgResult.reasons = [...new Set([...imgResult.reasons, ...domResult.reasons])];
      }
    }
    
    if (imgResult) {
      showDiagnosticFloatingTooltip({
        score: imgResult.score,
        reasons: imgResult.reasons,
        title: "IMAGE VERIFICATION",
        details: `Dimensions: ${element.naturalWidth || element.width}x${element.naturalHeight || element.height}px`
      }, mouseX, mouseY);
    } else {
      showDiagnosticFloatingTooltip({
        score: 8,
        reasons: ["Backend scan complete: no AI forensics flagged by the server, and no page-declared AI labels found."],
        title: "IMAGE VERIFICATION",
        details: "Cloud forensic ensemble: clean."
      }, mouseX, mouseY);
    }
    return;
  }

  // 2. Text checks
  const text = element.innerText || element.textContent || "";
  if (text.trim().length > 10) {
    showFloatingScannerTooltip("Evaluating syntactic distribution...", mouseX, mouseY);

    setTimeout(() => {
      const results = analyzeTextHeuristics(text);
      if (results) {
        showDiagnosticFloatingTooltip({
          score: results.score,
          reasons: results.reasons,
          title: "TEXT INTEGRITY SCAN",
          details: `Length: ${text.trim().length} chars | Paragraph Node`
        }, mouseX, mouseY);
      } else {
        showDiagnosticFloatingTooltip({
          score: 8,
          reasons: ["Syntax distributions, corporate emoji metrics, and formatting arrays look authentic (natural human authorship)."],
          title: "TEXT INTEGRITY SCAN",
          details: `Cadence variance looks high. Safe.`
        }, mouseX, mouseY);
      }
    }, 400);
  } else {
    showFloatingScannerTooltip("Content too short to audit.", mouseX, mouseY);
    setTimeout(() => removeFloatingTooltip(), 1500);
  }
};

const detectPurpleGradient = () => {
  const candidates = document.querySelectorAll('body, header, section, [class*="hero"], [class*="header"], [class*="banner"], h1, h2, [id*="hero"], [id*="header"]');
  const topDivs = Array.from(document.querySelectorAll('div')).slice(0, 50);
  const elementsToCheck = new Set([...candidates, ...topDivs]);

  const isPurpleRGB = (r, g, b) => {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    let h = 0, s = 0, l = (max + min) / 2;
    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) {
        h = (g - b) / d + (g < b ? 6 : 0);
      } else if (max === g) {
        h = (b - r) / d + 2;
      } else if (max === b) {
        h = (r - g) / d + 4;
      }
      h /= 6;
    }
    const hDeg = h * 360;
    // Expanded range to cover blue, indigo, purple, violet, magenta, pink (200 - 345)
    return hDeg >= 200 && hDeg <= 345 && s >= 0.25 && l >= 0.15 && l <= 0.85;
  };

  const parseGradients = (styleStr) => {
    if (!styleStr || !styleStr.includes('gradient')) return false;
    const rgbRegex = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/g;
    let match;
    let purpleCount = 0;
    while ((match = rgbRegex.exec(styleStr)) !== null) {
      const r = parseInt(match[1], 10);
      const g = parseInt(match[2], 10);
      const b = parseInt(match[3], 10);
      if (isPurpleRGB(r, g, b)) {
        purpleCount++;
      }
    }
    if (purpleCount > 0) return true;

    const lowerStyle = styleStr.toLowerCase();
    const fallbackKeywords = ["purple", "violet", "indigo", "magenta", "fuchsia", "deeppink", "blue", "cyan", "skyblue", "royalblue"];
    for (const kw of fallbackKeywords) {
      if (lowerStyle.includes(kw)) return true;
    }
    const hexRegex = /#([0-9a-f]{6})/g;
    let hexMatch;
    while ((hexMatch = hexRegex.exec(lowerStyle)) !== null) {
      const hex = hexMatch[1];
      const r = parseInt(hex.substring(0, 2), 16);
      const g = parseInt(hex.substring(2, 4), 16);
      const b = parseInt(hex.substring(4, 6), 16);
      if (isPurpleRGB(r, g, b)) {
        return true;
      }
    }
    return false;
  };

  for (const el of elementsToCheck) {
    if (!el) continue;
    try {
      const styles = window.getComputedStyle(el);
      const bgImg = styles.backgroundImage || '';
      const bg = styles.background || '';
      const classStr = (el.className && typeof el.className === 'string') ? '.' + el.className.trim().split(/\s+/).join('.') : '';

      if (parseGradients(bgImg) || parseGradients(bg)) {
        return {
          detected: true,
          element: el.tagName.toLowerCase() + classStr,
          style: bgImg || bg
        };
      }

      const textFill = styles.webkitTextFillColor || styles.textFillColor || '';
      if ((textFill === 'transparent' || styles.color === 'transparent') && parseGradients(bgImg)) {
        return {
          detected: true,
          element: el.tagName.toLowerCase() + classStr + ' (Text Gradient)',
          style: bgImg
        };
      }
    } catch (e) {
      // Ignore
    }
  }
  return { detected: false };
};

const detectBubbleHeader = () => {
  // Bound the DOM walk: pages with thousands of nodes shouldn't thrash layout.
  const elements = Array.from(document.querySelectorAll('a, span, div, p')).slice(0, 800);
  const h1El = document.querySelector('h1');
  const h1Top = h1El ? h1El.getBoundingClientRect().top + window.scrollY : 99999;

  for (const el of elements) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;

    const top = rect.top + window.scrollY;
    if (top > 450) continue;

    try {
      const style = window.getComputedStyle(el);
      const borderRadiusStr = style.borderRadius || '';

      let hasPillBorderRadius = false;
      if (borderRadiusStr.includes('9999') || borderRadiusStr.includes('50%')) {
        hasPillBorderRadius = true;
      } else {
        const numbers = borderRadiusStr.match(/\d+/g);
        if (numbers) {
          hasPillBorderRadius = numbers.some(n => parseInt(n, 10) >= 12);
        }
      }

      if (!hasPillBorderRadius) continue;

      const h = rect.height;
      const w = rect.width;
      if (h < 18 || h > 55 || w < 70 || w > 550) continue;

      const text = (el.innerText || el.textContent || '').trim();
      if (text.length === 0 || text.length > 100) continue;

      const hasDotChar = /[●•🟢🔴🟡🔵⚫⚪🟣·]/.test(text) || text.includes('·');

      let hasDotChild = false;
      const children = el.querySelectorAll('*');
      for (const child of children) {
        const childRect = child.getBoundingClientRect();
        if (childRect.width > 0 && childRect.width <= 16 && Math.abs(childRect.width - childRect.height) < 4) {
          const childStyle = window.getComputedStyle(child);
          const childRad = childStyle.borderRadius;
          if (childRad.includes('50%') || childRad.includes('9999') || parseInt(childRad) >= 4) {
            hasDotChild = true;
            break;
          }
        }
      }

      const isAnnouncementText =
        hasDotChar ||
        hasDotChild ||
        /^(new|introducing|announcing|launching|just released|read our|join|latest|v\d+|beta|check out|whats new|update|hid)/i.test(text) ||
        /introducing|announcing|whats new/i.test(text) ||
        /[\u{1F300}-\u{1F9FF}\u{2700}-\u{27BF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}]/u.test(text) ||
        text.includes('✨') || text.includes('🚀') || text.includes('🎉') || text.includes('📢') || text.includes('→') || text.includes('⚡') ||
        el.closest('[class*="hero"]') ||
        (top < h1Top);

      if (!isAnnouncementText) continue;

      const bg = style.backgroundColor;
      const border = style.borderWidth;
      const hasBg = bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)';
      const hasBorder = border && border !== '0px' && style.borderColor !== 'transparent';

      if (hasBg || hasBorder) {
        const classStr = (el.className && typeof el.className === 'string') ? '.' + el.className.trim().split(/\s+/).join('.') : '';
        return {
          detected: true,
          text: text,
          element: el.tagName.toLowerCase() + classStr
        };
      }
    } catch (e) {
      // Ignore
    }
  }
  return { detected: false };
};

const showVibecodedNotification = () => {
  const existing = document.getElementById("aegis-vibecoded-top-bar");
  if (existing) return;

  injectStyles();

  const topBar = document.createElement("div");
  topBar.id = "aegis-vibecoded-top-bar";
  topBar.className = "aegis-vibecoded-topbar";
  topBar.innerHTML = `
    <div style="display:flex; align-items:center; gap:8px;">
      <span style="font-size: 12px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid #7f1d1d; color: #7f1d1d; font-weight: 800; font-family: sans-serif; line-height: 1;">!</span>
      <span style="text-align: left; font-weight: 700;">This site may be VibeCoded. Proceed with caution.</span>
    </div>
    <button class="aegis-vibecoded-close" id="aegis-vibecoded-close-btn">Dismiss</button>
  `;

  document.body.appendChild(topBar);

  setTimeout(() => {
    topBar.classList.add("show");
    document.body.style.transition = "margin-top 0.4s cubic-bezier(0.16, 1, 0.3, 1)";
    document.body.style.marginTop = `${topBar.offsetHeight}px`;
  }, 100);

  document.getElementById("aegis-vibecoded-close-btn").addEventListener("click", () => {
    topBar.classList.remove("show");
    document.body.style.marginTop = "0px";
    document.body.style.transition = "";
    setTimeout(() => topBar.remove(), 400);
  });
};

// Scan the whole DOM
// Capture a CONTIGUOUS run of frames from a <video> element for cloud video
// analysis. The backend's temporal forensics (PwTF-DVD, temporal coherence)
// require frames spaced at the video's native frame rate: uniformly-spaced
// seeks across a clip alias real motion into high temporal frequencies and
// span scene cuts, which fabricates exactly the artifacts the detector looks
// for. So we play the video (muted) and grab every presented frame via
// requestVideoFrameCallback, recording the real per-frame intervals.
//
// Returns { frames: [...dataURLs], meanIntervalSeconds, droppedIntervals } or
// null on CORS-taint (cross-origin media without CORS headers), decode errors,
// or when the video has too little playable content. Pauses/resumes playback
// and restores the original position/time so the scan doesn't disrupt the page.
async function extractVideoElementFrames(videoEl, maxFrames = 32) {
  if (!videoEl || videoEl.tagName !== "VIDEO" || !videoEl.currentSrc) return null;
  if (videoEl.readyState < 2 || videoEl.error) return null;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;

  const duration = isFinite(videoEl.duration) && videoEl.duration > 0 ? videoEl.duration : 0;
  if (duration && duration < 2.0) return null; // too short for a meaningful window

  const wasPlaying = !videoEl.paused && !videoEl.ended;
  const originalTime = videoEl.currentTime;
  const originalVolume = videoEl.volume;
  const originalMuted = videoEl.muted;
  const frames = [];
  const intervals = [];
  let lastCaptureTime = null;

  const supportsRVFC = typeof videoEl.requestVideoFrameCallback === "function";

  try {
    if (!duration) return null; // live/stream sources have no seekable window
    videoEl.muted = true;
    const scale = Math.min(1, 320 / Math.max(videoEl.videoWidth || 320, videoEl.videoHeight || 320));
    canvas.width = Math.max(2, Math.round((videoEl.videoWidth || 320) * scale));
    canvas.height = Math.max(2, Math.round((videoEl.videoHeight || 320) * scale));

    // Start inside the clip (skip common intros/fades), leave headroom at the end.
    const startTime = Math.min(duration * 0.2, Math.max(0, duration - (maxFrames / 24 + 0.5)));
    await new Promise((resolve) => {
      const done = () => {
        videoEl.removeEventListener("seeked", done);
        resolve();
      };
      videoEl.addEventListener("seeked", done);
      videoEl.currentTime = startTime;
      setTimeout(done, 2500); // seek timeout guard
    });

    const capture = () => {
      try {
        ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
        // Throws on a CORS-tainted canvas - caught below, returns null.
        frames.push(canvas.toDataURL("image/jpeg", 0.8));
        const now = videoEl.currentTime;
        if (lastCaptureTime !== null) intervals.push(now - lastCaptureTime);
        lastCaptureTime = now;
      } catch (e) {
        throw e;
      }
    };

    if (supportsRVFC) {
      // Native-rate capture: one frame per presented video frame.
      await new Promise((resolve) => {
        let done = false;
        const finish = () => {
          if (!done) { done = true; resolve(); }
        };
        const step = () => {
          if (done || frames.length >= maxFrames) return finish();
          capture();
          if (frames.length >= maxFrames) return finish();
          videoEl.requestVideoFrameCallback(step);
        };
        videoEl.requestVideoFrameCallback(step);
        videoEl.play().catch(finish);
        // Hard cap ~8s of wall time regardless of capture progress.
        setTimeout(finish, 8000);
      });
    } else {
      // Legacy fallback: play + timed grabs at ~30fps. Intervals are wall-clock
      // based and only meaningful when playback runs at 1x; still contiguous.
      await videoEl.play().catch(() => {});
      const grabInterval = setInterval(capture, 33);
      const started = Date.now();
      while (frames.length < maxFrames && !videoEl.ended && Date.now() - started < 8000) {
        await new Promise((r) => setTimeout(r, 30));
      }
      clearInterval(grabInterval);
    }
  } catch (e) {
    return null;
  } finally {
    try { videoEl.pause(); } catch { /* ignore */ }
    videoEl.muted = originalMuted;
    videoEl.volume = originalVolume;
    try { videoEl.currentTime = originalTime; } catch { /* ignore */ }
    if (wasPlaying) {
      try { videoEl.play(); } catch { /* ignore */ }
    }
  }

  if (frames.length < 12) return null; // too few frames for the temporal FFT
  const meanInterval = intervals.length
    ? intervals.reduce((a, b) => a + b, 0) / intervals.length
    : null;
  const droppedIntervals = intervals.filter((dt) => dt > (meanInterval || 0.05) * 2.5).length;
  return {
    frames,
    meanIntervalSeconds: meanInterval,
    droppedIntervals
  };
}

const performPageScan = async (options = { text: true, images: true, videos: true }) => {
  injectStyles();
  const purpleGradientResult = detectPurpleGradient();
  const bubbleHeaderResult = detectBubbleHeader();
  const isVibecoded = purpleGradientResult.detected || bubbleHeaderResult.detected;

  const vibecodedData = {
    isVibecoded: isVibecoded,
    reasons: [],
    hasPurpleGradient: purpleGradientResult.detected,
    hasBubbleHeader: bubbleHeaderResult.detected
  };

  if (purpleGradientResult.detected) {
    vibecodedData.reasons.push(`Purple/violet CSS gradient styling on '${purpleGradientResult.element}'`);
  }
  if (bubbleHeaderResult.detected) {
    vibecodedData.reasons.push(`Rounded pill/bubble announcement header in hero: "${bubbleHeaderResult.text}"`);
  }

  const settingsResult = await new Promise((resolve) => {
    try {
      chrome.storage.local.get(["settings"], (res) => resolve(res ? res.settings : null));
    } catch (e) {
      resolve(null);
    }
  });
  if (settingsResult && typeof settingsResult.sensitivity === "number") {
    scanSensitivity = settingsResult.sensitivity;
  }
  const showVibe = (settingsResult && settingsResult.showVibecodedAlert !== undefined) ? settingsResult.showVibecodedAlert : false;
  const showBadges = (settingsResult && settingsResult.showInlineBadges !== undefined) ? settingsResult.showInlineBadges : true;

  const existingVibeBar = document.getElementById("aegis-vibecoded-top-bar");
  if (existingVibeBar && (!isVibecoded || !showVibe)) {
    existingVibeBar.remove();
    document.body.style.marginTop = "0px";
    document.body.style.transition = "";
  }

  if (isVibecoded && showVibe) {
    showVibecodedNotification();
  }

  scanResults = {
    text: [],
    images: [],
    videos: [],
    score: 100,
    scannedAt: Date.now(),
    vibecoded: vibecodedData
  };

  document.querySelectorAll(".aegis-badge, .aegis-image-overlay-text").forEach(e => e.remove());
  document.querySelectorAll(".aegis-highlight-ai, .aegis-highlight-suspected, .aegis-image-highlight-ai, .aegis-image-highlight-suspected").forEach(e => {
    e.classList.remove("aegis-highlight-ai", "aegis-highlight-suspected", "aegis-image-highlight-ai", "aegis-image-highlight-suspected");
  });

  let scannedCount = 0;
  let flaggedCount = 0;

  // A. Check if current domain is an AI generative workbench (ChatGPT, Claude, Gemini, DeepSeek, etc.)
  const isAiWorkbench = isAIGenerativeUrl(window.location.href);
  if (isAiWorkbench) {
    flaggedCount++;
    scanResults.text.push({
      id: "ai-workbench-flag",
      score: 100,
      reasons: [
        `Active browser domain matches known AI generative system: '${window.location.hostname}'`,
        "This portal is primarily used to converse with generative AI models or host AI-synthesized assets.",
        "Integrity score set to 0% (100% AI generated / AI interface workspace)."
      ],
      snippet: `Page loaded from ${window.location.hostname} (AI generative system).`,
      tagName: "body"
    });
  }

  // Text Scanner
  if (options.text) {
    const textNodes = [];
    const elements = document.querySelectorAll("p, blockquote, article, li, span, h1, h2, h3");

    elements.forEach(el => {
      if (el.closest("header") || el.closest("footer") || el.closest("nav") || el.closest(".aegis-drawer") || el.classList.contains("aegis-badge") || el.closest(".aegis-floating-tooltip")) {
        return;
      }

      const text = el.innerText || el.textContent;
      if (text && text.trim().length > 60) {
        textNodes.push({ element: el, text: text });
      }
    });

    for (const node of textNodes) {
      scannedCount++;
      const result = analyzeTextHeuristics(node.text);
      if (result) {
        flaggedCount++;
        const id = "text-" + Math.random().toString(36).substr(2, 9);
        const item = {
          id: id,
          score: result.score,
          reasons: result.reasons,
          snippet: result.text,
          tagName: node.element.tagName.toLowerCase()
        };

        scanResults.text.push(item);

        node.element.classList.add(result.score >= 60 ? "aegis-highlight-ai" : "aegis-highlight-suspected");

        if (showBadges) {
          const badge = document.createElement("span");
          badge.className = `aegis-badge ${result.score >= 60 ? "aegis-badge-ai" : "aegis-badge-suspected"}`;
          badge.textContent = `AI ${result.score}%`;
          badge.addEventListener("click", (e) => {
            e.stopPropagation();
            openDiagnosticDrawer(item, "text");
          });
          node.element.prepend(badge);
        }
      }
    }
  }

  // Image Scanner
  if (options.images) {
    const images = Array.from(document.querySelectorAll("img"));

    for (const img of images) {
      if (img.width < 50 || img.height < 50) continue;
      scannedCount++;

      // Backend verdict first. DOM-context signals (page-declared AI labels
      // in alt text / captions / URLs) are layered on top of the server score
      // — they never replace a scan. A result with score: null means the
      // backend was unreachable or the image unscannable: recorded honestly,
      // no badge, no fabricated score.
      let imgResult = await inspectImageMetadata(img.src);
      if (imgResult && imgResult.score === null) {
        // Backend offline or request failed — record as unscanned.
        scanResults.images.push({
          id: "img-" + Math.random().toString(36).substr(2, 9),
          score: null,
          unscanned: true,
          reasons: imgResult.reasons,
          src: img.src,
          width: img.naturalWidth || img.width,
          height: img.naturalHeight || img.height
        });
        continue;
      }
      if (!imgResult) {
        // Backend reachable and answered, image judged clean by the server.
        imgResult = inspectImageDOMContext(img);
      } else {
        const domResult = inspectImageDOMContext(img);
        if (domResult) {
          imgResult.score = Math.max(imgResult.score, domResult.score);
          imgResult.reasons = [...new Set([...imgResult.reasons, ...domResult.reasons])];
        }
      }

      if (imgResult) {
        flaggedCount++;
        const id = "img-" + Math.random().toString(36).substr(2, 9);
        const item = {
          id: id,
          score: imgResult.score,
          reasons: imgResult.reasons,
          src: img.src,
          width: img.naturalWidth || img.width,
          height: img.naturalHeight || img.height
        };

        scanResults.images.push(item);

        img.classList.add(imgResult.score >= 60 ? "aegis-image-highlight-ai" : "aegis-image-highlight-suspected");

        if (showBadges) {
          const parent = img.parentElement;
          if (parent && !parent.classList.contains("aegis-media-container")) {
            const badge = document.createElement("span");
            badge.className = `aegis-badge ${imgResult.score >= 60 ? "aegis-badge-ai" : "aegis-badge-suspected"} aegis-media-overlay-badge`;
            badge.textContent = `AI IMAGE ${imgResult.score}%`;
            badge.addEventListener("click", (e) => {
              e.preventDefault();
              e.stopPropagation();
              openDiagnosticDrawer(item, "image");
            });

            if (getComputedStyle(parent).position === "static") {
              parent.style.position = "relative";
            }
            parent.appendChild(badge);

          const overlayText = document.createElement("div");
          overlayText.className = "aegis-image-overlay-text";
          overlayText.style.cssText = `
            position: absolute !important;
            bottom: 0 !important;
            left: 0 !important;
            width: 100% !important;
            background: ${imgResult.score >= 60 ? 'rgba(220, 38, 38, 0.85)' : 'rgba(245, 158, 11, 0.85)'} !important;
            color: white !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            font-size: 11px !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
            padding: 6px 10px !important;
            box-sizing: border-box !important;
            text-align: center !important;
            pointer-events: none !important;
            z-index: 9999 !important;
            border-bottom-left-radius: inherit !important;
            border-bottom-right-radius: inherit !important;
          `;
          overlayText.innerText = imgResult.score >= 60 ? "AI Generated Image" : "Suspected AI Image";
          parent.appendChild(overlayText);
          }
        }
      }
    }
  }

  // Video Scanner
  if (options.videos) {
    const videos = Array.from(document.querySelectorAll("video, iframe"));

    // Cloud mode: the backend runs the full spatio-temporal ensemble on frames
    // extracted from real <video> elements. Local mode keeps the URL-substring
    // check below (the only offline signal available without a frame decoder).
    let cloudMode = false;
    try {
      const vSettings = await new Promise((resolve) => {
        chrome.storage.local.get(["settings"], (res) => resolve(res ? res.settings : null));
      });
      cloudMode = Boolean(vSettings && vSettings.apiMode === "cloud");
    } catch { cloudMode = false; }

    for (const vid of videos) {
      const src = vid.src || (vid.querySelector("source") ? vid.querySelector("source").src : "");
      if (!src) continue;

      scannedCount++;

      // First check for known AI video platforms (URL-based detection)
      const urlDetection = detectAIVideo(src);
      const isSuspectVideo = urlDetection.score >= 55 || src.includes("synthesia") || src.includes("heygen");

      if (isSuspectVideo) {
        flaggedCount++;
        const id = "vid-" + Math.random().toString(36).substr(2, 9);
        const reasons = urlDetection.flags.length > 0
          ? urlDetection.flags
          : ["Injected synthesia/heygen frame container structures."];
        const item = {
          id: id,
          score: urlDetection.score,
          reasons: reasons,
          src: src,
          width: vid.width || 640,
          height: vid.height || 360
        };

        scanResults.videos.push(item);

        const parent = vid.parentElement;
        if (parent) {
          const badge = document.createElement("span");
          badge.className = `aegis-badge ${urlDetection.score >= 60 ? "aegis-badge-ai" : "aegis-badge-suspected"} aegis-media-overlay-badge`;
          badge.textContent = `AI VIDEO ${urlDetection.score}%`;
          badge.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            openDiagnosticDrawer(item, "video");
          });

          if (getComputedStyle(parent).position === "static") {
            parent.style.position = "relative";
          }
          parent.appendChild(badge);
        }
        continue;
      }

      // Cloud mode: extract frames from a real <video> element and run the
      // backend's temporal ensemble. Every video that gets a real verdict is
      // recorded; flagging/badging only happens at >= 55. Extraction failures
      // (CORS-tainted cross-origin players, un-decoded videos) are recorded
      // honestly as skipped with a reason instead of vanishing silently.
      if (cloudMode && vid.tagName === "VIDEO" && !vid.dataset.rinseVideoChecked) {
        vid.dataset.rinseVideoChecked = "1";
        const capture = await extractVideoElementFrames(vid).catch(() => null);
        const frames = capture ? capture.frames : [];
        if (frames.length >= 12) {
          const res = await new Promise((resolve) => {
            try {
              chrome.runtime.sendMessage({
                action: "analyzeVideoFrames",
                frames,
                url: src,
                frameIntervalSeconds: capture.meanIntervalSeconds
              }, (r) => resolve(r || null));
            } catch { resolve(null); }
          });
          const id = "vid-" + Math.random().toString(36).substr(2, 9);
          const baseItem = {
            id: id,
            score: null,
            reasons: [],
            src: src,
            width: vid.videoWidth || vid.width || 640,
            height: vid.videoHeight || vid.height || 360
          };
          if (res && res.found && typeof res.score === "number") {
            // Only trust the score if we have valid temporal coherence data
            // (pwtf_metrics with coherence_p05). Without this, a high score
            // may be a false positive from compression/motion artifacts.
            const hasValidTemporalData =
              res.pwtf_metrics &&
              res.pwtf_metrics.coherence_p05 !== undefined &&
              res.pwtf_metrics.coherence_p05 !== null;
            
            // If score is in suspicious range (55-65) without valid temporal
            // data, don't flag it - it's likely a false positive.
            const trustScore = (
              res.score < 55 ||
              res.score > 65 ||
              hasValidTemporalData
            );
            
            // If score is suspicious but coherence floor didn't collapse
            // (p05 >= 0.25), don't flag as AI - real footage can trigger this.
            const coherenceCollapsed =
              hasValidTemporalData &&
              res.pwtf_metrics.coherence_p05 < 0.25;
            
            // The backend's tier is the source of truth (SYNTHETIC_AI /
            // SUSPICIOUS / UNCERTAIN / INCONCLUSIVE / AUTHENTIC_HUMAN). It
            // already enforces the false-positive guards before assigning a
            // decisive tier (the coherence floor must actually collapse,
            // corroboration requirements, temporal-evidence requirement for
            // 'authentic'), so flagging is tier-driven here - no duplicated
            // client-side gating that can disagree with the server.
            // The fallback tier computation only serves OLD backends that
            // don't send a tier yet.
            const tier = res.tier || (res.score >= 80 ? "SYNTHETIC_AI"
                          : res.score >= 69 ? "SUSPICIOUS"
                          : res.score >= 55 ? (coherenceCollapsed ? "SUSPICIOUS" : "UNCERTAIN")
                          : res.score >= 35 ? "INCONCLUSIVE"
                          : "AUTHENTIC_HUMAN");
            const shouldFlag = tier === "SYNTHETIC_AI" || tier === "SUSPICIOUS";

            const item = { ...baseItem, score: res.score, tier, confidence: res.confidence, reasons: res.reasons || [] };
            scanResults.videos.push(item);
            
            if (shouldFlag) {
              flaggedCount++;
              const parent = vid.parentElement;
              if (parent) {
                const badge = document.createElement("span");
                badge.className = `aegis-badge ${tier === "SYNTHETIC_AI" || res.score >= 70 ? "aegis-badge-ai" : "aegis-badge-suspected"} aegis-media-overlay-badge`;
                badge.textContent = `AI VIDEO ${res.score}%`;
                badge.addEventListener("click", (e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  openDiagnosticDrawer(item, "video");
                });
                if (getComputedStyle(parent).position === "static") {
                  parent.style.position = "relative";
                }
                parent.appendChild(badge);
              }
            }
          } else {
            // Backend reachable but analysis failed (undecodable stream,
            // server-side decoder missing, etc.) - show the real error.
            const errMsg = (res && res.error) || "Video analysis failed on the backend.";
            scanResults.videos.push({ ...baseItem, score: 0, reasons: [errMsg] });
            console.warn("RINSE video analysis error:", errMsg);
          }
        } else if (src && !src.startsWith("blob:") && !src.startsWith("data:")) {
          // Browser-side extraction failed (CORS-tainted cross-origin player
          // or an un-decoded <video>). Do not stay silent: send the direct
          // source URL to the backend - yt-dlp resolves platform links and
          // direct file URLs are downloaded and decoded server-side.
          const res = await new Promise((resolve) => {
            try {
              chrome.runtime.sendMessage({ action: "analyzeVideoUrl", url: src }, (r) => resolve(r || null));
            } catch { resolve(null); }
          });
          if (res && res.found && typeof res.score === "number") {
            const id = "vid-" + Math.random().toString(36).substr(2, 9);
            const tier = res.tier || (res.score >= 80 ? "SYNTHETIC_AI"
                          : res.score >= 69 ? "SUSPICIOUS"
                          : res.score >= 55 ? "UNCERTAIN"
                          : res.score >= 35 ? "INCONCLUSIVE"
                          : "AUTHENTIC_HUMAN");
            const item = {
              id: id,
              score: res.score,
              tier,
              confidence: res.confidence,
              reasons: res.reasons || [],
              src: src,
              width: vid.videoWidth || vid.width || 640,
              height: vid.videoHeight || vid.height || 360
            };
            scanResults.videos.push(item);
            if (res.score >= 55 && tier !== "INCONCLUSIVE") {
              flaggedCount++;
              const parent = vid.parentElement;
              if (parent) {
                const badge = document.createElement("span");
                badge.className = `aegis-badge ${tier === "SYNTHETIC_AI" || res.score >= 70 ? "aegis-badge-ai" : "aegis-badge-suspected"} aegis-media-overlay-badge`;
                badge.textContent = `AI VIDEO ${res.score}%`;
                badge.addEventListener("click", (e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  openDiagnosticDrawer(item, "video");
                });
                if (getComputedStyle(parent).position === "static") {
                  parent.style.position = "relative";
                }
                parent.appendChild(badge);
              }
            }
          } else {
            const errMsg = (res && res.error) || "Could not decode this video in the browser (cross-origin frame access is blocked), and server-side fetch failed. Download the clip and use the Playground upload instead.";
            scanResults.videos.push({
              id: "vid-" + Math.random().toString(36).substr(2, 9),
              score: 0,
              reasons: [errMsg],
              src: src,
              width: vid.videoWidth || vid.width || 640,
              height: vid.videoHeight || vid.height || 360
            });
          }
        }
      }
    }
  }

  // Integrity Score Calculation
  if (isAiWorkbench) {
    scanResults.score = 0;
  } else {
    // Calculate score based on the WORST detection, not average
    // This prevents dilution from non-suspicious items
    let maxAiScore = 0;
    let totalScanned = 0;
    let totalFlagged = 0;

    const allItems = [...scanResults.text, ...scanResults.images, ...scanResults.videos];
    for (const item of allItems) {
      totalScanned++;
      // INCONCLUSIVE verdicts (backend could not complete a full analysis -
      // e.g. a spatial-only video scan with no temporal evidence) carry a
      // score but must not push the page score toward either extreme: they
      // count as scanned-but-unresolved, not as evidence of authenticity.
      // Unscanned items (score: null — backend offline / request failed) are
      // scan failures, not evidence of authenticity either.
      const itemInconclusive = item.tier === "INCONCLUSIVE" || item.score === null;
      if (item.score > 0 && !itemInconclusive) {
        maxAiScore = Math.max(maxAiScore, item.score);
        if (item.score >= 55) {
          totalFlagged++;
        }
      }
    }

    // Score calculation: focus on the most suspicious content
    let finalScore = 100;

    if (totalScanned > 0) {
      if (totalFlagged > 0) {
        // If we found AI content, the score should reflect the highest AI confidence
        // but weighted by how much of the page is AI content
        const aiRatio = totalFlagged / totalScanned;
        finalScore = Math.round(100 - (maxAiScore * aiRatio * 1.2));

        // Ensure we don't go below 1 for highly AI pages
        if (maxAiScore >= 80 && aiRatio > 0.5) {
          finalScore = Math.min(finalScore, 30);
        }
      } else {
        // No flagged content - check if we scanned anything
        // If we scanned and found nothing suspicious, score stays high
        // But if we couldn't scan (backend offline, CORS issues), be
        // conservative: unscanned content is not evidence of authenticity.
        const hadScanningFailures = allItems.some(item =>
          (item.score === 0 && item.reasons && item.reasons.length > 0) ||
          (item.score === null && item.unscanned)
        );
        if (hadScanningFailures) {
          // We couldn't analyze some content - be slightly conservative
          finalScore = Math.max(70, finalScore - 10);
        }
      }
    }

    // Apply vibecoded penalties
    let vibecodedPenalty = 0;
    if (scanResults.vibecoded && scanResults.vibecoded.hasPurpleGradient) vibecodedPenalty += 15;
    if (scanResults.vibecoded && scanResults.vibecoded.hasBubbleHeader) vibecodedPenalty += 15;

    scanResults.score = Math.max(1, Math.min(100, finalScore - vibecodedPenalty));
  }

  try {
    chrome.runtime.sendMessage({ action: "updateBadge", count: flaggedCount });
    chrome.runtime.sendMessage({
      action: "saveScan",
      data: {
        url: window.location.href,
        title: document.title || window.location.hostname,
        score: scanResults.score,
        stats: {
          textCount: scanResults.text.length,
          imageCount: scanResults.images.length,
          videoCount: scanResults.videos.length
        },
        vibecoded: scanResults.vibecoded
      }
    });
  } catch (e) {
    // Catch extension disconnection exceptions
  }

  return scanResults;
};

// Open diagnostic drawer (builds DOM safely; page-derived strings are never parsed as HTML)
const openDiagnosticDrawer = (item, type) => {
  injectStyles();

  if (!sideDrawerElement) {
    sideDrawerElement = document.createElement("div");
    sideDrawerElement.className = "aegis-drawer";
    document.body.appendChild(sideDrawerElement);
  }

  const riskClass = item.score >= 60 ? "aegis-risk-red" : "aegis-risk-yellow";
  const label = type.toUpperCase() + " CONTENT DIAGNOSTICS";

  sideDrawerElement.textContent = "";

  // Header
  const header = document.createElement("div");
  header.className = "aegis-drawer-header";
  const title = document.createElement("div");
  title.className = "aegis-drawer-title";
  const shield = document.createElement("span");
  shield.style.color = item.score >= 60 ? "#EF4444" : "#F59E0B";
  shield.textContent = "🛡️";
  const titleText = document.createElement("span");
  titleText.textContent = "RINSE Inspector";
  title.appendChild(shield);
  title.appendChild(titleText);
  const closeBtn = document.createElement("button");
  closeBtn.className = "aegis-drawer-close";
  closeBtn.id = "aegis-drawer-close-btn";
  closeBtn.textContent = "×";
  closeBtn.setAttribute("aria-label", "Close inspector");
  header.appendChild(title);
  header.appendChild(closeBtn);

  const content = document.createElement("div");
  content.className = "aegis-drawer-content";

  const logTitle = document.createElement("div");
  logTitle.className = "aegis-log-title";
  logTitle.textContent = label;
  content.appendChild(logTitle);

  // Risk meter
  const riskCard = document.createElement("div");
  riskCard.className = "aegis-card aegis-risk-meter";
  const metricRow = document.createElement("div");
  metricRow.className = "aegis-metric-row";
  const metricLabel = document.createElement("span");
  metricLabel.className = "aegis-metric-label";
  metricLabel.textContent = "AI Generation Likelihood";
  const metricValue = document.createElement("span");
  metricValue.className = "aegis-metric-value";
  metricValue.style.color = item.score >= 60 ? "#F87171" : "#FBBF24";
  metricValue.textContent = `${item.score}%`;
  metricRow.appendChild(metricLabel);
  metricRow.appendChild(metricValue);
  const barContainer = document.createElement("div");
  barContainer.className = "aegis-risk-bar-container";
  const bar = document.createElement("div");
  bar.className = `aegis-risk-bar ${riskClass}`;
  bar.style.width = "0%";
  barContainer.appendChild(bar);
  riskCard.appendChild(metricRow);
  riskCard.appendChild(barContainer);
  content.appendChild(riskCard);

  // Diagnostics list
  const diagCard = document.createElement("div");
  diagCard.className = "aegis-card";
  const diagTitle = document.createElement("div");
  diagTitle.className = "aegis-log-title";
  diagTitle.textContent = "Detection Diagnostics";
  const ul = document.createElement("ul");
  ul.style.cssText = "padding-left: 20px; margin: 0; font-size: 13px; line-height: 1.6; color: #CBD5E1;";
  (item.reasons || []).forEach(r => {
    const li = document.createElement("li");
    li.textContent = r;
    ul.appendChild(li);
  });
  diagCard.appendChild(diagTitle);
  diagCard.appendChild(ul);
  content.appendChild(diagCard);

  if (type === "text") {
    const snippetCard = document.createElement("div");
    snippetCard.className = "aegis-card";
    const snippetTitle = document.createElement("div");
    snippetTitle.className = "aegis-log-title";
    snippetTitle.textContent = "Flagged Content Segment";
    const snippet = document.createElement("div");
    snippet.className = "aegis-snippet";
    snippet.textContent = `"${item.snippet || ""}"`;
    snippetCard.appendChild(snippetTitle);
    snippetCard.appendChild(snippet);
    content.appendChild(snippetCard);
  } else if (type === "image") {
    const previewWrap = document.createElement("div");
    previewWrap.style.cssText = "margin-top: 15px; border-radius: 8px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.3); display: flex; justify-content: center; align-items: center; max-height: 180px;";
    const img = document.createElement("img");
    img.src = item.src || "";
    img.alt = "Scanned image preview";
    img.style.cssText = "max-width: 100%; max-height: 180px; object-fit: contain;";
    previewWrap.appendChild(img);
    content.appendChild(previewWrap);
  }

  sideDrawerElement.appendChild(header);
  sideDrawerElement.appendChild(content);

  setTimeout(() => {
    sideDrawerElement.classList.add("open");
    const barEl = sideDrawerElement.querySelector(".aegis-risk-bar");
    if (barEl) barEl.style.width = `${item.score}%`;
  }, 50);

  closeBtn.addEventListener("click", () => {
    sideDrawerElement.classList.remove("open");
  });
};

// Create floating scanner tooltip (app-controlled text; built with DOM APIs for consistency)
const showFloatingScannerTooltip = (textStr, x, y) => {
  injectStyles();
  removeFloatingTooltip();

  floatingTooltipElement = document.createElement("div");
  floatingTooltipElement.className = "aegis-floating-tooltip";
  floatingTooltipElement.style.left = `${x + 10}px`;
  floatingTooltipElement.style.top = `${y + 10}px`;

  const inner = document.createElement("div");
  inner.style.cssText = "display:flex; align-items:center; gap:8px;";
  const dot = document.createElement("span");
  dot.style.cssText = "display:inline-block; width:8px; height:8px; border-radius:50%; background:#06b6d4; animation:pulse 1s infinite alternate;";
  const label = document.createElement("span");
  label.style.cssText = "font-size:11px; font-weight:700; color:#06b6d4; text-transform:uppercase;";
  label.textContent = textStr;
  inner.appendChild(dot);
  inner.appendChild(label);
  floatingTooltipElement.appendChild(inner);

  document.body.appendChild(floatingTooltipElement);
  setTimeout(() => floatingTooltipElement.classList.add("show"), 50);
};

// Create diagnostic floating tooltip (builds DOM safely; page-derived strings are never parsed as HTML)
const showDiagnosticFloatingTooltip = (data, x, y) => {
  injectStyles();
  removeFloatingTooltip();

  floatingTooltipElement = document.createElement("div");
  floatingTooltipElement.className = "aegis-floating-tooltip";
  floatingTooltipElement.style.left = `${x + 10}px`;
  floatingTooltipElement.style.top = `${y + 10}px`;

  const color = data.score >= 50 ? "#F87171" : "#34D399";

  // Header
  const header = document.createElement("div");
  header.className = "aegis-tooltip-header";
  const title = document.createElement("span");
  title.style.cssText = "font-size:10px; font-weight:800; color:#64748B;";
  title.textContent = data.title || "";
  const score = document.createElement("span");
  score.style.cssText = `font-size:12px; font-weight:800; color:${color};`;
  score.textContent = `AI: ${data.score}%`;
  header.appendChild(title);
  header.appendChild(score);

  const details = document.createElement("div");
  details.style.cssText = "font-size:9.5px; color:#94A3B8; margin-bottom:8px; font-style:italic;";
  details.textContent = data.details || "";

  const list = document.createElement("div");
  list.style.cssText = "max-height:100px; overflow-y:auto; padding-right:4px;";
  (data.reasons || []).forEach(r => {
    const row = document.createElement("div");
    row.style.cssText = "display:flex; align-items:flex-start; gap:4px; font-size:10px; line-height:1.3; color:#CBD5E1; margin-bottom:4px;";
    const dot = document.createElement("span");
    dot.style.color = color;
    dot.textContent = "•";
    const text = document.createElement("span");
    text.textContent = r;
    row.appendChild(dot);
    row.appendChild(text);
    list.appendChild(row);
  });

  const footer = document.createElement("div");
  footer.style.cssText = "display:flex; justify-content:space-between; align-items:center; margin-top:8px; border-top:1px solid rgba(255,255,255,0.05); padding-top:6px;";
  const brand = document.createElement("span");
  brand.style.cssText = "font-size:8px; color:#64748B;";
  brand.textContent = "RINSE ON-DEMAND";
  const closeBtn = document.createElement("button");
  closeBtn.id = "aegis-tooltip-close-btn";
  closeBtn.style.cssText = "background:none; border:none; color:#94A3B8; font-size:9px; cursor:pointer; font-weight:700;";
  closeBtn.textContent = "Close";
  footer.appendChild(brand);
  footer.appendChild(closeBtn);

  floatingTooltipElement.appendChild(header);
  floatingTooltipElement.appendChild(details);
  floatingTooltipElement.appendChild(list);
  floatingTooltipElement.appendChild(footer);

  document.body.appendChild(floatingTooltipElement);
  setTimeout(() => floatingTooltipElement.classList.add("show"), 50);

  closeBtn.addEventListener("click", removeFloatingTooltip);

  // Auto remove after 10 seconds
  const selfElement = floatingTooltipElement;
  setTimeout(() => {
    if (floatingTooltipElement === selfElement) {
      removeFloatingTooltip();
    }
  }, 10000);
};

// Remove tooltip helper
const removeFloatingTooltip = () => {
  const old = document.querySelector(".aegis-floating-tooltip");
  if (old) old.remove();
};

// Track mouse positioning
document.addEventListener("mousemove", (e) => {
  mouseX = e.pageX;
  mouseY = e.pageY;
});

document.addEventListener("mouseover", (e) => {
  // Track hovered element (prefer text containers or images)
  const el = e.target;
  if (el && (el.tagName === "P" || el.tagName === "LI" || el.tagName === "SPAN" || el.tagName === "IMG" || el.tagName === "H1" || el.tagName === "H2" || el.tagName === "H3" || el.tagName === "ARTICLE")) {
    hoveredElement = el;
  }
});

// Keypress listener for hotkey triggers (supports Option/Alt, Control, or custom shortcuts)
document.addEventListener("keydown", (e) => {
  // Ignore key repeats (holding Alt/Control used to fire repeated scans)
  if (e.repeat) return;
  // Don't hijack typing inside inputs/textareas/contenteditable
  const target = e.target;
  if (target && target.closest && target.closest("input, textarea, select, [contenteditable='true'], [contenteditable='']")) {
    return;
  }
  // Trigger on Alt (Option on Mac), Control, or Alt+A / Ctrl+A combos
  const isTriggerKey = e.key === "Alt" || e.key === "Control" || (e.altKey && e.key.toLowerCase() === "a") || (e.ctrlKey && e.key.toLowerCase() === "a");
  if (isTriggerKey && hoveredElement) {
    // Always check storage directly — the in-memory flag can be stale
    chrome.storage.local.get(["extensionEnabled"], (result) => {
      if (result.extensionEnabled === false) return;
      triggerLocalScan(hoveredElement);
    });
  }
});

// Removed unused HUD Controls

// Deep scan line animation sweep
const triggerDeepScanAnimation = (callback) => {
  injectStyles();

  if (!laserScannerElement) {
    laserScannerElement = document.createElement("div");
    laserScannerElement.className = "aegis-laser-scanner";
    document.body.appendChild(laserScannerElement);
  }

  laserScannerElement.style.display = "block";
  scanInProgress = true;

  setTimeout(async () => {
    const results = await performPageScan();
    laserScannerElement.style.display = "none";
    scanInProgress = false;
    if (callback) callback(results);
  }, 2500);
};

// Runtime messages from background context menus or popup dashboard
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getPageStatus") {
    if (scanResults.scannedAt) {
      sendResponse({ status: "success", data: scanResults });
    } else if (extensionEnabled) {
      performPageScan().then(results => {
        sendResponse({ status: "success", data: results });
      });
    } else {
      sendResponse({ status: "success", data: { text: [], images: [], videos: [], score: 100, scannedAt: null } });
    }
    return true;
  }

  else if (request.action === "runScan") {
    if (!extensionEnabled) {
      sendResponse({ status: "disabled" });
      return true;
    }
    performPageScan(request.options).then(results => {
      sendResponse({ status: "success", data: results });
    });
    return true;
  }

  else if (request.action === "runDeepScan") {
    if (!extensionEnabled) {
      sendResponse({ status: "disabled" });
      return true;
    }
    triggerDeepScanAnimation((results) => {
      sendResponse({ status: "success", data: results });
    });
    return true;
  }

  else if (request.action === "scanSelectedText") {
    if (!extensionEnabled) {
      sendResponse({ status: "disabled" });
      return true;
    }
    // Context Menu Trigger: analyze selected text segment
    const textSegment = request.text || "";
    if (textSegment.trim().length > 0) {
      injectStyles();
      const results = analyzeTextHeuristics(textSegment);
      showDiagnosticFloatingTooltip({
        score: results ? results.score : 10,
        reasons: results ? results.reasons : ["Selection analyzed clean of AI-generated keywords and cadences."],
        title: "SELECTED TEXT AUDIT",
        details: `Segment length: ${textSegment.length} characters`
      }, mouseX, mouseY);
    }
    sendResponse({ status: "success" });
  }

  else if (request.action === "scanSelectedImage") {
    if (!extensionEnabled) {
      sendResponse({ status: "disabled" });
      return true;
    }
    // Context Menu Trigger: analyze image source url (backend scan only)
    const imageUrl = request.url || "";
    if (imageUrl) {
      injectStyles();
      inspectImageMetadata(imageUrl).then(meta => {
        if (meta && meta.score === null) {
          showDiagnosticFloatingTooltip({
            score: 0,
            reasons: meta.reasons,
            title: "SELECTED IMAGE AUDIT — OFFLINE",
            details: "Detection backend not connected. No local scan is performed."
          }, mouseX, mouseY);
        } else {
          showDiagnosticFloatingTooltip({
            score: meta ? meta.score : 8,
            reasons: meta ? meta.reasons : ["Backend scan complete: no AI forensics flagged by the server."],
            title: "SELECTED IMAGE AUDIT",
            details: `Source: ${imageUrl.substring(0, 30)}...`
          }, mouseX, mouseY);
        }
      });
    }
    sendResponse({ status: "success" });
  }

  else if (request.action === "toggleHideAI") {
    const hide = request.hide;
    if (hide) {
      document.body.classList.add("aegis-hide-ai-active");
    } else {
      document.body.classList.remove("aegis-hide-ai-active");
    }
    sendResponse({ status: "success", isHidden: hide });
  }

  else if (request.action === "applyHideAI") {
    // Called from background.js context menu: apply or remove the hide state
    const hide = request.hide;
    if (hide) {
      document.body.classList.add("aegis-hide-ai-active");
    } else {
      document.body.classList.remove("aegis-hide-ai-active");
    }
    sendResponse({ status: "success", isHidden: hide });
  }

  else if (request.action === "getHideAIStatus") {
    const isHidden = document.body.classList.contains("aegis-hide-ai-active");
    sendResponse({ status: "success", isHidden: isHidden });
  }

  else if (request.action === "enableExtension") {
    extensionEnabled = true;
    sendResponse({ status: "success", enabled: true });
  }

  else if (request.action === "disableExtension") {
    extensionEnabled = false;
    // Remove all badges and highlights when disabling
    document.querySelectorAll(".aegis-badge, .aegis-image-overlay-text").forEach(e => e.remove());
    document.querySelectorAll(".aegis-highlight-ai, .aegis-highlight-suspected, .aegis-image-highlight-ai, .aegis-image-highlight-suspected").forEach(e => {
      e.classList.remove("aegis-highlight-ai", "aegis-highlight-suspected", "aegis-image-highlight-ai", "aegis-image-highlight-suspected");
    });
    document.body.classList.remove("aegis-hide-ai-active");
    sendResponse({ status: "success", enabled: false });
  }

  else if (request.action === "updateSettings") {
    const settings = request.settings;

    // Apply sensitivity changes immediately (not just on the next full scan)
    if (settings && typeof settings.sensitivity === "number") {
      scanSensitivity = settings.sensitivity;
    }
    
    // Image overlays setting
    const autoOverlays = (settings && settings.autoImageOverlays !== undefined) ? settings.autoImageOverlays : false;
    if (autoOverlays) {
      document.body.classList.remove("aegis-hide-image-overlays");
    } else {
      document.body.classList.add("aegis-hide-image-overlays");
    }

    // VibeCoded alert setting
    const showVibe = (settings && settings.showVibecodedAlert !== undefined) ? settings.showVibecodedAlert : false;
    const existingVibeBar = document.getElementById("aegis-vibecoded-top-bar");
    if (showVibe) {
      if (scanResults.vibecoded && scanResults.vibecoded.isVibecoded) {
        showVibecodedNotification();
      }
    } else {
      if (existingVibeBar) {
        existingVibeBar.classList.remove("show");
        document.body.style.marginTop = "0px";
        document.body.style.transition = "";
        setTimeout(() => existingVibeBar.remove(), 400);
      }
    }

    sendResponse({ status: "success" });
  }
});

// Initialize on page load
try {
  chrome.storage.local.get(["settings", "extensionEnabled"], (result) => {
    const settings = result.settings;
    const enableText = settings ? settings.enableTextScan : true;
    const enableImg = settings ? settings.enableImageScan : true;
    const enableVid = settings ? settings.enableVideoScan : true;
    const autoOverlays = (settings && settings.autoImageOverlays !== undefined) ? settings.autoImageOverlays : false;
    if (settings && typeof settings.sensitivity === "number") {
      scanSensitivity = settings.sensitivity;
    }

    // Restore the enabled/disabled state from storage
    if (result.extensionEnabled === false) {
      extensionEnabled = false;
    }

    injectStyles();
    if (!autoOverlays) {
      document.body.classList.add("aegis-hide-image-overlays");
    }

    // Only run the initial scan if the extension is enabled
    if (extensionEnabled) {
      setTimeout(() => {
        performPageScan({
          text: enableText,
          images: enableImg,
          videos: enableVid
        });
      }, 1500);
    }
  });
} catch (e) {
  // Silent fail if outside active extension runtime boundaries
}
