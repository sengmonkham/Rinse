import { useState, useEffect } from 'react';
import { 
  Shield, 
  FileText, 
  Settings as SettingsIcon, 
  History as HistoryIcon, 
  Sparkles, 
  Globe,
  RefreshCw,
  Keyboard
} from 'lucide-react';
import DetectorDashboard from './components/DetectorDashboard';
import ContentList from './components/ContentList';
import Playground from './components/Playground';
import PageHistory from './components/PageHistory';
import Settings from './components/Settings';
import ProofOfWork from './components/ProofOfWork';

declare const chrome: any;

export interface ScanStats {
  textCount: number;
  imageCount: number;
  videoCount: number;
}

export interface ScanItem {
  id: string;
  score: number;
  reasons: string[];
  snippet?: string;
  tagName?: string;
  src?: string;
  width?: number;
  height?: number;
}

export interface ScanResults {
  text: ScanItem[];
  images: ScanItem[];
  videos: ScanItem[];
  score: number;
  scannedAt: number | null;
  vibecoded?: {
    isVibecoded: boolean;
    reasons: string[];
    hasPurpleGradient: boolean;
    hasBubbleHeader: boolean;
  };
}

export interface AppSettings {
  enableTextScan: boolean;
  enableImageScan: boolean;
  enableVideoScan: boolean;
  sensitivity: number;
  showInlineBadges: boolean;
  apiMode: string;
  apiUrl: string;
  apiKey: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'inspector' | 'playground' | 'history' | 'settings' | 'pow'>('dashboard');
  const [isStandalone, setIsStandalone] = useState(true);
  const [currentUrl, setCurrentUrl] = useState("Local Dashboard Preview");
  const [currentTitle, setCurrentTitle] = useState("Standalone Simulator");
  const [scanning, setScanning] = useState(false);
  
  const [scanResults, setScanResults] = useState<ScanResults>({
    text: [],
    images: [],
    videos: [],
    score: 100,
    scannedAt: null,
    vibecoded: {
      isVibecoded: false,
      reasons: [],
      hasPurpleGradient: false,
      hasBubbleHeader: false
    }
  });

  const [settings, setSettings] = useState<AppSettings>({
    enableTextScan: true,
    enableImageScan: true,
    enableVideoScan: true,
    sensitivity: 50,
    showInlineBadges: true,
    apiMode: "local",
    apiUrl: "",
    apiKey: ""
  });

  const [scanHistory, setScanHistory] = useState<any[]>([]);
  const [aiHidden, setAiHidden] = useState(false);

