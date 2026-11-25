import { useState, useEffect, useCallback } from 'react';
import { Shield, ExternalLink, Scan, RefreshCw, Server } from 'lucide-react';
import { DEPLOYED_API_URL, LOCAL_API_URL } from '../backend';

// RINSE never scans its own website — the landing page legitimately contains
// self-referential demo copy ("AI 87%" badges, how-it-works bullets) that the
// heuristics are built to flag, so scanning it would only produce false
// positives. Mirrors the skip list in public/content.js.
const SKIPPED_HOSTS = ['getrinse.tech', 'www.getrinse.tech'];

const isSkippedTabUrl = (url: string): boolean => {
  if (!url) return false;
  try {
    const host = new URL(url).hostname.toLowerCase();
    return SKIPPED_HOSTS.includes(host) || host.endsWith('.getrinse.tech');
  } catch {
    return false;
  }
};

interface PopupSettings {
  enableTextScan: boolean;
  enableImageScan: boolean;
  enableVideoScan: boolean;
  showInlineBadges: boolean;
  showVibecodedAlert: boolean;
  sensitivity: number;
  apiMode: string;
  apiTarget: string;
  apiUrl: string;
}

interface BackendStatus {
  connected: boolean;
  url: string;
  latencyMs: number | null;
  server: {
    server?: string;
    version?: string;
    uptime_seconds?: number;
    mode?: string;
    detectzoo_loaded?: boolean;
    layers?: string[];
  } | null;
  error: string | null;
  checkedAt: number | null;
}

interface DevStatsData {
  backend: BackendStatus | null;
  deployedBackend: BackendStatus | null;
  localBackend: BackendStatus | null;
  extensionEnabled: boolean;
  apiMode: string;
  apiTarget: string;
  apiUrl: string;
  localUrl: string;
  deployedUrl: string;
  sensitivity: number;
  stats: {
    totalScans: number;
    totalTextFlags: number;
    totalImageFlags: number;
    totalVideoFlags: number;
    totalScoreSum: number;
    lastScanAt: number | null;
    lastScanUrl: string;
    recentScans: number;
  };
}

const IS_CHROME_EXT =
  typeof window !== 'undefined' &&
  typeof (window as any).chrome !== 'undefined' &&
  typeof chrome.runtime !== 'undefined' &&
  typeof chrome.runtime.id !== 'undefined';

const DEFAULT_SETTINGS: PopupSettings = {
  enableTextScan: true,
  enableImageScan: true,
  enableVideoScan: true,
  showInlineBadges: true,
  showVibecodedAlert: false,
  sensitivity: 50,
  apiMode: 'cloud',
  apiTarget: 'deployed',
  apiUrl: DEPLOYED_API_URL,
};

const formatRelativeTime = (ts: number): string => {
  const diff = Date.now() - ts;
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
};

const formatUptime = (seconds?: number): string => {
  if (seconds == null) return '';
  if (seconds < 60) return `${Math.round(seconds)}s up`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m up`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h up`;
  return `${Math.floor(seconds / 86400)}d up`;
};

