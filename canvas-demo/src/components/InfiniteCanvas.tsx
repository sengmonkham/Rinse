"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { Stage, Layer, Rect, Text, Image as KImage, Group, Circle, Line } from "react-konva";
import type Konva from "konva";
import type { CanvasItem, ScanResult } from "@/lib/types";
import { detectAIText, detectAIImage, detectAIVideo, parseVideoUrl, getYouTubeThumbnail } from "@/lib/detect";

interface InfiniteCanvasProps {
  items: CanvasItem[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onUpdateItem: (id: string, updates: Partial<CanvasItem>) => void;
  onDeleteItem: (id: string) => void;
  onScanItem: (id: string, result: ScanResult) => void;
  scanResults: Record<string, ScanResult>;
  onDropItem: (type: "text" | "image" | "video", content: string, label: string, x: number, y: number) => void;
}

export default function InfiniteCanvas({
  items,
  selectedId,
  onSelect,
  onUpdateItem,
  onDeleteItem,
  onScanItem,
  scanResults,
  onDropItem,
}: InfiniteCanvasProps) {
  const stageRef = useRef<Konva.Stage>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState({ width: 800, height: 600 });
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const [konvaImages, setKonvaImages] = useState<Record<string, HTMLImageElement>>({});
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; itemId: string } | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Resize observer
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setStageSize({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Load images and video thumbnails
  useEffect(() => {
    items.forEach((item) => {
      if (item.type === "image" && !konvaImages[item.id]) {
        const img = new window.Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          setKonvaImages((prev) => ({ ...prev, [item.id]: img }));
        };
        img.onerror = () => {
          console.warn(`Failed to load image: ${item.content}`);
        };
        img.src = item.content;
      }

      // Handle video items - try to load thumbnail
      if (item.type === "video" && !konvaImages[item.id]) {
        loadVideoThumbnail(item.content).then((img) => {
          if (img) {
            setKonvaImages((prev) => ({ ...prev, [item.id]: img }));
          }
        });
      }
    });
  }, [items, konvaImages]);

  // Wheel zoom
  const handleWheel = useCallback((e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;

    const oldScale = stage.scaleX();
    const pointer = stage.getPointerPosition();
    if (!pointer) return;

    const mousePointTo = {
      x: (pointer.x - stage.x()) / oldScale,
      y: (pointer.y - stage.y()) / oldScale,
    };

    const direction = e.evt.deltaY < 0 ? 1 : -1;
    const newScale = Math.max(0.1, Math.min(5, oldScale + direction * 0.08));

    setScale(newScale);
    setPosition({
      x: pointer.x - mousePointTo.x * newScale,
      y: pointer.y - mousePointTo.y * newScale,
    });
  }, []);

  // Pan via middle-click or shift+drag
  const handleMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      // Middle click or shift+click = pan
      if (e.evt.button === 1 || (e.evt.button === 0 && e.evt.shiftKey)) {
        e.evt.preventDefault();
        setIsPanning(true);
        setPanStart({ x: e.evt.clientX - position.x, y: e.evt.clientY - position.y });
        return;
      }

      // Click on empty area = deselect
      if (e.target === e.target.getStage() || e.target.getParent() === e.target.getStage()) {
        onSelect(null);
        setContextMenu(null);
      }
    },
    [position, onSelect]
  );

  const handleMouseMove = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (isPanning) {
        setPosition({
          x: e.evt.clientX - panStart.x,
          y: e.evt.clientY - panStart.y,
        });
      }
    },
    [isPanning, panStart]
  );

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  // Scan a single item
  const handleScan = useCallback(
    (item: CanvasItem) => {
      let result: ScanResult;
      if (item.type === "text") {
        result = detectAIText(item.content);
      } else if (item.type === "video") {
        result = detectAIVideo(item.content);
      } else {
        result = detectAIImage(item.content);
      }
      onScanItem(item.id, result);
    },
    [onScanItem]
  );

  // Load video thumbnail from YouTube/Instagram/Vimeo
  async function loadVideoThumbnail(url: string): Promise<HTMLImageElement | null> {
    try {
      const parsed = parseVideoUrl(url);
      let thumbnailUrl = "";

      if (parsed.source === "youtube" && parsed.id) {
        thumbnailUrl = getYouTubeThumbnail(parsed.id, "high");
      } else if (parsed.source === "instagram" && parsed.id) {
        // Instagram thumbnails require API access; use a placeholder
        thumbnailUrl = "";
      } else if (parsed.source === "vimeo" && parsed.id) {
        thumbnailUrl = `https://vumbnail.com/${parsed.id}.jpg`;
      }

      if (!thumbnailUrl) return null;

      return await new Promise((resolve) => {
        const img = new window.Image();
        img.crossOrigin = "anonymous";
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = thumbnailUrl;
      });
    } catch {
      return null;
    }
  }

  // Right-click context menu
  const handleContextMenu = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      e.evt.preventDefault();
      const target = e.target;
      const itemId = target.id();
      if (itemId && items.find((i) => i.id === itemId)) {
        setContextMenu({
          x: e.evt.clientX,
          y: e.evt.clientY,
          itemId,
        });
      }
    },
    [items]
  );

  // Close context menu on click elsewhere
  useEffect(() => {
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, []);

  // Drag-and-drop from sidebar
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);

      const raw = e.dataTransfer.getData("application/rinse-canvas-item");
      if (!raw) return;

      try {
        const { type, content, label } = JSON.parse(raw);

        // Convert screen drop position to canvas coordinates
        const container = containerRef.current;
        if (!container) return;
        const rect = container.getBoundingClientRect();
        const screenX = e.clientX - rect.left;
        const screenY = e.clientY - rect.top;

        // Account for pan and zoom
        const canvasX = (screenX - position.x) / scale;
        const canvasY = (screenY - position.y) / scale;

        onDropItem(type, content, label, canvasX, canvasY);
      } catch {
        // ignore malformed data
      }
    },
    [position, scale, onDropItem]
  );

  return (
    <div
      ref={containerRef}
      className={`w-full h-full relative bg-[#0a0a0f] ${isDragOver ? "ring-2 ring-inset ring-violet-500/40" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Grid background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)
          `,
          backgroundSize: `${40 * scale}px ${40 * scale}px`,
          backgroundPosition: `${position.x}px ${position.y}px`,
        }}
      />

      {/* Toolbar */}
      <div className="absolute top-4 left-4 z-10">
        <span className="text-sm font-semibold text-gray-300 tracking-wide">RINSE</span>
      </div>

      {/* Drag-over overlay */}
      {isDragOver && (
        <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
          <div className="px-8 py-4 rounded-2xl bg-violet-600/10 border-2 border-dashed border-violet-500/40 text-violet-300 text-lg font-medium backdrop-blur-sm">
            Drop here to add to canvas
          </div>
        </div>
      )}

      {/* Keyboard hint */}
      <div className="absolute bottom-4 left-4 z-10 text-[11px] text-gray-600 space-x-4">
        <span>Scroll = zoom</span>
        <span>Shift+drag = pan</span>
        <span>Drag from sidebar = add item</span>
      </div>

      <Stage
        ref={stageRef}
        width={stageSize.width}
        height={stageSize.height}
        scaleX={scale}
        scaleY={scale}
        x={position.x}
        y={position.y}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onContextMenu={handleContextMenu}
        draggable={false}
      >
        <Layer>
          {items.map((item) => {
            const isSelected = item.id === selectedId;
            const scanResult = scanResults[item.id];              return (
              <Group
                key={item.id}
                id={item.id}
                x={item.x}
                y={item.y}
                draggable
                onClick={() => {
                  onSelect(item.id);
                  setContextMenu(null);
                }}
                onDragEnd={(e) => {
                  onUpdateItem(item.id, {
                    x: e.target.x(),
                    y: e.target.y(),
                  });
                }}
              >
                {item.type === "text" ? (
                  <TextCard
                    item={item}
                    isSelected={isSelected}
                    scanResult={scanResult}
                    onScan={() => handleScan(item)}
                    onDelete={() => onDeleteItem(item.id)}
                  />
                ) : item.type === "video" ? (
                  <VideoCard
                    item={item}
                    isSelected={isSelected}
                    scanResult={scanResult}
                    image={konvaImages[item.id]}
                    onScan={() => handleScan(item)}
                    onDelete={() => onDeleteItem(item.id)}
                  />
                ) : (
                  <ImageCard
                    item={item}
                    isSelected={isSelected}
                    scanResult={scanResult}
                    image={konvaImages[item.id]}
                    onScan={() => handleScan(item)}
                    onDelete={() => onDeleteItem(item.id)}
                  />
                )}
              </Group>
            );
          })}
        </Layer>
      </Stage>

      {/* Context menu */}
      {contextMenu && (
        <div
          className="fixed z-50 bg-[#1a1a24] border border-gray-700 rounded-lg shadow-2xl py-1 min-w-[160px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              const item = items.find((i) => i.id === contextMenu.itemId);
              if (item) handleScan(item);
              setContextMenu(null);
            }}
            className="w-full text-left px-3 py-2 text-sm text-gray-200 hover:bg-violet-600/20 transition-colors"
          >
            🔍 Scan for AI
          </button>
          <button
            onClick={() => {
              onDeleteItem(contextMenu.itemId);
              setContextMenu(null);
            }}
            className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
          >
            🗑️ Delete
          </button>
        </div>
      )}
    </div>
  );
}

