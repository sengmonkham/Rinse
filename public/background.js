// Aegis AI - Background Service Worker

// Initialize state and listeners
chrome.runtime.onInstalled.addListener(() => {
  console.log("Aegis AI Content Authenticity Detector extension installed.");
  
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
    id: "aegisScanSelectedText",
    title: "Scan selection for AI patterns",
    contexts: ["selection"]
  });

  chrome.contextMenus.create({
    id: "aegisScanSelectedImage",
    title: "Scan image for AI markers",
    contexts: ["image"]
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab || !tab.id) return;
  
  if (info.menuItemId === "aegisScanSelectedText") {
    chrome.tabs.sendMessage(tab.id, {
      action: "scanSelectedText",
      text: info.selectionText
    });
  } else if (info.menuItemId === "aegisScanSelectedImage") {
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
  
  return true; // Keep channel open
});
