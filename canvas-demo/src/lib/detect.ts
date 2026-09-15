import type { ScanResult, VideoMetadata } from "./types";

/**
 * Heuristic AI text detector — simplified version of the Playground heuristics.
 * Scores 0-100 (higher = more likely AI-generated).
 */
export function detectAIText(text: string): ScanResult {
  let score = 0;
  const flags: string[] = [];
  const suggestions: string[] = [];

  if (!text.trim()) {
    return { score: 0, tier: "AUTHENTIC", flags: ["Empty text"] };
  }

  // 1. Corporate/hype emojis
  const hypeEmojis = [
    { char: "🚀", label: "Spaceship (hype)" },
    { char: "✨", label: "Sparkles (AI aesthetic)" },
    { char: "🧠", label: "Brain (AI pitch)" },
    { char: "💡", label: "Lightbulb (solution pitch)" },
    { char: "🎯", label: "Target (marketing)" },
    { char: "📈", label: "Chart (growth pitch)" },
    { char: "🔥", label: "Fire (hype)" },
    { char: "🤖", label: "Robot (AI indicator)" },
    { char: "💼", label: "Briefcase (corporate)" },
    { char: "🤝", label: "Handshake (connection)" },
    { char: "✅", label: "Checkmark (corporate)" },
    { char: "⚠️", label: "Warning (urgency hook)" },
    { char: "📢", label: "Megaphone (announcement)" },
    { char: "👇", label: "Point down (engagement)" },
  ];

  let emojiCount = 0;
  for (const emoji of hypeEmojis) {
    const regex = new RegExp(emoji.char, "g");
    const matches = text.match(regex);
    if (matches) {
      emojiCount += matches.length;
      score += 12 * Math.min(matches.length, 2);
      flags.push(`Emoji: ${emoji.char} — ${emoji.label}`);
    }
  }
  if (emojiCount > 2) {
    score += 10;
    flags.push(`Multiple hype emojis (${emojiCount} total)`);
  }

  // 2. AI buzzwords
  const buzzwords: Array<{ pattern: RegExp; points: number; label: string }> = [
    { pattern: /\bdelve\b/i, points: 18, label: "'delve'" },
    { pattern: /\btapestry\b/i, points: 18, label: "'tapestry'" },
    { pattern: /\btestament to\b/i, points: 14, label: "'testament to'" },
    { pattern: /\bsynergy\b/i, points: 14, label: "'synergy'" },
    { pattern: /\belevate\b/i, points: 14, label: "'elevate'" },
    { pattern: /\bfoster\b/i, points: 11, label: "'foster'" },
    { pattern: /\bseamlessly\b/i, points: 11, label: "'seamlessly'" },
    { pattern: /\brevolutionize\b/i, points: 14, label: "'revolutionize'" },
    { pattern: /\buncover\b/i, points: 9, label: "'uncover'" },
    { pattern: /\bimportant to note\b/i, points: 9, label: "'important to note'" },
    { pattern: /\bin conclusion\b/i, points: 9, label: "'in conclusion'" },
    { pattern: /\buncomfortable truth\b/i, points: 18, label: "'uncomfortable truth'" },
    { pattern: /\bno longer optional\b/i, points: 14, label: "'no longer optional'" },
    { pattern: /\bunderestimate this\b/i, points: 14, label: "'underestimate this'" },
    { pattern: /\bcutting-edge\b/i, points: 13, label: "'cutting-edge'" },
    { pattern: /\bstate-of-the-art\b/i, points: 13, label: "'state-of-the-art'" },
    { pattern: /\bgame-changing\b/i, points: 13, label: "'game-changing'" },
    { pattern: /\bthought-provoking\b/i, points: 13, label: "'thought-provoking'" },
    { pattern: /\buser-friendly\b/i, points: 13, label: "'user-friendly'" },
    { pattern: /\bcost-effective\b/i, points: 13, label: "'cost-effective'" },
    { pattern: /\bend-to-end\b/i, points: 13, label: "'end-to-end'" },
    { pattern: /\breal-time\b/i, points: 13, label: "'real-time'" },
  ];

  for (const bw of buzzwords) {
    const matches = text.match(bw.pattern);
    if (matches) {
      score += bw.points * matches.length;
      flags.push(`Buzzword: ${bw.label}`);
    }
  }

  // 3. Em-dash / en-dash
  const dashCount = (text.match(/[\u2014\u2013]/g) || []).length;
  if (dashCount > 0) {
    score += 18 * Math.min(dashCount, 2);
    flags.push(`Em/en-dash used ${dashCount}x (AI punctuation style)`);
  }

  // 4. Bold bullet lists
  const boldBullets = text.match(/(\*|-|\d+\.)\s+\*\*[^*]+\*\*:/g);
  if (boldBullets) {
    score += 18 * Math.min(boldBullets.length, 3);
    flags.push(`Bold bullet list headers (${boldBullets.length}x)`);
  }

  // 5. Broetry — single-sentence paragraphs
  const paragraphs = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  if (paragraphs.length >= 4) {
    const singleSentenceParas = paragraphs.filter((p) => {
      const sents = p.split(/[.!?]+/).map((s) => s.trim()).filter(Boolean);
      return sents.length === 1;
    });
    const ratio = singleSentenceParas.length / paragraphs.length;
    if (ratio >= 0.7) {
      score += 30;
      flags.push(`Broetry layout: ${Math.round(ratio * 100)}% single-sentence paragraphs`);
    }
  }

  // 6. Bullet points density
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const bullets = lines.filter((l) => /^(•|-|\*|→|▪|✓|\d+\.)\s+/.test(l));
  if (bullets.length >= 3) {
    score += Math.min(bullets.length * 12, 36);
    flags.push(`Heavy bullet formatting (${bullets.length} bullets)`);
  }

  // 7. Engagement question at end
  if (lines.length > 2) {
    const last = lines[lines.length - 1];
    if (last.endsWith("?") || (last.includes("?") && last.length < 120)) {
      score += 18;
      flags.push("Ends with engagement question");
    }
  }

  // 8. First-line emoji hook
  if (lines.length > 0) {
    const first = lines[0];
    const emojiInFirst = /[\u{1F300}-\u{1F9FF}\u{2700}-\u{27BF}]/u.test(first);
    if (emojiInFirst && first.includes("?")) {
      score += 25;
      flags.push("AI hook: rhetorical question + emoji in first line");
    } else if (emojiInFirst) {
      score += 15;
      flags.push("AI hook: emoji in opening line");
    }
  }

  // 9. Hashtag salad
  const hashtags = text.match(/#\w+/g) || [];
  if (hashtags.length >= 3) {
    score += 15;
    flags.push(`Hashtag salad (${hashtags.length} hashtags)`);
  }

  // 10. Low sentence variance (uniform cadence)
  const sentences = text.split(/[.!?]+/).map((s) => s.trim()).filter(Boolean);
  if (sentences.length >= 4) {
    const wc = sentences.map((s) => s.split(/\s+/).length);
    const avg = wc.reduce((a, b) => a + b, 0) / wc.length;
    const variance = wc.reduce((a, b) => a + (b - avg) ** 2, 0) / wc.length;
    const stdDev = Math.sqrt(variance);
    if (stdDev < 3) {
      score += 25;
      flags.push("Low sentence-length variance (uniform machine cadence)");
    } else if (stdDev < 5) {
      score += 12;
      flags.push("Moderately uniform sentence rhythm");
    }
  }

  // 11. AI narrative patterns
  const narrativePatterns: Array<{ pattern: RegExp; label: string }> = [
    { pattern: /\bBack in \d{4}\b/i, label: "'Back in [year]'" },
    { pattern: /\bThis led me to\b/i, label: "'This led me to'" },
    { pattern: /\bBecause of this\b/i, label: "'Because of this'" },
    { pattern: /\btaught me a big lesson\b/i, label: "'taught me a big lesson'" },
    { pattern: /\bflipped my entire\b/i, label: "'flipped my entire'" },
    { pattern: /\bThe passion was always there\b/i, label: "'The passion was always there'" },
    { pattern: /\bjust buried under\b/i, label: "'just buried under'" },
    { pattern: /\bcouldn't stay away\b/i, label: "'couldn't stay away'" },
    { pattern: /\btruly matter\b/i, label: "'truly matter'" },
    { pattern: /\bchips? away at\b/i, label: "'chips away at'" },
    { pattern: /\bmore than anything else\b/i, label: "'more than anything else'" },
    { pattern: /\bgenuinely care\b/i, label: "'genuinely care'" },
    { pattern: /\bThat matters to me\b/i, label: "'That matters to me'" },
  ];

  let narrativeHits = 0;
  for (const np of narrativePatterns) {
    if (np.pattern.test(text)) {
      narrativeHits++;
      flags.push(`Narrative pattern: ${np.label}`);
    }
  }
  if (narrativeHits >= 4) {
    score += 20;
    flags.push(`${narrativeHits} AI narrative patterns detected`);
  } else if (narrativeHits >= 2) {
    score += 8;
  }

  // 12. Causal connector density
  const causalWords = text.toLowerCase().match(/\b(because|therefore|thus|hence|consequently|led to|resulted in|taught me|made me|so I|so it)\b/g) || [];
  const causalDensity = causalWords.length / Math.max(1, sentences.length);
  if (causalDensity > 0.25 && sentences.length >= 3) {
    score += 18;
    flags.push(`High causal connector density (${causalWords.length} across ${sentences.length} sentences)`);
  }

  // Suggestions
  if (emojiCount > 2) {
    suggestions.push("Remove hype emojis — real writing doesn't need visual crutches");
  }
  if (boldBullets && boldBullets.length >= 2) {
    suggestions.push("Replace bold bullet headers with flowing prose");
  }
  const aiBuzzwordMatches = buzzwords.filter((bw) => text.match(bw.pattern));
  if (aiBuzzwordMatches.length >= 2) {
    suggestions.push(`Replace AI buzzwords: ${aiBuzzwordMatches.map((b) => b.label).join(", ")}`);
  }
  if (dashCount > 1) {
    suggestions.push("Replace em-dashes with commas, periods, or parentheses");
  }
  if (hashtags.length >= 3) {
    suggestions.push("Reduce hashtags to 1-2 relevant ones");
  }

  const finalScore = Math.min(99, Math.max(0, score));

  let tier: ScanResult["tier"];
  if (finalScore >= 80) tier = "AI_DEFINITE";
  else if (finalScore >= 55) tier = "AI_LIKELY";
  else if (finalScore >= 30) tier = "SUSPICIOUS";
  else tier = "AUTHENTIC";

  return { score: finalScore, tier, flags, suggestions };
}

/** Detect AI images by URL pattern matching (same as Playground) */
export function detectAIImage(url: string): ScanResult {
  const flags: string[] = [];
  let score = 0;

  const aiHosts = [
    "chatgpt", "claude", "deepseek", "gemini", "openai", "midjourney",
    "stability", "generative", "replicate", "civitai", "flux-ai",
    "leonardo", "lexica", "playgroundai", "bing.com/images/create",
  ];

  const lower = url.toLowerCase();
  for (const host of aiHosts) {
    if (lower.includes(host)) {
      score = 90;
      flags.push(`URL matches AI host: ${host}`);
      break;
    }
  }
  if (lower.includes(".ai") || lower.includes("/ai/")) {
    score = Math.max(score, 75);
    flags.push("URL contains .ai or /ai/ path");
  }
  if (lower.includes("data:image")) {
    score = Math.max(score, 40);
    flags.push("Base64-encoded image (can't verify source)");
  }

  const tier: ScanResult["tier"] =
    score >= 80 ? "AI_DEFINITE" : score >= 55 ? "AI_LIKELY" : score >= 30 ? "SUSPICIOUS" : "AUTHENTIC";

  return {
    score,
    tier,
    flags: flags.length > 0 ? flags : ["No URL-based AI indicators found"],
  };
}

// --- Video URL Parsing ---

interface ParsedVideoUrl {
  source: "youtube" | "instagram" | "vimeo" | "unknown";
  id?: string;
  url: string;
}

/** Extract video ID from YouTube URL */
function parseYouTubeUrl(url: string): ParsedVideoUrl {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})/,
    /^([a-zA-Z0-9_-]{11})$/, // bare video ID
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) {
      return { source: "youtube", id: match[1], url };
    }
  }
  return { source: "unknown", url };
}

