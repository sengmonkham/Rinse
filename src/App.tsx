import { useState } from 'react';
import { useTrendSimulator } from './hooks/useTrendSimulator';
import { DashboardView } from './components/DashboardView';
import { DirectoryView } from './components/DirectoryView';
import { BotManagerView } from './components/BotManagerView';
import { ReportsView } from './components/ReportsView';
import { LeadRadarView } from './components/LeadRadarView';
import { AlertNotification } from './components/AlertNotification';
import type { Trend, ViewType } from './types';
import { 
  LayoutDashboard, 
  Compass, 
  Cpu, 
  FileText, 
  Sparkles,
  Terminal,
  RefreshCw,
  Target,
  Bell
} from 'lucide-react';

function App() {
  const [activeTab, setActiveTab] = useState<ViewType>('dashboard');
  const [selectedDetailedTrend, setSelectedDetailedTrend] = useState<Trend | null>(null);

  const {
    trends,
    bots,
    logs,
    alerts,
    leads,
    businessProfile,
    clearLogs,
    toggleBot,
    addTrackerToBot,
    removeTrackerFromBot,
    addWatchedAccount,
    dismissAlert,
    updateLeadStatus,
    updateBusinessProfile,
  } = useTrendSimulator();

  const activeBots = bots.filter(b => b.status !== 'idle').length;
  const hotLeadCount = leads.filter(l => l.isHot && l.status !== 'dismissed').length;
  const activeAlertCount = alerts.filter(a => !a.dismissed).length;

  const handleViewTrendFromAlert = (trendId: string) => {
    const trend = trends.find(t => t.id === trendId);
    if (trend) {
      setSelectedDetailedTrend(trend);
      setActiveTab('directory');
    }
  };

  const getHeaderTitle = () => {
    switch (activeTab) {
      case 'dashboard': return 'Dashboard';
      case 'directory': return 'Trend Directory';
      case 'bots': return 'Scraper Bots';
      case 'reports': return 'Reports & Alerts';
      case 'leads': return '🎯 Lead Radar';
      default: return '';
    }
  };

  const getHeaderDescription = () => {
    switch (activeTab) {
      case 'dashboard': return 'Real-time aggregated social intelligence — hot trends, emerging signals, and platform-specific feeds.';
      case 'directory': return 'Browse active trends filtered by platform origin, type, and heat score. Click any card for full intel.';
      case 'bots': return 'Configure virtual micro-scrapers, account watchlists, and active crawler intent modes.';
      case 'reports': return 'Compile intelligence briefs and track high-velocity spike events across all platforms.';
      case 'leads': return 'Buyer intent detection — identify potential customers with purchasing power profiling and tier-adapted outreach.';
      default: return '';
    }
  };

  const renderActiveView = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <DashboardView 
            trends={trends} 
            bots={bots} 
            logs={logs}
            alerts={alerts}
            hotLeadCount={hotLeadCount}
            onClearLogs={clearLogs}
            onViewTrendDetails={(trend) => {
              setSelectedDetailedTrend(trend);
              setActiveTab('directory');
            }}
            onGoToLeads={() => setActiveTab('leads')}
          />
        );
      case 'directory':
        return (
          <DirectoryView 
            trends={trends} 
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
            onAddWatchedAccount={addWatchedAccount}
          />
        );
      case 'reports':
        return (
          <ReportsView 
            trends={trends} 
            logs={logs}
          />
        );
      case 'leads':
        return (
          <LeadRadarView
            leads={leads}
            businessProfile={businessProfile}
            onUpdateStatus={updateLeadStatus}
            onUpdateBusinessProfile={updateBusinessProfile}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="app-container">
      
      {/* Alert Notification Stack */}
      <AlertNotification
        alerts={alerts}
        onDismiss={dismissAlert}
        onViewTrend={handleViewTrendFromAlert}
        onViewLead={() => setActiveTab('leads')}
      />

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
            {/* Lead Radar */}
            <li 
              className={`sidebar-item ${activeTab === 'leads' ? 'active' : ''}`}
              onClick={() => setActiveTab('leads')}
              style={{ position: 'relative' }}
            >
              <Target size={18} />
              <span>Lead Radar</span>
              {hotLeadCount > 0 && (
                <span style={{
                  marginLeft: 'auto',
                  background: '#ef4444',
                  color: '#fff',
                  borderRadius: '9999px',
                  fontSize: '0.65rem',
                  fontWeight: 800,
                  padding: '0.1rem 0.4rem',
                  lineHeight: 1.5,
                  minWidth: '18px',
                  textAlign: 'center',
                  animation: 'hot-lead-pulse 2s ease-in-out infinite',
                }}>
                  {hotLeadCount}
                </span>
              )}
            </li>
          </ul>
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-version">
            <Terminal size={12} />
            <span>Engine v3.0-radar</span>
          </div>
          <div className="sidebar-version">
            <RefreshCw size={12} style={{ animation: activeBots > 0 ? 'spin 4s linear infinite' : 'none' }} />
            <span>{activeBots > 0 ? `${activeBots} bots active` : 'Scanners idle'}</span>
          </div>
          {activeAlertCount > 0 && (
            <div 
              className="sidebar-version"
              style={{ color: '#f87171', cursor: 'pointer' }}
              onClick={() => setActiveTab('reports')}
            >
              <Bell size={12} />
              <span>{activeAlertCount} alerts live</span>
            </div>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        <header className="main-header">
          <div className="header-title-container">
            <h1>{getHeaderTitle()}</h1>
            <p>{getHeaderDescription()}</p>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            {activeBots > 0 ? (
              <div className="scanner-status-tag">
                <span className="status-dot-pulse"></span>
                <span>{activeBots} Scrapers Live</span>
              </div>
            ) : (
              <div className="scanner-status-tag" style={{ color: 'var(--text-muted)', borderColor: 'rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
                <span className="status-dot-pulse" style={{ backgroundColor: 'var(--text-muted)', animation: 'none' }}></span>
                <span>Scrapers Suspended</span>
              </div>
            )}

            {hotLeadCount > 0 && (
              <div
                style={{ padding: '0.5rem 0.85rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '9999px', cursor: 'pointer', color: '#f87171', fontSize: '0.8rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.35rem' }}
                onClick={() => setActiveTab('leads')}
              >
                🔴 {hotLeadCount} Hot Lead{hotLeadCount > 1 ? 's' : ''}
              </div>
            )}
            
            <div 
              style={{ padding: '0.5rem', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--panel-border)', borderRadius: '50%', cursor: 'pointer', color: activeAlertCount > 0 ? 'var(--accent-pink)' : 'var(--text-muted)', position: 'relative' }}
              title="Notifications"
              onClick={() => setActiveTab('reports')}
            >
              <Bell size={18} />
              {activeAlertCount > 0 && (
                <span style={{ position: 'absolute', top: '-2px', right: '-2px', width: '8px', height: '8px', background: 'var(--accent-pink)', borderRadius: '50%', border: '2px solid var(--bg-primary)' }} />
              )}
            </div>
          </div>
        </header>

        {/* Dynamic View Injection */}
        {renderActiveView()}
      </main>

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
