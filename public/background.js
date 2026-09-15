// RINSE - Background Service Worker

// Initialize state and listeners
chrome.runtime.onInstalled.addListener(() => {
  console.log("RINSE (Remove Inauthentic Noise) extension installed.");
  
  // Set default settings if not already set
  chrome.storage.local.get(["settings", "subscriptionState"], (result) => {
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
          apiKey: "",
          webAppUrl: "http://localhost:3000",
          authToken: ""
        },
        scanHistory: [],
        devStats: {
          totalScans: 0,
          totalTextFlags: 0,
          totalImageFlags: 0,
          totalVideoFlags: 0,
          totalScoreSum: 0,
          lastScanAt: null,
          lastScanUrl: ""
        }
      });
    }

    if (!result.subscriptionState) {
      chrome.storage.local.set({
        subscriptionState: {
          isPaying: false,
          plan: "free",
          status: "inactive",
          expiresAt: null,
          licenseKey: null,
          lastChecked: null
        }
      });
    }
  });

  // Schedule periodic subscription status check (every 6 hours)
  chrome.alarms.create("checkSubscription", { periodInMinutes: 360 });

  // Initial subscription check
  checkSubscriptionStatus();

  // Create context menu entries
  chrome.contextMenus.create({
    id: "rinseScanSelectedText",
    title: "Scan selection for AI patterns",
    contexts: ["selection"]
  });

  chrome.contextMenus.create({
    id: "rinseScanSelectedImage",
    title: "Scan image for AI markers",
    contexts: ["image"]
  });

  chrome.contextMenus.create({
    id: "rinseToggleHideAI",
    title: "Hide AI Generated Content",
    contexts: ["page"]
  });
});

// Periodic alarm listener
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "checkSubscription") {
    checkSubscriptionStatus();
  }
});

// Extension startup listener
chrome.runtime.onStartup.addListener(() => {
  checkSubscriptionStatus();
});

// Update context menu title to reflect current tab's hide state when the user switches tabs
chrome.tabs.onActivated.addListener((activeInfo) => {
  const storageKey = `hideAI_${activeInfo.tabId}`;
  chrome.storage.local.get([storageKey], (result) => {
    const isHidden = Boolean(result[storageKey]);
    chrome.contextMenus.update("rinseToggleHideAI", {
      title: isHidden ? "Show AI Generated Content" : "Hide AI Generated Content"
    });
  });
});

// Resolve the backend base URL from settings. Cloud mode stores a full
// endpoint like "https://api.rinse.app/v1" or "http://localhost:5001/predict";
// the health probe always lives at {base}/health.
function resolveBackendBaseUrl(settings) {
  let base = (settings.apiUrl || "http://localhost:5001").trim();
  base = base.replace(/\/predict(\/.*)?$/, ""); // strip /predict or /predict/... suffixes
  base = base.replace(/\/+$/, "");
  return base || "http://localhost:5001";
}

// Ping the backend /health endpoint, measure latency, and cache the result
// in chrome.storage.local so the popup can render it instantly.
function checkBackendHealth(sendResponse) {
  chrome.storage.local.get(["settings"], (result) => {
    const settings = result.settings || {};
    const base = resolveBackendBaseUrl(settings);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    const startedAt = performance.now();

    fetch(`${base}/health`, { method: "GET", signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        clearTimeout(timeout);
        const status = {
          connected: true,
          url: base,
          latencyMs: Math.round(performance.now() - startedAt),
          server: data,
          error: null,
          checkedAt: Date.now()
        };
        chrome.storage.local.set({ backendStatus: status }, () => {
          console.log("RINSE backend health:", status);
          if (sendResponse) sendResponse({ status: "success", data: status });
        });
      })
      .catch((err) => {
        clearTimeout(timeout);
        const status = {
          connected: false,
          url: base,
          latencyMs: null,
          server: null,
          error: err.name === "AbortError" ? "timeout" : err.message,
          checkedAt: Date.now()
        };
        chrome.storage.local.set({ backendStatus: status }, () => {
          if (sendResponse) sendResponse({ status: "success", data: status });
        });
      });
  });
}