/** Extract media ID from Instagram URL */
function parseInstagramUrl(url: string): ParsedVideoUrl {
  const patterns = [
    /instagram\.com\/reel\/([a-zA-Z0-9_-]+)/,
    /instagram\.com\/p\/([a-zA-Z0-9_-]+)/,
    /instagram\.com\/tv\/([a-zA-Z0-9_-]+)/,
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) {
      return { source: "instagram", id: match[1], url };
    }
  }
  return { source: "unknown", url };
}

/** Extract video ID from Vimeo URL */
function parseVimeoUrl(url: string): ParsedVideoUrl {
  const match = url.match(/vimeo\.com\/(\d+)/);
  if (match) {
    return { source: "vimeo", id: match[1], url };
  }
  return { source: "unknown", url };
}

/** Parse any video URL and extract metadata */
export function parseVideoUrl(url: string): ParsedVideoUrl {
  // Try YouTube first
  const ytResult = parseYouTubeUrl(url);
  if (ytResult.source !== "unknown") return ytResult;

  // Try Instagram
  const igResult = parseInstagramUrl(url);
  if (igResult.source !== "unknown") return igResult;

  // Try Vimeo
  const vmResult = parseVimeoUrl(url);
  if (vmResult.source !== "unknown") return vmResult;

  return { source: "unknown", url };
}

