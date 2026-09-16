import { useState, useEffect, useCallback } from 'react';
import { 
  Sparkles
} from 'lucide-react';
import Playground from './components/Playground';
import PageHistory from './components/PageHistory';
import Settings from './components/Settings';
import Popup from './components/Popup';

// Detect popup mode: Chrome extension popup appends #popup to the URL
const IS_POPUP = typeof window !== 'undefined' && window.location.hash === '#popup';

export interface SubscriptionState {
  isPaying: boolean;
  plan: string;
  status: string;
  expiresAt: string | null;
  licenseKey: string | null;
  lastChecked: number | null;
}

export interface AppSettings {
  enableTextScan: boolean;
  enableImageScan: boolean;
  enableVideoScan: boolean;
  sensitivity: number;
  showInlineBadges: boolean;
  autoImageOverlays: boolean;
  showVibecodedAlert: boolean;
  apiMode: string;
  apiUrl: string;
  apiKey: string;
  webAppUrl?: string;
  authToken?: string;
}

const DEFAULT_SETTINGS: AppSettings = {
  enableTextScan: true,
  enableImageScan: true,
  enableVideoScan: true,
  sensitivity: 50,
  showInlineBadges: true,
  autoImageOverlays: false,
  showVibecodedAlert: false,
  apiMode: "local",
  apiUrl: "",
  apiKey: "",
  webAppUrl: "http://localhost:3000",
  authToken: ""
};

// Computed once at module load — never changes during the session.
const IS_CHROME_EXT: boolean =
  typeof window !== 'undefined' &&
  typeof (window as typeof window & { chrome?: { runtime?: { id?: string } } }).chrome !== 'undefined' &&
  typeof chrome.runtime !== 'undefined' &&
  typeof chrome.runtime.id !== 'undefined';

const IS_STANDALONE = !IS_CHROME_EXT;