// Query /api/v1/me on the web app to verify subscription status
function checkSubscriptionStatus(sendResponse) {
  chrome.storage.local.get(["settings", "subscriptionState"], (result) => {
    const settings = result.settings || {};
    const webAppUrl = (settings.webAppUrl || "http://localhost:3000").replace(/\/$/, "");
    const token = settings.authToken || settings.apiKey || "";

    if (!token) {
      const freeState = {
        isPaying: false,
        plan: "free",
        status: "inactive",
        expiresAt: null,
        licenseKey: null,
        lastChecked: Date.now()
      };
      chrome.storage.local.set({ subscriptionState: freeState }, () => {
        if (sendResponse) sendResponse({ status: "success", data: freeState, unauthenticated: true });
      });
      return;
    }

    fetch(`${webAppUrl}/api/v1/me`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${token}`
      }
    })
    .then(async (res) => {
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      return res.json();
    })
    .then((data) => {
      const state = {
        isPaying: Boolean(data.is_paying),
        plan: data.plan || "free",
        status: data.is_paying ? "active" : "inactive",
        expiresAt: data.expires_at || null,
        licenseKey: data.license_key || null,
        lastChecked: Date.now()
      };
      chrome.storage.local.set({ subscriptionState: state }, () => {
        console.log("RINSE Subscription status updated:", state);
        if (sendResponse) sendResponse({ status: "success", data: state });
      });
    })
    .catch((err) => {
      console.warn("Failed to check subscription status:", err.message);
      if (sendResponse) {
        sendResponse({
          status: "error",
          error: err.message,
          data: result.subscriptionState || { isPaying: false, plan: "free" }
        });
      }
    });
  });
}

// Broadcast extensionEnabled state to all tabs when storage changes
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.extensionEnabled) {
    const enabled = changes.extensionEnabled.newValue !== false;
    chrome.tabs.query({}, (tabs) => {
      for (const tab of tabs) {
        if (tab.id) {
          chrome.tabs.sendMessage(tab.id, {
            action: enabled ? "enableExtension" : "disableExtension",
          }).catch(() => {}); // Ignore tabs without content script
        }
      }
    });
  }
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab || !tab.id) return;
  
  if (info.menuItemId === "rinseScanSelectedText") {
    chrome.tabs.sendMessage(tab.id, {
      action: "scanSelectedText",
      text: info.selectionText
    });
  } else if (info.menuItemId === "rinseScanSelectedImage") {
    chrome.tabs.sendMessage(tab.id, {
      action: "scanSelectedImage",
      url: info.srcUrl
    });
  } else if (info.menuItemId === "rinseToggleHideAI") {
    const tabId = tab.id;
    // Read current per-tab hide state, toggle it, and notify the content script
    const storageKey = `hideAI_${tabId}`;
    chrome.storage.local.get([storageKey], (result) => {
      const currentlyHidden = Boolean(result[storageKey]);
      const nextHidden = !currentlyHidden;
      chrome.storage.local.set({ [storageKey]: nextHidden });
      chrome.tabs.sendMessage(tabId, {
        action: "applyHideAI",
        hide: nextHidden
      });
      chrome.contextMenus.update("rinseToggleHideAI", {
        title: nextHidden ? "Show AI Generated Content" : "Hide AI Generated Content"
      });
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
    chrome.storage.local.get(["scanHistory", "devStats"], (result) => {
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
      
      // Cumulative dev counters (survive the 50-item history cap)
      const stats = request.data.stats || {};
      const prev = result.devStats || {};
      const devStats = {
        totalScans: (prev.totalScans || 0) + 1,
        totalTextFlags: (prev.totalTextFlags || 0) + (stats.textCount || 0),
        totalImageFlags: (prev.totalImageFlags || 0) + (stats.imageCount || 0),
        totalVideoFlags: (prev.totalVideoFlags || 0) + (stats.videoCount || 0),
        totalScoreSum: (prev.totalScoreSum || 0) + (request.data.score || 0),
        lastScanAt: Date.now(),
        lastScanUrl: request.data.url || ""
      };
      
      chrome.storage.local.set({ scanHistory: history, devStats: devStats }, () => {
        sendResponse({ status: "success", history: history });
      });
    });
    return true; // Keep message channel open for async response
  }
  
  else if (request.action === "checkBackend") {
    checkBackendHealth((response) => {
      sendResponse(response);
    });
    return true; // Keep message channel open for async response
  }
  
  else if (request.action === "getDevStats") {
    chrome.storage.local.get(["devStats", "scanHistory", "settings", "extensionEnabled", "backendStatus"], (result) => {
      const devStats = result.devStats || {};
      const settings = result.settings || {};
      sendResponse({
        status: "success",
        data: {
          backend: result.backendStatus || null,
          extensionEnabled: result.extensionEnabled !== false,
          apiMode: settings.apiMode || "local",
          apiUrl: settings.apiUrl || "",
          sensitivity: settings.sensitivity ?? 50,
          stats: {
            totalScans: devStats.totalScans || 0,
            totalTextFlags: devStats.totalTextFlags || 0,
            totalImageFlags: devStats.totalImageFlags || 0,
            totalVideoFlags: devStats.totalVideoFlags || 0,
            totalScoreSum: devStats.totalScoreSum || 0,
            lastScanAt: devStats.lastScanAt || null,
            lastScanUrl: devStats.lastScanUrl || "",
            recentScans: (result.scanHistory || []).length
          }
        }
      });
    });
    return true; // Keep message channel open for async response
  }
  
  else if (request.action === "fetchImageMetadata") {
    const imgUrl = request.url;
    chrome.storage.local.get(["settings"], (result) => {
      const settings = result.settings || {};
      
      const apiMode = settings.apiMode;
      if (apiMode === "cloud") {      const apiEndpoint = settings.apiUrl || "http://localhost:5001/predict";

      // Guard: reject blob: and non-http URLs early — the backend only accepts
      // http(s) or data: URIs, so anything else would 400.
      if (imgUrl.startsWith("blob:") || (!imgUrl.startsWith("data:") && !imgUrl.startsWith("http://") && !imgUrl.startsWith("https://"))) {
        runLocalHeuristics(imgUrl, sendResponse);
        return;
      }

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
        .then(res => {
          if (!res.ok) {
            console.warn("Cloud detector returned HTTP", res.status, "— falling back to local heuristics");
            runLocalHeuristics(imgUrl, sendResponse);
            return;
          }
          return res.json();
        })
        .then(data => {
          if (!data) return; // Already handled above
          sendResponse({
            status: "success",
            found: true,
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
  
  else if (request.action === "analyzeVideoFrames") {
    // Cloud-mode video analysis: send browser-extracted frames to the backend's
    // /predict/video/deep endpoint for the full spatio-temporal ensemble. The
    // frames are a contiguous native-rate capture and frameIntervalSeconds is
    // the real per-frame spacing - without it the backend disables the
    // temporal layers rather than voting on aliased data.
    chrome.storage.local.get(["settings"], (result) => {
      const settings = result.settings || {};
      const frames = request.frames || [];
      if (settings.apiMode !== "cloud" || frames.length < 3) {
        sendResponse({ status: "success", found: false });
        return;
      }
      const raw = (settings.apiUrl || "http://localhost:5001").trim();
      const base = raw.replace(/\/predict(\/.*)?$/, "").replace(/\/+$/, "");
      const apiEndpoint = `${base}/predict/video/deep`;
      const payload = { frames_base64: frames };
      if (typeof request.frameIntervalSeconds === "number" &&
          isFinite(request.frameIntervalSeconds) && request.frameIntervalSeconds > 0 &&
          request.frameIntervalSeconds <= 0.5) {
        payload.frame_interval_seconds = request.frameIntervalSeconds;
      }
      fetch(apiEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(settings.apiKey ? { "Authorization": `Bearer ${settings.apiKey}` } : {})
        },
        body: JSON.stringify(payload)
      })
      .then(async (res) => {
        if (!res.ok) {
          // Parse the backend's JSON error so the user sees the real cause.
          let msg = "Server returned HTTP " + res.status + ".";
          try {
            const j = await res.json();
            if (j && j.error) msg = j.error + (j.hint ? ` (${j.hint})` : "");
          } catch { /* non-JSON error body */ }
          throw Object.assign(new Error(msg), { handled: true });
        }
        return res.json();
      })
      .then((data) => {
        sendResponse({
          status: "success",
          found: true,
          score: data.score,
          tier: data.tier,
          confidence: data.confidence,
          reasons: data.reasons || ["Analyzed via cloud spatio-temporal ensemble."],
          url: request.url
        });
      })
      .catch((err) => {
        const detail = err && err.message ? err.message : "Video analysis failed.";
        console.warn("Cloud video analysis failed:", detail);
        sendResponse({ status: "success", found: false, error: detail });
      });
    });
    return true; // Keep message channel open for async response
  }

  else if (request.action === "analyzeVideoUrl") {
    // Cloud-mode fallback for videos whose frames cannot be extracted in the
    // browser (CORS-tainted cross-origin players). The backend fetches the
    // source itself and resolves platform pages via yt-dlp when installed.
    chrome.storage.local.get(["settings"], (result) => {
      const settings = result.settings || {};
      if (settings.apiMode !== "cloud" || !request.url) {
        sendResponse({ status: "success", found: false });
        return;
      }
      const raw = (settings.apiUrl || "http://localhost:5001").trim();
      const base = raw.replace(/\/predict(\/.*)?$/, "").replace(/\/+$/, "");
      fetch(`${base}/predict/video/deep`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(settings.apiKey ? { "Authorization": `Bearer ${settings.apiKey}` } : {})
        },
        body: JSON.stringify({ video_url: request.url })
      })
      .then(async (res) => {
        if (!res.ok) {
          let msg = "Server returned HTTP " + res.status + ".";
          try {
            const j = await res.json();
            if (j && j.error) msg = j.error + (j.hint ? ` (${j.hint})` : "");
          } catch { /* non-JSON error body */ }
          throw Object.assign(new Error(msg), { handled: true });
        }
        return res.json();
      })
      .then((data) => {
        sendResponse({
          status: "success",
          found: true,
          score: data.score,
          tier: data.tier,
          confidence: data.confidence,
          reasons: data.reasons || ["Analyzed via cloud spatio-temporal ensemble."],
          url: request.url
        });
      })
      .catch((err) => {
        const detail = err && err.message ? err.message : "Server-side video fetch failed.";
        console.warn("Cloud video URL analysis failed:", detail);
        sendResponse({ status: "success", found: false, error: detail });
      });
    });
    return true; // Keep message channel open for async response
  }
  
  else if (request.action === "syncSubscription") {
    checkSubscriptionStatus((response) => {
      sendResponse(response);
    });
    return true; // Keep message channel open for async response
  }
  
  else if (request.action === "getSubscriptionState") {
    chrome.storage.local.get(["subscriptionState"], (result) => {
      sendResponse({
        status: "success",
        data: result.subscriptionState || {
          isPaying: false,
          plan: "free",
          status: "inactive",
          expiresAt: null,
          licenseKey: null,
          lastChecked: null
        }
      });
    });
    return true;
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
    label: "Tung Tung Tung Sahur news/video still (viral AI-generated meme character)",
    dhash: "4a4b0b2e2d2e3e3e"
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
    // key gate: genuine flat renders sit above 0.5 while dark-table photos of
    // receipts stay around 0.5-0.6 (calibrated at 256px; mirrored in server.py).
    // A strict AND over every feature misses news/video stills of AI toon
    // characters: heavy JPEG recompression inflates edge noise, so the signature
    // is a SATURATION GATE + scored soft signals instead:
    //   gate:     mean saturation > 0.50 (camera photos rarely exceed this)
    //   required: smooth shaded regions (smooth8 0.25-0.70) - large gradient-
    //             shaded areas typical of 3D renders; real macro florals/fruit
    //             are textured EVERYWHERE (smooth8 ~0.1) and fail this, while
    //             blank/bokeh photos (smooth8 > 0.7) fail the upper bound
    //   signals:  few distinct colors (< 700) - flat render palettes
    //             sparse edges (edge_density < 0.10) - clean outlines
    // 2/2 signals -> strong boost; 1/2 -> moderate boost.
    let signals = 0;
    const satGate = satMean > 0.50;

    // Smooth-region ratio: fraction of 8x8 patches with std < 8 (variance < 64),
    // computed over luma below along with the existing flat (std < 3) ratio.
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

    // Flat-region ratio (8x8 patches with std < 3 => variance < 9) and
    // smooth-region ratio (std < 8 => variance < 64).
    let flat = 0, smooth8 = 0, patches = 0;
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
        const variance = sum2 / 64 - mean * mean;
        if (variance < 9) flat++;
        if (variance < 64) smooth8++;
      }
    }
    const flatRatio = patches > 0 ? flat / patches : 0;
    const smooth8Ratio = patches > 0 ? smooth8 / patches : 0;

    if (satGate) {
      if (buckets.size < 700) signals++;
      if (edgeDensity < 0.10) signals++;
      const smoothWindow = smooth8Ratio > 0.25 && smooth8Ratio < 0.70;
      if (smoothWindow && signals >= 1) {
        if (signals >= 2) {
          return {
            score: 80,
            reasons: [
              `Synthetic render signature: cel-shaded/3D-render palette (${buckets.size} distinct colors, ${Math.round(satMean * 100)}% saturation, sparse edges at ${Math.round(edgeDensity * 100)}% density, ${Math.round(smooth8Ratio * 100)}% smooth shaded regions) at ${w}x${h}px - AI toon/character art shows this exact color profile; camera photos - even saturated macro shots - keep dense texture edges instead.`
            ]
          };
        }
        return {
          score: 60,
          reasons: [
            `Synthetic render signature (moderate): saturated image with a limited palette (${buckets.size} colors, ${Math.round(satMean * 100)}% saturation) and partially smooth shading (${Math.round(smooth8Ratio * 100)}% smooth regions, edge density ${Math.round(edgeDensity * 100)}%) at ${w}x${h}px - consistent with AI toon/3D-render character art, uncommon for camera photos.`
          ]
        };
      }
    }

    // Document-render signature: AI-generated receipts/tickets/documents have a
    // perfectly smooth background (photos/scans always show texture or shadows)
    // and soft anti-aliased type (real print has crisp high-contrast edges).
    // Calibrated against real receipts/photos - identical thresholds to server.py.

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

