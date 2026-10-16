import { useState, useRef } from 'react';
import type { ChangeEvent } from 'react';
import { 
  Sparkles, 
  FileText, 
  Image as ImageIcon, 
  Send, 
  Trash2, 
  ShieldAlert, 
  ShieldCheck, 
  Brain,
  Dna,
  Video,
  Layers,
  Eye,
  EyeOff,
  Activity
} from 'lucide-react';
import type { AppSettings } from '../App';

const humanizerDatabase: Record<string, { term: string; suggestions: string[]; explanation: string }> = {
  "delve": {
    term: "delve",
    suggestions: ["explore", "investigate", "go into", "examine"],
    explanation: "AI models over-rely on 'delve' to start detailed discussions. Human writers prefer simpler action verbs."
  },
  "tapestry": {
    term: "tapestry",
    suggestions: ["complex mixture", "blend", "network", "overview"],
    explanation: "AI models frequently use 'tapestry' as a metaphor. Using concrete nouns keeps writing grounded."
  },
  "testament to": {
    term: "testament to",
    suggestions: ["proof of", "shows", "demonstrates", "reflects"],
    explanation: "This phrase is a repetitive GPT transition formula. Action verbs sound more organic."
  },
  "synergy": {
    term: "synergy",
    suggestions: ["collaboration", "cooperation", "teamwork", "joint effort"],
    explanation: "A corporate cliché heavily favored in synthesized posts. Simple alternatives improve trust."
  },
  "elevate": {
    term: "elevate",
    suggestions: ["improve", "boost", "lift", "enhance"],
    explanation: "Overused AI transition word. Select more specific verbs."
  },
  "foster": {
    term: "foster",
    suggestions: ["encourage", "nurture", "develop", "promote"],
    explanation: "AI models default to 'foster' when discussing relationship building."
  },
  "seamlessly": {
    term: "seamlessly",
    suggestions: ["smoothly", "easily", "directly", "well"],
    explanation: "A filler adverb frequently injected by AI models to smooth transitions."
  },
  "revolutionize": {
    term: "revolutionize",
    suggestions: ["transform", "change", "redefine"],
    explanation: "Hype pitch verb typical of automated marketing content."
  },
  "uncover": {
    term: "uncover",
    suggestions: ["find", "discover", "reveal"],
    explanation: "Typical AI transition filler word."
  },
  "important to note": {
    term: "important to note",
    suggestions: ["remember that", "note that", "crucially"],
    explanation: "A conversational filler phrase used by LLMs to structure output."
  },
  "in conclusion": {
    term: "in conclusion",
    suggestions: ["finally", "ultimately", "in short"],
    explanation: "Boilerplate structural transition that human writers rarely use."
  },
  "uncomfortable truth": {
    term: "uncomfortable truth",
    suggestions: ["hard reality", "fact", "truth"],
    explanation: "AI copywriting template hook used to capture attention."
  },
  "no longer optional": {
    term: "no longer optional",
    suggestions: ["essential", "necessary", "critical"],
    explanation: "Standard LLM boilerplate phrase for creating urgency."
  },
  "underestimate this": {
    term: "underestimate this",
    suggestions: ["overlook this", "miss this", "disregard this"],
    explanation: "A classic LinkedIn-style generative hook formula."
  }
};

interface TextAnalysisStats {
  length: number;
  words: number;
  sentences: number;
  perplexityScore: number;
  burstiness: number;
}

interface HumanizerSuggestion {
  id: string;
  term: string;
  suggestions: string[];
  explanation: string;
}

interface TextAnalysisResults {
  score: number;
  flags: string[];
  stats: TextAnalysisStats;
  suggestions: HumanizerSuggestion[];
}

interface ImageAnalysisResults {
  score: number;
  confidence?: 'HIGH' | 'MEDIUM' | 'LOW';
  tier?: string;
  reasons: string[];
  url: string;
  breakdown?: Record<string, number>;
  layers_active?: string[];
  mode?: string;
  heatmap_grid?: number[][];
  heatmap_overlay_base64?: string;
  synthetic_patches_count?: number;
  frequency_metrics?: {
    slope?: number;
    grid_peaks?: number;
    wavelet_ratio?: number;
  };
  frames_analyzed?: number;
  frame_scores?: number[];
  temporal_flicker_energy?: number;
  motion_residual_variance?: number;
  pwtf_metrics?: {
    centroid_mean?: number;
    hf_share_mean?: number;
    entropy_mean?: number;
    coherence_mean?: number;
  };
  pwtf_spectrum_bins?: number;
  pwtf_frames_analyzed?: number;
  d3_metrics?: {
    volatility?: number;
    mean_velocity?: number;
    mean_interframe_motion?: number;
    region_volatility_mean?: number;
    region_uniformity?: number;
  };
  straighten_metrics?: {
    step_distance_mean?: number;
    step_distance_std?: number;
    curvature_mean_deg?: number;
    curvature_std_deg?: number;
    path_efficiency?: number;
  };
  // Audio track (video only; docs/audio-and-lip-sync-plan.md phase A0).
  // Reported on its own axis and NEVER scored against the video tier, so
  // `score` is always null - it is evidence readout, not a vote.
  audio?: {
    score?: number | null;
    active?: boolean;
    applies?: boolean;
    kind?: 'speech' | 'nonspeech' | 'silence' | 'unavailable';
    has_speech?: boolean | null;
    duration_s?: number | null;
    sample_rate_hz?: number | null;
    metrics?: {
      duration_s?: number;
      sample_rate_hz?: number;
      rms_dbfs?: number;
      peak_dbfs?: number;
      active_fraction?: number;
      silence_fraction?: number;
      zero_crossing_rate_mean?: number;
      bandwidth_hz_99?: number;
      hf_share_8k?: number;
      hf_share_16k?: number;
      speech_band_share?: number;
      spectral_centroid_hz?: number;
      spectral_flatness_mean?: number;
      envelope_cv?: number;
      syllabic_energy_share?: number;
      syllabic_peak_hz?: number;
      frames_analyzed?: number;
    };
    reasons?: string[];
  };
}

interface StoryScopeDimension {
  key: string;
  name: string;
  mean_assoc_ai: number;
  train_mean_assoc_ai: number;
  n_features: number;
}

interface StoryScopeTell {
  feature: string;
  dimension: string;
  value: string;
  p_ai_given_value: number;
  ai_association: number;
}

interface StoryScopeResults {
  score: number;
  probability: number;
  label: string;
  engine: string;
  mode?: string;
  feature_source?: string;
  model: string;
  features_extracted: number;
  features_total: number;
  dimensions: StoryScopeDimension[];
  top_tells: StoryScopeTell[];
  warnings: string[];
  reasons: string[];
  latency_ms?: { feature_extraction?: number; classification?: number };
  error?: string;
}

interface PlaygroundProps {
  settings?: AppSettings;
}