export default function App() {
  // Popup mode: render minimal toggle UI
  if (IS_POPUP) {
    return <Popup />;
  }

  const [activeTab, setActiveTab] = useState<'playground' | 'history' | 'settings'>('playground');

  const [settings, setSettings] = useState<AppSettings>(() => {
    if (typeof window === "undefined") return DEFAULT_SETTINGS;
    const saved = localStorage.getItem("rinse_settings");
    if (saved) {
      try {
        return { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
      } catch {
        // Ignore corrupt saved settings
      }
    }
    return DEFAULT_SETTINGS;
  });

  const [subscription, setSubscription] = useState<SubscriptionState>(() => {
    if (typeof window === "undefined") return { isPaying: false, plan: "free", status: "inactive", expiresAt: null, licenseKey: null, lastChecked: null };
    const saved = localStorage.getItem("rinse_subscription");
    if (saved) {
      try {
        return JSON.parse(saved) as SubscriptionState;
      } catch {
        // Ignore corrupt saved subscription
      }
    }
    return { isPaying: false, plan: "free", status: "inactive", expiresAt: null, licenseKey: null, lastChecked: null };
  });

  const [scanHistory, setScanHistory] = useState<ScanHistoryEntry[]>(() => {
    if (typeof window === "undefined") return [];
    const saved = localStorage.getItem("rinse_history");
    if (saved) {
      try {
        return JSON.parse(saved) as ScanHistoryEntry[];
      } catch {
        // Ignore corrupt saved history
      }
    }
    return [];
  });

  // Detect mode & initialize
  useEffect(() => {
    if (IS_CHROME_EXT) {
      // Load settings, subscription and history from extension local storage
      chrome.storage.local.get(["settings", "scanHistory", "subscriptionState"], (result: Record<string, unknown>) => {
        if (result.settings) setSettings(result.settings as AppSettings);
        if (result.scanHistory) setScanHistory(result.scanHistory as ScanHistoryEntry[]);
        if (result.subscriptionState) setSubscription(result.subscriptionState as SubscriptionState);
      });
    }
    // Standalone mode: settings, subscription and history load lazily from localStorage above.
  }, []);

  // Sync subscription status with web app
  const handleSyncSubscription = useCallback(async (): Promise<SubscriptionState> => {
    if (IS_CHROME_EXT) {
      return new Promise<SubscriptionState>((resolve) => {
        chrome.runtime.sendMessage({ action: "syncSubscription" }, (response: MessageResponse) => {
          if (response && response.status === "success" && response.data) {
            const nextState = response.data as SubscriptionState;
            setSubscription(nextState);
            resolve(nextState);
          } else {
            chrome.storage.local.get(["subscriptionState"], (res: Record<string, unknown>) => {
              const current = (res.subscriptionState as SubscriptionState) || {
                isPaying: false,
                plan: "free",
                status: "inactive",
                expiresAt: null,
                licenseKey: null,
                lastChecked: Date.now()
              };
              setSubscription(current);
              resolve(current);
            });
          }
        });
      });
    } else {
      // Standalone simulator mode
      const webUrl = (settings.webAppUrl || "http://localhost:3000").replace(/\/$/, "");
      const token = settings.authToken || settings.apiKey || "";
      if (!token) {
        const freeState: SubscriptionState = {
          isPaying: false,
          plan: "free",
          status: "inactive",
          expiresAt: null,
          licenseKey: null,
          lastChecked: Date.now()
        };
        setSubscription(freeState);
        localStorage.setItem("rinse_subscription", JSON.stringify(freeState));
        return freeState;
      }
      try {
        const res = await fetch(`${webUrl}/api/v1/me`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          const syncedState: SubscriptionState = {
            isPaying: Boolean(data.is_paying),
            plan: data.plan || "free",
            status: data.is_paying ? "active" : "inactive",
            expiresAt: data.expires_at || null,
            licenseKey: data.license_key || null,
            lastChecked: Date.now()
          };
          setSubscription(syncedState);
          localStorage.setItem("rinse_subscription", JSON.stringify(syncedState));
          return syncedState;
        } else {
          throw new Error(`HTTP ${res.status}`);
        }
      } catch (e: unknown) {
        const errMsg = e instanceof Error ? e.message : "Unknown error";
        console.warn("Sync failed in standalone mode:", errMsg);
        return subscription;
      }
    }
  }, [settings.webAppUrl, settings.authToken, settings.apiKey, subscription]);

  // Update Settings
  const handleSaveSettings = useCallback((newSettings: AppSettings) => {
    setSettings(newSettings);
    if (!IS_STANDALONE) {
      chrome.storage.local.set({ settings: newSettings });
      // Notify active tab content script of updated settings
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs: ChromeTabInfo[]) => {
        const tab = tabs[0];
        if (tab && tab.id) {
          chrome.tabs.sendMessage(tab.id, { action: "updateSettings", settings: newSettings });
        }
      });
    } else {
      localStorage.setItem("rinse_settings", JSON.stringify(newSettings));
    }
  }, []);

  // Clear history items
  const handleClearHistory = useCallback(() => {
    if (!IS_STANDALONE) {
      chrome.storage.local.set({ scanHistory: [] }, () => {
        setScanHistory([]);
      });
    } else {
      setScanHistory([]);
      localStorage.removeItem("rinse_history");
    }
  }, []);

  return (
    <div className="dashboard-root">
      {/* Header */}
      <header className="dashboard-header">
        <div className="dashboard-header-left">
          <h1 className="dashboard-logo">RINSE</h1>
          <span className="dashboard-badge">v1.0</span>
          {subscription.isPaying && (
            <span className="dashboard-badge dashboard-badge-pro">
              <Sparkles size={10} />
              {subscription.plan.toUpperCase()}
            </span>
          )}
        </div>
        <div className="dashboard-header-right"></div>
      </header>

      {/* Tab Navigation */}
      <nav className="dashboard-tabs">
        <button
          onClick={() => setActiveTab('playground')}
          className={`dashboard-tab ${activeTab === 'playground' ? 'active' : ''}`}
        >
          Sandbox
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`dashboard-tab ${activeTab === 'history' ? 'active' : ''}`}
        >
          History
        </button>
        <button
          onClick={() => setActiveTab('settings')}
          className={`dashboard-tab ${activeTab === 'settings' ? 'active' : ''}`}
        >
          Settings
        </button>
      </nav>

      {/* Active Tab View */}
      <main className="dashboard-content">
        {activeTab === 'playground' && (
          <Playground settings={settings} />
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
            subscription={subscription}
            onSyncSubscription={handleSyncSubscription}
          />
        )}
      </main>
    </div>
  );
}
