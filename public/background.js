// RINSE - Background Service Worker

// Backend targets. "deployed" is the hosted Hugging Face Space; "local" is the
// developer server on this machine. Settings/popup store the user's choice.
const DEPLOYED_API_URL = "https://senkmonkham-rinse-detector.hf.space";
const LOCAL_API_URL = "http://localhost:5001";

// --- Deployed-backend keep-alive -------------------------------------------
// Hugging Face Spaces sleep after a few minutes without traffic. A periodic
// /health ping on a Chrome alarm keeps the Space warm even when no tab is being
// scanned and the popup is closed (alarms wake the service worker).
const KEEPALIVE_ALARM = "rinseBackendKeepAlive";
const KEEPALIVE_PERIOD_MINUTES = 3;

function deployedHealthUrl(settings) {
  let base = String((settings && settings.apiUrl) || "").trim();
  base = base.replace(/\/predict(\/.*)?$/, "").replace(/\/+$/, "");
  // A loopback or empty URL is not something that can sleep — ping the Space.
  if (!base || base === LOCAL_API_URL || /localhost|127\.0\.0\.1/.test(base)) {
    base = DEPLOYED_API_URL;
  }
  return `${base}/health`;
}

function ensureKeepAliveAlarm() {
  chrome.alarms.get(KEEPALIVE_ALARM, (alarm) => {
    if (!alarm) {
      chrome.alarms.create(KEEPALIVE_ALARM, {
        delayInMinutes: 1,
        periodInMinutes: KEEPALIVE_PERIOD_MINUTES
      });
    }
  });
}

function pingDeployedBackend() {
  chrome.storage.local.get(["settings"], (result) => {
    const url = deployedHealthUrl(result.settings);
    fetch(url, { method: "GET", cache: "no-store" })
      .then((res) => console.log(`RINSE keep-alive: ${url} -> HTTP ${res.status}`))
      .catch((err) => console.warn(`RINSE keep-alive failed: ${url} (${err.message})`));
  });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEPALIVE_ALARM) pingDeployedBackend();
});
chrome.runtime.onInstalled.addListener(ensureKeepAliveAlarm);
chrome.runtime.onStartup.addListener(ensureKeepAliveAlarm);
ensureKeepAliveAlarm();

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
          apiMode: "cloud", // "local" (offline heuristics) or "cloud" (backend)
          apiTarget: "deployed", // "deployed" (hosted Space) or "local" (localhost:5001)
          apiUrl: DEPLOYED_API_URL,
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

// Resolve the backend base URL from settings. The user picks where verdicts
// come from: the deployed Hugging Face Space ("deployed", the default) or the
// dev server on this machine ("local"). settings.apiUrl holds the deployed
// Space URL so it stays editable; the local URL is fixed. The health probe
// always lives at {base}/health.
function resolveBackendBaseUrl(settings) {
  settings = settings || {};
  // Legacy settings saved before apiTarget existed: honour a loopback apiUrl.
  const target =
    settings.apiTarget === "local" ||
    (!settings.apiTarget && /localhost|127\.0\.0\.1/.test(settings.apiUrl || ""))
      ? "local"
      : "deployed";
  const fallback = target === "local" ? LOCAL_API_URL : DEPLOYED_API_URL;
  let base = (target === "local" ? LOCAL_API_URL : (settings.apiUrl || DEPLOYED_API_URL)).trim();
  base = base.replace(/\/predict(\/.*)?$/, ""); // strip /predict or /predict/... suffixes
  base = base.replace(/\/+$/, "");
  return base || fallback;
}

// Ping one backend's /health endpoint, measure latency, and return the status
// object. Never throws — an unreachable host is a valid "not connected" answer.
function probeBackend(base, callback) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  const startedAt = performance.now();

  fetch(`${base}/health`, { method: "GET", signal: controller.signal })
    .then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then((data) => {
      clearTimeout(timeout);
      callback({
        connected: true,
        url: base,
        latencyMs: Math.round(performance.now() - startedAt),
        server: data,
        error: null,
        checkedAt: Date.now()
      });
    })
    .catch((err) => {
      clearTimeout(timeout);
      callback({
        connected: false,
        url: base,
        latencyMs: null,
        server: null,
        error: err.name === "AbortError" ? "timeout" : err.message,
        checkedAt: Date.now()
      });
    });
}

