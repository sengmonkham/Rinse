import React, { useMemo } from 'react';
import type { Trend, ScannerBot, LogEntry, TrendAlert } from '../types';
import { Activity, TrendingUp, Terminal, Trash2, Zap, Target } from 'lucide-react';
import { BrandIcon } from './BrandIcon';

interface DashboardViewProps {
  trends: Trend[];
  bots: ScannerBot[];
  logs: LogEntry[];
  alerts: TrendAlert[];
  hotLeadCount: number;
  onClearLogs: () => void;
  onViewTrendDetails: (trend: Trend) => void;
  onGoToLeads: () => void;
}

const PLATFORM_COLORS: Record<string, string> = {
  twitter: 'var(--platform-twitter)',
  instagram: 'var(--platform-instagram)',
  youtube: 'var(--platform-youtube)',
};

const HEAT_CLASS = (score: number) =>
  score >= 90 ? 'fire' : score >= 75 ? 'hot' : score >= 55 ? 'rising' : 'cool';

const TREND_TYPE_ICONS: Record<string, string> = {
  breaking: '🔴',
  controversial: '⚡',
  viral: '🚀',
  uprising: '📡',
  fading: '📉',
};

export const DashboardView: React.FC<DashboardViewProps> = ({
  trends, bots, logs, alerts, hotLeadCount, onClearLogs, onViewTrendDetails, onGoToLeads
}) => {
  const activeBots = bots.filter(b => b.status !== 'idle').length;
  const totalBots = bots.length;

  const trendBots = bots.filter(b => b.mode === 'trend');
  const totalSignals = trendBots.reduce((s, b) => s + b.signalsDetected, 0);
  const emergingCount = trends.filter(t => t.emergenceScore >= 55 && t.volume < 300000).length;

  const topTrend = useMemo(() => [...trends].sort((a, b) => b.heatScore - a.heatScore)[0], [trends]);

  // Platform columns: top 3 per platform by heat score
  const platformTrends = useMemo(() => {
    const byPlatform = (p: string) =>
      [...trends]
        .filter(t => t.platformOrigin === p || t.platforms[p as keyof typeof t.platforms] >= 30)
        .sort((a, b) => b.heatScore - a.heatScore)
        .slice(0, 4);
    return {
      twitter: byPlatform('twitter'),
      instagram: byPlatform('instagram'),
      youtube: byPlatform('youtube'),
    };
  }, [trends]);

  // Alert ticker items (duplicate for seamless scroll)
  const tickerItems = useMemo(() => {
    const items = alerts
      .filter(a => !a.dismissed)
      .slice(0, 6)
      .map(a => ({
        label: a.trend?.name || 'Lead Alert',
        msg: a.message.slice(0, 50),
      }));
    if (items.length === 0) {
      return [
        { label: '#BlockTheBot', msg: 'Surging +643% · 4 watched accounts active' },
        { label: 'MrBeast Production Leak', msg: '🔥 Critical · 1.2M mentions · YouTube' },
        { label: 'OpenAI Exodus', msg: 'Breaking · +1192% in 6h' },
        { label: 'Deinfluencing 2.0', msg: 'Instagram surging · 448k mentions' },
      ];
    }
    return items;
  }, [alerts]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Alert Ticker */}
      <div className="alert-ticker-wrap">
        <div className="alert-ticker-label">
          <span className="status-dot-pulse" style={{ width: 6, height: 6 }} />
          LIVE
        </div>
        <div style={{ overflow: 'hidden', flex: 1 }}>
          <div className="alert-ticker-track">
            {[...tickerItems, ...tickerItems].map((item, i) => (
              <span key={i} className="alert-ticker-item">
                <strong>{item.label}</strong> — {item.msg}
                <span style={{ color: 'rgba(255,255,255,0.15)', marginLeft: '1rem' }}>·</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="stats-grid">
        <div className="glass-panel stat-widget">
          <div>
            <span className="stat-label">Active Scanners</span>
            <div className="stat-val">{activeBots}<span style={{ color: 'var(--text-muted)', fontSize: '1.25rem', fontWeight: 500 }}>/{totalBots}</span></div>
            <div className="stat-change up">
              <span className="status-dot-pulse" style={{ width: 6, height: 6 }} />
              Scanning Feeds Live
            </div>
          </div>
          <div className="stat-icon-wrapper"><Activity size={20} /></div>
        </div>

        <div className="glass-panel stat-widget">
          <div>
            <span className="stat-label">Signals Detected</span>
            <div className="stat-val">{totalSignals}</div>
            <div className="stat-change up"><TrendingUp size={12} /> Emergence signals</div>
          </div>
          <div className="stat-icon-wrapper"><Zap size={20} /></div>
        </div>

        <div className="glass-panel stat-widget">
          <div>
            <span className="stat-label">Early Signals</span>
            <div className="stat-val" style={{ color: 'var(--accent-blue)' }}>{emergingCount}</div>
            <div className="stat-change" style={{ color: 'var(--accent-blue)' }}>
              <TrendingUp size={12} /> Pre-viral trends
            </div>
          </div>
          <div className="stat-icon-wrapper" style={{ color: 'var(--accent-blue)' }}><TrendingUp size={20} /></div>
        </div>

        <div
          className="glass-panel stat-widget"
          style={{ cursor: 'pointer' }}
          onClick={onGoToLeads}
        >
          <div>
            <span className="stat-label">Hot Leads</span>
            <div className="stat-val" style={{ color: hotLeadCount > 0 ? '#f87171' : undefined }}>{hotLeadCount}</div>
            <div className="stat-change" style={{ color: hotLeadCount > 0 ? '#f87171' : 'var(--text-muted)' }}>
              🎯 View Lead Radar →
            </div>
          </div>
          <div className="stat-icon-wrapper" style={{ color: '#f87171' }}><Target size={20} /></div>
        </div>
      </div>

      {/* Platform Columns + Console */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1.25rem' }}>
        {(['twitter', 'instagram', 'youtube'] as const).map(platform => {
          const platformTrendList = platformTrends[platform];
          return (
            <div key={platform} className="glass-panel" style={{ overflow: 'hidden' }}>
              <div className="platform-col-header" style={{ color: PLATFORM_COLORS[platform] }}>
                <BrandIcon platform={platform} size={14} />
                {platform === 'twitter' ? 'X / Twitter' : platform === 'instagram' ? 'Instagram' : 'YouTube'}
                <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                  {platformTrendList.length} trends
                </span>
              </div>
              <div className="platform-col-body">
                {platformTrendList.map(t => (
                  <div
                    key={t.id}
                    className={`platform-trend-pill ${t.heatScore >= 90 ? 'heat-critical' : t.heatScore >= 75 ? 'heat-high' : t.heatScore >= 55 ? 'heat-medium' : ''}`}
                    onClick={() => onViewTrendDetails(t)}
                  >
                    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '2px', background: PLATFORM_COLORS[platform], opacity: 0.4 }} />
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.4rem' }}>
                      <span className={`trend-type-badge ${t.trendType}`}>
                        {TREND_TYPE_ICONS[t.trendType]} {t.trendType}
                      </span>
                      <span className={`heat-badge ${HEAT_CLASS(t.heatScore)}`}>🌡 {t.heatScore}</span>
                    </div>
                    <div className="platform-trend-pill-name">{t.name}</div>
                    <div className="platform-trend-pill-meta">
                      <span>{(t.volume / 1000).toFixed(0)}k mentions</span>
                      <span style={{ color: t.growth > 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }}>
                        +{t.growth.toLocaleString()}%
                      </span>
                      {t.firstSeenBy.length > 0 && (
                        <span style={{ marginLeft: 'auto' }}>via {t.firstSeenBy[0]}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Emerging Alpha + Console Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
        {/* Emerging / Early Signal Feed */}
        <div className="glass-panel" style={{ padding: '1.25rem' }}>
          <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', letterSpacing: '0.05em' }}>
            <span style={{ color: 'var(--accent-blue)' }}>📡</span> Early Signal Radar — Pre-Viral
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {[...trends]
              .filter(t => t.emergenceScore >= 50 && t.emergenceScore < 80)
              .sort((a, b) => b.emergenceScore - a.emergenceScore)
              .slice(0, 4)
              .map(t => (
                <div key={t.id} className="glass-card" style={{ padding: '0.85rem 1rem', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  onClick={() => onViewTrendDetails(t)}>
                  <div>
                    <div style={{ fontSize: '0.88rem', fontWeight: 700 }}>{t.name}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                      {t.signalAccountCount} accounts · {t.predictedPeak}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>
                      First seen by {t.firstSeenBy[0] || 'unknown'}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--accent-blue)', fontWeight: 700 }}>
                      📡 {t.emergenceScore}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>emergence</div>
                  </div>
                </div>
              ))}
            {trends.filter(t => t.emergenceScore >= 50 && t.emergenceScore < 80).length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '1.5rem 0' }}>
                No early signals at the moment — all trends are established.
              </div>
            )}
          </div>
        </div>

        {/* Live Console */}
        <div className="glass-panel console-panel">
          <div className="console-header">
            <span className="console-title">
              <Terminal size={15} className="color-twitter" /> Scanner Output
            </span>
            <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
              onClick={onClearLogs}>
              <Trash2 size={11} /> Clear
            </button>
          </div>
          <div className="console-body">
            {logs.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: '3rem', fontStyle: 'italic' }}>
                &gt;_ Awaiting scanner pipelines...
              </div>
            ) : (
              logs.map(log => (
                <div key={log.id} className={`log-line ${log.type === 'success' ? 'success' : ''} ${log.type === 'alert' ? 'alert' : ''}`}>
                  <span className="log-time">[{log.timestamp}]</span>
                  <span className={`log-tag ${log.platform}`}>{log.botName.split('-')[0].toLowerCase()}</span>
                  <span className="log-message">{log.message}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