/** Get YouTube thumbnail URL from video ID */
export function getYouTubeThumbnail(videoId: string, quality: "default" | "medium" | "high" = "default"): string {
  const qualityMap = {
    default: "default.jpg",
    medium: "mqdefault.jpg",
    high: "hqdefault.jpg",
  };
  return `https://img.youtube.com/vi/${videoId}/${qualityMap[quality]}`;
}

/** Check if video platform is known AI video generator */
function checkAiVideoHosts(url: string): { score: number; flags: string[] } {
  const flags: string[] = [];
  let score = 0;
  const lower = url.toLowerCase();

  const aiVideoHosts = [
    { host: "sora", label: "OpenAI Sora" },
    { host: "runwayml", label: "Runway ML" },
    { host: "pika-ai", label: "Pika Labs" },
    { host: "lumaai", label: "Luma Dream Machine" },
    { host: "kaiber", label: "Kaiber" },
    { host: "heynetflixai", label: "Netflix AI experiments" },
    { host: "deforum", label: "Deforum (Stable Diffusion" },
    { host: "stable-video-diffusion", label: "Stable Video Diffusion" },
    { host: "zeroscope", label: "ZeroScope" },
    { host: "moondream", label: "MoonDream" },
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
  ];

  for (const { pattern, label } of aiVideoTerms) {
    if (pattern.test(lower)) {
      score = Math.max(score, 70);
      flags.push(`URL contains: ${label}`);
    }
  }

  return { score, flags };
}

