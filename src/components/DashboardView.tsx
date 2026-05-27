import React, { useMemo } from 'react';
import type { Trend, ScannerBot, LogEntry } from '../types';
import { 
  Activity, 
  TrendingUp, 
  Terminal, 
  Hash, 
  Trash2, 
  BarChart2,
  TrendingDown
} from 'lucide-react';
import { BrandIcon } from './BrandIcon';

interface DashboardViewProps {
  trends: Trend[];
  bots: ScannerBot[];
  logs: LogEntry[];
  onToggleBot: (botId: string) => void;
  onClearLogs: () => void;
  onViewTrendDetails: (trend: Trend) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  trends,
  bots,
  logs,
  onClearLogs,
  onViewTrendDetails
}) => {
  // Stat calculations
  const totalBots = bots.length;
  const activeBots = bots.filter(b => b.status !== 'idle').length;
  
  const totalTrackers = useMemo(() => {
    const allKeywords = bots.flatMap(b => b.trackers);
    return new Set(allKeywords).size;
  }, [bots]);

  const highGrowthCount = useMemo(() => {
    return trends.filter(t => t.growth > 100).length;
  }, [trends]);

  const topCategory = useMemo(() => {
    const counts: Record<string, number> = {};
    trends.forEach(t => {
      counts[t.category] = (counts[t.category] || 0) + t.volume;
    });
    let bestCat = 'None';
    let bestVal = 0;
    Object.entries(counts).forEach(([cat, val]) => {
      if (val > bestVal) {
        bestVal = val;
        bestCat = cat;
      }
    });
    return bestCat;
  }, [trends]);

  // Aggregate platforms share across all trends
  const platformShare = useMemo(() => {
    let tw = 0, ig = 0, yt = 0;
    trends.forEach(t => {
      tw += t.volume * (t.platforms.twitter / 100);
      ig += t.volume * (t.platforms.instagram / 100);
      yt += t.volume * (t.platforms.youtube / 100);
    });
    const total = tw + ig + yt || 1;
    return {
      twitter: Math.round((tw / total) * 100),
      instagram: Math.round((ig / total) * 100),
      youtube: Math.round((yt / total) * 100),
    };
  }, [trends]);

  // Sort and pick top 3 trends by volume
  const topTrends = useMemo(() => {
    return [...trends].sort((a, b) => b.volume - a.volume).slice(0, 3);
  }, [trends]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      
      {/* Stats Widgets */}
      <div className="stats-grid">
        <div className="glass-panel stat-widget">
          <div>
            <span className="stat-label">Active Scanners</span>
            <div className="stat-val">{activeBots}<span style={{ color: 'var(--text-muted)', fontSize: '1.25rem', fontWeight: 500 }}>/{totalBots}</span></div>
            <div className="stat-change up" style={{ color: activeBots > 0 ? 'var(--success)' : 'var(--text-muted)' }}>
              <span className="status-dot-pulse" style={{ animationDuration: '2s', width: '6px', height: '6px', display: activeBots > 0 ? 'inline-block' : 'none' }}></span>
              {activeBots > 0 ? 'Scanning Feeds Live' : 'All Bots Idle'}
            </div>
          </div>
          <div className="stat-icon-wrapper">
            <Activity size={20} />
          </div>
        </div>

        <div className="glass-panel stat-widget">
          <div>
            <span className="stat-label">Tracked Keywords</span>
            <div className="stat-val">{totalTrackers}</div>
            <div className="stat-change up">
              <TrendingUp size={12} /> Live Scraper Filters
            </div>
          </div>
          <div className="stat-icon-wrapper">
            <Hash size={20} />
          </div>
        </div>

        <div className="glass-panel stat-widget">
          <div>
            <span className="stat-label">Surging Trends</span>
            <div className="stat-val">{highGrowthCount}</div>
            <div className="stat-change up" style={{ color: 'var(--accent-pink)' }}>
              <TrendingUp size={12} /> Growth rate &gt; 100%
            </div>
          </div>
          <div className="stat-icon-wrapper">
            <TrendingUp size={20} />
          </div>
        </div>

        <div className="glass-panel stat-widget">
          <div>
            <span className="stat-label">Dominant Niche</span>
            <div className="stat-val" style={{ fontSize: '1.25rem', marginTop: '1rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '170px' }}>
              {topCategory}
            </div>
            <div className="stat-change" style={{ color: 'var(--accent-blue)' }}>
              <BarChart2 size={12} /> By Total Scan volume
            </div>
          </div>
          <div className="stat-icon-wrapper">
            <BarChart2 size={20} />
          </div>
        </div>
      </div>

      {/* Main Panel Content: Chart & Ticker/Console */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '1.5rem' }}>
        
        {/* Left Column: Live Analytics Overview */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          {/* Top Trends Widget */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 style={{ fontSize: '1rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <TrendingUp size={16} className="color-twitter" /> Top Velocity Social Trends
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {topTrends.map((trend) => (
                <div 
                  key={trend.id} 
                  className="glass-card" 
                  style={{ padding: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                  onClick={() => onViewTrendDetails(trend)}
                >
                  <div>
                    <span className="trend-category-tag" style={{ fontSize: '0.7rem' }}>{trend.category}</span>
                    <h4 style={{ fontSize: '1rem', fontWeight: 700, marginTop: '0.2rem' }}>{trend.name}</h4>
                    <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                      Scan Volume: {(trend.volume).toLocaleString()} mentions
                    </p>
                  </div>
                  
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: trend.growth > 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 700, fontSize: '0.9rem' }}>
                      {trend.growth > 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                      +{trend.growth}%
                    </div>
                    <span className="momentum-badge surging" style={{ fontSize: '0.6rem', marginTop: '0.25rem', display: 'inline-block', padding: '0.1rem 0.4rem' }}>
                      {trend.momentum}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Platform Share Overview */}
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 style={{ fontSize: '1rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
              Platform Scanner Density
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--platform-twitter)', fontWeight: 600 }}>
                    <BrandIcon platform="twitter" size={14} /> Twitter / X Scrapers
                  </span>
                  <span style={{ fontWeight: 700 }}>{platformShare.twitter}%</span>
                </div>
                <div className="demog-bar-outer" style={{ height: '8px' }}>
                  <div className="demog-bar-inner" style={{ width: `${platformShare.twitter}%`, background: 'var(--platform-twitter)' }}></div>
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--platform-instagram)', fontWeight: 600 }}>
                    <BrandIcon platform="instagram" size={14} /> Instagram API Scanners
                  </span>
                  <span style={{ fontWeight: 700 }}>{platformShare.instagram}%</span>
                </div>
                <div className="demog-bar-outer" style={{ height: '8px' }}>
                  <div className="demog-bar-inner" style={{ width: `${platformShare.instagram}%`, background: 'linear-gradient(90deg, #f39c12, #e1306c, #9b59b6)' }}></div>
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--platform-youtube)', fontWeight: 600 }}>
                    <BrandIcon platform="youtube" size={14} /> YouTube Semantic Bots
                  </span>
                  <span style={{ fontWeight: 700 }}>{platformShare.youtube}%</span>
                </div>
                <div className="demog-bar-outer" style={{ height: '8px' }}>
                  <div className="demog-bar-inner" style={{ width: `${platformShare.youtube}%`, background: 'var(--platform-youtube)' }}></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Live Terminal Console Logs */}
        <div className="glass-panel console-panel">
          <div className="console-header">
            <span className="console-title">
              <Terminal size={16} className="color-twitter" /> Real-time Scanner Output
            </span>
            <button 
              className="btn btn-secondary" 
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
              onClick={onClearLogs}
              title="Clear Terminal logs"
            >
              <Trash2 size={12} /> Clear Logs
            </button>
          </div>

          <div className="console-body">
            {logs.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: '4rem', fontStyle: 'italic' }}>
                &gt;_ Awaiting scanner pipelines to initialize...
              </div>
            ) : (
              logs.map((log) => (
                <div key={log.id} className={`log-line ${log.type === 'success' ? 'success' : ''} ${log.type === 'alert' ? 'alert' : ''}`}>
                  <span className="log-time">[{log.timestamp}]</span>
                  <span className={`log-tag ${log.platform}`}>
                    {log.botName.split('-')[0].toLowerCase()}
                  </span>
                  <span className="log-message">
                    {log.type === 'alert' ? '💥 ' : ''}
                    {log.message}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

      </div>
    </div>
  );
};