export default function Popup() {
  const [extensionEnabled, setExtensionEnabled] = useState(true);
  const [hideAI, setHideAI] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanCount, setScanCount] = useState(0);
  const [currentTab, setCurrentTab] = useState({ title: '', url: '' });
  const [settings, setSettings] = useState<PopupSettings>(DEFAULT_SETTINGS);
  const [devStats, setDevStats] = useState<DevStatsData>({
    backend: null,
    deployedBackend: null,
    localBackend: null,
    extensionEnabled: true,
    apiMode: 'cloud',
    apiTarget: 'deployed',
    apiUrl: DEPLOYED_API_URL,
    localUrl: LOCAL_API_URL,
    deployedUrl: DEPLOYED_API_URL,
    sensitivity: 50,
    stats: {
      totalScans: 0,
      totalTextFlags: 0,
      totalImageFlags: 0,
      totalVideoFlags: 0,
      totalScoreSum: 0,
      lastScanAt: null,
      lastScanUrl: '',
      recentScans: 0
    }
  });
  const [checkingBackend, setCheckingBackend] = useState(false);
  const [isSkippedSite, setIsSkippedSite] = useState(false);

  // Load state on mount
  useEffect(() => {
    if (!IS_CHROME_EXT) return;

    // Load extension enabled state
    chrome.storage.local.get(['extensionEnabled', 'settings'], (result: any) => {
      if (result.extensionEnabled !== undefined) {
        setExtensionEnabled(result.extensionEnabled);
      }
      if (result.settings) {
        setSettings({
          enableTextScan: result.settings.enableTextScan ?? true,
          enableImageScan: result.settings.enableImageScan ?? true,
          enableVideoScan: result.settings.enableVideoScan ?? true,
          showInlineBadges: result.settings.showInlineBadges ?? true,
          showVibecodedAlert: result.settings.showVibecodedAlert ?? false,
          sensitivity: result.settings.sensitivity ?? 50,
          apiMode: result.settings.apiMode ?? 'cloud',
          apiTarget: result.settings.apiTarget ?? 'deployed',
          apiUrl: result.settings.apiUrl || DEPLOYED_API_URL,
        });
      }
    });

    // Load dev stats (backend connection status + cumulative counters)
    chrome.runtime.sendMessage({ action: 'getDevStats' }, (response: MessageResponse) => {
      if (response?.status === 'success' && response.data) {
        setDevStats(response.data as DevStatsData);
      }
    });

    // Probe the active backend and the local dev server so both status lines
    // are current when the popup opens (local status is shown either way).
    chrome.runtime.sendMessage({ action: 'checkBackend' }, (response: MessageResponse) => {
      if (response?.status === 'success' && response.data) {
        setDevStats(prev => ({ ...prev, backend: response.data as BackendStatus }));
      }
      chrome.storage.local.get(['deployedBackendStatus', 'localBackendStatus'], (res: any) => {
        setDevStats(prev => ({
          ...prev,
          deployedBackend: res.deployedBackendStatus ?? prev.deployedBackend,
          localBackend: res.localBackendStatus ?? prev.localBackend,
        }));
      });
    });

    // Get current tab info
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
      const tab = tabs[0];
      if (tab && tab.url) {
        setCurrentTab({ title: tab.title || '', url: tab.url });

        // RINSE's own site is excluded from scanning (self-referential demo
        // content reads as AI by design).
        if (isSkippedTabUrl(tab.url)) {
          setIsSkippedSite(true);
          return;
        }

        // Get scan results count
        chrome.tabs.sendMessage(tab.id, { action: 'getPageStatus' }, (response: any) => {
          if (response?.status === 'success' && response.data) {
            const total = (response.data.text?.length || 0) + (response.data.images?.length || 0);
            setScanCount(total);
          }
        });

        // Get hide AI status
        chrome.tabs.sendMessage(tab.id, { action: 'getHideAIStatus' }, (response: any) => {
          if (!chrome.runtime.lastError && response?.status === 'success') {
            setHideAI(response.isHidden ?? false);
          }
        });
      }
    });
  }, []);

  // Helper: save settings to storage and notify content script
  const updateSetting = useCallback((key: keyof PopupSettings, value: boolean | number | string) => {
    setSettings(prev => {
      const next = { ...prev, [key]: value };
      if (IS_CHROME_EXT) {
        chrome.storage.local.get(['settings'], (result: any) => {
          const updated = { ...(result.settings || {}), [key]: value };
          chrome.storage.local.set({ settings: updated });
          // Notify active tab content script
          chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
            const tab = tabs[0];
            if (tab?.id) {
              chrome.tabs.sendMessage(tab.id, { action: 'updateSettings', settings: updated });
            }
          });
        });
      }
      return next;
    });
  }, []);

  // Switch where scan verdicts come from (deployed Space or local dev server)
  const handleSelectTarget = useCallback((target: 'deployed' | 'local') => {
    setSettings(prev => ({ ...prev, apiTarget: target }));
    if (!IS_CHROME_EXT) return;
    chrome.storage.local.get(['settings'], (result: any) => {
      const updated = { ...(result.settings || {}), apiTarget: target };
      chrome.storage.local.set({ settings: updated });
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
        const tab = tabs[0];
        if (tab?.id) {
          chrome.tabs.sendMessage(tab.id, { action: 'updateSettings', settings: updated });
        }
      });
      chrome.runtime.sendMessage({ action: 'checkBackend' }, (response: MessageResponse) => {
        if (response?.status === 'success' && response.data) {
          setDevStats(prev => ({ ...prev, backend: response.data as BackendStatus, apiTarget: target }));
        }
        chrome.storage.local.get(['deployedBackendStatus', 'localBackendStatus'], (res: any) => {
          setDevStats(prev => ({
            ...prev,
            deployedBackend: res.deployedBackendStatus ?? prev.deployedBackend,
            localBackend: res.localBackendStatus ?? prev.localBackend,
          }));
        });
      });
    });
  }, []);

  // Toggle extension on/off
  const handleToggleExtension = useCallback((enabled: boolean) => {
    setExtensionEnabled(enabled);
    if (IS_CHROME_EXT) {
      chrome.storage.local.set({ extensionEnabled: enabled });
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
        const tab = tabs[0];
        if (tab?.id) {
          chrome.tabs.sendMessage(tab.id, {
            action: enabled ? 'enableExtension' : 'disableExtension',
          });
        }
      });
    }
  }, []);

  // Toggle hide AI content
  const handleToggleHideAI = useCallback(() => {
    const next = !hideAI;
    setHideAI(next);
    if (IS_CHROME_EXT) {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
        const tab = tabs[0];
        if (tab?.id) {
          chrome.tabs.sendMessage(tab.id, { action: 'toggleHideAI', hide: next }, (response: any) => {
            if (response?.status === 'success') {
              setHideAI(response.isHidden ?? next);
            }
          });
        }
      });
    }
  }, [hideAI]);

  // Run scan
  const handleScan = useCallback(() => {
    if (scanning || !IS_CHROME_EXT) return;
    if (isSkippedSite) return; // RINSE does not scan its own website
    setScanning(true);

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
      const tab = tabs[0];
      if (tab?.id) {
        chrome.tabs.sendMessage(tab.id, {
          action: 'runScan',
          options: {
            text: settings.enableTextScan,
            images: settings.enableImageScan,
            videos: settings.enableVideoScan,
          },
        }, (response: any) => {
          setScanning(false);
          if (response?.status === 'success' && response.data) {
            const total = (response.data.text?.length || 0) + (response.data.images?.length || 0);
            setScanCount(total);
          }
        });
      }
    });
  }, [scanning, isSkippedSite, settings.enableTextScan, settings.enableImageScan, settings.enableVideoScan]);

  // Re-ping the backend health endpoint
  const handleCheckBackend = useCallback(() => {
    if (!IS_CHROME_EXT || checkingBackend) return;
    setCheckingBackend(true);
    chrome.runtime.sendMessage({ action: 'checkBackend' }, (response: MessageResponse) => {
      setCheckingBackend(false);
      if (response?.status === 'success' && response.data) {
        setDevStats(prev => ({ ...prev, backend: response.data as BackendStatus }));
      }
    });
  }, [checkingBackend]);

  const handleOpenDashboard = useCallback(() => {
    if (IS_CHROME_EXT) {
      const dashboardUrl = chrome.runtime.getURL('index.html');
      chrome.tabs.create({ url: dashboardUrl });
    } else {
      window.open(window.location.pathname, '_blank');
    }
  }, []);

  const isInternal = currentTab.url?.startsWith('chrome://') || currentTab.url?.startsWith('chrome-extension://');
  const isDisabled = !extensionEnabled;
  // Skipped site: same UX treatment as chrome:// pages — scanning actions are
  // disabled and the button explains why.
  const isExcluded = isInternal || isSkippedSite;

  return (
    <div className="popup-root">
      {/* Header */}
      <div className="popup-header">
        <div className="popup-logo">
          <div>
            <h1 className="popup-title">RINSE</h1>
            <p className="popup-subtitle">Remove Inauthentic Noise</p>
          </div>
        </div>
        <span className="popup-version">v1.0</span>
      </div>

      {/* Master Toggle */}
      <div className="popup-toggle-master">
        <div className="popup-toggle-info">
          <span className="popup-toggle-label">Extension Active</span>
          <span className={`popup-toggle-status ${extensionEnabled ? 'on' : 'off'}`}>
            {extensionEnabled ? 'ON' : 'OFF'}
          </span>
        </div>
        <label className="popup-switch">
          <input
            type="checkbox"
            checked={extensionEnabled}
            onChange={(e) => handleToggleExtension(e.target.checked)}
          />
          <span className="popup-slider" />
        </label>
      </div>

      {/* Backend target — where scan verdicts come from */}
      <div className="popup-target">
        <span className="popup-target-label">Results from</span>
        <div className="popup-target-group">
          <button
            type="button"
            className={`popup-target-btn ${settings.apiTarget === 'deployed' ? 'active' : ''}`}
            onClick={() => handleSelectTarget('deployed')}
            disabled={isDisabled}
          >
            Deployed
          </button>
          <button
            type="button"
            className={`popup-target-btn ${settings.apiTarget === 'local' ? 'active' : ''}`}
            onClick={() => handleSelectTarget('local')}
            disabled={isDisabled}
          >
            Local
          </button>
        </div>
      </div>

      {/* Toggle List */}
      <div className="popup-toggles">
        {/* Text Scanning */}
        <div className="popup-toggle-row">
          <div className="popup-toggle-info">
            <Scan size={13} className="popup-toggle-icon" />
            <div>
              <span className="popup-toggle-label">Text Scanning</span>
              <span className="popup-toggle-desc">Analyze text blocks for AI patterns</span>
            </div>
          </div>
          <label className="popup-switch">
            <input
              type="checkbox"
              checked={settings.enableTextScan}
              onChange={(e) => updateSetting('enableTextScan', e.target.checked)}
              disabled={isDisabled}
            />
            <span className="popup-slider" />
          </label>
        </div>

        {/* Image Scanning */}
        <div className="popup-toggle-row">
          <div className="popup-toggle-info">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="popup-toggle-icon"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
            <div>
              <span className="popup-toggle-label">Image Scanning</span>
              <span className="popup-toggle-desc">Check EXIF metadata and visual markers</span>
            </div>
          </div>
          <label className="popup-switch">
            <input
              type="checkbox"
              checked={settings.enableImageScan}
              onChange={(e) => updateSetting('enableImageScan', e.target.checked)}
              disabled={isDisabled}
            />
            <span className="popup-slider" />
          </label>
        </div>

        {/* Hide AI Content */}
        <div className="popup-toggle-row">
          <div className="popup-toggle-info">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="popup-toggle-icon"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            <div>
              <span className="popup-toggle-label">Hide AI Content</span>
              <span className="popup-toggle-desc">Automatically hide flagged elements on page</span>
            </div>
          </div>
          <label className="popup-switch">
            <input
              type="checkbox"
              checked={hideAI}
              onChange={handleToggleHideAI}
              disabled={isDisabled}
            />
            <span className="popup-slider" />
          </label>
        </div>

        {/* Show Inline Badges */}
        <div className="popup-toggle-row">
          <div className="popup-toggle-info">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="popup-toggle-icon"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
            <div>
              <span className="popup-toggle-label">Show Badges</span>
              <span className="popup-toggle-desc">Display AI percentage badges on flagged content</span>
            </div>
          </div>
          <label className="popup-switch">
            <input
              type="checkbox"
              checked={settings.showInlineBadges}
              onChange={(e) => updateSetting('showInlineBadges', e.target.checked)}
              disabled={isDisabled}
            />
            <span className="popup-slider" />
          </label>
        </div>

        {/* VibeCoded Alert */}
        <div className="popup-toggle-row">
          <div className="popup-toggle-info">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="popup-toggle-icon"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <div>
              <span className="popup-toggle-label">VibeCoded Alerts</span>
              <span className="popup-toggle-desc">Warn when visiting AI-generated websites</span>
            </div>
          </div>
          <label className="popup-switch">
            <input
              type="checkbox"
              checked={settings.showVibecodedAlert}
              onChange={(e) => updateSetting('showVibecodedAlert', e.target.checked)}
              disabled={isDisabled}
            />
            <span className="popup-slider" />
          </label>
        </div>
      </div>

      {/* Dev Tools (backend connectivity + stats) */}
      {IS_CHROME_EXT && (
        <div className="popup-dev">
          <div className="popup-dev-header">
            <span className="popup-dev-title">
              <Server size={11} />
              DEV TOOLS
            </span>
            <button
              className="popup-dev-retest"
              onClick={handleCheckBackend}
              disabled={checkingBackend}
            >
              <RefreshCw size={10} className={checkingBackend ? 'popup-spinner-icon' : ''} />
              {checkingBackend ? 'Testing...' : 'Re-test'}
            </button>
          </div>

          {/* Deployed HF Space — always its own line */}
          <div className="popup-dev-row" title={devStats.deployedUrl}>
            <span className="popup-dev-label">HF backend</span>
            <span className="popup-dev-value">
              <span className={`popup-dev-dot ${devStats.deployedBackend ? (devStats.deployedBackend.connected ? 'ok' : 'err') : 'idle'}`} />
              {devStats.deployedBackend === null ? 'Unknown' : devStats.deployedBackend.connected ? 'Connected' : 'Not connected'}
            </span>
          </div>

          {/* Local dev server — always its own line */}
          <div className="popup-dev-row" title={devStats.localUrl}>
            <span className="popup-dev-label">Local</span>
            <span className="popup-dev-value">
              <span className={`popup-dev-dot ${devStats.localBackend ? (devStats.localBackend.connected ? 'ok' : 'err') : 'idle'}`} />
              {devStats.localBackend === null ? 'Unknown' : devStats.localBackend.connected ? 'Connected' : 'Not connected'}
            </span>
          </div>

          {devStats.deployedBackend && (
            <>
              <div className="popup-dev-row">
                <span className="popup-dev-label">Endpoint</span>
                <span className="popup-dev-value popup-dev-url" title={devStats.deployedBackend.url}>
                  {devStats.deployedBackend.url}
                </span>
              </div>
              {devStats.deployedBackend.connected && devStats.deployedBackend.server ? (
                <>
                  <div className="popup-dev-row">
                    <span className="popup-dev-label">Latency</span>
                    <span className="popup-dev-value">{devStats.deployedBackend.latencyMs != null ? `${devStats.deployedBackend.latencyMs} ms` : '—'}</span>
                  </div>
                  <div className="popup-dev-row">
                    <span className="popup-dev-label">Server</span>
                    <span className="popup-dev-value">
                      v{devStats.deployedBackend.server.version ?? '?'} · {devStats.deployedBackend.server.mode ?? 'heuristic'} · {formatUptime(devStats.deployedBackend.server.uptime_seconds) || '—'}
                    </span>
                  </div>
                  <div className="popup-dev-row">
                    <span className="popup-dev-label">DetectZoo</span>
                    <span className="popup-dev-value">{devStats.deployedBackend.server.detectzoo_loaded ? 'loaded' : 'fallback'}</span>
                  </div>
                </>
              ) : (
                <div className="popup-dev-row">
                  <span className="popup-dev-label">Error</span>
                  <span className="popup-dev-value popup-dev-err">{devStats.deployedBackend.error ?? 'failed'}</span>
                </div>
              )}
            </>
          )}

          {/* Engine mode */}
          <div className="popup-dev-row">
            <span className="popup-dev-label">Engine</span>
            <span className="popup-dev-value popup-dev-url" title={devStats.apiUrl}>
              {devStats.apiMode === 'cloud' ? (devStats.apiUrl ? `Cloud API · ${devStats.apiUrl}` : 'Cloud API') : 'Heuristics (Offline)'}
            </span>
          </div>

          {/* Scan stats */}
          <div className="popup-dev-stats">
            <div className="popup-dev-stat">
              <span className="popup-dev-stat-num">{devStats.stats.totalScans}</span>
              <span className="popup-dev-stat-label">SCANS</span>
            </div>
            <div className="popup-dev-stat">
              <span className="popup-dev-stat-num">{devStats.stats.totalTextFlags}</span>
              <span className="popup-dev-stat-label">TEXT</span>
            </div>
            <div className="popup-dev-stat">
              <span className="popup-dev-stat-num">{devStats.stats.totalImageFlags}</span>
              <span className="popup-dev-stat-label">IMG</span>
            </div>
            <div className="popup-dev-stat">
              <span className="popup-dev-stat-num">{devStats.stats.totalVideoFlags}</span>
              <span className="popup-dev-stat-label">VID</span>
            </div>
          </div>

          {devStats.stats.lastScanAt && (
            <div className="popup-dev-row">
              <span className="popup-dev-label">Last scan</span>
              <span className="popup-dev-value popup-dev-url" title={devStats.stats.lastScanUrl || ''}>
                {formatRelativeTime(devStats.stats.lastScanAt)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Scan Button */}
      <button
        className="popup-scan-btn"
        onClick={handleScan}
        disabled={isDisabled || scanning || isExcluded}
      >
        {scanning ? (
          <>
            <RefreshCw size={13} className="popup-spinner-icon" />
            Scanning...
          </>
        ) : isSkippedSite ? (
          <>
            <Shield size={13} />
            Not scanned — RINSE's own site
          </>
        ) : scanCount > 0 ? (
          <>
            <RefreshCw size={13} />
            Re-scan ({scanCount} found)
          </>
        ) : (
          <>
            <Scan size={13} />
            Scan This Page
          </>
        )}
      </button>

      {/* Open Dashboard */}
      <button className="popup-dashboard-btn" onClick={handleOpenDashboard}>
        <ExternalLink size={13} />
        Open Full Dashboard
      </button>

      {/* Current page info */}
      {currentTab.title && !isExcluded && (
        <div className="popup-page-info">
          <span className="popup-page-title">{currentTab.title}</span>
        </div>
      )}

      {/* Skipped-site notice */}
      {isSkippedSite && (
        <div className="popup-page-info">
          <span className="popup-page-title">
            This is RINSE's website — scanning is skipped here by design, so the
            site's own AI-content demos can't produce false flags.
          </span>
        </div>
      )}
    </div>
  );
}