// --- Sub-components ---

function ScoreBadge({ score, tier }: { score: number; tier: string }) {
  const color =
    tier === "AI_DEFINITE"
      ? "bg-red-500"
      : tier === "AI_LIKELY"
      ? "bg-orange-500"
      : tier === "SUSPICIOUS"
      ? "bg-yellow-500"
      : "bg-green-500";

  return (
    <div className={`absolute -top-3 -right-3 ${color} text-white text-[11px] font-bold px-2 py-0.5 rounded-full shadow-lg z-10`}>
      {score}%
    </div>
  );
}

function TextCard({
  item,
  isSelected,
  scanResult,
  onScan,
  onDelete,
}: {
  item: CanvasItem;
  isSelected: boolean;
  scanResult?: ScanResult;
  onScan: () => void;
  onDelete: () => void;
}) {
  const maxChars = 500;
  const displayText = item.content.length > maxChars
    ? item.content.slice(0, maxChars) + "..."
    : item.content;

  // Truncate text to fit
  const lines = displayText.split("\n");
  const maxLines = 12;
  const truncatedLines = lines.slice(0, maxLines);
  const needsTruncation = lines.length > maxLines || displayText.length > maxChars;
  const displayTextFinal = truncatedLines.join("\n") + (needsTruncation ? "\n..." : "");

  return (
    <Group>
      {/* Selection ring */}
      {isSelected && (
        <Rect
          x={-3}
          y={-3}
          width={item.width + 6}
          height={item.height + 6}
          cornerRadius={14}
          stroke="#8b5cf6"
          strokeWidth={2}
          dash={[6, 3]}
        />
      )}

      {/* Card background */}
      <Rect
        width={item.width}
        height={item.height}
        cornerRadius={12}
        fill={isSelected ? "#1a1a2e" : "#14141e"}
        stroke={scanResult ? getTierColor(scanResult.tier) : "#2a2a3a"}
        strokeWidth={isSelected ? 1.5 : 1}
        shadowColor="black"
        shadowBlur={isSelected ? 15 : 8}
        shadowOpacity={0.4}
      />

      {/* Label bar */}
      <Rect
        width={item.width}
        height={28}
        cornerRadius={[12, 12, 0, 0]}
        fill="#1e1e2a"
      />
      <Text
        x={10}
        y={7}
        text={item.label}
        fontSize={12}
        fontFamily="system-ui, sans-serif"
        fontStyle="bold"
        fill="#a0a0b0"
      />

      {/* Tag */}
      {scanResult && <ScoreBadge score={scanResult.score} tier={scanResult.tier} />}

      {/* Scan / Delete buttons (top-right) */}
      <Group x={item.width - 60} y={4}>
        <Rect
          width={24}
          height={20}
          cornerRadius={4}
          fill="#2a2a3a"
          onClick={(e) => {
            e.cancelBubble = true;
            onScan();
          }}
          onMouseEnter={(e) => {
            (e.target as Konva.Rect).fill("#3a3a5a");
          }}
          onMouseLeave={(e) => {
            (e.target as Konva.Rect).fill("#2a2a3a");
          }}
          cursor="pointer"
        />
        <Text
          x={4}
          y={3}
          text="🔍"
          fontSize={13}
          onClick={(e) => {
            e.cancelBubble = true;
            onScan();
          }}
          cursor="pointer"
        />
        <Rect
          x={28}
          width={24}
          height={20}
          cornerRadius={4}
          fill="#2a2a3a"
          onClick={(e) => {
            e.cancelBubble = true;
            onDelete();
          }}
          onMouseEnter={(e) => {
            (e.target as Konva.Rect).fill("#4a2020");
          }}
          onMouseLeave={(e) => {
            (e.target as Konva.Rect).fill("#2a2a3a");
          }}
          cursor="pointer"
        />
        <Text
          x={32}
          y={3}
          text="✕"
          fontSize={13}
          fill="#ef4444"
          onClick={(e) => {
            e.cancelBubble = true;
            onDelete();
          }}
          cursor="pointer"
        />
      </Group>

      {/* Text content */}
      <Text
        x={12}
        y={36}
        width={item.width - 24}
        text={displayTextFinal}
        fontSize={11}
        fontFamily="system-ui, sans-serif"
        fill="#c0c0d0"
        lineHeight={1.4}
        wrap="word"
      />
    </Group>
  );
}

