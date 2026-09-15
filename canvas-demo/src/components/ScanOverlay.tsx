"use client";

import type { CanvasItem, ScanResult } from "@/lib/types";

interface ScanOverlayProps {
  result: ScanResult;
  item: CanvasItem;
  onClose: () => void;
}

export default function ScanOverlay({ result, item, onClose }: ScanOverlayProps) {
  const tierConfig = {
    AI_DEFINITE: {
      color: "text-red-400",
      bg: "bg-red-500/10",
      border: "border-red-500/30",
      label: "AI DEFINITE",
      emoji: "🔴",
    },
    AI_LIKELY: {
      color: "text-orange-400",
      bg: "bg-orange-500/10",
      border: "border-orange-500/30",
      label: "AI LIKELY",
      emoji: "🟠",
    },
    SUSPICIOUS: {
      color: "text-yellow-400",
      bg: "bg-yellow-500/10",
      border: "border-yellow-500/30",
      label: "SUSPICIOUS",
      emoji: "🟡",
    },
    AUTHENTIC: {
      color: "text-green-400",
      bg: "bg-green-500/10",
      border: "border-green-500/30",
      label: "AUTHENTIC",
      emoji: "🟢",
    },
  };

  const config = tierConfig[result.tier];

  return (
    <div className="absolute bottom-4 left-4 right-4 md:left-auto md:right-4 md:bottom-4 md:w-96 z-20">
      <div className={`bg-[#111118] border ${config.border} rounded-xl shadow-2xl overflow-hidden`}>
        {/* Header */}
        <div className={`flex items-center justify-between px-4 py-3 ${config.bg} border-b ${config.border}`}>
          <div className="flex items-center gap-2">
            <span className="text-lg">{config.emoji}</span>
            <div>
              <span className={`text-sm font-bold ${config.color}`}>{config.label}</span>
              <span className="text-gray-400 text-xs ml-2">{result.score}/100</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white text-sm transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Score bar */}
        <div className="px-4 py-2 border-b border-gray-800">
          <div className="flex items-center justify-between text-[11px] text-gray-500 mb-1">
            <span>Human</span>
            <span>AI-Generated</span>
          </div>
          <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width: `${result.score}%`,
                background:
                  result.score >= 80
                    ? "linear-gradient(90deg, #f97316, #ef4444)"
                    : result.score >= 55
                    ? "linear-gradient(90deg, #eab308, #f97316)"
                    : result.score >= 30
                    ? "linear-gradient(90deg, #22c55e, #eab308)"
                    : "#22c55e",
              }}
            />
          </div>
        </div>

        {/* Content preview */}
        <div className="px-4 py-2 border-b border-gray-800">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Scanned Content</p>
          <p className="text-xs text-gray-400 line-clamp-2">
            {item.type === "text"
              ? item.content.slice(0, 100) + (item.content.length > 100 ? "..." : "")
              : item.type === "video"
              ? `🎬 Video: ${item.label}\n🔗 ${item.content}`.slice(0, 120) +
                (item.content.length > 120 ? "..." : "")
              : `🖼 Image: ${item.label}`}
          </p>
        </div>

        {/* Flags */}
        {result.flags.length > 0 && (
          <div className="px-4 py-2 max-h-48 overflow-y-auto">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
              Detection Flags ({result.flags.length})
            </p>
            <div className="space-y-1.5">
              {result.flags.map((flag, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <span className="text-red-400 mt-0.5 shrink-0">•</span>
                  <span className="text-gray-300 leading-relaxed">{flag}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Suggestions */}
        {result.suggestions && result.suggestions.length > 0 && (
          <div className="px-4 py-2 border-t border-gray-800">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
              💡 Suggestions
            </p>
            <div className="space-y-1.5">
              {result.suggestions.map((s, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <span className="text-violet-400 mt-0.5 shrink-0">→</span>
                  <span className="text-gray-400 leading-relaxed">{s}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
