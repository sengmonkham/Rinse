import { useState, useEffect, useCallback } from 'react';
import { Shield, ExternalLink, Scan, RefreshCw } from 'lucide-react';

interface PopupSettings {
  enableTextScan: boolean;
  enableImageScan: boolean;
  enableVideoScan: boolean;
  showInlineBadges: boolean;
  showVibecodedAlert: boolean;
  sensitivity: number;
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
};

export default function Popup() {
  const [extensionEnabled, setExtensionEnabled] = useState(true);
  const [hideAI, setHideAI] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanCount, setScanCount] = useState(0);
  const [currentTab, setCurrentTab] = useState({ title: '', url: '' });
  const [settings, setSettings] = useState<PopupSettings>(DEFAULT_SETTINGS);

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
        });
      }
    });

    // Get current tab info
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
      const tab = tabs[0];
      if (tab && tab.url) {
        setCurrentTab({ title: tab.title || '', url: tab.url });

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
  const updateSetting = useCallback((key: keyof PopupSettings, value: boolean | number) => {
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
  }, [scanning, settings.enableTextScan, settings.enableImageScan, settings.enableVideoScan]);

  // Open full dashboard in new tab
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

  return (
    <div className="popup-root">
      {/* Header */}
      <div className="popup-header">
        <div className="popup-logo">
          <div className="popup-logo-icon">
            <Shield size={16} color="#ffffff" />
          </div>
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

      {/* Scan Button */}
      <button
        className="popup-scan-btn"
        onClick={handleScan}
        disabled={isDisabled || scanning || isInternal}
      >
        {scanning ? (
          <>
            <RefreshCw size={13} className="popup-spinner-icon" />
            Scanning...
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
      {currentTab.title && !isInternal && (
        <div className="popup-page-info">
          <span className="popup-page-title">{currentTab.title}</span>
        </div>
      )}
    </div>
  );
}