/** Detect AI-generated videos by URL analysis */
export function detectAIVideo(url: string): ScanResult {
  const flags: string[] = [];
  let score = 0;

  const parsed = parseVideoUrl(url);

  // 1. Check AI video hosts/terms
  const aiHostCheck = checkAiVideoHosts(url);
  score += aiHostCheck.score;
  flags.push(...aiHostCheck.flags);

  // 2. Platform-specific analysis
  if (parsed.source === "youtube" && parsed.id) {
    flags.push("YouTube video detected");
    flags.push(`Video ID: ${parsed.id}`);
    flags.push(`Thumbnail: ${getYouTubeThumbnail(parsed.id)}`);

    // YouTube itself isn't AI, but we note it's accessible for thumbnail analysis
    score = Math.max(score, 10); // Low baseline — YouTube is neutral
  } else if (parsed.source === "instagram" && parsed.id) {
    flags.push("Instagram video/reel detected");
    flags.push(`Media ID: ${parsed.id}`);

    // Instagram reels often have AI content but platform itself is neutral
    score = Math.max(score, 15);
  } else if (parsed.source === "vimeo" && parsed.id) {
    flags.push("Vimeo video detected");
    score = Math.max(score, 10);
  } else if (parsed.source === "unknown") {
    flags.push("Unrecognized video URL format");
    score = Math.max(score, 25); // Unknown sources are suspicious

    // Check if it might be a direct video file
    if (/\.(mp4|webm|ogg|mov|avi|mkv)/i.test(url)) {
      flags.push("Direct video file URL");
      flags.push("Cannot verify source authenticity");
      score = Math.max(score, 30);
    }
  }

  // 3. Check for short URL services that hide the real source
  const urlLower = url.toLowerCase();
  const shorteners = ["bit.ly", "tinyurl", "t.co", "buff.ly", "ow.ly", "qr.io"];
  if (shorteners.some((s) => urlLower.includes(s))) {
    flags.push("URL uses shortener service — actual source hidden");
    score += 20;
  }

  // 4. Check for suspicious domain patterns
  if (/\bgenAIC|\bai-video|\bcontent-ai/i.test(url)) {
    score = Math.max(score, 60);
    flags.push("Domain suggests AI-generated content");
  }

  const tier: ScanResult["tier"] =
    score >= 80 ? "AI_DEFINITE" : score >= 55 ? "AI_LIKELY" : score >= 30 ? "SUSPICIOUS" : "AUTHENTIC";

  return {
    score: Math.min(99, score),
    tier,
    flags: flags.length > 0 ? flags : ["No AI indicators found in video URL"],
  };
}

