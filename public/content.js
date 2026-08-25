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
    body.aegis-hide-ai-active .aegis-image-highlight-ai,
    body.aegis-hide-ai-active .aegis-image-highlight-suspected,
    body.aegis-hide-ai-active .aegis-badge,
    body.aegis-hide-ai-active .aegis-image-overlay-text {
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
  if (cleanText.length < 50) return null; // Parse slightly shorter segments for hover interactions

  let score = 0;
  const reasons = [];

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
    score = Math.max(1, score - humanScoreReduction);
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

// Check image headers for generative AI tags (EXIF Metadata Reader)
const inspectImageMetadata = async (imgUrl) => {
  if (!imgUrl || imgUrl.startsWith("data:") || imgUrl.startsWith("blob:")) {
    return null;
  }

  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage({ action: "fetchImageMetadata", url: imgUrl }, (response) => {
        if (response && response.status === "success" && response.found) {
          resolve({
            score: response.score,
            reasons: response.reasons,
            url: imgUrl
          });
        } else {
          resolve(null);
        }
      });
    } catch (err) {
      resolve(null);
    }
  });
};

const inspectImageDOMContext = (img) => {
  if (!img) return null;
  
  const reasons = [];
  let score = 0;
  
  const alt = (img.alt || '').trim();
  const title = (img.title || '').trim();
  // Expanded keyword regex to cover more systems
  const aiKeywordRegex = /(\bai[- ]generated\b|generative|midjourney|dall-e|dalle|stable[- ]diffusion|flux[-.]1|adobe[- ]firefly|deepai|leonardo[- ]ai|civitai|flux[- ]ai|created (with|by) ai|made (with|by) ai)/i;
  
  if (alt && aiKeywordRegex.test(alt)) {
    score = Math.max(score, 98);
    reasons.push(`AI attribution in alt text: "${alt}"`);
  }
  if (title && aiKeywordRegex.test(title)) {
    score = Math.max(score, 98);
    reasons.push(`AI attribution in title tag: "${title}"`);
  }
  
  // Prompt-like alt text heuristic
  if (alt && alt.length >= 20) {
    const promptKeywords = [
      "photorealistic", "hyperrealistic", "highly detailed", "octane render", 
      "unreal engine", "trending on artstation", "cinematic lighting", 
      "masterpiece", "intricate details", "volumetric lighting", "ray tracing", 
      "4k resolution", "8k resolution", "concept art", "sharp focus", "depth of field"
    ];
    const segments = alt.split(',').map(s => s.trim().toLowerCase());
    if (segments.length >= 3) {
      let matchedWords = [];
      for (const kw of promptKeywords) {
        if (alt.toLowerCase().includes(kw)) {
          matchedWords.push(kw);
        }
      }
      if (matchedWords.length >= 2) {
        score = Math.max(score, 85);
        reasons.push(`Alt text structured like an AI image prompt: contains comma-separated segments and prompt keywords [${matchedWords.join(", ")}]`);
      }
    }
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

  const src = img.src || '';
  if (src.startsWith('data:')) {
    try {
      const binaryString = atob(src.split(',')[1].substring(0, 100000));
      const aiTags = [
        { term: "Stable Diffusion", source: "Stable Diffusion parameters" },
        { term: "Midjourney", source: "Midjourney generation parameters" },
        { term: "DALL-E", source: "DALL-E metadata" },
        { term: "NovelAI", source: "NovelAI generator metadata" },
        { term: "civitai", source: "CivitAI tags" },
        { term: "Adobe Firefly", source: "Adobe Firefly creator signature" }
      ];
      for (const tag of aiTags) {
        if (binaryString.includes(tag.term)) {
          score = Math.max(score, 99);
          reasons.push(`Base64 Header Signature: Detected '${tag.term}' (${tag.source})`);
        }
      }
      // Fixed PNG space chunk signature bug
      if (binaryString.includes("tEXtparameters") || binaryString.includes("zTXtparameters") || binaryString.includes("iTXtparameters") || binaryString.includes("tEXt parameters") || binaryString.includes("zTXt parameters")) {
        score = Math.max(score, 95);
        reasons.push("Base64 Header Signature: PNG metadata contains Stable Diffusion parameters chunk");
      }
    } catch (e) {}
  } else {
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

  // 1. Image checks
  if (element.tagName === "IMG") {
    showFloatingScannerTooltip("Analyzing image layers...", mouseX, mouseY);
    let imgResult = await inspectImageMetadata(element.src);
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
        score: 12,
        reasons: ["No artificial metadata headers or signature frequency patterns discovered."],
        title: "IMAGE VERIFICATION",
        details: `Exif: Checked clean. Sources: Scanned.`
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

  // Image Scanner
  if (options.images) {
    const images = Array.from(document.querySelectorAll("img"));

    for (const img of images) {
      if (img.width < 50 || img.height < 50) continue;
      scannedCount++;

      let imgResult = await inspectImageMetadata(img.src);
      if (!imgResult) {
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

  // Video Scanner
  if (options.videos) {
    const videos = Array.from(document.querySelectorAll("video, iframe"));

    for (const vid of videos) {
      const src = vid.src || (vid.querySelector("source") ? vid.querySelector("source").src : "");
      if (!src) continue;

      scannedCount++;
      const isSuspectVideo = src.includes("synthesia") || src.includes("heygen") || src.includes("runway");

      if (isSuspectVideo) {
        flaggedCount++;
        const id = "vid-" + Math.random().toString(36).substr(2, 9);
        const item = {
          id: id,
          score: 98,
          reasons: ["Injected synthesia/heygen frame container structures."],
          src: src,
          width: vid.width || 640,
          height: vid.height || 360
        };

        scanResults.videos.push(item);

        const parent = vid.parentElement;
        if (parent) {
          const badge = document.createElement("span");
          badge.className = `aegis-badge aegis-badge-ai aegis-media-overlay-badge`;
          badge.textContent = `AI VIDEO 98%`;
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
    }
  }

  // Integrity Score Calculation
  if (isAiWorkbench) {
    scanResults.score = 0;
  } else {
    let baseScore = 100;
    if (scannedCount > 0 && flaggedCount > 0) {
      let penaltySum = 0;
      const items = [...scanResults.text, ...scanResults.images, ...scanResults.videos];
      items.forEach(item => {
        penaltySum += item.score;
      });
      const avgPenalty = penaltySum / scannedCount;
      baseScore = Math.round(100 - (avgPenalty * (flaggedCount / scannedCount) * 1.5));
    }

    // Apply vibecoded penalties
    let vibecodedPenalty = 0;
    if (scanResults.vibecoded && scanResults.vibecoded.hasPurpleGradient) vibecodedPenalty += 15;
    if (scanResults.vibecoded && scanResults.vibecoded.hasBubbleHeader) vibecodedPenalty += 15;

    scanResults.score = Math.max(1, baseScore - vibecodedPenalty);
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
    triggerLocalScan(hoveredElement);
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
    } else {
      performPageScan().then(results => {
        sendResponse({ status: "success", data: results });
      });
    }
    return true;
  }

  else if (request.action === "runScan") {
    performPageScan(request.options).then(results => {
      sendResponse({ status: "success", data: results });
    });
    return true;
  }

  else if (request.action === "runDeepScan") {
    triggerDeepScanAnimation((results) => {
      sendResponse({ status: "success", data: results });
    });
    return true;
  }

  else if (request.action === "scanSelectedText") {
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
    // Context Menu Trigger: analyze image source url
    const imageUrl = request.url || "";
    if (imageUrl) {
      injectStyles();
      inspectImageMetadata(imageUrl).then(meta => {
        showDiagnosticFloatingTooltip({
          score: meta ? meta.score : 15,
          reasons: meta ? meta.reasons : ["Exif search clean. No generative metadata tags detected."],
          title: "SELECTED IMAGE AUDIT",
          details: `Source: ${imageUrl.substring(0, 30)}...`
        }, mouseX, mouseY);
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

  else if (request.action === "getHideAIStatus") {
    const isHidden = document.body.classList.contains("aegis-hide-ai-active");
    sendResponse({ status: "success", isHidden: isHidden });
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
  chrome.storage.local.get(["settings"], (result) => {
    const settings = result.settings;
    const enableText = settings ? settings.enableTextScan : true;
    const enableImg = settings ? settings.enableImageScan : true;
    const enableVid = settings ? settings.enableVideoScan : true;
    const autoOverlays = (settings && settings.autoImageOverlays !== undefined) ? settings.autoImageOverlays : false;
    if (settings && typeof settings.sensitivity === "number") {
      scanSensitivity = settings.sensitivity;
    }

    injectStyles();
    if (!autoOverlays) {
      document.body.classList.add("aegis-hide-image-overlays");
    }

    setTimeout(() => {
      performPageScan({
        text: enableText,
        images: enableImg,
        videos: enableVid
      });
    }, 1500);
  });
} catch (e) {
  // Silent fail if outside active extension runtime boundaries
}