  // Detect mode & initialize
  useEffect(() => {
    const isChromeExt = typeof window !== "undefined" && typeof (window as any).chrome !== "undefined" && typeof chrome.runtime !== "undefined" && typeof chrome.runtime.id !== "undefined";
    setIsStandalone(!isChromeExt);
    
    if (isChromeExt) {
      // 1. Get current active tab info
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
        const tab = tabs[0];
        if (tab && tab.url) {
          // Ignore chrome:// internal pages
          if (tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://")) {
            setCurrentUrl("Chrome Internal Page");
            setCurrentTitle("Scanning disabled on System Pages");
            setScanResults({
              text: [],
              images: [],
              videos: [],
              score: 100,
              scannedAt: Date.now(),
              vibecoded: {
                isVibecoded: false,
                reasons: [],
                hasPurpleGradient: false,
                hasBubbleHeader: false
              }
            });
            return;
          }
          setCurrentUrl(tab.url);
          setCurrentTitle(tab.title || new URL(tab.url).hostname);
          
          // Request status from active content script
          chrome.tabs.sendMessage(tab.id!, { action: "getPageStatus" }, (response: any) => {
            if (chrome.runtime.lastError) {
              console.log("No content script listener found. (Needs manual scan trigger)");
            } else if (response && response.status === "success") {
              setScanResults(response.data);
            }
          });

          // Request hidden status from active content script
          chrome.tabs.sendMessage(tab.id!, { action: "getHideAIStatus" }, (response: any) => {
            if (!chrome.runtime.lastError && response && response.status === "success") {
              setAiHidden(response.isHidden);
            }
          });
        }
      });

      // 2. Load settings and history from extension local storage
      chrome.storage.local.get(["settings", "scanHistory"], (result: any) => {
        if (result.settings) setSettings(result.settings);
        if (result.scanHistory) setScanHistory(result.scanHistory);
      });
    } else {
      // Standalone mode: Load settings and history from localStorage
      const savedSettings = localStorage.getItem("aegis_settings");
      if (savedSettings) {
        setSettings(JSON.parse(savedSettings));
      }
      
      const savedHistory = localStorage.getItem("aegis_history");
      if (savedHistory) {
        setScanHistory(JSON.parse(savedHistory));
      }
      
      setScanResults({
        text: [],
        images: [],
        videos: [],
        score: 100,
        scannedAt: Date.now(),
        vibecoded: {
          isVibecoded: false,
          reasons: [],
          hasPurpleGradient: false,
          hasBubbleHeader: false
        }
      });
    }
  }, []);

  // Update Settings
  const handleSaveSettings = (newSettings: AppSettings) => {
    setSettings(newSettings);
    if (!isStandalone) {
      chrome.storage.local.set({ settings: newSettings });
      // Notify active tab content script of changed HUD settings
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
        const tab = tabs[0];
        if (tab && tab.id) {
          chrome.tabs.sendMessage(tab.id, { action: "toggleHUD", enabled: newSettings.showInlineBadges });
        }
      });
    } else {
      localStorage.setItem("aegis_settings", JSON.stringify(newSettings));
    }
  };

  // Trigger quick page scan
  const triggerScan = () => {
    if (scanning) return;
    setScanning(true);
    
    if (!isStandalone) {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
        const tab = tabs[0];
        if (tab && tab.id) {
          chrome.tabs.sendMessage(tab.id, { 
            action: "runScan", 
            options: {
              text: settings.enableTextScan,
              images: settings.enableImageScan,
              videos: settings.enableVideoScan
            } 
          }, (response: any) => {
            setScanning(false);
            if (response && response.status === "success") {
              setScanResults(response.data);
              // Refresh history
              chrome.storage.local.get(["scanHistory"], (result: any) => {
                if (result.scanHistory) setScanHistory(result.scanHistory);
              });
            } else {
              alert("Could not communicate with the page. Try refreshing the webpage.");
            }
          });
        }
      });
    } else {
      setTimeout(() => {
        setScanning(false);
        alert("Please load Aegis as an unpacked Chrome Extension to scan active webpages. For quick tests, use the 'Sandbox' tab!");
      }, 500);
    }
  };

  // Trigger visual deep scan laser animation
  const triggerDeepScan = () => {
    if (scanning) return;
    setScanning(true);

    if (!isStandalone) {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
        const tab = tabs[0];
        if (tab && tab.id) {
          // Close popup window so they see scan? 
          // Better to just let it run. In Chrome, keeping popup open works, or we can send message.
          chrome.tabs.sendMessage(tab.id, { action: "runDeepScan" }, (response: any) => {
            setScanning(false);
            if (response && response.status === "success") {
              setScanResults(response.data);
              chrome.storage.local.get(["scanHistory"], (result: any) => {
                if (result.scanHistory) setScanHistory(result.scanHistory);
              });
            } else {
              alert("Error executing scan. Make sure the page is fully loaded.");
            }
          });
        }
      });
    } else {
      setTimeout(() => {
        setScanning(false);
        alert("Please load Aegis as an unpacked Chrome Extension to run deep visual scans on web tabs.");
      }, 500);
    }
  };

  // Toggle hiding AI generated content
  const handleToggleHideAI = () => {
    if (isStandalone) {
      alert("Please load Aegis as an unpacked Chrome Extension to toggle content visibility.");
      setAiHidden(!aiHidden);
      return;
    }
    const nextHidden = !aiHidden;
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs: any[]) => {
      const tab = tabs[0];
      if (tab && tab.id) {
        chrome.tabs.sendMessage(tab.id, { action: "toggleHideAI", hide: nextHidden }, (response: any) => {
          if (response && response.status === "success") {
            setAiHidden(response.isHidden);
          }
        });
      }
    });
  };

  // Clear history items
  const handleClearHistory = () => {
    if (!isStandalone) {
      chrome.storage.local.set({ scanHistory: [] }, () => {
        setScanHistory([]);
      });
    } else {
      setScanHistory([]);
      localStorage.removeItem("aegis_history");
    }
  };

  return (
    <div className={`app-container glass ${isStandalone ? 'standalone-layout' : 'popup-mode'}`}>
      {/* Header */}
      <header className="app-header">
        <div className="logo-container">
          <div className="logo-icon">
            <Shield size={18} color="#070a13" style={{ fill: "#070a13" }} />
          </div>
          <div>
            <h1 className="logo-text">AEGIS AI</h1>
            <p style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Content Verifier</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isStandalone && (
            <span className="badge-version" style={{ color: '#06b6d4', background: 'rgba(6, 182, 212, 0.1)', border: '1px solid rgba(6, 182, 212, 0.2)' }}>
              DEV SIMULATOR
            </span>
          )}
          <span className="badge-version">v1.0.0</span>
        </div>
      </header>

      {/* Chrome Extension Load Guidelines */}
      {isStandalone && activeTab !== 'playground' && activeTab !== 'settings' && activeTab !== 'pow' && (
        <div className="glass" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px', borderLeft: '4px solid var(--primary)' }}>
          <h4 style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Sparkles size={14} color="var(--primary)" />
            <span>Load Aegis as a Chrome Extension</span>
          </h4>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
            To scan live webpages and use right-clicks or keyboard shortcut tracking, build and load the unpacked extension:
          </p>
          <ol style={{ fontSize: '11px', color: 'var(--text-secondary)', paddingLeft: '16px', lineHeight: '1.4', margin: '0' }}>
            <li>Run <code>npm run build</code> in the project directory.</li>
            <li>Go to <code>chrome://extensions</code> in your browser.</li>
            <li>Turn on <strong>Developer mode</strong> (top-right toggle).</li>
            <li>Click <strong>Load unpacked</strong> and select the <code>dist/</code> folder.</li>
            <li>Hover element + press <strong>Control</strong> (or <strong>Option/Alt</strong>) on any webpage to scan locally!</li>
          </ol>
        </div>
      )}

      {/* Target Address Info */}
      {activeTab !== 'playground' && activeTab !== 'settings' && activeTab !== 'pow' && (
        <div className="glass" style={{ padding: '12px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '8px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <Globe size={18} className="glow-text" style={{ color: 'var(--primary)' }} />
          </div>
          <div style={{ overflow: 'hidden', flex: '1' }}>
            <div style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-primary)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
              {currentTitle}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
              {currentUrl}
            </div>
          </div>
          <button 
            onClick={triggerScan}
            disabled={scanning || currentUrl === "Chrome Internal Page"}
            className="btn btn-secondary" 
            style={{ padding: '8px', borderRadius: '8px' }}
            title="Reload scanning"
          >
            <RefreshCw size={14} className={scanning ? 'pulse-glow' : ''} />
          </button>
        </div>
      )}

      {/* Tab Navigation */}
      <nav className="tab-navigation">
        <button 
          onClick={() => setActiveTab('dashboard')} 
          className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
        >
          <Shield size={14} />
          <span>Dashboard</span>
        </button>
        <button 
          onClick={() => setActiveTab('inspector')} 
          className={`tab-btn ${activeTab === 'inspector' ? 'active' : ''}`}
        >
          <FileText size={14} />
          <span>Matches</span>
        </button>
        <button 
          onClick={() => setActiveTab('playground')} 
          className={`tab-btn ${activeTab === 'playground' ? 'active' : ''}`}
        >
          <Sparkles size={14} />
          <span>Sandbox</span>
        </button>
        <button 
          onClick={() => setActiveTab('pow')} 
          className={`tab-btn ${activeTab === 'pow' ? 'active' : ''}`}
        >
          <Keyboard size={14} />
          <span>Writer POW</span>
        </button>
        <button 
          onClick={() => setActiveTab('history')} 
          className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
        >
          <HistoryIcon size={14} />
          <span>History</span>
        </button>
        <button 
          onClick={() => setActiveTab('settings')} 
          className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
        >
          <SettingsIcon size={14} />
          <span>Settings</span>
        </button>
      </nav>

      {/* Active Tab View */}
      <main style={{ flex: '1', minHeight: '0', display: 'flex', flexDirection: 'column' }}>
        {activeTab === 'dashboard' && (
          <DetectorDashboard 
            scanResults={scanResults} 
            scanning={scanning} 
            onScanQuick={triggerScan} 
            onScanDeep={triggerDeepScan}
            disabled={currentUrl === "Chrome Internal Page"}
            aiHidden={aiHidden}
            onToggleHideAI={handleToggleHideAI}
          />
        )}
        {activeTab === 'inspector' && (
          <ContentList 
            scanResults={scanResults} 
          />
        )}
        {activeTab === 'playground' && (
          <Playground settings={settings} />
        )}
        {activeTab === 'pow' && (
          <ProofOfWork />
        )}
        {activeTab === 'history' && (
          <PageHistory 
            history={scanHistory} 
            onClear={handleClearHistory} 
            onSelectUrl={(url) => {
              window.open(url, '_blank');
            }}
          />
        )}
        {activeTab === 'settings' && (
          <Settings 
            settings={settings} 
            onSave={handleSaveSettings} 
          />
        )}
      </main>
    </div>
  );
}