/** Extract video metadata for display and further analysis */
export async function fetchVideoMetadata(url: string): Promise<VideoMetadata> {
  const parsed = parseVideoUrl(url);

  const result: VideoMetadata = {
    source: parsed.source,
  };

  // Try to get YouTube thumbnail
  if (parsed.source === "youtube" && parsed.id) {
    result.thumbnailUrl = getYouTubeThumbnail(parsed.id, "high");

    // Try oEmbed for metadata
    try {
      const oembedUrl = `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${parsed.id}&format=json`;
      const response = await fetch(oembedUrl, {
        headers: { Accept: "application/json" },
      });
      if (response.ok) {
        const data = await response.json();
        result.title = data.title;
        result.author = data.author_name;
      }
    } catch {
      // oEmbed may fail; thumbnail is still available
    }
  }

  // Instagram thumbnail (approximate)
  if (parsed.source === "instagram" && parsed.id) {
    result.thumbnailUrl = `https://i.instagram.com/v1/media/${parsed.id}/image/?v=1`; // May not work without auth
  }

  // Vimeo thumbnail via oEmbed
  if (parsed.source === "vimeo" && parsed.id) {
    result.thumbnailUrl = `https://vumbnail.com/${parsed.id}.jpg`;
    try {
      const oembedUrl = `https://vimeo.com/api/oembed.json?url=https://vimeo.com/${parsed.id}`;
      const response = await fetch(oembedUrl);
      if (response.ok) {
        const data = await response.json();
        result.title = data.title;
        result.author = data.author_name;
      }
    } catch {
      // ignore
    }
  }

  return result;
}