function ImageCard({
  item,
  isSelected,
  scanResult,
  image,
  onScan,
  onDelete,
}: {
  item: CanvasItem;
  isSelected: boolean;
  scanResult?: ScanResult;
  image?: HTMLImageElement;
  onScan: () => void;
  onDelete: () => void;
}) {
  const headerH = 28;
  const imgH = item.height - headerH;

  return (
    <Group>
      {/* Selection ring */}
      {isSelected && (
        <Rect
          x={-3}
          y={-3}
          width={item.width + 6}
          height={item.height + 6}
          cornerRadius={14}
          stroke="#8b5cf6"
          strokeWidth={2}
          dash={[6, 3]}
        />
      )}

      {/* Card background */}
      <Rect
        width={item.width}
        height={item.height}
        cornerRadius={12}
        fill={isSelected ? "#1a1a2e" : "#14141e"}
        stroke={scanResult ? getTierColor(scanResult.tier) : "#2a2a3a"}
        strokeWidth={isSelected ? 1.5 : 1}
        shadowColor="black"
        shadowBlur={isSelected ? 15 : 8}
        shadowOpacity={0.4}
      />

      {/* Label bar */}
      <Rect
        width={item.width}
        height={headerH}
        cornerRadius={[12, 12, 0, 0]}
        fill="#1e1e2a"
      />
      <Text
        x={10}
        y={7}
        text={item.label}
        fontSize={12}
        fontFamily="system-ui, sans-serif"
        fontStyle="bold"
        fill="#a0a0b0"
      />

      {scanResult && <ScoreBadge score={scanResult.score} tier={scanResult.tier} />}

      {/* Scan / Delete buttons */}
      <Group x={item.width - 60} y={4}>
        <Rect
          width={24}
          height={20}
          cornerRadius={4}
          fill="#2a2a3a"
          onClick={(e) => {
            e.cancelBubble = true;
            onScan();
          }}
          onMouseEnter={(e) => (e.target as Konva.Rect).fill("#3a3a5a")}
          onMouseLeave={(e) => (e.target as Konva.Rect).fill("#2a2a3a")}
          cursor="pointer"
        />
        <Text
          x={4}
          y={3}
          text="🔍"
          fontSize={13}
          onClick={(e) => {
            e.cancelBubble = true;
            onScan();
          }}
          cursor="pointer"
        />
        <Rect
          x={28}
          width={24}
          height={20}
          cornerRadius={4}
          fill="#2a2a3a"
          onClick={(e) => {
            e.cancelBubble = true;
            onDelete();
          }}
          onMouseEnter={(e) => (e.target as Konva.Rect).fill("#4a2020")}
          onMouseLeave={(e) => (e.target as Konva.Rect).fill("#2a2a3a")}
          cursor="pointer"
        />
        <Text
          x={32}
          y={3}
          text="✕"
          fontSize={13}
          fill="#ef4444"
          onClick={(e) => {
            e.cancelBubble = true;
            onDelete();
          }}
          cursor="pointer"
        />
      </Group>

      {/* Image */}
      {image && (
        <KImage
          image={image}
          x={4}
          y={headerH + 4}
          width={item.width - 8}
          height={imgH - 8}
          cornerRadius={4}
        />
      )}

      {/* Placeholder if image not loaded */}
      {!image && (
        <Group>
          <Rect
            x={4}
            y={headerH + 4}
            width={item.width - 8}
            height={imgH - 8}
            cornerRadius={4}
            fill="#1e1e2a"
          />
          <Text
            x={item.width / 2 - 30}
            y={headerH + imgH / 2}
            text="Loading..."
            fontSize={12}
            fill="#555"
          />
        </Group>
      )}
    </Group>
  );
}

