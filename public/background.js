// Detoxify - Background Service Worker

// Initialize state and listeners
chrome.runtime.onInstalled.addListener(() => {
  console.log("Detoxify Content Authenticity Detector extension installed.");
  
  // Set default settings if not already set
  chrome.storage.local.get(["settings"], (result) => {
    if (!result.settings) {
      chrome.storage.local.set({
        settings: {
          enableTextScan: true,
          enableImageScan: true,
          enableVideoScan: true,
          sensitivity: 50, // 0 to 100
          showInlineBadges: true,
          autoImageOverlays: false,
          showVibecodedAlert: false,
          apiMode: "local", // "local" or "cloud"
          apiUrl: "",
          apiKey: ""
        },
        scanHistory: []
      });
    }
  });

  // Create context menu entries
  chrome.contextMenus.create({
    id: "detoxifyScanSelectedText",
    title: "Scan selection for AI patterns",
    contexts: ["selection"]
  });

  chrome.contextMenus.create({
    id: "detoxifyScanSelectedImage",
    title: "Scan image for AI markers",
    contexts: ["image"]
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab || !tab.id) return;
  
  if (info.menuItemId === "detoxifyScanSelectedText") {
    chrome.tabs.sendMessage(tab.id, {
      action: "scanSelectedText",
      text: info.selectionText
    });
  } else if (info.menuItemId === "detoxifyScanSelectedImage") {
    chrome.tabs.sendMessage(tab.id, {
      action: "scanSelectedImage",
      url: info.srcUrl
    });
  }
});

// Listener for runtime messages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "updateBadge") {
    const tabId = sender.tab ? sender.tab.id : request.tabId;
    if (tabId) {
      const count = request.count;
      const text = count > 0 ? count.toString() : "";
      
      chrome.action.setBadgeText({ tabId: tabId, text: text });
      
      // Select badge color based on count and risk
      let badgeColor = "#10B981"; // Green for clean
      if (count > 5) {
        badgeColor = "#EF4444"; // Red for high danger
      } else if (count > 0) {
        badgeColor = "#F59E0B"; // Amber for warning
      }
      
      chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: badgeColor });
    }
    sendResponse({ status: "success" });
  }
  
  else if (request.action === "saveScan") {
    chrome.storage.local.get(["scanHistory"], (result) => {
      let history = result.scanHistory || [];
      
      // Prevent duplicates of the same URL by removing prior entries
      history = history.filter(item => item.url !== request.data.url);
      
      // Add new scan to start of history
      history.unshift({
        url: request.data.url,
        title: request.data.title,
        score: request.data.score,
        stats: request.data.stats,
        timestamp: Date.now()
      });
      
      // Limit history to last 50 items
      if (history.length > 50) {
        history = history.slice(0, 50);
      }
      
      chrome.storage.local.set({ scanHistory: history }, () => {
        sendResponse({ status: "success", history: history });
      });
    });
    return true; // Keep message channel open for async response
  }
  
  else if (request.action === "fetchImageMetadata") {
    const imgUrl = request.url;
    chrome.storage.local.get(["settings"], (result) => {
      const settings = result.settings || {};
      
      const apiMode = settings.apiMode;
      if (apiMode === "cloud") {
        const apiEndpoint = settings.apiUrl || "http://localhost:5001/predict";
        
        fetch(apiEndpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(settings.apiKey ? { "Authorization": `Bearer ${settings.apiKey}` } : {})
          },
          body: JSON.stringify({
            image_url: imgUrl.startsWith("data:") ? null : imgUrl,
            image_base64: imgUrl.startsWith("data:") ? imgUrl : null
          })
        })
        .then(res => {
          if (!res.ok) throw new Error("HTTP error " + res.status);
          return res.json();
        })
        .then(data => {
          sendResponse({
            status: "success",
            found: true, // Always return successful cloud API response
            score: data.score,
            reasons: data.reasons || ["Detected via cloud service."],
            url: imgUrl
          });
        })
        .catch(err => {
          console.error("Cloud detector failed, falling back to local heuristics:", err);
          runLocalHeuristics(imgUrl, sendResponse);
        });
      } else {
        runLocalHeuristics(imgUrl, sendResponse);
      }
    });
    return true; // Keep message channel open for async response
  }
  
  return true; // Keep channel open
});

