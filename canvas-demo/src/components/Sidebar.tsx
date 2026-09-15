"use client";

import { useState } from "react";
import type { SampleText, SampleImage } from "@/lib/samples";

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  texts: SampleText[];
  images: SampleImage[];
  onClearAll: () => void;
  itemCount: number;
  scanCount: number;
  onAddUrl: (type: "image" | "video", url: string, label: string) => void;
}

export default function Sidebar({
  isOpen,
  onToggle,
  texts,
  images,
  onClearAll,
  itemCount,
  scanCount,
  onAddUrl,
}: SidebarProps) {
  const [tab, setTab] = useState<"texts" | "images">("texts");
  const [filter, setFilter] = useState<"all" | "AI" | "Human">("all");
  const [dragging, setDragging] = useState<string | null>(null);

  const filteredTexts = texts.filter((t) => filter === "all" || t.tag === filter);
  const filteredImages = images.filter((i) => filter === "all" || i.tag === filter);

  const handleDragStart = (
    e: React.DragEvent,
    type: "text" | "image",
    content: string,
    label: string
  ) => {
    setDragging(label);
    e.dataTransfer.setData(
      "application/rinse-canvas-item",
      JSON.stringify({ type, content, label })
    );
    e.dataTransfer.effectAllowed = "copy";
  };

  const handleDragEnd = () => {
    setDragging(null);
  };

  const [urlInput, setUrlInput] = useState("");
  const [urlType, setUrlType] = useState<"image" | "video">("image");

  const handleUrlSubmit = () => {
    if (!urlInput.trim()) return;
    const label = urlType === "video" ? "Video" : "Image";
    onAddUrl(urlType, urlInput.trim(), label);
    setUrlInput("");
  };

  // Auto-detect URL type
  const detectUrlType = (url: string) => {
    if (/youtube\.com|youtu\.be|vimeo\.com|instagram\.com|twitch\.tv/i.test(url)) {
      setUrlType("video");
    } else if (/\.(jpg|jpeg|png|gif|webp|svg|bmp)(\?.*)?$/i.test(url) || /data:image/i.test(url)) {
      setUrlType("image");
    }
  };

  return (
    <div
      className={`flex flex-col bg-[#111118] border-r border-gray-800 transition-all duration-300 ${
        isOpen ? "w-80" : "w-12"
      }`}
    >
      {/* Toggle */}
      <button
        onClick={onToggle}
        className="flex items-center justify-center h-12 border-b border-gray-800 hover:bg-gray-800/50 transition-colors"
      >
        <span className={`text-gray-400 text-lg transition-transform ${isOpen ? "" : "rotate-180"}`}>
          ◀
        </span>
        {isOpen && (
          <span className="ml-2 text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Samples
          </span>
        )}
      </button>

      {isOpen && (
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Stats */}
          <div className="flex items-center gap-4 px-4 py-3 border-b border-gray-800 text-xs text-gray-500">
            <span>{itemCount} items</span>
            <span>{scanCount} scanned</span>
            <button
              onClick={onClearAll}
              className="ml-auto text-red-400 hover:text-red-300 transition-colors"
            >
              Clear all
            </button>
          </div>

          {/* Tab bar */}
          <div className="flex border-b border-gray-800">
            <button
              onClick={() => setTab("texts")}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                tab === "texts"
                  ? "text-white border-b-2 border-violet-500"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              📝 Texts
            </button>
            <button
              onClick={() => setTab("images")}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                tab === "images"
                  ? "text-white border-b-2 border-violet-500"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              🖼️ Images
            </button>
          </div>

          {/* Filter */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-800">
            {(["all", "AI", "Human"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                  filter === f
                    ? f === "AI"
                      ? "bg-red-500/20 text-red-300 ring-1 ring-red-500/50"
                      : f === "Human"
                      ? "bg-green-500/20 text-green-300 ring-1 ring-green-500/50"
                      : "bg-gray-700 text-gray-200 ring-1 ring-gray-600"
                    : "text-gray-500 hover:text-gray-300 hover:bg-gray-800"
                }`}
              >
                {f}
              </button>
            ))}
          </div>

          {/* Items */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {tab === "texts" &&
              filteredTexts.map((sample, idx) => (
                <div
                  key={idx}
                  draggable
                  onDragStart={(e) => handleDragStart(e, "text", sample.content, sample.label)}
                  onDragEnd={handleDragEnd}
                  className={`w-full text-left p-3 rounded-lg bg-[#1a1a24] border transition-all group cursor-grab active:cursor-grabbing ${
                    dragging === sample.label
                      ? "border-violet-400 bg-violet-500/10 opacity-60 scale-95"
                      : "border-gray-700/50 hover:border-violet-500/50 hover:bg-[#1e1e2a]"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-gray-600 text-xs">⠿</span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        sample.tag === "AI"
                          ? "bg-red-500/20 text-red-300"
                          : "bg-green-500/20 text-green-300"
                      }`}
                    >
                      {sample.tag}
                    </span>
                    <span className="text-sm font-medium text-gray-200 group-hover:text-white transition-colors">
                      {sample.label}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 line-clamp-2 leading-relaxed">
                    {sample.content.slice(0, 120)}...
                  </p>
                  <div className="mt-2 text-[10px] text-violet-400 opacity-0 group-hover:opacity-100 transition-opacity">
                    Drag onto canvas →
                  </div>
                </div>
              ))}

            {tab === "images" &&
              filteredImages.map((sample, idx) => (
                <div
                  key={idx}
                  draggable
                  onDragStart={(e) => handleDragStart(e, "image", sample.url, sample.label)}
                  onDragEnd={handleDragEnd}
                  className={`w-full text-left p-3 rounded-lg bg-[#1a1a24] border transition-all group cursor-grab active:cursor-grabbing ${
                    dragging === sample.label
                      ? "border-violet-400 bg-violet-500/10 opacity-60 scale-95"
                      : "border-gray-700/50 hover:border-violet-500/50 hover:bg-[#1e1e2a]"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-gray-600 text-xs">⠿</span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        sample.tag === "AI"
                          ? "bg-red-500/20 text-red-300"
                          : "bg-green-500/20 text-green-300"
                      }`}
                    >
                      {sample.tag}
                    </span>
                    <span className="text-sm font-medium text-gray-200 group-hover:text-white transition-colors">
                      {sample.label}
                    </span>
                  </div>
                  <div className="w-full h-24 rounded bg-gray-800 overflow-hidden">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={sample.url}
                      alt={sample.label}
                      className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                    />
                  </div>
                  <div className="mt-2 text-[10px] text-violet-400 opacity-0 group-hover:opacity-100 transition-opacity">
                    Drag onto canvas →
                  </div>
                </div>
              ))}
          </div>

          {/* URL Input */}
          <div className="px-4 py-3 border-t border-gray-800">
            <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">Add URL</p>
            <div className="flex gap-2">
              <input
                type="text"
                value={urlInput}
                onChange={(e) => {
                  setUrlInput(e.target.value);
                  detectUrlType(e.target.value);
                }}
                onKeyDown={(e) => e.key === "Enter" && handleUrlSubmit()}
                placeholder="Paste YouTube/Instagram/Image URL..."
                className="flex-1 bg-[#1a1a24] border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-violet-500"
              />
              <select
                value={urlType}
                onChange={(e) => setUrlType(e.target.value as "image" | "video")}
                className="bg-[#1a1a24] border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-violet-500 cursor-pointer"
              >
                <option value="image">🖼 Image</option>
                <option value="video">🎬 Video</option>
              </select>
              <button
                onClick={handleUrlSubmit}
                className="bg-violet-600 hover:bg-violet-500 text-white px-3 py-1.5 rounded text-xs font-medium transition-colors"
              >
                Add
              </button>
            </div>
            <p className="text-[10px] text-gray-600 mt-1">
              {urlType === "video"
                ? "YouTube & Vimeo thumbnails load automatically."
                : "Direct image URLs only (no Instagram/TikTok)."}
            </p>
          </div>

          {/* Footer hint */}
          <div className="px-4 py-3 border-t border-gray-800 text-[11px] text-gray-600">
            Drag items onto the canvas → then scan with 🔍
          </div>
        </div>
      )}
    </div>
  );
}
