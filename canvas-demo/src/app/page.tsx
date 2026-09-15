"use client";

import { useState, useCallback } from "react";
import InfiniteCanvas from "@/components/InfiniteCanvas";
import Sidebar from "@/components/Sidebar";
import ScanOverlay from "@/components/ScanOverlay";
import type { CanvasItem, ScanResult } from "@/lib/types";
import { SAMPLE_TEXTS, SAMPLE_IMAGES } from "@/lib/samples";

export default function Home() {
  const [items, setItems] = useState<CanvasItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scanResults, setScanResults] = useState<Record<string, ScanResult>>({});
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const handleDropItem = useCallback(
    (
      type: "text" | "image" | "video",
      content: string,
      label: string,
      x: number,
      y: number
    ) => {
      const id = `item-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const w = type === "text" ? 380 : 400;
      const h = type === "text" ? 200 : 300;
      setItems((prev) => [
        ...prev,
        { id, type, content, label, x: x - w / 2, y: y - h / 2, width: w, height: h },
      ]);
    },
    []
  );

  const handleAddUrl = useCallback(
    (type: "image" | "video", url: string, label: string) => {
      // For video URLs, try to add to canvas at center
      const id = `item-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const stage = document.querySelector("[data-stage]");
      const defaultX = 200;
      const defaultY = 200;
      setItems((prev) => [
        ...prev,
        {
          id,
          type,
          content: url,
          label: label || (type === "video" ? "Video" : "Image"),
          x: defaultX - 200,
          y: defaultY - 150,
          width: 400,
          height: type === "video" ? 300 : 300,
        },
      ]);
    },
    []);


  const handleDeleteItem = useCallback(
    (id: string) => {
      setItems((prev) => prev.filter((i) => i.id !== id));
      setScanResults((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      if (selectedId === id) setSelectedId(null);
    },
    [selectedId]
  );

  const handleScanItem = useCallback((id: string, result: ScanResult) => {
    setScanResults((prev) => ({ ...prev, [id]: result }));
  }, []);

  const handleClearAll = useCallback(() => {
    setItems([]);
    setScanResults({});
    setSelectedId(null);
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0a0a0f] text-white">
      {/* Sidebar */}
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        texts={SAMPLE_TEXTS}
        images={SAMPLE_IMAGES}
        onClearAll={handleClearAll}
        itemCount={items.length}
        scanCount={Object.keys(scanResults).length}
        onAddUrl={handleAddUrl}
      />

      {/* Canvas area */}
      <div className="relative flex-1">
        <InfiniteCanvas
          items={items}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onUpdateItem={(id, updates) =>
            setItems((prev) =>
              prev.map((i) => (i.id === id ? { ...i, ...updates } : i))
            )
          }
          onDeleteItem={handleDeleteItem}
          onScanItem={handleScanItem}
          scanResults={scanResults}
          onDropItem={handleDropItem}
        />

        {/* Scan overlay for selected item */}
        {selectedId && scanResults[selectedId] && (
          <ScanOverlay
            result={scanResults[selectedId]}
            item={items.find((i) => i.id === selectedId)!}
            onClose={() => setSelectedId(null)}
          />
        )}

        {/* Playground watermark */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <span className="text-6xl font-bold text-gray-500/20 select-none">Playground</span>
        </div>
      </div>
    </div>
  );
}