function runLocalHeuristics(imgUrl, sendResponse) {
  fetch(imgUrl, {
    headers: { 'Range': 'bytes=0-65535' }
  })
  .then(async response => {
    if (!response.ok) {
      throw new Error("HTTP error " + response.status);
    }
    const buffer = await response.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    
    let text = "";
    for (let i = 0; i < bytes.length; i++) {
      if (bytes[i] >= 32 && bytes[i] <= 126) {
        text += String.fromCharCode(bytes[i]);
      } else {
        text += " ";
      }
    }
    
    const aiTags = [
      { term: "Stable Diffusion", source: "Stable Diffusion metadata signature" },
      { term: "Midjourney", source: "Midjourney metadata signature" },
      { term: "DALL-E", source: "DALL-E metadata signature" },
      { term: "NovelAI", source: "NovelAI metadata signature" },
      { term: "civitai", source: "CivitAI tag in metadata" },
      { term: "Adobe Firefly", source: "Adobe Firefly creator tag" }
    ];

    for (const tag of aiTags) {
      if (text.includes(tag.term)) {
        sendResponse({
          status: "success",
          found: true,
          score: 99,
          reasons: [`Detected '${tag.term}' tag: ${tag.source}`],
          url: imgUrl
        });
        return;
      }
    }

    if (text.includes("tEXtparameters") || text.includes("zTXtparameters") || text.includes("iTXtparameters") || text.includes("tEXt parameters") || text.includes("zTXt parameters")) {
      sendResponse({
        status: "success",
        found: true,
        score: 95,
        reasons: ["PNG metadata contains generation 'parameters' chunk (Stable Diffusion parameter data)"],
        url: imgUrl
      });
      return;
    }

    // 3. Pixel-structure forensics (flat cel-shaded render art, e.g. AI meme characters)
    // Determine whether the Range response already contains the whole image, and
    // skip pixel analysis for large assets (avoids a second full download).
    const contentRange = response.headers.get("Content-Range") || "";
    const crMatch = contentRange.match(/\/(\d+)$/);
    const totalSize = crMatch ? parseInt(crMatch[1], 10) : buffer.byteLength;
    if (totalSize <= 512 * 1024) {
      const pixelResult = await analyzeFlatRenderSignature(imgUrl, buffer, totalSize <= buffer.byteLength);
      if (pixelResult) {
        sendResponse({
          status: "success",
          found: true,
          score: pixelResult.score,
          reasons: pixelResult.reasons,
          url: imgUrl
        });
        return;
      }
    }
    
    sendResponse({ status: "success", found: false });
  })
  .catch(err => {
    sendResponse({ status: "success", found: false, error: err.message });
  });
}

// Perceptual fingerprints of famous AI-generated meme artwork (64-bit dHash hex).
// Mirrors KNOWN_AI_ARTWORK_FINGERPRINTS in server.py. Match = Hamming distance <= 10.
const KNOWN_AI_ARTWORK_FINGERPRINTS = [
  {
    label: "Tung Tung Tung Sahur cover art (viral AI-generated meme character)",
    dhash: "64a425353458d269"
  },
  {
    label: "Viral AI-generated receipt artwork (Webflow CDN)",
    dhash: "232b2b2f230f2b27"
  }
];

function hammingDistanceHex(hexA, hexB) {
  let dist = 0;
  for (let i = 0; i < 16; i++) {
    let x = parseInt(hexA[i], 16) ^ parseInt(hexB[i], 16);
    while (x) {
      dist += x & 1;
      x = Math.floor(x / 2);
    }
  }
  return dist;
}