function getTierColor(tier: string): string {
  switch (tier) {
    case "AI_DEFINITE":
      return "#ef4444";
    case "AI_LIKELY":
      return "#f97316";
    case "SUSPICIOUS":
      return "#eab308";
    case "AUTHENTIC":
      return "#22c55e";
    default:
      return "#2a2a3a";
  }
}

// --- Video Card Component ---

function VideoCard({
  item,
  isSelected,
  scanResult,
  image,
  onScan,
  onDelete,
}: {
  item: CanvasItem;
  isSelected: boolean;
  scanResult?: ScanResult;
  image?: HTMLImageElement;
  onScan: () => void;
  onDelete: () => void;
}) {
  const headerH = 28;
  const imgH = item.height - headerH;

  // Parse URL to show platform info
  const url = item.content;
  const hasYoutube = /youtube\.com|youtu\.be/i.test(url);
  const hasInstagram = /instagram\.com/i.test(url);
  const hasVimeo = /vimeo\.com/i.test(url);

  return (
    <Group>
      {/* Selection ring */}
      {isSelected && (
        <Rect
          x={-3}
          y={-3}
          width={item.width + 6}
          height={item.height + 6}
          cornerRadius={14}
          stroke="#8b5cf6"
          strokeWidth={2}
          dash={[6, 3]}
        />
      )}

      {/* Card background */}
      <Rect
        width={item.width}
        height={item.height}
        cornerRadius={12}
        fill={isSelected ? "#1a1a2e" : "#14141e"}
        stroke={scanResult ? getTierColor(scanResult.tier) : "#2a2a3a"}
        strokeWidth={isSelected ? 1.5 : 1}
        shadowColor="black"
        shadowBlur={isSelected ? 15 : 8}
        shadowOpacity={0.4}
      />

      {/* Label bar */}
      <Rect
        width={item.width}
        height={headerH}
        cornerRadius={[12, 12, 0, 0]}
        fill="#1e1e2a"
      />
      <Text
        x={10}
        y={7}
        text={item.label}
        fontSize={12}
        fontFamily="system-ui, sans-serif"
        fontStyle="bold"
        fill="#a0a0b0"
      />

      {scanResult && <ScoreBadge score={scanResult.score} tier={scanResult.tier} />}

      {/* Scan / Delete buttons */}
      <Group x={item.width - 60} y={4}>
        <Rect
          width={24}
          height={20}
          cornerRadius={4}
          fill="#2a2a3a"
          onClick={(e) => {
            e.cancelBubble = true;
            onScan();
          }}
          onMouseEnter={(e) => {
            (e.target as Konva.Rect).fill("#3a3a5a");
          }}
          onMouseLeave={(e) => {
            (e.target as Konva.Rect).fill("#2a2a3a");
          }}
          cursor="pointer"
        />
        <Text
          x={4}
          y={3}
          text="🔍"
          fontSize={13}
          onClick={(e) => {
            e.cancelBubble = true;
            onScan();
          }}
          cursor="pointer"
        />
        <Rect
          x={28}
          width={24}
          height={20}
          cornerRadius={4}
          fill="#2a2a3a"
          onClick={(e) => {
            e.cancelBubble = true;
            onDelete();
          }}
          onMouseEnter={(e) => {
            (e.target as Konva.Rect).fill("#4a2020");
          }}
          onMouseLeave={(e) => {
            (e.target as Konva.Rect).fill("#2a2a3a");
          }}
          cursor="pointer"
        />
        <Text
          x={32}
          y={3}
          text="✕"
          fontSize={13}
          fill="#ef4444"
          onClick={(e) => {
            e.cancelBubble = true;
            onDelete();
          }}
          cursor="pointer"
        />
      </Group>

      {/* Platform badge */}
      <Group x={8} y={headerH + 4}>
        <Rect
          width={60}
          height={18}
          cornerRadius={4}
          fill={hasYoutube ? "#ff0000" : hasInstagram ? "#E1306C" : hasVimeo ? "#1ab7ea" : "#666"}
        />
        <Text
          x={8}
          y={4}
          text={hasYoutube ? "YouTube" : hasInstagram ? "Instagram" : hasVimeo ? "Vimeo" : "Video"}
          fontSize={9}
          fontFamily="system-ui, sans-serif"
          fontStyle="bold"
          fill="white"
        />
      </Group>

      {/* Play button overlay */}
      <Circle
        x={item.width / 2}
        y={headerH + imgH / 2}
        radius={20}
        fill="#000"
        opacity={image ? 0.7 : 0.9}
      />
      <Text
        x={item.width / 2 - 8}
        y={headerH + imgH / 2 - 8}
        text="▶"
        fontSize={24}
        fontFamily="system-ui, sans-serif"
        fontStyle="bold"
        fill="white"
      />

      {/* Video thumbnail or placeholder */}
      {image && (
        <KImage
          image={image}
          x={4}
          y={headerH + 4}
          width={item.width - 8}
          height={imgH - 8}
          cornerRadius={4}
        />
      )}

      {/* Placeholder if video thumbnail not loaded */}
      {!image && (
        <Group>
          <Rect
            x={4}
            y={headerH + 4}
            width={item.width - 8}
            height={imgH - 8}
            cornerRadius={4}
            fill="#1e1e2a"
          />
          <Text
            x={item.width / 2 - 50}
            y={headerH + imgH / 2 - 50}
            text="🎬"
            fontSize={48}
          />
          <Text
            x={item.width / 2 - 60}
            y={headerH + imgH / 2}
            text="Click scan to analyze"
            fontSize={11}
            fill="#555"
          />
        </Group>
      )}

      {/* URL hint at bottom */}
      <Text
        x={8}
        y={item.height - 16}
        text={url.length > 40 ? url.slice(0, 37) + "..." : url}
        fontSize={8}
        fontFamily="monospace"
        fill="#444"
      />
    </Group>
  );
}