// Probe the active backend (stored as backendStatus), plus the deployed HF Space
// (deployedBackendStatus) and the local dev server (localBackendStatus), so the
// popup can show "HF backend: Connected" and "Local: Not connected" side by
// side regardless of which target is selected.
function checkBackendHealth(sendResponse) {
  chrome.storage.local.get(["settings"], (result) => {
    const settings = result.settings || {};
    const activeBase = resolveBackendBaseUrl(settings);

    // The deployed Space URL stays editable, so keep it handy even when the
    // local server is the active target.
    const deployedBase = (() => {
      if (activeBase !== LOCAL_API_URL) return activeBase;
      let base = (settings.apiUrl || DEPLOYED_API_URL).trim();
      base = base.replace(/\/predict(\/.*)?$/, "").replace(/\/+$/, "");
      return !base || base === LOCAL_API_URL ? DEPLOYED_API_URL : base;
    })();

    const statuses = {};
    const probes = [];

    // Active target (drives scan routing).
    probes.push([activeBase, (status) => { statuses.backendStatus = status; }]);

    // Deployed HF Space — always its own line in the popup.
    if (deployedBase !== activeBase) {
      probes.push([deployedBase, (status) => { statuses.deployedBackendStatus = status; }]);
    }

    // Local dev server — always its own line in the popup.
    if (activeBase !== LOCAL_API_URL) {
      probes.push([LOCAL_API_URL, (status) => { statuses.localBackendStatus = status; }]);
    }

    let remaining = probes.length;
    const done = () => {
      if (--remaining > 0) return;
      // Clone the active target's result onto its own-line field.
      if (deployedBase === activeBase) statuses.deployedBackendStatus = statuses.backendStatus;
      if (activeBase === LOCAL_API_URL) statuses.localBackendStatus = statuses.backendStatus;
      chrome.storage.local.set(statuses, () => {
        console.log("RINSE backend health:", statuses);
        if (sendResponse) sendResponse({ status: "success", data: statuses.backendStatus });
      });
    };

    probes.forEach(([base, assign]) => {
      probeBackend(base, (status) => {
        assign(status);
        done();
      });
    });
  });
}