// Pixel-structure check: cel-shaded AI character art has very few distinct colors
// paired with high saturation, while camera photos (even heavily compressed ones)
// rarely exceed 0.5 mean saturation. Runs on ANY image (no CORS canvas taint in the
// service worker) via createImageBitmap + OffscreenCanvas. Reuses the partial bytes
// from the metadata fetch when they contain the whole image.
async function analyzeFlatRenderSignature(imgUrl, partialBytes, partialComplete) {
  try {
    let blob;
    if (partialComplete) {
      blob = new Blob([partialBytes]);
    } else {
      const resp = await fetch(imgUrl);
      if (!resp.ok) return null;
      blob = await resp.blob();
    }
    if (blob.size > 512 * 1024) return null; // only worth it for small assets

    const bitmap = await createImageBitmap(blob);
    const w = Math.min(bitmap.width, 256);
    const h = Math.min(bitmap.height, 256);
    const canvas = new OffscreenCanvas(w, h);
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(bitmap, 0, 0, w, h);
    const px = ctx.getImageData(0, 0, w, h).data;

    // 4-bit quantized palette + mean saturation
    const buckets = new Set();
    let satSum = 0;
    const count = px.length / 4;
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i], g = px[i + 1], b = px[i + 2];
      buckets.add(((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4));
      const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
      satSum += mx > 0 ? (mx - mn) / mx : 0;
    }
    const satMean = satSum / count;

    // Perceptual dHash fingerprint for known-AI-artwork matching (9x8 luma)
    const dCanvas = new OffscreenCanvas(9, 8);
    const dCtx = dCanvas.getContext("2d");
    dCtx.drawImage(bitmap, 0, 0, 9, 8);
    const dPx = dCtx.getImageData(0, 0, 9, 8).data;
    bitmap.close();

    let hashBits = "";
    for (let row = 0; row < 8; row++) {
      for (let col = 0; col < 8; col++) {
        const li = (row * 9 + col) * 4;
        const ri = (row * 9 + col + 1) * 4;
        const lumaL = 0.299 * dPx[li] + 0.587 * dPx[li + 1] + 0.114 * dPx[li + 2];
        const lumaR = 0.299 * dPx[ri] + 0.587 * dPx[ri + 1] + 0.114 * dPx[ri + 2];
        hashBits += lumaL > lumaR ? "1" : "0";
      }
    }
    let hexHash = "";
    for (let i = 0; i < 64; i += 4) {
      hexHash += parseInt(hashBits.substr(i, 4), 2).toString(16);
    }

    // Known AI artwork fingerprint match (same DB as the cloud server)
    for (const entry of KNOWN_AI_ARTWORK_FINGERPRINTS) {
      if (hammingDistanceHex(hexHash, entry.dhash) <= 10) {
        return { score: 99, reasons: [`Perceptual fingerprint match: ${entry.label}`] };
      }
    }

    // Flat synthetic palette signature. Saturation is scale-invariant and is the
    // key gate: genuine flat renders sit well above 0.6 while dark-table photos of
    // receipts stay around 0.5-0.6 (calibrated at 256px; mirrored in server.py).
    if (buckets.size < 700 && satMean > 0.6) {
      return {
        score: 70,
        reasons: [
          `Flat synthetic palette signature: only ${buckets.size} distinct colors with ${Math.round(satMean * 100)}% saturation at ${w}x${h}px - typical of cel-shaded AI-generated character art, not camera photos.`
        ]
      };
    }

    // Document-render signature: AI-generated receipts/tickets/documents have a
    // perfectly smooth background (photos/scans always show texture or shadows)
    // and soft anti-aliased type (real print has crisp high-contrast edges).
    // Calibrated against real receipts/photos - identical thresholds to server.py.
    const lumaArr = new Float32Array(w * h);
    for (let i = 0, idx = 0; i < px.length; i += 4, idx++) {
      lumaArr[idx] = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
    }

    // Simple gradient magnitude |dx| + |dy|
    const grad = new Float32Array(w * h);
    for (let y = 1; y < h; y++) {
      for (let x = 1; x < w; x++) {
        const idx = y * w + x;
        grad[idx] = Math.abs(lumaArr[idx] - lumaArr[idx - w]) + Math.abs(lumaArr[idx] - lumaArr[idx - 1]);
      }
    }
    let strong = 0, medium = 0, edgePix = 0;
    const total = w * h;
    for (let i = 0; i < total; i++) {
      if (grad[i] > 120) strong++;
      else if (grad[i] > 40) medium++;
      if (grad[i] > 60) edgePix++;
    }
    const edgeDensity = edgePix / total;
    const edgeRatio = strong / Math.max(medium, 1);

    // Flat-region ratio (8x8 patches with std < 3 => variance < 9)
    let flat = 0, patches = 0;
    for (let y = 0; y + 8 <= h; y += 8) {
      for (let x = 0; x + 8 <= w; x += 8) {
        patches++;
        let sum = 0, sum2 = 0;
        for (let yy = y; yy < y + 8; yy++) {
          for (let xx = x; xx < x + 8; xx++) {
            const v = lumaArr[yy * w + xx];
            sum += v; sum2 += v * v;
          }
        }
        const mean = sum / 64;
        if (sum2 / 64 - mean * mean < 9) flat++;
      }
    }
    const flatRatio = patches > 0 ? flat / patches : 0;

    // Border (background) region standard deviation
    const bw = Math.max(2, Math.floor(w / 20));
    const bh = Math.max(2, Math.floor(h / 20));
    let bSum = 0, bSum2 = 0, bCount = 0;
    for (let x = 0; x < w; x++) {
      for (let y = 0; y < bh; y++) { const v = lumaArr[y * w + x]; bSum += v; bSum2 += v * v; bCount++; }
      for (let y = h - bh; y < h; y++) { const v = lumaArr[y * w + x]; bSum += v; bSum2 += v * v; bCount++; }
    }
    for (let y = bh; y < h - bh; y++) {
      for (let x = 0; x < bw; x++) { const v = lumaArr[y * w + x]; bSum += v; bSum2 += v * v; bCount++; }
      for (let x = w - bw; x < w; x++) { const v = lumaArr[y * w + x]; bSum += v; bSum2 += v * v; bCount++; }
    }
    const bMean = bSum / bCount;
    const borderStd = Math.sqrt(Math.max(0, bSum2 / bCount - bMean * bMean));

    if (edgeDensity > 0.06 && flatRatio < 0.35 && borderStd < 20.0 && edgeRatio < 1.1) {
      return {
        score: 75,
        reasons: [
          `Synthetic document render signature: text-dense image with unnaturally smooth background (border variance ${borderStd.toFixed(1)}) and soft anti-aliased type (strong/medium edge ratio ${edgeRatio.toFixed(2)}) at ${w}x${h}px - AI generators render receipts/documents with uniform paper and smooth glyphs, unlike real photos/scans.`
        ]
      };
    }
    return null;
  } catch (e) {
    return null; // decode failure or unsupported format - skip silently
  }
}