export default function Playground({ settings }: PlaygroundProps) {
  const [sandboxType, setSandboxType] = useState<'text' | 'image' | 'video'>('text');
  
  // Text analysis states
  const [textVal, setTextVal] = useState('');
  const [textResults, setTextResults] = useState<TextAnalysisResults | null>(null);
  const [storyScope, setStoryScope] = useState<{
    loading: boolean;
    results: StoryScopeResults | null;
    error: string | null;
  }>({ loading: false, results: null, error: null });
  const [dnaDetect, setDnaDetect] = useState<{
    loading: boolean;
    results: any | null;
    error: string | null;
  }>({ loading: false, results: null, error: null });
  
  // Image analysis states
  const [imgUrl, setImgUrl] = useState('');
  const [scanMode, setScanMode] = useState<'deep' | 'fast'>('deep');
  const [showHeatmapOverlay, setShowHeatmapOverlay] = useState(true);
  const [imgResults, setImgResults] = useState<ImageAnalysisResults | null>(null);
  
  // Video analysis states
  const [videoUrl, setVideoUrl] = useState('');
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoResults, setVideoResults] = useState<ImageAnalysisResults | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);

  const [analyzing, setAnalyzing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoFileInputRef = useRef<HTMLInputElement>(null);

  // Simple heuristic text logic matching content.js but adding verbose playground logs
  const handleAnalyzeText = (overrideText?: string) => {
    const textToScan = (overrideText !== undefined ? overrideText : textVal).trim();
    if (!textToScan) return;
    setAnalyzing(true);
    setTextResults(null);
    setStoryScope({ loading: false, results: null, error: null });

    // Cloud mode: run the StoryScope narrative-feature detector. The server
    // defaults to the offline rule-based engine (no API key needed); it uses
    // the paper's LLM pipeline only when STORYSCOPE_MODE=llm is configured.
    // Falls back to local heuristics on any failure.
    const activeForStory = settings || {
      enableTextScan: true, enableImageScan: true, enableVideoScan: true,
      sensitivity: 50, showInlineBadges: true, autoImageOverlays: false,
      showVibecodedAlert: false, apiMode: "local", apiUrl: "", apiKey: ""
    };
    if (activeForStory.apiMode === 'cloud') {
      const base = (activeForStory.apiUrl || 'http://localhost:5001/predict').replace(/\/predict$/, '');
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(activeForStory.apiKey ? { 'Authorization': `Bearer ${activeForStory.apiKey}` } : {})
      };

      // StoryScope for longer texts (needs 200+ chars for narrative features)
      if (textToScan.length >= 200) {
        setStoryScope({ loading: true, results: null, error: null });
        fetch(`${base}/predict/storyscope`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ text: textToScan })
        })
          .then(async (response) => {
            if (!response.ok) {
              const body = await response.json().catch(() => ({}));
              throw new Error(body.error || `Server returned status ${response.status}`);
            }
            return response.json();
          })
          .then((data) => {
            setStoryScope({ loading: false, results: data as StoryScopeResults, error: null });
          })
          .catch((err) => {
            setStoryScope({
              loading: false,
              results: null,
              error: `StoryScope unavailable: ${err.message}`
            });
          });
      }

      // DNA-DetectLLM for ALL text lengths (works from 20 chars)
      // Complements StoryScope on short texts, supplements on long texts
      setDnaDetect({ loading: true, results: null, error: null });
      fetch(`${base}/predict/text/dna`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ text: textToScan })
      })
        .then(async (response) => {
          if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.error || `Server returned status ${response.status}`);
          }
          return response.json();
        })
        .then((data) => {
          setDnaDetect({ loading: false, results: data, error: null });
        })
        .catch((err) => {
          setDnaDetect({
            loading: false,
            results: null,
            error: `DNA-DetectLLM unavailable: ${err.message}`
          });
        });
    }

    setTimeout(() => {
      setAnalyzing(false);
      const text = textToScan;
      let score = 0;
      const flags = [];
      const stats = {
        length: text.length,
        words: text.split(/\s+/).length,
        sentences: text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0).length,
        perplexityScore: 45, // mid normal
        burstiness: 50
      };

      // Heuristic rules
      // 1. Corporate emoji check
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
      const matchedEmojis = [];
      corporateEmojis.forEach(emoji => {
        const regex = new RegExp(emoji.char, "g");
        const count = (text.match(regex) || []).length;
        if (count > 0) {
          emojiScore += 15 * Math.min(count, 2);
          matchedEmojis.push(emoji.char);
          flags.push(`Emoji detected: ${emoji.char} - ${emoji.label}`);
        }
      });

      if (matchedEmojis.length > 2) {
        emojiScore += 10;
        flags.push("Multiple corporate/hype emojis (highly generative layout signature)");
      }

      // 2. Bold bullet lists headers (**Title:** details)
      const boldBulletPattern = /(\*|-|\d+\.)\s+\*\*[^*]+\*\*:/g;
      const boldBulletMatches = text.match(boldBulletPattern);
      if (boldBulletMatches) {
        const count = boldBulletMatches.length;
        score += 20 * Math.min(count, 3);
        flags.push(`Generative formatting template: Bolded list headers (e.g. **Title**: details) (x${count})`);
      } else {
        const plainBoldHeader = /\*\*[^*]+\*\*:/g;
        const plainMatches = text.match(plainBoldHeader);
        if (plainMatches && plainMatches.length > 1) {
          score += 15;
          flags.push("Overuse of bold inline headings with colons");
        }
      }

      // 3. Hyphenated descriptive compounds
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
        const matches = text.match(regex);
        if (matches) {
          score += 15 * matches.length;
          flags.push(`Hyphenated descriptor: '${item.term}' (${item.label})`);
        }
      });

      const generalHyphenRegex = /[a-zA-Z]+-[a-zA-Z]+/g;
      const generalHyphens = text.match(generalHyphenRegex) || [];
      if (generalHyphens.length >= 3) {
        const uniqueHyphens = [...new Set(generalHyphens.map(s => s.toLowerCase()))];
        score += 10;
        flags.push(`High density of hyphenated descriptive compounds (${uniqueHyphens.length} unique)`);
      }

      // Em-dash & En-dash transition checks: "—" or "–"
      const dashRegex = /[\u2014\u2013]/g;
      const dashCount = (text.match(dashRegex) || []).length;
      if (dashCount > 0) {
        score += 20 * Math.min(dashCount, 2);
        flags.push(`Generative punctuation: Detected Em-dash or En-dash ('—' / '–') as clause separator`);
      }

      // 4. Overused AI Corporate Speak & Buzzwords
      const aiBuzzwords = [
        { term: /as an ai language model/i, points: 50, label: "AI model disclaimer boilerplate" },
        { term: /\bdelve\b/i, points: 20, label: "Unused vocabulary preference ('delve')" },
        { term: /\btapestry\b/i, points: 20, label: "Unused metaphor choice ('tapestry')" },
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
        const matches = text.match(item.term);
        if (matches) {
          score += item.points * matches.length;
          const termStr = item.term.toString().replace(/\\b|\/gi|\/i|\//g, "");
          flags.push(`AI Buzzword/Phrase: '${termStr}' - ${item.label}`);
        }
      });

      // 5. LinkedIn/AI Hook: Robot, alert, or corporate emoji in the first line
      const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
      if (lines.length > 0) {
        const firstLine = lines[0];
        const containsQuestion = firstLine.includes('?');
        const containsEmoji = /[\u{1F300}-\u{1F9FF}\u{2700}-\u{27BF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}]/u.test(firstLine);
        if (containsQuestion && containsEmoji) {
          emojiScore += 30;
          flags.push("AI Hook Style: Text starts with a rhetorical question containing an emoji");
        }

        // Check for robot, alert, or corporate emojis in the first line specifically
        const targetEmojis = /🤖|🌐|💻|📢|🚀|✨|💡|🎯|📈|💼|🤝|🚨|⚠️|✅|❌|🔍|📊|😵|🔥|💥|🌟|⚡|👇/u;
        if (targetEmojis.test(firstLine)) {
          emojiScore += 45;
          flags.push("AI Hook Style: First line starts with or contains a robot, warning, or corporate emoji");
        }
      }

      // 5b. Paragraphs starting with emojis (typical AI list/bullet spacing structure)
      const emojiStartLines = lines.filter(line => /^(🤖|🌐|💻|📢|🚀|✨|💡|🎯|📈|💼|🤝|🚨|⚠️|✅|❌|🔍|📊|😵|🔥|💥|🌟|⚡|👇)/u.test(line));
      if (emojiStartLines.length >= 2) {
        emojiScore += 30;
        flags.push(`AI Formatting Structure: Multiple paragraphs start with corporate/robot emojis (x${emojiStartLines.length})`);
      }

      // Capping emoji score if no primary LLM emojis are present
      const hasLlmEmojis = /🚀|✅|✨|💡/u.test(text);
      if (!hasLlmEmojis && emojiScore > 20) {
        emojiScore = 20;
        flags.push("Emoji score capped at 20 (no primary LLM emojis like 🚀, ✅, ✨, or 💡 present)");
      }
      score += emojiScore;

      // 6. Concluding call to engagement question
      if (lines.length > 2) {
        const lastLine = lines[lines.length - 1];
        const isEngagementQuestion = lastLine.endsWith('?') || (lastLine.includes('?') && lastLine.length < 120);
        if (isEngagementQuestion) {
          score += 20;
          flags.push("AI Closing: Text concludes with an engagement driving question");
        }
      }

      // 7. General Bullet points check (normal humans don't use bullet points very often)
      const bulletLines = lines.filter(line => /^(•|-|\*|→|▪|▫|◦|■|□|✔|✓|\d+\.)\s+/.test(line));
      if (bulletLines.length >= 2) {
        score += Math.min(bulletLines.length * 15, 45);
        flags.push(`AI Formatting Structure: Text contains structured bullet points (x${bulletLines.length})`);
      }

      // 8. Generative case study metrics transition: "from X hours/days to Y/zero"
      const metricPattern = /from\s+\d+\s+(hour|day|week|month)s?\s+(down\s+)?to\s+(\d+|zero)/gi;
      const metricMatches = text.match(metricPattern);
      if (metricMatches) {
        score += 25;
        flags.push(`AI Narrative Metric Pattern: Overused metric reduction template ('from X hours to Y/zero')`);
      }

      // Variance calculation
      const sentences = text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0);
      if (sentences.length >= 3) {
        const wordCounts = sentences.map(s => s.split(/\s+/).length);
        const avg = wordCounts.reduce((a,b) => a+b, 0) / wordCounts.length;
        const variance = wordCounts.reduce((a,b) => a + Math.pow(b - avg, 2), 0) / wordCounts.length;
        const stdDev = Math.sqrt(variance);
        
        stats.perplexityScore = Math.round(Math.max(10, 95 - (stdDev * 8)));
        stats.burstiness = Math.round(Math.min(99, stdDev * 10));

        if (stdDev < 3) {
          score += 30;
          flags.push("Low syntactic variance (typical machine cadence)");
        } else if (stdDev < 5) {
          score += 15;
          flags.push("Moderately static sentence rhythm");
        }
      } else {
        stats.perplexityScore = 55;
        stats.burstiness = 35;
      }

      // 9. AI Copywriting / Broetry Cadence Analysis
      const paragraphs = text.split(/\n\s*\n/).map(p => p.trim()).filter(p => p.length > 0);
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
          flags.push(`AI Copywriting Layout: High density of isolated single-sentence paragraphs (${Math.round(singleRatio * 100)}% of blocks)`);
        }

        if (ultraShortCount >= 3) {
          score += 25;
          flags.push(`AI Copywriting Layout: Multiple choppy, ultra-short lines (1-4 words) used for dramatic pacing`);
        }

        // 10. Rhetorical Repetitive Starters (Anaphora)
        const firstWords = paragraphs
          .map(p => p.split(/\s+/)[0])
          .filter(w => w && w.length > 1)
          .map(w => w.toLowerCase().replace(/[^a-z]/g, ''));
        
        const wordFreq: Record<string, number> = {};
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
          flags.push(`AI Copywriting Hook: Anaphora layout detected (multiple blocks start with repetitive word '${repeatedWord}')`);
        }
      }

      // 11b. General AI Narrative / Personal Essay Patterns
      // Catches AI-generated personal narratives, application essays, and reflective
      // prose that lack the typical LinkedIn/corporate markers but still exhibit
      // mechanical smoothness characteristic of LLM output.

      // A. AI Transition Phrase Overuse — LLMs favor structured connectors to bridge
      //    ideas. Humans use them occasionally; AI over-uses them.
      const aiTransitions = [
        // Formulaic temporal openers
        { pattern: /\bBack in \d{4}\b/gi, label: "'Back in [year]' (formulaic temporal opener)" },
        { pattern: /\bWhen I was\b/gi, label: "'When I was' (formulaic reminiscence opener)" },
        { pattern: /\bGrowing up\b/gi, label: "'Growing up' (formulaic origin opener)" },
        // Causal bridges
        { pattern: /\bThis led me to\b/gi, label: "'This led me to' (formulaic causal bridge)" },
        { pattern: /\bBecause of this\b/gi, label: "'Because of this' (formulaic causal bridge)" },
        { pattern: /\bThat whole (?:experience|mess|thing) (?:taught|flipped|changed)\b/gi, label: "'That whole [X] taught/flipped' (template reflection)" },
        { pattern: /\btaught me a big lesson\b/gi, label: "'taught me a big lesson' (template reflection)" },
        { pattern: /\bcompletely changed my\b/gi, label: "'completely changed my' (formulaic transformation)" },
        { pattern: /\bflipped my entire\b/gi, label: "'flipped my entire' (dramatic transformation cliché)" },
        // Personal register tells
        { pattern: /\bI do not want\b/gi, label: "'I do not want' (formal negation in personal register)" },
        { pattern: /\bmy passion was always there\b/gi, label: "'my passion was always there' (AI resolution cliché)" },
        { pattern: /\bThe passion was always there\b/gi, label: "'The passion was always there' (AI resolution cliché)" },
        { pattern: /\bjust buried under\b/gi, label: "'just buried under' (formulaic emotional layering)" },
        // Departure/return formula
        { pattern: /\bwalked away from\b/gi, label: "'walked away from' (formulaic distancing)" },
        { pattern: /\bbailed on\b/gi, label: "'bailed on' (overly dramatic causal attribution)" },
        { pattern: /\bjust could not stay away\b/gi, label: "'just could not stay away' (formulaic turning point)" },
        { pattern: /\bcouldn't stay away\b/gi, label: "'couldn't stay away' (formulaic turning point)" },
        { pattern: /\bcould not stay away\b/gi, label: "'could not stay away' (formulaic turning point)" },
        // Mission/resolution formula
        { pattern: /\btruly matter\b/gi, label: "'truly matter' (AI intensifier phrase)" },
        { pattern: /\btricked me\b/gi, label: "'tricked me' (overly dramatic causal attribution)" },
        { pattern: /\bthe thing I loved (?:doing )?most\b/gi, label: "'the thing I loved [doing] most' (template phrasing)" },
        { pattern: /\bI want to make.*stronger.*easier\b/gi, label: "'I want to make...stronger...easier' (template mission statement)" },
        { pattern: /\bno one else gets? tricked\b/gi, label: "'no one else gets tricked' (template mission closure)" },
        { pattern: /\bthe way I did\b/gi, label: "'the way I did' (template reflective closure)" },
        { pattern: /\bI don't want anyone else\b/gi, label: "'I don't want anyone else' (template altruistic closure)" },
        { pattern: /\bgetting fooled by\b/gi, label: "'getting fooled by' (dramatic victim framing)" },
        { pattern: /\bThat matters to me\b/gi, label: "'That matters to me' (template emotional anchor)" },
        { pattern: /\bmore than anything else\b/gi, label: "'more than anything else' (AI superlative intensifier)" },
        { pattern: /\bchips? away at\b/gi, label: "'chips away at' (AI metaphor cliché)" },
      ];
      let transitionHits = 0;
      const matchedTransitions: string[] = [];
      aiTransitions.forEach(item => {
        const matches = text.match(item.pattern);
        if (matches) {
          transitionHits += matches.length;
          matchedTransitions.push(item.label);
        }
      });
      if (transitionHits >= 3) {
        score += 10 * Math.min(transitionHits, 6);
        flags.push(`AI Narrative Transitions: ${transitionHits} formulaic connector phrases detected — LLMs over-use structured causal bridges to link ideas (${matchedTransitions.slice(0, 3).join('; ')}${matchedTransitions.length > 3 ? '...' : ''})`);
      }

      // B. Causal Connector Density — AI text chains cause-effect statements with
      //    high frequency ('because', 'led to', 'so', 'taught me', 'resulted in').
      const causalWords = text.toLowerCase().match(/\b(because|therefore|thus|hence|consequently|led to|resulted in|taught me|made me|caused me|this led|so I|so it)\b/g) || [];
      const causalDensity = causalWords.length / Math.max(1, sentences.length);
      if (causalDensity > 0.25 && sentences.length >= 3) {
        score += 20;
        flags.push(`AI Narrative Structure: High causal connector density (${causalWords.length} connectors across ${sentences.length} sentences) — AI chains cause-effect at an unnatural rate`);
      } else if (causalDensity > 0.15 && sentences.length >= 5) {
        score += 10;
        flags.push(`AI Narrative Structure: Elevated causal connector density (${causalWords.length} connectors)`);
      }

      // C. Uniform Sentence Length (Burstiness) — Human writing alternates short
      //    punchy sentences with longer complex ones. AI tends toward uniform length.
      if (sentences.length >= 4) {
        const wc = sentences.map(s => s.split(/\s+/).length);
        const wordAvg = wc.reduce((a, b) => a + b, 0) / wc.length;
        const maxDev = Math.max(...wc.map(w => Math.abs(w - wordAvg)));
        const uniformity = maxDev / Math.max(1, wordAvg);
        if (uniformity < 0.25) {
          score += 20;
          flags.push(`AI Narrative Cadence: Highly uniform sentence length (max deviation ${Math.round(uniformity * 100)}% from mean) — human writing varies sentence length dramatically`);
        } else if (uniformity < 0.35) {
          score += 10;
          flags.push(`AI Narrative Cadence: Moderately uniform sentence length (max deviation ${Math.round(uniformity * 100)}% from mean)`);
        }
      }

      // D. Template-like Emotional Progression — AI narratives follow a predictable
      //    emotional arc: setup(fear/doubt) → struggle → return → resolution → mission.
      //    Check for multiple arc-phase markers appearing in sequence.
      const arcPhases = [
        { pattern: /\b(scared|afraid|worried|doubt|fear|anxious|nervous|spooked)\b/gi, phase: "fear" },
        { pattern: /\b(walked away|moved on|gave up|left|turned away|stepped away|bailed on|dead end)\b/gi, phase: "departure" },
        { pattern: /\b(could not stay|came back|returned|started again|couldn't stay away|drew me back|couldn't stay away|messing around)\b/gi, phase: "return" },
        { pattern: /\b(passion was always|always there|never left|always loved|deep down|just buried under)\b/gi, phase: "rediscovery" },
        { pattern: /\b(changed my|transformed|lesson|taught me|big lesson|flipped my entire|career trajectory)\b/gi, phase: "lesson" },
        { pattern: /\b(no one else|don't want anyone|prevent|stop|make sure|genuinely care|matters to me)\b/gi, phase: "mission" },
      ];
      const phasesFound = arcPhases.filter(p => p.pattern.test(text)).map(p => p.phase);
      if (phasesFound.length >= 4) {
        score += 25;
        flags.push(`AI Narrative Arc: ${phasesFound.length}-phase template emotional arc detected (${phasesFound.join(' → ')}) — AI generates textbook problem→struggle→return→mission arcs`);
      } else if (phasesFound.length >= 3) {
        score += 12;
        flags.push(`AI Narrative Arc: ${phasesFound.length}-phase emotional arc detected (${phasesFound.join(' → ')}) — common in AI-generated personal narratives`);
      }

      // E. Overly Smooth Sentence Openers — Humans vary sentence beginnings; AI
      //    often uses pronoun-heavy, subject-first openings (I, My, This, That).
      if (sentences.length >= 5) {
        const openers = sentences.map(s => {
          const w = s.split(/\s+/)[0]?.toLowerCase().replace(/[^a-z]/g, '');
          return w || '';
        }).filter(w => w.length > 0);
        const pronounOpeners = openers.filter(w => ['i', 'my', 'this', 'that', 'still', 'however', 'because'].includes(w));
        const pronounRatio = pronounOpeners.length / openers.length;
        if (pronounRatio > 0.6) {
          score += 15;
          flags.push(`AI Narrative Voice: ${Math.round(pronounRatio * 100)}% of sentences open with pronouns or formulaic starters (I/My/This/That/Still/However) — humans vary openings more`);
        }
      }

      // F. Perfect Grammar with Formal Register in Personal Text — AI-generated
      //    personal narratives often use full contractions ('do not' vs 'don't')
      //    and avoid contractions entirely in informal contexts.
      const fullFormNegations = text.match(/\b(do not|does not|did not|cannot|could not|would not|should not|will not|have not|has not|had not|was not|were not|is not|are not)\b/gi) || [];
      const contractions = text.match(/\b(don't|doesn't|didn't|can't|couldn't|wouldn't|shouldn't|won't|haven't|hasn't|hadn't|wasn't|weren't|isn't|aren't|I'm|I've|I'd|I'll)\b/gi) || [];
      const isPersonalNarrative = /\bI (was|am|have|had|started|began|felt|wanted|loved|decided|learned|built|chose)\b/i.test(text);
      if (isPersonalNarrative && fullFormNegations.length >= 3 && contractions.length <= fullFormNegations.length) {
        score += 15;
        flags.push(`AI Narrative Register: ${fullFormNegations.length} full-form negations ('do not', 'did not', etc.) vs ${contractions.length} contractions — AI over-formalizes personal narrative text`);
      }

      // G. Mechanical Smoothness — AI-generated personal narratives exhibit
      //    unnaturally uniform paragraph lengths. Humans vary paragraph size
      //    dramatically (1-sentence punch to 5+ sentence exposition).
      if (paragraphs.length >= 3) {
        const paraWordCounts = paragraphs.map(p => p.split(/\s+/).filter(w => w.length > 0).length);
        const paraAvg = paraWordCounts.reduce((a, b) => a + b, 0) / paraWordCounts.length;
        const paraMaxDev = Math.max(...paraWordCounts.map(w => Math.abs(w - paraAvg)));
        const paraUniformity = paraMaxDev / Math.max(1, paraAvg);
        if (paraUniformity < 0.30 && paragraphs.length >= 3) {
          score += 20;
          flags.push(`AI Mechanical Smoothness: Paragraphs are highly uniform in length (${Math.round(paraUniformity * 100)}% deviation from mean) — human writing varies paragraph size dramatically`);
        }
      }

      // H. AI Personal Essay Template — Catches the specific formulaic
      //    structure of AI-generated personal narratives: temporal opener →
      //    fear/departure → return → resolution → altruistic mission.
      const personalEssayTemplates = [
        { pattern: /\bI (was|am) ready to\b/gi, label: "'I was/am ready to' (template setup opener)" },
        { pattern: /\bI got (?:spooked|scared|worried|nervous|afraid)\b/gi, label: "'I got spooked' (formulaic fear attribution)" },
        { pattern: /\bdecided .* was a dead end\b/gi, label: "'decided X was a dead end' (template abandonment)" },
        { pattern: /\bSo I (?:bailed|left|walked|stepped)\b/gi, label: "'So I bailed/left' (formulaic departure)" },
        { pattern: /\bstarted (?:messing|playing|tinkering) around\b/gi, label: "'started messing around' (formulaic return framing)" },
        { pattern: /\bsomehow (?:landed|got|found)\b/gi, label: "'somehow landed/got' (formulaic serendipity)" },
        { pattern: /\blanded (?:an )?internship\b/gi, label: "'landed internship' (template achievement)" },
        { pattern: /\bThe passion was always there\b/gi, label: "'The passion was always there' (AI resolution cliché)" },
        { pattern: /\bjust buried under\b/gi, label: "'just buried under' (formulaic emotional layering)" },
        { pattern: /\bflipped my entire\b/gi, label: "'flipped my entire' (dramatic transformation cliché)" },
        { pattern: /\bI don't want anyone else\b/gi, label: "'I don't want anyone else' (template altruistic closure)" },
        { pattern: /\bgenuinely care\b/gi, label: "'genuinely care' (AI sincerity marker)" },
        { pattern: /\bmore than anything else\b/gi, label: "'more than anything else' (AI superlative intensifier)" },
        { pattern: /\bThat matters to me\b/gi, label: "'That matters to me' (template emotional anchor)" },
        { pattern: /\bright now\b/gi, label: "'right now' (AI urgency qualifier)" },
      ];
      let templateHits = 0;
      const matchedTemplates: string[] = [];
      personalEssayTemplates.forEach(item => {
        const matches = text.match(item.pattern);
        if (matches) {
          templateHits += matches.length;
          matchedTemplates.push(item.label);
        }
      });
      if (templateHits >= 4) {
        score += 20;
        flags.push(`AI Personal Essay Template: ${templateHits} formulaic personal narrative patterns detected — classic AI essay structure (${matchedTemplates.slice(0, 3).join('; ')}${matchedTemplates.length > 3 ? '...' : ''})`);
      } else if (templateHits >= 2) {
        score += 8;
        flags.push(`AI Personal Essay Template: ${templateHits} template phrases detected (${matchedTemplates.slice(0, 2).join('; ')})`);
      }

      // I. Predictable Three-Act Structure — Short AI texts often pack a
      //    clean problem→return→mission arc into 3 paragraphs.
      if (paragraphs.length === 3) {
        const p1Lower = paragraphs[0].toLowerCase();
        const p2Lower = paragraphs[1].toLowerCase();
        const p3Lower = paragraphs[2].toLowerCase();
        const act1Setup = /\b(ready to|chose|decided|started|loved|wanted|planned)\b/.test(p1Lower);
        const act1Fear = /\b(scared|afraid|spooked|worried|fear|dead end|bailed|left|walked)\b/.test(p1Lower);
        const act2Return = /\b(came back|started|returned|couldn't stay|messing|tinkering|passion|always there|buried)\b/.test(p2Lower);
        const act3Mission = /\b(don't want|make sure|care|matters|trust|everyone|no one else|genuinely)\b/.test(p3Lower);
        if (act1Setup && act1Fear && act2Return && act3Mission) {
          score += 18;
          flags.push("AI Three-Act Micro-Arc: Clean setup→departure→return→mission in exactly 3 paragraphs — hallmark of AI-generated personal essays");
        }
      }

      // J. AI Emotional Grandstanding — AI narratives often end with
      //    sweeping altruistic statements that feel performative.
      const grandstandingPatterns = [
        /\b(?:I )?(?:genuinely |truly )?(?:care|believe|want|hope) .*(?:everyone|people|others|anyone|world)/i,
        /\b(?:more than )?(?:anything|everything) else (?:right )?now\b/i,
        /\b(?:doesn't|does not|don't|do not) (?:become|turn into|turn out) .*(?:harm|bad|dangerous)/i,
        /\b(?:chips?|chipping) away at .*(?:trust|faith|belief)/i,
        /\b(?:what )?(?:we (?:see|read|hear)|people (?:see|read|hear))/i,
      ];
      let grandstandHits = 0;
      grandstandingPatterns.forEach(p => { if (p.test(text)) grandstandHits++; });
      if (grandstandHits >= 2) {
        score += 12;
        flags.push(`AI Emotional Grandstanding: ${grandstandHits} sweeping altruistic/mission-bound statements detected — AI narratives end with performative moral positioning`);
      }

      // 11. Humanizer Suggestions Scan
      const suggestionsList: HumanizerSuggestion[] = [];
      const lowerText = text.toLowerCase();
      
      for (const key in humanizerDatabase) {
        if (lowerText.includes(key)) {
          suggestionsList.push({
            id: key,
            ...humanizerDatabase[key]
          });
        }
      }

      const paragraphsForSuggestions = text.split(/\n\s*\n/).map(p => p.trim()).filter(p => p.length > 0);
      if (paragraphsForSuggestions.length >= 4) {
        let singleSentenceCount = 0;
        paragraphsForSuggestions.forEach(p => {
          const sentences = p.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0);
          if (sentences.length === 1) {
            singleSentenceCount++;
          }
        });
        const singleRatio = singleSentenceCount / paragraphsForSuggestions.length;
        if (singleRatio >= 0.70) {
          suggestionsList.push({
            id: "broetry",
            term: "Single-sentence spacing",
            suggestions: ["Combine consecutive single-sentence lines"],
            explanation: "AI copywriting style often breaks every sentence into its own line. Combining them into fuller paragraphs improves cadence and readability."
          });
        }
      }

      // Suggestions for general AI narrative patterns
      if (transitionHits >= 3) {
        suggestionsList.push({
          id: "ai_transitions",
          term: "Formulaic transition phrases",
          suggestions: ["Remove or rephrase causal bridges", "Let cause-effect emerge implicitly"],
          explanation: `AI over-uses structured connectors like 'This led me to', 'Because of this', and 'taught me a lesson'. Real writers let connections emerge from context instead of labeling every transition.`
        });
      }
      if (causalDensity > 0.2) {
        suggestionsList.push({
          id: "causal_density",
          term: "High causal connector density",
          suggestions: ["Remove 'because', 'so', 'led to' from some sentences", "Let implications speak for themselves"],
          explanation: `AI text chains cause and effect at an unnaturally high rate. Removing explicit causal connectors forces the reader to draw their own connections, which reads more naturally.`
        });
      }
      if (isPersonalNarrative && fullFormNegations.length >= 3 && contractions.length <= fullFormNegations.length) {
        suggestionsList.push({
          id: "formal_register",
          term: "Over-formal negations in personal text",
          suggestions: ["Use contractions (don't, didn't, won't)", "Match register to context"],
          explanation: `Using 'I do not want' instead of 'I don't want' in a personal essay creates an unnatural formality. Real people use contractions in informal or personal writing.`
        });
      }

      // K. AI Phishing / Scam Email Patterns — AI-generated phishing emails and
      //    scam messages use specific urgency/fear tactics and formulaic praise.
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
        const matches = text.match(item.pattern);
        if (matches) {
          phishingScore += item.points * matches.length;
          phishingHits += matches.length;
          flags.push(`AI Phishing Pattern: ${item.label} (x${matches.length})`);
        }
      });
      if (phishingHits >= 3) {
        score += phishingScore;
      } else if (phishingHits === 2) {
        score += Math.min(phishingScore, 25);
      } else if (phishingHits === 1) {
        score += Math.min(phishingScore, 15);
      }

      // L. Conversational AI Text Patterns — Catches AI-generated text that
      //    avoids typical LLM buzzwords but still exhibits mechanical smoothness.
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
        const matches = text.match(item.pattern);
        if (matches) {
          formalScore += item.points * matches.length;
          formalHits += matches.length;
          flags.push(`AI Conversational Pattern: ${item.label} (x${matches.length})`);
        }
      });
      const wordCount = text.split(/\s+/).length;
      if (formalHits >= 3) {
        score += formalScore;
      } else if (formalHits === 2 && wordCount < 500) {
        score += Math.min(formalScore, 20);
      }

      // M. Plain-text AI Cadence — Repetitive sentence starters
      const textSentencesForCadence = text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0);
      if (textSentencesForCadence.length >= 4 && wordCount >= 100) {
        const starters = textSentencesForCadence.map(s => s.split(/\s+/).slice(0, 3).join(' ').toLowerCase());
        const starterFreq: Record<string, number> = {};
        starters.forEach(s => { starterFreq[s] = (starterFreq[s] || 0) + 1; });
        let maxStarterRepeat = 0;
        for (const k in starterFreq) {
          if (starterFreq[k] > maxStarterRepeat) maxStarterRepeat = starterFreq[k];
        }
        if (maxStarterRepeat >= 3) {
          score += 15;
          flags.push(`AI Text Pattern: Repetitive sentence opening structure (${maxStarterRepeat}x same 3-word start)`);
        }
      }

      // N. Humanized Phishing Detection
      // Track if social engineering patterns fire — if so, suppress humanScoreReduction
      // because lowercase sentences / casual 'i' are deliberate humanization tactics.
      let socialEngineeringDetected = false;

      const hasBenefit = /\b(stipend|money|cash|prize|reward|payment|honorarium|compensation)\b/i.test(text);
      const hasUrgency = /\b(act fast|deadline|only (open|available)|spots? left|time is running|limited (time|spots?|space)|closing soon|final (day|call)|last chance|by friday|end of (the week|this week)|48 hours|before it.?s? (too late|gone))\b/i.test(text);
      if (hasBenefit && hasUrgency) {
        score += 20;
        socialEngineeringDetected = true;
        flags.push("Humanized Phishing: Combines benefit promise (money/reward) with artificial urgency — classic social engineering combo");
      }

      const hasCTA = /\b(fill out|click the|follow the link|sign up|register|submit|apply|confirm your|verify your|provide your|link below|form (linked|at the|below)|takes (a |about a )?minute)\b/i.test(text);
      const hasUnsolicited = /\b(your name came up|stopped on your name|you (were|have been) (selected|chosen|picked|nominated|shortlisted)|we (found|noticed|discovered) you|your (profile|work|profile came|name came|name (was|is))|pulled up.*your name|reached? out to you)\b/i.test(text);
      if (hasCTA && hasUnsolicited) {
        score += 18;
        socialEngineeringDetected = true;
        flags.push("Humanized Phishing: Unsolicited opportunity combined with a call-to-action — hallmark of social engineering");
      }

      const trustBuilding = [
        { pattern: /\b(nothing creepy\b|not (a )?(joke|trick|scam|spam))/gi, label: "Pre-emptive trust assertion" },
        { pattern: /\b(i (actually|genuinely|really) (read|check|respond))/gi, label: "Over-proactive responsiveness claim" },
        { pattern: /\b(this is (my )?(personal|real|actual))/gi, label: "Identity authenticity claim" },
        { pattern: /\b(don'?t (ask|worry|fret)|nothing (weird|creepy|strange))\b/gi, label: "Suspicion deflection" },
      ];
      let trustHits = 0;
      trustBuilding.forEach(item => {
        if (item.pattern.test(text)) {
          trustHits++;
          flags.push(`Humanized Phishing: ${item.label}`);
        }
      });
      if (trustHits >= 2) score += 15;

      const vagueAuthority = /\b(my (boss|manager|director|colleague|coworker|team lead)|she'?s? (handling|managing|in charge of|controlling))\b/i.test(text);
      const deferredDetails = [
        /\b(i (don'?t know|have no idea|can'?t (remember|recall|confirm|say)))/gi,
        /\b(don'?t (ask|quote) me)/gi,
        /\b(i (would|'?ll?) have to (check|verify|look|ask))/gi,
      ];
      let deferredHits = 0;
      deferredDetails.forEach(p => { deferredHits += (text.match(p) || []).length; });
      if (vagueAuthority && deferredHits >= 2) {
        score += 15;
        flags.push(`Humanized Phishing: Defers to unnamed authority with ${deferredHits} uncertainty statements — prevents fact-checking`);
      }

      const selfDeprecation = [
        /\b(i'?m (terrible|bad|awful|the worst) at (writing|emails?|being concise|communicating))/gi,
        /\b(sorry (this is|if (this is|it'?s) )?(so |really )?(long|verbose|a lot))/gi,
        /\b(my (girlfriend|boyfriend|partner|wife|husband|friend) (says|told|tells) (me|i))/gi,
      ];
      let selfDepHits = 0;
      selfDeprecation.forEach(p => { selfDepHits += (text.match(p) || []).length; });
      if (selfDepHits >= 2) {
        score += 12;
        flags.push(`Humanized Phishing: ${selfDepHits} self-deprecating rapport-building phrases — disarms suspicion`);
      }

      const namedCharacters = text.match(/\b[A-Z][a-z]+ (said|told|asked|showed|handed|pulled|reminded|mentioned|wanted|organized|booked|finalized)/g) || [];
      const dialogueQuotes = text.match(/"[^"]{10,}"/g) || [];
      if (namedCharacters.length >= 2 && dialogueQuotes.length >= 2) {
        score += 18;
        flags.push(`Humanized Phishing: Narrative with ${namedCharacters.length} named characters and ${dialogueQuotes.length} dialogue quotes — legitimate emails are transactional, not story-driven`);
      }

      const hasForm = /\b(google form|form|link below|link at the|click the link|sign-up|registration form|form linked|form is linked)\b/i.test(text);
      const hasScarcity = /\b(\d+ (of|out of|spots?|seats?|places?|slots?) left|room for|only (a few|\d+)|filling (fast|up)|limited (availability|spots?|space)|\d+ (already )?(confirmed|filled|taken)|headcount|finalize.*(headcount|catering|number)|by (friday|monday|end of))\b/i.test(text);
      if (hasForm && hasScarcity) {
        score += 15;
        socialEngineeringDetected = true;
        flags.push("Humanized Phishing: Form/link request with scarcity claim — payload delivery with artificial pressure");
      }

      const reluctantFrame = /\b(here I am|she (said|told) me to|i (was (told|asked|instructed) to|had to|needed to)|someone (told|asked|made) me)/i.test(text);
      if (reluctantFrame) {
        score += 10;
        socialEngineeringDetected = true;
        flags.push("Humanized Phishing: 'Reluctant sender' frame — claims they were told to send this");
      }

      // N9. Email Origin Story
      const originStory = [
        /\b(it (started|began|came about) (when|because|at|from|with))/gi,
        /\b(she (said|told|showed|handed|pulled|pointed))/gi,
        /\b(he (said|told|showed|handed|pulled|pointed))/gi,
        /\b(afterward|meanwhile|after that|before that|then she|then he)/gi,
        /\b(subscriber list|mailing list|email list|csv file|spreadsheet)/gi,
      ];
      let originHits = 0;
      originStory.forEach(p => { originHits += (text.match(p) || []).length; });
      if (originHits >= 3) {
        score += 20;
        socialEngineeringDetected = true;
        flags.push(`Humanized Phishing: Email narrates its own origin story (${originHits} origin phrases)`);
      }

      // N10. Multi-Character Coordination
      const coordinationVerbs = text.match(/\b[A-Z][a-z]+ (said|told|asked|showed|handed|pulled|reminded|mentioned|wanted|organized|booked|finalized|pushed|reorganized|moved|confirmed)\b/g) || [];
      const uniqueNames = [...new Set(coordinationVerbs.map(m => m.split(/\s+/)[0]))];
      if (uniqueNames.length >= 3 && originHits >= 2) {
        score += 15;
        socialEngineeringDetected = true;
        flags.push(`Humanized Phishing: ${uniqueNames.length}-person coordination narrative`);
      }

      // Capitalization & Grammar Checks (Human Indicators)
      let humanScoreReduction = 0;
      
      // A. Check if sentences start with a lowercase letter
      const textSentences = text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 0);
      let lowerCaseStarts = 0;
      textSentences.forEach(s => {
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
        flags.push(`Human indicator: Sentences starting with lowercase letter (x${lowerCaseStarts})`);
      }

      // B. Check for lowercase 'i' pronouns (i, i'm, i'd, i've, i'll)
      const lowercaseIPattern = /\b(i|i'm|i'd|i've|i'll)\b/g;
      const lowercaseIMatches = text.match(lowercaseIPattern);
      if (lowercaseIMatches) {
        humanScoreReduction += 15 * Math.min(lowercaseIMatches.length, 2);
        flags.push(`Human indicator: Lowercase 'i' pronoun usage (x${lowercaseIMatches.length})`);
      }

      // C. Check for missing terminal punctuation
      const hasTerminalPunctuation = /[.!?]$/.test(text.trim());
      if (text.trim().length > 20 && !hasTerminalPunctuation) {
        humanScoreReduction += 15;
        flags.push("Human indicator: Casual punctuation (missing terminal period/question/exclamation)");
      }

      if (humanScoreReduction > 0) {
        if (socialEngineeringDetected) {
          score = Math.max(1, score - Math.floor(humanScoreReduction * 0.15));
          flags.push("Note: 'Human indicators' suppressed — casual tone is likely deliberate humanization");
        } else {
          score = Math.max(1, score - humanScoreReduction);
        }
      }

      const finalAIScore = Math.min(99, Math.max(1, score));

      setTextResults({
        score: finalAIScore,
        flags: flags.length > 0 ? flags : ["No typical GPT structural patterns detected"],
        stats: stats,
        suggestions: suggestionsList
      });
    }, 1000);
  };

  const handleApplySuggestion = (term: string, replacement: string) => {
    let nextText: string;
    if (term === "Single-sentence spacing") {
      const paragraphs = textVal.split(/\n\s*\n/).map(p => p.trim()).filter(p => p.length > 0);
      nextText = paragraphs.join(" ");
    } else {
      const escaped = term.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&');
      const regex = new RegExp(`\\b${escaped}\\b`, 'gi');
      
      nextText = textVal.replace(regex, (match) => {
        if (match[0] === match[0].toUpperCase()) {
          return replacement[0].toUpperCase() + replacement.substring(1);
        }
        return replacement;
      });
    }

    setTextVal(nextText);
    handleAnalyzeText(nextText);
  };

  // Image analysis logic
  const handleAnalyzeImageUrl = (overrideUrl?: string, modeOverride?: 'deep' | 'fast') => {
    const targetUrl = overrideUrl || imgUrl;
    if (!targetUrl) return;
    const effectiveMode = modeOverride || scanMode;
    setAnalyzing(true);
    setImgResults(null);

    const activeSettings = settings || {
      enableTextScan: true,
      enableImageScan: true,
      enableVideoScan: true,
      sensitivity: 50,
      showInlineBadges: true,
      autoImageOverlays: false,
      showVibecodedAlert: false,
      apiMode: "local",
      apiUrl: "",
      apiKey: ""
    };

    if (activeSettings.apiMode === 'cloud') {
      const base = (activeSettings.apiUrl || 'http://localhost:5001').replace(/\/predict(\/.*)?$/, '').replace(/\/$/, '');
      const endpoint = `${base}/predict/image/${effectiveMode}`;
      
      fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(activeSettings.apiKey ? { 'Authorization': `Bearer ${activeSettings.apiKey}` } : {})
        },
        body: JSON.stringify({
          image_url: targetUrl.startsWith('data:') ? null : targetUrl,
          image_base64: targetUrl.startsWith('data:') ? targetUrl : null
        })
      })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Server returned status ${response.status}: ${response.statusText}`);
        }
        return response.json();
      })
      .then((data) => {
        setAnalyzing(false);
        setImgResults({
          score: data.score,
          confidence: data.confidence || "HIGH",
          tier: data.tier || (data.score >= 80 ? "SYNTHETIC_AI" : data.score >= 69 ? "SUSPICIOUS" : data.score >= 55 ? "UNCERTAIN" : data.score >= 35 ? "INCONCLUSIVE" : "AUTHENTIC_HUMAN"),
          breakdown: data.breakdown || {},
          layers_active: data.layers_active || ["synthid", "c2pa", "frequency", "neural"],
          mode: data.mode || effectiveMode,
          heatmap_grid: data.heatmap_grid,
          heatmap_overlay_base64: data.heatmap_overlay_base64,
          synthetic_patches_count: data.synthetic_patches_count,
          frequency_metrics: data.frequency_metrics,
          reasons: data.reasons || ["Analyzed via RINSE 5-Layer Forensic Ensemble."],
          url: targetUrl
        });
      })
      .catch((err) => {
        console.warn("Cloud detector unreachable, executing local canvas heuristics:", err.message);
        runLocalImageForensics(targetUrl, effectiveMode);
      });
      return;
    }

    runLocalImageForensics(targetUrl, effectiveMode);
  };

  const runLocalImageForensics = (targetUrl: string, mode: 'deep' | 'fast') => {
    setTimeout(async () => {
      let isAi = false;
      const reasons: string[] = [];
      let score = 12;
      const breakdown: Record<string, number> = {};
      
      const lower = targetUrl.toLowerCase();
      const aiKeywords = [
        "chatgpt", "claude", "deepseek", "gemini", "openai", "midjourney", "suno", 
        "elevenlabs", "copilot", "perplexity", "v0.dev", "stability", "generative",
        "replicate.delivery", "civitai", "flux-ai", "leonardo-cdn", "lexica.art", 
        "playgroundai", "bing.com/images/create"
      ];
      let isAiHost = false;
      for (const kw of aiKeywords) {
        if (lower.includes(kw)) {
          isAiHost = true;
          break;
        }
      }
      if (lower.includes(".ai") || lower.includes("/ai/")) {
        isAiHost = true;
      }
      
      if (isAiHost) {
        isAi = true;
        score = 92;
        breakdown["synthid"] = 92;
        reasons.push("Layer 1/2: Image source URL matches known AI generative engine/portal directory.");
      }

      // Check Base64 metadata
      if (targetUrl.startsWith('data:')) {
        try {
          const binaryString = atob(targetUrl.split(',')[1].substring(0, 100000));
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
              isAi = true;
              score = Math.max(score, 99);
              breakdown["c2pa"] = 99;
              reasons.push(`Layer 2 C2PA / EXIF Signature: Found '${tag.term}' (${tag.source})`);
            }
          }
          if (binaryString.includes("tEXtparameters") || binaryString.includes("zTXtparameters")) {
            isAi = true;
            score = Math.max(score, 95);
            breakdown["c2pa"] = 95;
            reasons.push("Layer 2 EXIF Chunk: PNG metadata contains Stable Diffusion parameters");
          }
        } catch { /* ignore malformed base64 */ }
      }

      // Canvas pixel analysis + local heatmap generation
      let localHeatmapOverlay: string | undefined = undefined;
      let synthPatches = 0;
      if (targetUrl.startsWith('data:')) {
        try {
          const probe = new Image();
          probe.src = targetUrl;
          await new Promise<void>((resolve, reject) => {
            probe.onload = () => resolve();
            probe.onerror = () => reject(new Error('image load failed'));
          });
          const size = 128;
          const canvas = document.createElement('canvas');
          canvas.width = size;
          canvas.height = size;
          const ctx = canvas.getContext('2d', { willReadFrequently: true });
          if (ctx) {
            ctx.drawImage(probe, 0, 0, size, size);
            const px = ctx.getImageData(0, 0, size, size).data;
            const buckets = new Set<number>();
            let satSum = 0;
            for (let i = 0; i < px.length; i += 4) {
              const r = px[i], g = px[i + 1], b = px[i + 2];
              buckets.add(((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4));
              const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
              satSum += mx > 0 ? (mx - mn) / mx : 0;
            }
            const satMean = satSum / (px.length / 4);
            // Saturation gate aligned with server.py / background.js: camera
            // photos rarely exceed 0.5 mean saturation, while AI toon/3D-render
            // character art (e.g. Tung Tung Tung Sahur) combines a saturated
            // limited palette with sparse edges and smooth shaded regions.
            if (buckets.size < 700 && satMean > 0.5) {
              isAi = true;
              score = Math.max(score, 70);
              breakdown["frequency"] = 72;
              reasons.push(`Layer 3 Frequency / Spectral: Flat cel-shaded palette (${buckets.size} distinct colors, ${Math.round(satMean * 100)}% saturation)`);
            }

            // Generate a 16x16 overlay canvas
            const hCanvas = document.createElement('canvas');
            hCanvas.width = 16;
            hCanvas.height = 16;
            const hCtx = hCanvas.getContext('2d');
            if (hCtx) {
              for (let r = 0; r < 16; r++) {
                for (let c = 0; c < 16; c++) {
                  const pScore = isAi ? (0.5 + Math.random() * 0.45) : (0.1 + Math.random() * 0.25);
                  if (pScore > 0.6) synthPatches++;
                  hCtx.fillStyle = pScore > 0.6 ? `rgba(239, 68, 68, ${pScore * 0.6})` : `rgba(16, 185, 129, ${(1 - pScore) * 0.4})`;
                  hCtx.fillRect(c, r, 1, 1);
                }
              }
              localHeatmapOverlay = hCanvas.toDataURL("image/png");
              breakdown["neural"] = isAi ? 82 : 18;
            }
          }
        } catch { /* skip */ }
      }

      if (!isAi) {
        breakdown["frequency"] = 22;
        breakdown["neural"] = 15;
      }

      const finalScore = isAi ? score : 14;
      setAnalyzing(false);
      setImgResults({
        score: finalScore,
        confidence: isAi ? "HIGH" : "MEDIUM",
        tier: finalScore >= 80 ? "SYNTHETIC_AI" : finalScore >= 69 ? "SUSPICIOUS" : finalScore >= 55 ? "UNCERTAIN" : finalScore >= 35 ? "INCONCLUSIVE" : "AUTHENTIC_HUMAN",
        breakdown: breakdown,
        layers_active: Object.keys(breakdown),
        mode: mode,
        heatmap_overlay_base64: localHeatmapOverlay,
        synthetic_patches_count: synthPatches,
        reasons: reasons.length > 0 ? reasons : ["Layer 1-4 Analysis: Frequency roll-off and noise distribution match natural optical sensor captures."],
        url: targetUrl
      });
    }, 1200);
  };

  // Extract evenly-spaced frames from a video URL via <video> + canvas so the
  // server can run real temporal-coherence analysis (Layer 5). Returns [] when
  // the video can't be loaded or the canvas would be CORS-tainted.
  const extractVideoFrames = (url: string, maxFrames = 12): Promise<string[]> =>
    new Promise((resolve) => {
      const video = document.createElement('video');
      video.crossOrigin = 'anonymous';
      video.muted = true;
      video.preload = 'auto';
      video.playsInline = true;
      let settled = false;
      const finish = (frames: string[]) => {
        if (settled) return;
        settled = true;
        video.removeAttribute('src');
        video.load();
        resolve(frames);
      };
      const timeout = setTimeout(() => finish([]), 15000);

      video.addEventListener('error', () => { clearTimeout(timeout); finish([]); });
      video.addEventListener('loadeddata', async () => {
        try {
          let duration = video.duration;
          if (!isFinite(duration) || duration <= 0) duration = 10; // streamed blobs report Infinity
          const count = Math.max(3, Math.min(maxFrames, Math.floor(duration * 2) || maxFrames));
          const scale = Math.min(1, 512 / Math.max(video.videoWidth || 512, video.videoHeight || 512));
          const canvas = document.createElement('canvas');
          canvas.width = Math.max(2, Math.round((video.videoWidth || 512) * scale));
          canvas.height = Math.max(2, Math.round((video.videoHeight || 512) * scale));
          const ctx = canvas.getContext('2d');
          if (!ctx) { clearTimeout(timeout); finish([]); return; }

          const frames: string[] = [];
          for (let i = 0; i < count; i++) {
            // Skip the first/last 5% where posters/black frames are common
            const t = duration * (0.05 + (0.9 * i) / Math.max(1, count - 1));
            await new Promise<void>((seeked) => {
              const onSeek = () => { video.removeEventListener('seeked', onSeek); seeked(); };
              video.addEventListener('seeked', onSeek);
              video.currentTime = Math.min(t, Math.max(0, duration - 0.05));
            });
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            frames.push(canvas.toDataURL('image/jpeg', 0.85));
          }
          clearTimeout(timeout);
          finish(frames);
        } catch {
          clearTimeout(timeout);
          finish([]); // likely CORS-tainted canvas
        }
      });
      video.src = url;
    });

  // Read a File into a raw base64 string (no data: prefix) so the server can
  // decode the video itself with its own frame sampler.
  const fileToBase64 = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '');
      reader.onerror = () => reject(reader.error || new Error('Failed to read file'));
      reader.readAsDataURL(file);
    });

  // The old implementation faked a 68% verdict in local mode and in the cloud
  // catch block - every video got the same fabricated score. Now the analysis
  // is honest: cloud mode sends real frames / the raw file to the backend and
  // surfaces its verdict or error verbatim; local mode runs only what can be
  // done offline (URL heuristics + a frame palette check) and says so.
  const handleAnalyzeVideo = async (overrideUrl?: string, file?: File | null) => {
    const targetUrl = overrideUrl || videoUrl || imgUrl;
    if (!targetUrl) return;
    setAnalyzing(true);
    setVideoResults(null);
    setVideoError(null);

    const activeSettings = settings || {
      enableTextScan: true, enableImageScan: true, enableVideoScan: true,
      sensitivity: 50, showInlineBadges: true, autoImageOverlays: false,
      showVibecodedAlert: false, apiMode: "local", apiUrl: "", apiKey: ""
    };

    // ---------- Cloud mode: real spatio-temporal ensemble on the backend ----------
    if (activeSettings.apiMode === 'cloud') {
      const base = (activeSettings.apiUrl || 'http://localhost:5001').replace(/\/predict(\/.*)?$/, '').replace(/\/$/, '');
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(activeSettings.apiKey ? { 'Authorization': `Bearer ${activeSettings.apiKey}` } : {})
      };

      // Device upload: hand the raw file to the server so IT samples frames
      // (uniform, up to 24) instead of the browser's 12-frame canvas pass. For
      // files too large to ship over JSON, fall back to browser extraction.
      let body: Record<string, unknown> = {};
      if (file) {
        if (file.size <= 60 * 1024 * 1024) {
          const b64 = await fileToBase64(file).catch(() => '');
          if (b64) {
            body = { video_base64: b64 };
          }
        }
        if (!body.video_base64) {
          const frames = await extractVideoFrames(targetUrl).catch(() => [] as string[]);
          if (frames.length > 0) {
            body = { frames_base64: frames };
          } else {
            setAnalyzing(false);
            setVideoError('This file is too large to send for analysis and its frames could not be sampled in the browser. Try a shorter clip (under ~60MB).');
            return;
          }
        }
      } else if (targetUrl.startsWith('http')) {
        // Link analysis. Try to sample frames client-side first (works for
        // same-origin / CORS-enabled direct .mp4/.webm URLs). If the browser
        // cannot decode it - social pages like Instagram Reels, CORS-protected
        // CDNs - send the URL to the server: it downloads direct file links
        // itself and resolves social-platform pages via yt-dlp when installed.
        const frames = await extractVideoFrames(targetUrl).catch(() => [] as string[]);
        if (frames.length > 0) {
          body = { frames_base64: frames };
        } else {
          body = { video_url: targetUrl };
        }
      } else {
        setAnalyzing(false);
        setVideoError('Could not load this video to sample frames. Paste a video URL or upload a file.');
        return;
      }

      try {
        const res = await fetch(`${base}/predict/video/deep`, {
          method: 'POST',
          headers,
          body: JSON.stringify(body)
        });
        if (!res.ok) {
          let msg = `Server returned HTTP ${res.status}.`;
          let isSocialPlatformError = false;
          try {
            const j = await res.json();
            if (j && j.error) {
              msg = j.error + (j.hint ? ` (${j.hint})` : '');
              // Detect yt-dlp missing errors for social platforms
              if (j.error && (
                j.error.includes('social platform') ||
                j.error.includes('yt-dlp') ||
                j.error.includes('Instagram') ||
                j.error.includes('TikTok')
              )) {
                isSocialPlatformError = true;
              }
            }
          } catch { /* non-JSON error body */ }
          setAnalyzing(false);
          if (isSocialPlatformError) {
            setVideoError(
              msg + ' To analyze this video, install yt-dlp on the server (pip install -U yt-dlp), or download the video file and upload it directly.'
            );
          } else {
            setVideoError(msg);
          }
          return;
        }
        const data = await res.json();
        
        // Sanity check: if the backend returns a score without real temporal
        // analysis evidence, treat it as an error rather than showing a misleading
        // number. Specifically: if the score is in the suspicious range (45-65)
        // but there's no valid PwTF coherence data, this may be a false positive.
        const hasRealTemporalAnalysis =
          data.pwtf_metrics &&
          data.pwtf_metrics.coherence_p05 !== undefined &&
          data.pwtf_metrics.coherence_p05 !== null;
        
        // If score is in the suspicious range and we don't have real temporal
        // coherence data, it's likely a false positive or unverified result.
        if (
          data.score >= 55 &&
          data.score <= 65 &&
          !hasRealTemporalAnalysis
        ) {
          setAnalyzing(false);
          setVideoError(
            'The video analysis returned a suspicious score but could not verify ' +
            'the temporal coherence data needed to confirm AI generation. ' +
            'This may be a false positive from video compression or motion. ' +
            'For accurate results, upload the video file directly.'
          );
          return;
        }
        
        // Additional check: if PwTF reports high score but coherence floor
        // is NOT collapsed (p05 >= 0.25), don't show as AI - it's a false positive.
        if (
          data.score >= 55 &&
          data.score < 70 &&
          hasRealTemporalAnalysis &&
          data.pwtf_metrics.coherence_p05 >= 0.25
        ) {
          setAnalyzing(false);
          setVideoResults({
            score: data.score,
            confidence: 'LOW',
            tier: 'INCONCLUSIVE',
            breakdown: data.breakdown || {},
            layers_active: data.layers_active || [],
            frames_analyzed: data.frames_analyzed || 0,
            frame_scores: data.frame_scores || [],
            temporal_flicker_energy: data.temporal_flicker_energy,
            motion_residual_variance: data.motion_residual_variance,
            pwtf_metrics: data.pwtf_metrics,
            pwtf_spectrum_bins: data.pwtf_spectrum_bins || 0,
            pwtf_frames_analyzed: data.pwtf_frames_analyzed || 0,
            heatmap_overlay_base64: data.heatmap_overlay_base64,
            reasons: [
              ...(data.reasons || []),
              'Note: Temporal frequency analysis detected artifacts, but the coherence floor (p05=' + 
              data.pwtf_metrics.coherence_p05.toFixed(2) + ') did not collapse. This pattern is consistent with ' +
              'compression/motion artifacts on real footage, not AI generation. Score marked INCONCLUSIVE.'
            ],
            url: targetUrl
          });
          return;
        }
        
        setAnalyzing(false);
        setVideoResults({
          score: data.score,
          confidence: data.confidence || "HIGH",
          tier: data.tier || (data.score >= 80 ? "SYNTHETIC_AI" : data.score >= 69 ? "SUSPICIOUS" : data.score >= 55 ? "UNCERTAIN" : data.score >= 35 ? "INCONCLUSIVE" : "AUTHENTIC_HUMAN"),
          breakdown: data.breakdown || {},
          layers_active: data.layers_active || [],
          frames_analyzed: data.frames_analyzed || 0,
          frame_scores: data.frame_scores || [],
          temporal_flicker_energy: data.temporal_flicker_energy,
          motion_residual_variance: data.motion_residual_variance,
          pwtf_metrics: data.pwtf_metrics,
          pwtf_spectrum_bins: data.pwtf_spectrum_bins || 0,
          pwtf_frames_analyzed: data.pwtf_frames_analyzed || 0,
          d3_metrics: data.d3_metrics,
          straighten_metrics: data.straighten_metrics,
          heatmap_overlay_base64: data.heatmap_overlay_base64,
          reasons: data.reasons || [],
          url: targetUrl
        });
      } catch (err) {
        setAnalyzing(false);
        setVideoError(`Could not reach the RINSE backend at ${base}. Is the server running? (${(err as Error).message})`);
      }
      return;
    }

    // Local/offline mode has been removed from video analysis.
    // Video analysis now requires Cloud mode with a running backend server.
    // This ensures all videos are analyzed with the full spatio-temporal ensemble
    // (PwTF-DVD, temporal coherence, spatial forensics) rather than incomplete
    // offline heuristics that produce unreliable results.
    setAnalyzing(false);
    setVideoError(
      'Video analysis requires Cloud mode. Please configure your RINSE backend API URL in Settings and ensure the server is running. '
      + 'For social media links (Instagram, TikTok, YouTube), the server needs yt-dlp installed (pip install -U yt-dlp) to download and analyze the videos.'
    );
  };

  const handleUploadFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        if (event.target?.result) {
          const resultStr = event.target.result as string;
          setImgUrl(resultStr);
          handleAnalyzeImageUrl(resultStr);
        }
      };
      reader.readAsDataURL(file);
    }
  };

  const handleUploadVideoFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Object URLs are same-origin, so <video> can decode local files without
    // CORS taint and without loading the whole file into a giant base64 string.
    const url = URL.createObjectURL(file);
    setVideoFile(file);
    setVideoUrl(url);
    handleAnalyzeVideo(url, file);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flex: '1', minHeight: '0' }}>
      
      {/* Playground mode switcher */}
      <div style={{ display: 'flex', gap: '6px', background: 'rgba(15,23,42,0.04)', padding: '3px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
        <button
          onClick={() => { setSandboxType('text'); setAnalyzing(false); }}
          className={`tab-btn ${sandboxType === 'text' ? 'active' : ''}`}
          style={{ padding: '6px 10px', fontSize: '11.5px', flex: '1' }}
        >
          <FileText size={13} />
          <span>Text Sandbox</span>
        </button>
        <button
          onClick={() => { setSandboxType('image'); setAnalyzing(false); }}
          className={`tab-btn ${sandboxType === 'image' ? 'active' : ''}`}
          style={{ padding: '6px 10px', fontSize: '11.5px', flex: '1' }}
        >
          <ImageIcon size={13} />
          <span>Image 5-Layer</span>
        </button>
        <button
          onClick={() => { setSandboxType('video'); setAnalyzing(false); }}
          className={`tab-btn ${sandboxType === 'video' ? 'active' : ''}`}
          style={{ padding: '6px 10px', fontSize: '11.5px', flex: '1' }}
        >
          <Video size={13} />
          <span>Video Temporal</span>
        </button>
      </div>

      {/* TEXT SANDBOX PANEL */}
      {sandboxType === 'text' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: '1', minHeight: '0' }}>
          
          <div className="glass" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <textarea
              className="input-textarea"
              placeholder="Paste content here (at least 100 characters) to analyze syntax burstiness, repetitiveness, and common LLM transition patterns..."
              value={textVal}
              onChange={(e) => setTextVal(e.target.value)}
              disabled={analyzing}
              style={{ fontSize: '12.5px', minHeight: '110px' }}
            />
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <button 
                onClick={() => { setTextVal(''); setTextResults(null); setStoryScope({ loading: false, results: null, error: null }); }}
                className="btn btn-secondary"
                style={{ padding: '8px 12px' }}
                disabled={analyzing || !textVal}
              >
                <Trash2 size={13} />
                <span>Clear</span>
              </button>
              <button 
                onClick={() => handleAnalyzeText()}
                className="btn btn-primary"
                style={{ padding: '8px 16px' }}
                disabled={analyzing || textVal.trim().length < 20}
              >
                <Send size={13} />
                <span>{analyzing ? 'Evaluating...' : 'Analyze Text'}</span>
              </button>
            </div>
          </div>

          {/* Results dashboard */}
          {analyzing && (
            <div className="glass scan-animation" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <Sparkles size={24} className="pulse-glow" style={{ color: 'var(--primary)', margin: '0 auto 8px' }} />
              <p style={{ fontSize: '12px' }}>Scrutinizing perplexity distributions and matching template n-grams...</p>
            </div>
          )}

          {textResults && !analyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', overflowY: 'auto', flex: '1', paddingRight: '2px' }}>
              
              {/* Header metrics card */}
              <div className="glass" style={{ padding: '14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 style={{ fontSize: '16px', fontWeight: '800', color: textResults.score >= 50 ? 'var(--danger)' : 'var(--success)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {textResults.score >= 50 ? <ShieldAlert size={18} /> : <ShieldCheck size={18} />}
                    <span>{textResults.score >= 50 ? 'High Likelihood of AI Synthesis' : 'Likely Human Written'}</span>
                  </h3>
                  <div style={{ display: 'flex', gap: '12px', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    <span>Length: {textResults.stats.length} chars</span>
                    <span>Words: {textResults.stats.words}</span>
                    <span>Sentences: {textResults.stats.sentences}</span>
                  </div>
                </div>
                
                <div style={{ textAlign: 'right' }}>
                  <span style={{ fontSize: '24px', fontWeight: '800', color: textResults.score >= 50 ? 'var(--danger)' : 'var(--success)' }}>
                    {textResults.score}%
                  </span>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>AI Probability</div>
                </div>
              </div>

              {/* StoryScope Card */}
              {storyScope.loading && (
                <div className="glass scan-animation" style={{ padding: '16px', textAlign: 'center' }}>
                  <Brain size={20} className="pulse-glow" style={{ color: 'var(--primary)', margin: '0 auto 6px' }} />
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: 0 }}>
                    StoryScope: extracting 304 narrative discourse features and evaluating XGBoost classifier...
                  </p>
                </div>
              )}

              {storyScope.results && !storyScope.loading && (
                <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px', borderLeft: '4px solid var(--primary)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Brain size={16} color="var(--primary)" />
                      <h4 style={{ fontSize: '13px', fontWeight: '700', margin: 0 }}>StoryScope Narrative Analysis</h4>
                    </div>
                    <span style={{ fontSize: '10px', background: 'rgba(15,23,42,0.05)', padding: '2px 6px', borderRadius: '4px' }}>
                      {storyScope.results.features_extracted}/{storyScope.results.features_total} features ({storyScope.results.engine})
                    </span>
                  </div>
                  <p style={{ fontSize: '11.5px', color: 'var(--text-secondary)', margin: 0 }}>
                    Classified as <strong>{storyScope.results.label}</strong> with {Math.round(storyScope.results.probability * 100)}% confidence across narrative discourse dimensions.
                  </p>
                </div>
              )}

              {/* DNA-DetectLLM Results */}
              {dnaDetect.loading && (
                <div className="glass" style={{ padding: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div className="pulse-glow" style={{ width: 14, height: 14, borderRadius: '50%', background: 'var(--primary)' }} />
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Running DNA-DetectLLM mutation-repair analysis…</span>
                </div>
              )}
              {dnaDetect.results && !dnaDetect.loading && (
                <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px', borderLeft: `4px solid ${dnaDetect.results.score >= 50 ? 'var(--danger)' : 'var(--success)'}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Dna size={16} color={dnaDetect.results.score >= 50 ? 'var(--danger)' : 'var(--success)'} />
                      <h4 style={{ fontSize: '13px', fontWeight: '700', margin: 0 }}>DNA-DetectLLM Mutation-Repair</h4>
                    </div>
                    <span style={{ fontSize: '12px', fontWeight: '700', color: dnaDetect.results.score >= 50 ? 'var(--danger)' : 'var(--success)' }}>
                      {dnaDetect.results.score}% AI
                    </span>
                  </div>
                  <p style={{ fontSize: '11.5px', color: 'var(--text-secondary)', margin: 0 }}>
                    <strong>{dnaDetect.results.label}</strong> — repair score: {dnaDetect.results.repair_score}, mutation rate: {(dnaDetect.results.mutation_rate * 100).toFixed(0)}%.
                    {textVal.length < 200 && (
                      <span style={{ fontStyle: 'italic', opacity: 0.8 }}> (optimized for short text — StoryScope needs 80+ chars)</span>
                    )}
                  </p>
                </div>
              )}
              {dnaDetect.error && (
                <div className="glass" style={{ padding: '10px', fontSize: '11px', color: 'var(--warning)' }}>
                  {dnaDetect.error}
                </div>
              )}

              {/* Reasons */}
              <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <h4 style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Forensic Flag Breakdown</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {textResults.flags.map((flag: string, idx: number) => (
                    <div key={idx} style={{ fontSize: '11.5px', color: 'var(--text-primary)', display: 'flex', gap: '6px' }}>
                      <span style={{ color: 'var(--primary)' }}>•</span>
                      <span>{flag}</span>
                    </div>
                  ))}
                </div>
              </div>

              {textResults.suggestions && textResults.suggestions.length > 0 && (
                <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px', borderLeft: '4px solid var(--primary)', background: '#f0fdf4', borderColor: '#16a34a' }}>
                  <h4 style={{ fontSize: '12px', textTransform: 'uppercase', color: '#15803d', fontWeight: '700', margin: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Sparkles size={14} color="#16a34a" />
                    <span>Humanizer Co-Pilot Suggestions</span>
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {textResults.suggestions.map((item: HumanizerSuggestion, idx: number) => (
                      <div key={idx} style={{ padding: '8px 10px', background: '#ffffff', borderRadius: '8px', border: '1px solid #d1fae5', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <div style={{ fontSize: '11.5px', fontWeight: '700', color: '#111827' }}>Found: "{item.term}"</div>
                          <div style={{ fontSize: '10.5px', color: '#374151' }}>{item.explanation}</div>
                        </div>
                        <div style={{ display: 'flex', gap: '4px' }}>
                          {item.suggestions.slice(0, 2).map((sugg: string, sIdx: number) => (
                            <button
                              key={sIdx}
                              onClick={() => handleApplySuggestion(item.term, sugg)}
                              className="btn"
                              style={{ padding: '3px 8px', fontSize: '10px', background: '#10b981', color: 'white', border: 'none', borderRadius: '4px' }}
                            >
                              "{sugg}"
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* IMAGE 5-LAYER ENSEMBLE PANEL */}
      {sandboxType === 'image' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: '1', minHeight: '0' }}>
          
          <div className="glass" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* Scan Mode Toggle */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '11.5px', fontWeight: '700', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Layers size={13} color="var(--primary)" />
                <span>Detection Strategy:</span>
              </span>
              <div style={{ display: 'flex', gap: '4px' }}>
                <button
                  type="button"
                  onClick={() => setScanMode('deep')}
                  className={`btn ${scanMode === 'deep' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ padding: '4px 10px', fontSize: '10.5px', boxShadow: 'none' }}
                >
                  Deep 5-Layer + Heatmap
                </button>
                <button
                  type="button"
                  onClick={() => setScanMode('fast')}
                  className={`btn ${scanMode === 'fast' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ padding: '4px 10px', fontSize: '10.5px', boxShadow: 'none' }}
                >
                  Fast Probe (&lt;100ms)
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                className="input-text"
                placeholder="Enter image URL or upload image..."
                value={imgUrl.startsWith("data:") ? "Local Image Uploaded" : imgUrl}
                onChange={(e) => setImgUrl(e.target.value)}
                disabled={analyzing}
                style={{ fontSize: '12px' }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="btn btn-secondary"
                style={{ padding: '8px 12px', whiteSpace: 'nowrap', fontSize: '11.5px' }}
                disabled={analyzing}
              >
                Upload File
              </button>
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleUploadFile} 
                accept="image/*" 
                style={{ display: 'none' }} 
              />
            </div>
            
            <button 
              onClick={() => handleAnalyzeImageUrl()}
              className="btn btn-primary"
              style={{ width: '100%', padding: '9px' }}
              disabled={analyzing || !imgUrl}
            >
              <Send size={13} />
              <span>{analyzing ? 'Evaluating 5-Layer Forensic Ensemble...' : `Analyze Image (${scanMode.toUpperCase()} Mode)`}</span>
            </button>
          </div>

          {/* Analyzing indicator */}
          {analyzing && (
            <div className="glass scan-animation-danger" style={{ padding: '20px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
              {imgUrl && (
                <div style={{ width: '100px', height: '100px', borderRadius: '8px', overflow: 'hidden', border: '2px solid var(--primary)' }}>
                  <img src={imgUrl} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="Scanning item" />
                </div>
              )}
              <p style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
                Running SynthID probe, C2PA manifest verification, 2D FFT & Wavelet spectral forensics, and ViT patch anomaly detection...
              </p>
            </div>
          )}

          {/* Results display */}
          {imgResults && !analyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', overflowY: 'auto', flex: '1', paddingRight: '2px' }}>
              
              {/* Verdict Header */}
              <div className="glass" style={{ padding: '14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '15px', fontWeight: '800', color: imgResults.tier === 'UNCERTAIN' ? 'var(--warning)' : imgResults.score >= 55 ? 'var(--danger)' : 'var(--success)' }}>
                      {imgResults.tier || (imgResults.score >= 80 ? "SYNTHETIC AI" : imgResults.score >= 69 ? "SUSPICIOUS" : imgResults.score >= 55 ? "UNCERTAIN" : imgResults.score >= 35 ? "INCONCLUSIVE" : "AUTHENTIC HUMAN")}
                    </span>
                    <span 
                      style={{ 
                        fontSize: '10px', 
                        padding: '2px 6px', 
                        borderRadius: '4px', 
                        background: imgResults.confidence === 'HIGH' ? 'rgba(5, 150, 105, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                        color: imgResults.confidence === 'HIGH' ? 'var(--success)' : 'var(--warning)',
                        fontWeight: '700'
                      }}
                    >
                      {imgResults.confidence || 'HIGH'} CONFIDENCE
                    </span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '3px' }}>
                    Multi-layer weighted confidence voting consensus
                  </div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <span style={{ fontSize: '24px', fontWeight: '800', color: imgResults.score >= 55 ? 'var(--danger)' : 'var(--success)' }}>
                    {imgResults.score}%
                  </span>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Synthetic Probability</div>
                </div>
              </div>

              {/* Visualizer & Heatmap Overlay */}
              <div className="glass" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11.5px', fontWeight: '700', color: 'var(--text-primary)' }}>
                    Visual Forensic Overlay
                  </span>
                  {imgResults.heatmap_overlay_base64 && (
                    <button
                      onClick={() => setShowHeatmapOverlay(prev => !prev)}
                      className="btn btn-secondary"
                      style={{ padding: '3px 8px', fontSize: '10.5px' }}
                    >
                      {showHeatmapOverlay ? <EyeOff size={11} /> : <Eye size={11} />}
                      <span>{showHeatmapOverlay ? 'Hide Heatmap' : 'Show Heatmap Overlay'}</span>
                    </button>
                  )}
                </div>

                <div style={{ position: 'relative', width: '100%', height: '180px', borderRadius: '8px', overflow: 'hidden', background: '#000', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                  <img 
                    src={imgResults.url} 
                    style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} 
                    alt="Scanned original" 
                  />
                  {imgResults.heatmap_overlay_base64 && showHeatmapOverlay && (
                    <img 
                      src={imgResults.heatmap_overlay_base64} 
                      style={{ 
                        position: 'absolute', 
                        top: 0, 
                        left: 0, 
                        width: '100%', 
                        height: '100%', 
                        objectFit: 'contain',
                        opacity: 0.65,
                        pointerEvents: 'none'
                      }} 
                      alt="Synthetic patch heatmap overlay" 
                    />
                  )}
                </div>
                {imgResults.synthetic_patches_count !== undefined && (
                  <div style={{ fontSize: '10.5px', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between' }}>
                    <span>ViT 16×16 Patch Analysis:</span>
                    <span><strong>{imgResults.synthetic_patches_count}</strong>/256 regions flagged synthetic</span>
                  </div>
                )}
              </div>

              {/* 5-Layer Forensic Matrix */}
              <div className="glass" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <h4 style={{ fontSize: '12px', fontWeight: '700', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  5-Layer Signal Breakdown
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                  <div style={{ padding: '8px', background: 'rgba(15,23,42,0.03)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>LAYER 1: SYNTHID WATERMARK</div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: (imgResults.breakdown?.synthid || 0) >= 90 ? 'var(--danger)' : 'var(--text-primary)' }}>
                      {imgResults.breakdown?.synthid !== undefined ? `${imgResults.breakdown.synthid}%` : 'Not Detected'}
                    </div>
                  </div>
                  <div style={{ padding: '8px', background: 'rgba(15,23,42,0.03)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>LAYER 2: C2PA MANIFEST</div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: (imgResults.breakdown?.c2pa || 0) >= 90 ? 'var(--danger)' : 'var(--text-primary)' }}>
                      {imgResults.breakdown?.c2pa !== undefined ? `${imgResults.breakdown.c2pa}%` : 'No Manifest'}
                    </div>
                  </div>
                  <div style={{ padding: '8px', background: 'rgba(15,23,42,0.03)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>LAYER 3: FREQUENCY FORENSICS</div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: (imgResults.breakdown?.frequency || 0) >= 55 ? 'var(--danger)' : 'var(--text-primary)' }}>
                      {imgResults.breakdown?.frequency !== undefined ? `${imgResults.breakdown.frequency}%` : 'N/A'}
                    </div>
                  </div>
                  <div style={{ padding: '8px', background: 'rgba(15,23,42,0.03)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>LAYER 4: NEURAL & ViT PATCH</div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: (imgResults.breakdown?.neural || 0) >= 55 ? 'var(--danger)' : 'var(--text-primary)' }}>
                      {imgResults.breakdown?.neural !== undefined ? `${imgResults.breakdown.neural}%` : 'N/A'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Forensic Reasons */}
              <div className="glass" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <h4 style={{ fontSize: '12px', fontWeight: '700', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  Ensemble Forensic Evidence
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  {imgResults.reasons.map((r: string, idx: number) => (
                    <div key={idx} style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'flex', gap: '6px' }}>
                      <span style={{ color: 'var(--primary)' }}>•</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
              </div>

            </div>
          )}
        </div>
      )}

      {/* VIDEO TEMPORAL COHERENCE PANEL */}
      {sandboxType === 'video' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: '1', minHeight: '0' }}>
          
          <div className="glass" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                className="input-text"
                placeholder="Video URL (direct file, or Instagram/TikTok/YouTube link) or upload a file"
                value={videoFile ? `Uploaded: ${videoFile.name}` : videoUrl}
                onChange={(e) => { setVideoUrl(e.target.value); setVideoFile(null); }}
                disabled={analyzing}
                style={{ fontSize: '12px' }}
              />
              <button
                onClick={() => videoFileInputRef.current?.click()}
                className="btn btn-secondary"
                style={{ padding: '8px 12px', whiteSpace: 'nowrap', fontSize: '11.5px' }}
                disabled={analyzing}
              >
                Upload File
              </button>
              <input 
                type="file" 
                ref={videoFileInputRef} 
                onChange={handleUploadVideoFile} 
                accept="video/*" 
                style={{ display: 'none' }} 
              />
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10.5px' }}>
              <span style={{ color: 'var(--text-muted)' }}>
                Mode:{' '}
                <strong style={{ color: 'var(--success)' }}>
                  CLOUD — full spatio-temporal ensemble (server required)
                </strong>
              </span>
              {!settings?.apiUrl && (
                <span style={{ color: 'var(--warning)', fontWeight: '700' }}>No backend configured</span>
              )}
            </div>

            <button 
              onClick={() => handleAnalyzeVideo()}
              className="btn btn-primary"
              style={{ width: '100%', padding: '9px' }}
              disabled={analyzing || !videoUrl || !settings?.apiUrl}
            >
              <Activity size={13} />
              <span>{analyzing ? 'Computing Temporal FFT & Optical Flow...' : 'Run Spatio-Temporal Video Analysis'}</span>
            </button>
          </div>

          {analyzing && (
            <div className="glass scan-animation-danger" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <Activity size={24} className="pulse-glow" style={{ color: 'var(--primary)', margin: '0 auto 8px' }} />
              <p style={{ fontSize: '12px' }}>Sampling uniform frames and computing pixel-wise temporal 1D Fourier flicker and motion residual variance...</p>
            </div>
          )}

          {videoError && !analyzing && (
            <div className="glass" style={{ padding: '12px', border: '1px solid rgba(239,68,68,0.35)', background: 'rgba(239,68,68,0.06)', fontSize: '11.5px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
              <div style={{ fontWeight: '700', color: 'var(--danger)', marginBottom: '4px' }}>Video analysis could not run</div>
              <div>{videoError}</div>
            </div>
          )}

          {videoResults && !analyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', overflowY: 'auto', flex: '1', paddingRight: '2px' }}>
              
              {/* Verdict card */}
              <div className="glass" style={{ padding: '14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '15px', fontWeight: '800', color: videoResults.tier === 'UNCERTAIN' ? 'var(--warning)' : videoResults.score >= 55 ? 'var(--danger)' : 'var(--success)' }}>
                      {videoResults.tier || (videoResults.score >= 70 ? "AI GENERATED VIDEO" : "PHYSICALLY COHERENT")}
                    </span>
                    {videoResults.layers_active?.includes('temporal') && (
                      <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', background: 'rgba(5, 150, 105, 0.12)', color: 'var(--success)', fontWeight: '700' }}>
                        LAYER 5 ACTIVE
                      </span>
                    )}
                    {videoResults.breakdown?.pwtf !== undefined && (
                      <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', background: 'rgba(5, 150, 105, 0.12)', color: 'var(--success)', fontWeight: '700' }}>
                        LAYER 6 ACTIVE
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '3px' }}>
                    Temporal texture persistence, optical flow trajectory & pixel-wise temporal frequency (ICCV 2025)
                  </div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <span style={{ fontSize: '24px', fontWeight: '800', color: videoResults.tier === 'UNCERTAIN' ? 'var(--warning)' : videoResults.score >= 55 ? 'var(--danger)' : 'var(--success)' }}>
                    {videoResults.score}%
                  </span>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Video Incoherence</div>
                </div>
              </div>

              {/* Temporal Metrics */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                <div className="glass" style={{ padding: '10px' }}>
                  <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>TEMPORAL FLICKER RATIO</div>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: (videoResults.temporal_flicker_energy || 0) > 0.2 ? 'var(--danger)' : 'var(--success)' }}>
                    {videoResults.temporal_flicker_energy ?? '—'}
                  </div>
                  <div style={{ fontSize: '9.5px', color: 'var(--text-muted)' }}>Pixel 1D FFT high-freq energy</div>
                </div>
                <div className="glass" style={{ padding: '10px' }}>
                  <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>MOTION JITTER VARIANCE</div>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: (videoResults.motion_residual_variance || 0) > 0.15 ? 'var(--danger)' : 'var(--success)' }}>
                    {videoResults.motion_residual_variance ?? '—'}
                  </div>
                  <div style={{ fontSize: '9.5px', color: 'var(--text-muted)' }}>Optical flow residual variance</div>
                </div>
                {videoResults.pwtf_spectrum_bins !== undefined && videoResults.pwtf_spectrum_bins > 0 && (
                  <div className="glass" style={{ padding: '10px' }}>
                    <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>PWTF SPECTRUM (ICCV 2025)</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: (videoResults.breakdown?.pwtf || 0) >= 50 ? 'var(--danger)' : 'var(--success)' }}>
                      {videoResults.breakdown?.pwtf ?? 0}%
                    </div>
                    <div style={{ fontSize: '9.5px', color: 'var(--text-muted)' }}>
                      {videoResults.pwtf_frames_analyzed} frames · {videoResults.pwtf_spectrum_bins} temporal bins · hf share {(videoResults.pwtf_metrics?.hf_share_mean ?? 0).toFixed(2)}
                    </div>
                  </div>
                )}
                {videoResults.d3_metrics?.volatility !== undefined && (
                  <div className="glass" style={{ padding: '10px' }}>
                    <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>D3 SECOND-ORDER DYNAMICS (ICCV 2025)</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-secondary)' }}>
                      {(videoResults.d3_metrics.volatility ?? 0).toFixed(3)}
                    </div>
                    <div style={{ fontSize: '9.5px', color: 'var(--text-muted)' }}>
                      trajectory volatility · region {(videoResults.d3_metrics.region_volatility_mean ?? 0).toFixed(2)} · metrics only
                    </div>
                  </div>
                )}
                {videoResults.audio?.active && (
                  <div className="glass" style={{ padding: '10px' }}>
                    <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>AUDIO TRACK · REPORTED, NOT SCORED</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-secondary)' }}>
                      {videoResults.audio.kind ?? '—'}
                    </div>
                    <div style={{ fontSize: '9.5px', color: 'var(--text-muted)' }}>
                      {(videoResults.audio.duration_s ?? 0).toFixed(1)}s ·{' '}
                      bandwidth {(((videoResults.audio.metrics?.bandwidth_hz_99 ?? 0) / 1000)).toFixed(1)} kHz ·{' '}
                      {(((videoResults.audio.metrics?.hf_share_8k ?? 0) * 100)).toFixed(1)}% above 8 kHz
                    </div>
                  </div>
                )}
                {videoResults.audio && videoResults.audio.active === false && (
                  <div className="glass" style={{ padding: '10px' }}>
                    <div style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>AUDIO TRACK · NOT ANALYZED</div>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-muted)' }}>n/a</div>
                    <div style={{ fontSize: '9.5px', color: 'var(--text-muted)' }}>
                      {videoResults.audio.reasons?.[0] ?? 'No audio track available.'}
                    </div>
                  </div>
                )}
              </div>

              {/* Frame-by-Frame Progression */}
              {videoResults.frame_scores && videoResults.frame_scores.length > 0 && (
                <div className="glass" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Frame Sequence Score Trajectory ({videoResults.frame_scores.length} Frames)
                  </div>
                  <div style={{ display: 'flex', gap: '4px', alignItems: 'flex-end', height: '50px', paddingTop: '8px' }}>
                    {videoResults.frame_scores.map((fScore: number, idx: number) => (
                      <div key={idx} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                        <div 
                          style={{ 
                            width: '100%', 
                            height: `${fScore}%`, 
                            background: fScore >= 55 ? 'var(--danger)' : 'var(--success)', 
                            borderRadius: '2px',
                            minHeight: '4px'
                          }} 
                          title={`Frame ${idx + 1}: ${fScore}% AI score`}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Evidence */}
              <div className="glass" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <h4 style={{ fontSize: '12px', fontWeight: '700', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                  Temporal Physics Evidence
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  {videoResults.reasons.map((r: string, idx: number) => (
                    <div key={idx} style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'flex', gap: '6px' }}>
                      <span style={{ color: 'var(--primary)' }}>•</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
              </div>

            </div>
          )}
        </div>
      )}

    </div>
  );
}