// Resolve whether the backend is currently reachable. Uses the cached /health
// result when it is fresh (< 30s old); otherwise re-probes. Every analysis
// request is gated on this so an unreachable backend is reported honestly
// ("not connected") instead of silently falling back to local scanning.
function ensureBackendConnected(callback) {
  chrome.storage.local.get(["backendStatus"], (result) => {
    const cached = result.backendStatus;
    if (cached && cached.checkedAt && (Date.now() - cached.checkedAt) < 30000) {
      callback({ connected: Boolean(cached.connected), server: cached.server, error: cached.error || null });
      return;
    }
    checkBackendHealth((res) => {
      const status = res && res.data ? res.data : null;
      callback({
        connected: Boolean(status && status.connected),
        server: status ? status.server : null,
        error: status ? status.error : "health check failed"
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
      // A scan "found AI" when at least one item was flagged at 55+ (the
      // badge/flagging threshold) - text, image, or video.
      const foundAi = (stats.textCount || 0) + (stats.imageCount || 0) + (stats.videoCount || 0) > 0;
      const devStats = {
        totalScans: (prev.totalScans || 0) + 1,
        totalTextFlags: (prev.totalTextFlags || 0) + (stats.textCount || 0),
        totalImageFlags: (prev.totalImageFlags || 0) + (stats.imageCount || 0),
        totalVideoFlags: (prev.totalVideoFlags || 0) + (stats.videoCount || 0),
        scansWithAi: (prev.scansWithAi || 0) + (foundAi ? 1 : 0),
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
    chrome.storage.local.get(["devStats", "scanHistory", "settings", "extensionEnabled", "backendStatus", "deployedBackendStatus", "localBackendStatus"], (result) => {
      const devStats = result.devStats || {};
      const settings = result.settings || {};
      const activeBase = resolveBackendBaseUrl(settings);
      sendResponse({
        status: "success",
        data: {
          backend: result.backendStatus || null,
          deployedBackend: result.deployedBackendStatus || null,
          localBackend: result.localBackendStatus || null,
          extensionEnabled: result.extensionEnabled !== false,
          apiMode: settings.apiMode || "cloud",
          apiTarget: activeBase === LOCAL_API_URL ? "local" : "deployed",
          apiUrl: activeBase,
          localUrl: LOCAL_API_URL,
          deployedUrl: DEPLOYED_API_URL,
          sensitivity: settings.sensitivity ?? 50,
          stats: {
            totalScans: devStats.totalScans || 0,
            totalTextFlags: devStats.totalTextFlags || 0,
            totalImageFlags: devStats.totalImageFlags || 0,
            totalVideoFlags: devStats.totalVideoFlags || 0,
            scansWithAi: devStats.scansWithAi || 0,
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
    // Image analysis ALWAYS runs on the backend — there is intentionally no
    // local fallback. When the backend cannot be reached the extension reports
    // "not connected" instead of making up a verdict locally.
    const imgUrl = request.url;
    chrome.storage.local.get(["settings"], (result) => {
      const settings = result.settings || {};

      if (settings.apiMode !== "cloud") {
        sendResponse({
          status: "backend_offline",
          found: false,
          connected: false,
          url: imgUrl,
          error: "Heuristics (Offline) mode does not scan images — switch to Cloud Detector mode in Settings."
        });
        return;
      }

      const base = resolveBackendBaseUrl(settings);

      // Guard: blob: URLs are session-local references the backend cannot
      // fetch, and anything that is not http(s)/data: would be rejected 400.
      if (imgUrl.startsWith("blob:") || (!imgUrl.startsWith("data:") && !imgUrl.startsWith("http://") && !imgUrl.startsWith("https://"))) {
        sendResponse({
          status: "error",
          found: false,
          url: imgUrl,
          error: "This image uses a blob:/unsupported URL the backend cannot fetch — open it in a tab and scan it from the Playground."
        });
        return;
      }

      // Always POST the deep path at {base}/predict. Normalizing the URL here
      // (instead of using settings.apiUrl verbatim) fixes the flood of POST
      // 404s when the configured URL has no /predict suffix (e.g. a bare
      // "http://localhost:5001" or a trailing slash).
      const apiEndpoint = `${base}/predict`;
      const headers = {
        "Content-Type": "application/json",
        ...(settings.apiKey ? { "Authorization": `Bearer ${settings.apiKey}` } : {})
      };
      const body = imgUrl.startsWith("data:")
        ? { image_base64: imgUrl }
        : { image_url: imgUrl };
      // Page-declared provenance context (alt text, caption, page title/URL,
      // surrounding post text) rides along; the backend's AI-metadata layer
      // scans it as provenance evidence. Sanitized to plain strings.
      const ctx = request.context && typeof request.context === "object" ? request.context : {};
      const pickStr = (v, max) => (typeof v === "string" ? v.slice(0, max) : "");
      if (pickStr(ctx.alt_text, 400)) body.alt_text = pickStr(ctx.alt_text, 400);
      if (pickStr(ctx.page_title, 200)) body.page_title = pickStr(ctx.page_title, 200);
      if (pickStr(ctx.page_url, 500)) body.page_url = pickStr(ctx.page_url, 500);
      if (pickStr(ctx.page_context, 1500)) body.page_context = pickStr(ctx.page_context, 1500);

      // Health gate: confirm the backend is actually live before scanning
      // (uses the cached /health result when fresh, else re-probes).
      ensureBackendConnected((health) => {
        if (!health.connected) {
          sendResponse({
            status: "backend_offline",
            found: false,
            connected: false,
            url: imgUrl,
            error: `Not connected to the internet — the detection backend at ${base} is unreachable (${health.error || "no response"}). No local scanning is performed.`
          });
          return;
        }

        // POST a payload to the backend image endpoint and normalize the
        // response into the content-script verdict shape.
        const postPredict = (payload) =>
          fetch(apiEndpoint, { method: "POST", headers, body: JSON.stringify(payload) })
            .then(async (res) => {
              if (!res.ok) {
                // Surface the backend's real error message (a 400/404/413 from
                // the API is an answer, not a reason to scan locally).
                let msg = "Server returned HTTP " + res.status + ".";
                try {
                  const j = await res.json();
                  if (j && j.error) msg = j.error + (j.hint ? ` (${j.hint})` : "");
                } catch { /* non-JSON error body */ }
                throw new Error(msg);
              }
              return res.json();
            })
            .then((data) => {
              if (!data || typeof data.score !== "number") {
                throw new Error("Backend returned an invalid verdict.");
              }
              return {
                status: "success",
                found: true,
                score: data.score,
                tier: data.tier,
                confidence: data.confidence,
                reasons: data.reasons || ["Analyzed via the cloud forensic ensemble."],
                url: imgUrl
              };
            });

        // Fetch the image bytes here in the service worker and convert them
        // to a data URL. Hotlink-protected CDNs (e.g. search-result proxies
        // like imgs.search.brave.com) reject the backend's server-side
        // download with 403 while the browser renders the very same image —
        // so the browser relays the bytes and the backend still performs
        // 100% of the analysis. No local scanning happens at any point.
        const fetchImageAsDataUrl = (url) =>
          fetch(url)
            .then((res) => {
              if (!res.ok) return null;
              return res.blob();
            })
            .then(async (blob) => {
              if (!blob || blob.size > 16 * 1024 * 1024) return null;
              const bytes = new Uint8Array(await blob.arrayBuffer());
              let binary = "";
              const CHUNK = 0x8000;
              for (let i = 0; i < bytes.length; i += CHUNK) {
                binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
              }
              const mime = blob.type && blob.type.startsWith("image/") ? blob.type : "image/png";
              return `data:${mime};base64,${btoa(binary)}`;
            })
            .catch(() => null);

        (async () => {
          let lastErr = null;
          try {
            sendResponse(await postPredict(body));
            return;
          } catch (err) {
            lastErr = err;
          }
          // NOTE: the byte-relay fallback below must keep the context fields -
          // it rebuilds the payload as { image_base64: dataUrl, ...body } so
          // alt/caption context survives the relay.
          const serverFetchFailed = lastErr &&
            /failed to load image|failed to download|http 40[134]|forbidden|connection|timed? ?out|timeout/i
              .test(lastErr.message || "");
          if (!imgUrl.startsWith("data:") && serverFetchFailed) {
            const dataUrl = await fetchImageAsDataUrl(imgUrl);
            if (dataUrl) {
              try {
                sendResponse(await postPredict({ image_base64: dataUrl, ...body }));
                return;
              } catch (err2) {
                lastErr = err2;
              }
            }
          }
          sendResponse({
            status: "error",
            found: false,
            connected: true,
            url: imgUrl,
            error: lastErr && lastErr.message ? lastErr.message : "Image analysis request failed."
          });
        })();
      });
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
      const base = resolveBackendBaseUrl(settings);
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
      const base = resolveBackendBaseUrl(settings);
      // Forward page context for AI-provenance metadata detection (caption,
      // page title, URL) - matches the image scan context behavior.
      const ctx = request.context && typeof request.context === "object" ? request.context : {};
      const pickStr = (v, max) => (typeof v === "string" ? v.slice(0, max) : "");
      const payload = { video_url: request.url };
      if (pickStr(ctx.source_caption, 2000)) payload.source_caption = pickStr(ctx.source_caption, 2000);
      if (pickStr(ctx.page_title, 200)) payload.page_title = pickStr(ctx.page_title, 200);
      if (pickStr(ctx.page_url, 500)) payload.page_url = pickStr(ctx.page_url, 500);
      if (pickStr(ctx.page_context, 1500)) payload.page_context = pickStr(ctx.page_context, 1500);
      fetch(`${base}/predict/video/deep`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(settings.apiKey ? { "Authorization": `Bearer ${settings.apiKey}` } : {})
        },
        body: JSON.stringify(payload)
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
