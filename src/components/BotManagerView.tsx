import React, { useState } from 'react';
import type { ScannerBot } from '../types';
import { 
  Play, 
  Square, 
  Plus, 
  Cpu, 
  Sliders,
  Users,
  Target,
  Radar
} from 'lucide-react';
import { BrandIcon } from './BrandIcon';

interface BotManagerViewProps {
  bots: ScannerBot[];
  onToggleBot: (botId: string) => void;
  onAddTracker: (botId: string, keyword: string) => void;
  onRemoveTracker: (botId: string, keyword: string) => void;
  onAddWatchedAccount: (botId: string, handle: string, niche: string) => void;
}

export const BotManagerView: React.FC<BotManagerViewProps> = ({
  bots,
  onToggleBot,
  onAddTracker,
  onRemoveTracker,
  onAddWatchedAccount,
}) => {
  const [newTrackers, setNewTrackers] = useState<Record<string, string>>({});
  const [newAccountHandle, setNewAccountHandle] = useState<Record<string, string>>({});
  const [newAccountNiche, setNewAccountNiche] = useState<Record<string, string>>({});
  const [activeSubTab, setActiveSubTab] = useState<Record<string, 'keywords' | 'watchlist'>>({});

  const handleAddKeyword = (botId: string, e: React.FormEvent) => {
    e.preventDefault();
    const keyword = newTrackers[botId] || '';
    if (!keyword.trim()) return;
    onAddTracker(botId, keyword.trim());
    setNewTrackers(prev => ({ ...prev, [botId]: '' }));
  };

  const handleAddAccount = (botId: string, e: React.FormEvent) => {
    e.preventDefault();
    const handle = newAccountHandle[botId] || '';
    const niche = newAccountNiche[botId] || 'General';
    if (!handle.trim()) return;
    onAddWatchedAccount(botId, handle.trim(), niche.trim());
    setNewAccountHandle(prev => ({ ...prev, [botId]: '' }));
    setNewAccountNiche(prev => ({ ...prev, [botId]: '' }));
  };

  const getSubTab = (botId: string) => activeSubTab[botId] || 'keywords';
  const setSubTab = (botId: string, tab: 'keywords' | 'watchlist') => {
    setActiveSubTab(prev => ({ ...prev, [botId]: tab }));
  };

  const getPlatformColor = (platform: string) => {
    switch (platform) {
      case 'twitter': return 'var(--platform-twitter)';
      case 'instagram': return 'var(--platform-instagram)';
      case 'youtube': return 'var(--platform-youtube)';
      default: return 'var(--primary)';
    }
  };

  const trendBots = bots.filter(b => b.mode === 'trend');
  const intentBots = bots.filter(b => b.mode === 'intent');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      
      {/* Description */}
      <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div className="stat-icon-wrapper" style={{ background: 'var(--primary-glow)', color: 'var(--primary-bright)' }}>
          <Cpu size={24} />
        </div>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Scraper Bots Configuration Panel</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
            Manage scanner instances across social platforms. Configure keywords, account watchlists, and intent detection modes.
            Toggle individual bots, review efficiency scores, and add custom trackers in real-time.
          </p>
        </div>
      </div>

      {/* Summary Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
        <div className="glass-panel" style={{ padding: '1rem', textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--success)' }}>{bots.filter(b => b.status !== 'idle').length}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.1rem', textTransform: 'uppercase' }}>Active Bots</div>
        </div>
        <div className="glass-panel" style={{ padding: '1rem', textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary-bright)' }}>{trendBots.length}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.1rem', textTransform: 'uppercase' }}>Trend Bots</div>
        </div>
        <div className="glass-panel" style={{ padding: '1rem', textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f87171' }}>{intentBots.length}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.1rem', textTransform: 'uppercase' }}>Lead Radar Bots</div>
        </div>
        <div className="glass-panel" style={{ padding: '1rem', textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--accent-blue)' }}>
            {bots.reduce((s, b) => s + b.watchedAccounts.length, 0)}
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.1rem', textTransform: 'uppercase' }}>Watched Accounts</div>
        </div>
      </div>

      {/* Trend Bots Section */}
      {trendBots.length > 0 && (
        <div>
          <h2 style={{ fontSize: '0.9rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-secondary)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Radar size={16} style={{ color: 'var(--primary-bright)' }} /> Trend Intelligence Bots
          </h2>
          <div className="bot-cards-grid">
            {trendBots.map((bot) => (
              <BotCard
                key={bot.id}
                bot={bot}
                subTab={getSubTab(bot.id)}
                setSubTab={(t) => setSubTab(bot.id, t)}
                newTracker={newTrackers[bot.id] || ''}
                setNewTracker={(v) => setNewTrackers(prev => ({ ...prev, [bot.id]: v }))}
                newAccountHandle={newAccountHandle[bot.id] || ''}
                setNewAccountHandle={(v) => setNewAccountHandle(prev => ({ ...prev, [bot.id]: v }))}
                newAccountNiche={newAccountNiche[bot.id] || ''}
                setNewAccountNiche={(v) => setNewAccountNiche(prev => ({ ...prev, [bot.id]: v }))}
                onToggleBot={onToggleBot}
                onAddKeyword={(e) => handleAddKeyword(bot.id, e)}
                onAddAccount={(e) => handleAddAccount(bot.id, e)}
                onRemoveTracker={onRemoveTracker}
                getPlatformColor={getPlatformColor}
              />
            ))}
          </div>
        </div>
      )}

      {/* Lead Radar Bots Section */}
      {intentBots.length > 0 && (
        <div>
          <h2 style={{ fontSize: '0.9rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-secondary)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Target size={16} style={{ color: '#f87171' }} /> Lead Radar Intent Bots
          </h2>
          <div className="bot-cards-grid">
            {intentBots.map((bot) => (
              <BotCard
                key={bot.id}
                bot={bot}
                subTab={getSubTab(bot.id)}
                setSubTab={(t) => setSubTab(bot.id, t)}
                newTracker={newTrackers[bot.id] || ''}
                setNewTracker={(v) => setNewTrackers(prev => ({ ...prev, [bot.id]: v }))}
                newAccountHandle={newAccountHandle[bot.id] || ''}
                setNewAccountHandle={(v) => setNewAccountHandle(prev => ({ ...prev, [bot.id]: v }))}
                newAccountNiche={newAccountNiche[bot.id] || ''}
                setNewAccountNiche={(v) => setNewAccountNiche(prev => ({ ...prev, [bot.id]: v }))}
                onToggleBot={onToggleBot}
                onAddKeyword={(e) => handleAddKeyword(bot.id, e)}
                onAddAccount={(e) => handleAddAccount(bot.id, e)}
                onRemoveTracker={onRemoveTracker}
                getPlatformColor={getPlatformColor}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ── Bot Card Sub-component ──────────────────────────────────────────────────

interface BotCardProps {
  bot: ScannerBot;
  subTab: 'keywords' | 'watchlist';
  setSubTab: (t: 'keywords' | 'watchlist') => void;
  newTracker: string;
  setNewTracker: (v: string) => void;
  newAccountHandle: string;
  setNewAccountHandle: (v: string) => void;
  newAccountNiche: string;
  setNewAccountNiche: (v: string) => void;
  onToggleBot: (botId: string) => void;
  onAddKeyword: (e: React.FormEvent) => void;
  onAddAccount: (e: React.FormEvent) => void;
  onRemoveTracker: (botId: string, keyword: string) => void;
  getPlatformColor: (p: string) => string;
}

const BotCard: React.FC<BotCardProps> = ({
  bot, subTab, setSubTab,
  newTracker, setNewTracker,
  newAccountHandle, setNewAccountHandle,
  newAccountNiche, setNewAccountNiche,
  onToggleBot, onAddKeyword, onAddAccount, onRemoveTracker,
  getPlatformColor,
}) => {
  const platformColor = getPlatformColor(bot.platform);

  return (
    <div className="glass-panel bot-card" style={{ borderTop: `2px solid ${platformColor}30` }}>
      
      {/* Header */}
      <div className="bot-card-header">
        <div className="bot-card-title">
          {bot.mode === 'intent' ? (
            <Target size={16} style={{ color: '#f87171' }} />
          ) : (
            <Cpu size={16} style={{ color: platformColor }} />
          )}
          <span style={{ fontSize: '0.95rem' }}>{bot.name}</span>
        </div>
        <div 
          className="bot-platform-badge" 
          style={{ background: platformColor, boxShadow: `0 0 10px ${platformColor}80` }}
        >
          <BrandIcon platform={bot.platform} size={14} style={{ color: '#fff' }} />
        </div>
      </div>

      {/* Mode badge */}
      {bot.mode === 'intent' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.72rem', fontWeight: 700, color: '#f87171', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '6px', padding: '0.3rem 0.6rem', width: 'fit-content' }}>
          <Target size={10} /> LEAD RADAR MODE
        </div>
      )}

      {/* Diagnostics Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem', padding: '0.75rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
        <div style={{ textAlign: 'center' }}>
          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Status</span>
          <div className={`bot-status-indicator ${bot.status}`} style={{ marginTop: '0.15rem', justifyContent: 'center' }}>
            {bot.status !== 'idle' && <span className="status-dot-pulse" style={{ width: '6px', height: '6px', backgroundColor: bot.status === 'analyzing' ? 'var(--accent-blue)' : undefined }}></span>}
            {bot.status}
          </div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Accuracy</span>
          <div style={{ fontSize: '0.88rem', fontWeight: 800, marginTop: '0.15rem', color: 'var(--success)' }}>{bot.efficiency}%</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>Signals</span>
          <div style={{ fontSize: '0.88rem', fontWeight: 800, marginTop: '0.15rem', color: 'var(--primary-bright)' }}>{bot.signalsDetected}</div>
        </div>
      </div>

      {/* Queries processed */}
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
        <span style={{ color: 'var(--text-secondary)' }}>Queries processed:</span>
        <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{bot.activityCount.toLocaleString()}</span>
      </div>

      {/* Sub-tabs: Keywords / Watchlist (only for trend bots) */}
      {bot.mode === 'trend' && (
        <div style={{ display: 'flex', gap: '0.35rem', borderBottom: '1px solid rgba(255,255,255,0.04)', paddingBottom: '0.75rem' }}>
          <button
            className={`filter-tab${subTab === 'keywords' ? ' active' : ''}`}
            style={{ fontSize: '0.72rem', padding: '0.25rem 0.6rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
            onClick={() => setSubTab('keywords')}
          >
            <Sliders size={11} /> Keywords ({bot.trackers.length})
          </button>
          <button
            className={`filter-tab${subTab === 'watchlist' ? ' active' : ''}`}
            style={{ fontSize: '0.72rem', padding: '0.25rem 0.6rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
            onClick={() => setSubTab('watchlist')}
          >
            <Users size={11} /> Watchlist ({bot.watchedAccounts.length})
          </button>
        </div>
      )}

      {/* Keywords tab */}
      {(bot.mode === 'intent' || subTab === 'keywords') && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <Sliders size={11} /> {bot.mode === 'intent' ? 'Intent Triggers' : 'Scraper Keywords'} ({bot.trackers.length})
          </span>
          
          <div className="bot-trackers-box">
            {bot.trackers.length === 0 ? (
              <span style={{ fontSize: '0.75rem', fontStyle: 'italic', color: 'var(--text-muted)' }}>No keywords monitored.</span>
            ) : (
              bot.trackers.map((tracker) => (
                <span key={tracker} className="bot-tracker-tag">
                  {tracker}
                  <span 
                    className="bot-tracker-del" 
                    onClick={() => onRemoveTracker(bot.id, tracker)}
                    title="Remove tracker"
                  >
                    ×
                  </span>
                </span>
              ))
            )}
          </div>

          <form onSubmit={onAddKeyword} style={{ display: 'flex', gap: '0.4rem' }}>
            <input 
              type="text" 
              placeholder={bot.mode === 'intent' ? "Add intent keyword..." : "Add hashtag / keyword..."} 
              className="form-input" 
              style={{ padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}
              value={newTracker}
              onChange={(e) => setNewTracker(e.target.value)}
            />
            <button type="submit" className="btn btn-secondary" style={{ padding: '0.4rem' }}>
              <Plus size={14} />
            </button>
          </form>
        </div>
      )}

      {/* Watchlist tab (trend bots only) */}
      {bot.mode === 'trend' && subTab === 'watchlist' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
            Watched Accounts
          </span>

          {bot.watchedAccounts.length === 0 ? (
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>No accounts on watchlist.</span>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '180px', overflowY: 'auto' }}>
              {bot.watchedAccounts.map(acc => (
                <div key={acc.id} className="account-chip">
                  <img src={acc.avatar} alt="" className="account-chip-avatar" />
                  <div className="account-chip-info">
                    <div className="account-chip-handle">{acc.handle}</div>
                    <div className="account-chip-niche">{acc.niche} · {(acc.followerCount / 1000000).toFixed(1)}M</div>
                  </div>
                  <span className={`account-chip-tier ${acc.tier}`}>{acc.tier}</span>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '0.7rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-blue)' }}>
                      ⚡{acc.signalStrength}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <form onSubmit={onAddAccount} style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            <input 
              type="text"
              placeholder="@handle"
              className="form-input"
              style={{ padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}
              value={newAccountHandle}
              onChange={e => setNewAccountHandle(e.target.value)}
            />
            <div style={{ display: 'flex', gap: '0.35rem' }}>
              <input
                type="text"
                placeholder="Niche (e.g. Tech VC)"
                className="form-input"
                style={{ padding: '0.4rem 0.6rem', fontSize: '0.8rem', flex: 1 }}
                value={newAccountNiche}
                onChange={e => setNewAccountNiche(e.target.value)}
              />
              <button type="submit" className="btn btn-secondary" style={{ padding: '0.4rem 0.7rem' }}>
                <Plus size={13} />
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Run / Stop Actions */}
      <div className="bot-actions">
        <button 
          className={`btn ${bot.status !== 'idle' ? 'btn-danger' : 'btn-primary'}`}
          style={{ flexGrow: 1, padding: '0.45rem' }}
          onClick={() => onToggleBot(bot.id)}
        >
          {bot.status !== 'idle' ? (
            <><Square size={12} /> Suspend</>
          ) : (
            <><Play size={12} /> Resume</>
          )}
        </button>
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', alignSelf: 'center', marginLeft: '0.5rem' }}>
          {bot.lastScanned}
        </div>
      </div>
    </div>
  );
};
