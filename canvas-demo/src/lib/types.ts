export interface CanvasItem {
  id: string;
  type: "text" | "image" | "video";
  content: string; // text content, image URL, or video URL
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  scanned?: boolean;
}

export interface ScanResult {
  score: number; // 0-100 AI confidence
  tier: "AUTHENTIC" | "SUSPICIOUS" | "AI_LIKELY" | "AI_DEFINITE";
  flags: string[];
  suggestions?: string[];
}

export interface VideoMetadata {
  title?: string;
  duration?: string;
  thumbnailUrl?: string;
  author?: string;
  source: "youtube" | "instagram" | "vimeo" | "unknown";
}
