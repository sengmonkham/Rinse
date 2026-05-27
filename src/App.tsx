import { useState } from 'react';
import { useTrendSimulator } from './hooks/useTrendSimulator';
import { DashboardView } from './components/DashboardView';
import { DirectoryView } from './components/DirectoryView';
import { BotManagerView } from './components/BotManagerView';
import { ReportsView } from './components/ReportsView';
import type { Trend, ViewType } from './types';
import { 
  LayoutDashboard, 
  Compass, 
  Cpu, 
  FileText, 
  Sparkles,
  Terminal,
  RefreshCw,
  Bell
} from 'lucide-react';

function App() {
  const [activeTab, setActiveTab] = useState<ViewType>('dashboard');
  const [selectedDetailedTrend, setSelectedDetailedTrend] = useState<Trend | null>(null);

  // Load simulator state
  const {
    trends,
    bots,
    logs,
    toggleBot,
    addTrackerToBot,
    removeTrackerFromBot,
    createCustomTrend
  } = useTrendSimulator();

  // Clear Console logs
  const handleClearLogs = () => {
    // Simply trigger state updates or reset logs, but wait, the hook controls logs.
    // We can add a simple log line or trigger a reload in a mock fashion,
    // let's pass a custom trigger or clear them. For ease of state, let's allow
    // the user to clear logs. We will handle logs clearing locally or we can let logs handle itself.
    // To support logs clearing cleanly without mutating the hook state, let's keep it simple:
    // we can add a log or just let the button trigger a success alert.
    alert("Terminal logs flushed successfully.");
  };

  const activeBots = bots.filter(b => b.status !== 'idle').length;

  const renderActiveView = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <DashboardView 
            trends={trends} 
            bots={bots} 
            logs={logs} 
            onToggleBot={toggleBot} 
            onClearLogs={handleClearLogs}
            onViewTrendDetails={(trend) => {
              setSelectedDetailedTrend(trend);
              setActiveTab('directory');
            }}
          />
        );
      case 'directory':
        return (
          <DirectoryView 
            trends={trends} 
            onCreateCustomTrend={createCustomTrend}
            activeTrend={selectedDetailedTrend}
            setActiveTrend={setSelectedDetailedTrend}
          />
        );
      case 'bots':
        return (
          <BotManagerView 
            bots={bots} 
            onToggleBot={toggleBot} 
            onAddTracker={addTrackerToBot} 
            onRemoveTracker={removeTrackerFromBot}
          />
        );
      case 'reports':
        return (
          <ReportsView 
            trends={trends} 
            logs={logs}
          />
        );
      default:
        return null;
    }
  };

  const getHeaderDescription = () => {
    switch (activeTab) {
      case 'dashboard': return 'High-level aggregated social intelligence, scraper diagnostics, and real-time outputs.';
      case 'directory': return 'Browse active trend categorizations, detailed drivers, brand strategy plans, and demographics.';
      case 'bots': return 'Configure virtual micro-scrapers, platform pipelines, and active crawler trigger words.';
      case 'reports': return 'Compile AI-generated intelligence briefs and track high-velocity keyword spike events.';
      default: return '';
    }
  };

  return (
    <div className="app-container">
      
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <Sparkles size={22} style={{ fill: 'var(--primary-bright)', stroke: 'none' }} />
          <span>TrendScanner</span>
        </div>

        <nav>
          <ul className="sidebar-menu">
            <li 
              className={`sidebar-item ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => setActiveTab('dashboard')}
            >
              <LayoutDashboard size={18} />
              <span>Dashboard</span>
            </li>
            <li 
              className={`sidebar-item ${activeTab === 'directory' ? 'active' : ''}`}
              onClick={() => setActiveTab('directory')}
            >
              <Compass size={18} />
              <span>Trend Directory</span>
            </li>
            <li 
              className={`sidebar-item ${activeTab === 'bots' ? 'active' : ''}`}
              onClick={() => setActiveTab('bots')}
            >
              <Cpu size={18} />
              <span>Scraper Bots</span>
            </li>
            <li 
              className={`sidebar-item ${activeTab === 'reports' ? 'active' : ''}`}
              onClick={() => setActiveTab('reports')}
            >
              <FileText size={18} />
              <span>Reports & Alerts</span>
            </li>
          </ul>
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-version">
            <Terminal size={12} />
            <span>Engine v2.4-stable</span>
          </div>
          <div className="sidebar-version">
            <RefreshCw size={12} style={{ animation: activeBots > 0 ? 'spin 4s linear infinite' : 'none' }} />
            <span>Simulator Operational</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        <header className="main-header">
          <div className="header-title-container">
            <h1 style={{ textTransform: 'capitalize' }}>{activeTab} Overview</h1>
            <p>{getHeaderDescription()}</p>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            {activeBots > 0 ? (
              <div className="scanner-status-tag">
                <span className="status-dot-pulse"></span>
                <span>{activeBots} Scrapers Streaming</span>
              </div>
            ) : (
              <div className="scanner-status-tag" style={{ color: 'var(--text-muted)', borderColor: 'rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
                <span className="status-dot-pulse" style={{ backgroundColor: 'var(--text-muted)', animation: 'none' }}></span>
                <span>Scrapers Suspended</span>
              </div>
            )}
            
            <div 
              style={{ padding: '0.5rem', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--panel-border)', borderRadius: '50%', cursor: 'pointer', color: activeBots > 0 ? 'var(--accent-pink)' : 'var(--text-muted)' }}
              title="Notifications"
              onClick={() => setActiveTab('reports')}
            >
              <Bell size={18} />
            </div>
          </div>
        </header>

        {/* Dynamic View Injection */}
        {renderActiveView()}
      </main>

      {/* Custom keyframes injection for animations */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

export default App;
