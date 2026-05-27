import React, { useState } from 'react';
import type { ScannerBot } from '../types';
import { 
  Play, 
  Square, 
  Plus, 
  Cpu, 
  Sliders
} from 'lucide-react';
import { BrandIcon } from './BrandIcon';

interface BotManagerViewProps {
  bots: ScannerBot[];
  onToggleBot: (botId: string) => void;
  onAddTracker: (botId: string, keyword: string) => void;
  onRemoveTracker: (botId: string, keyword: string) => void;
}

export const BotManagerView: React.FC<BotManagerViewProps> = ({
  bots,
  onToggleBot,
  onAddTracker,
  onRemoveTracker
}) => {
  const [newTrackers, setNewTrackers] = useState<Record<string, string>>({});

  const handleAddKeyword = (botId: string, e: React.FormEvent) => {
    e.preventDefault();
    const keyword = newTrackers[botId] || '';
    if (!keyword.trim()) return;

    onAddTracker(botId, keyword.trim());
    setNewTrackers(prev => ({ ...prev, [botId]: '' }));
  };

  const handleTextChange = (botId: string, value: string) => {
    setNewTrackers(prev => ({ ...prev, [botId]: value }));
  };

  const getPlatformIcon = (platform: 'twitter' | 'instagram' | 'youtube') => {
    return <BrandIcon platform={platform} size={14} style={{ color: '#fff' }} />;
  };

  const getPlatformColor = (platform: string) => {
    switch (platform) {
      case 'twitter': return 'var(--platform-twitter)';
      case 'instagram': return 'var(--platform-instagram)';
      case 'youtube': return 'var(--platform-youtube)';
      default: return 'var(--primary)';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      
      {/* Page Description */}
      <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div className="stat-icon-wrapper" style={{ background: 'var(--primary-glow)', color: 'var(--primary-bright)' }}>
          <Cpu size={24} />
        </div>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Scraper Bots Configuration Panel</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
            Manage the scraper instances searching social media platforms. Toggle bots, review pipeline parser efficiencies, or configure custom hashtag filters in real-time.
          </p>
        </div>
      </div>

      {/* Bots Grid */}
      <div className="bot-cards-grid">
        {bots.map((bot) => (
          <div key={bot.id} className="glass-panel bot-card">
            
            {/* Header info */}
            <div className="bot-card-header">
              <div className="bot-card-title">
                <Cpu size={16} style={{ color: getPlatformColor(bot.platform) }} />
                <span>{bot.name}</span>
              </div>
              
              <div 
                className="bot-platform-badge" 
                style={{ 
                  background: getPlatformColor(bot.platform),
                  boxShadow: `0 0 10px ${getPlatformColor(bot.platform)}80`
                }}
              >
                {getPlatformIcon(bot.platform)}
              </div>
            </div>

            {/* Diagnostics Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', padding: '0.75rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Status</span>
                <div className={`bot-status-indicator ${bot.status}`} style={{ marginTop: '0.15rem' }}>
                  {bot.status === 'scanning' && <span className="status-dot-pulse" style={{ width: '6px', height: '6px' }}></span>}
                  {bot.status === 'analyzing' && <span className="status-dot-pulse" style={{ width: '6px', height: '6px', backgroundColor: 'var(--accent-blue)' }}></span>}
                  {bot.status}
                </div>
              </div>
              <div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Quality Score</span>
                <div style={{ fontSize: '0.9rem', fontWeight: 800, marginTop: '0.15rem', color: 'var(--success)' }}>
                  {bot.efficiency}% Accurate
                </div>
              </div>
            </div>

            {/* Operation counters */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Parsed Records:</span>
              <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{bot.activityCount} queries</span>
            </div>

            {/* Keyword Monitor Trackers section */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <Sliders size={12} /> Active Scraper Rules ({bot.trackers.length})
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
                        title="Delete keyword scraper trigger"
                      >
                        ×
                      </span>
                    </span>
                  ))
                )}
              </div>
            </div>

            {/* Input to add trigger keywords */}
            <form onSubmit={(e) => handleAddKeyword(bot.id, e)} style={{ display: 'flex', gap: '0.4rem', marginTop: '0.5rem' }}>
              <input 
                type="text" 
                placeholder="Add hashtag / keyword..." 
                className="form-input" 
                style={{ padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}
                value={newTrackers[bot.id] || ''}
                onChange={(e) => handleTextChange(bot.id, e.target.value)}
              />
              <button type="submit" className="btn btn-secondary" style={{ padding: '0.4rem' }}>
                <Plus size={14} />
              </button>
            </form>

            {/* Run / Stop toggle Actions */}
            <div className="bot-actions">
              <button 
                className={`btn ${bot.status !== 'idle' ? 'btn-danger' : 'btn-primary'}`}
                style={{ flexGrow: 1, padding: '0.45rem' }}
                onClick={() => onToggleBot(bot.id)}
              >
                {bot.status !== 'idle' ? (
                  <>
                    <Square size={12} /> Suspend Scraper
                  </>
                ) : (
                  <>
                    <Play size={12} /> Resume Scraper
                  </>
                )}
              </button>
            </div>

          </div>
        ))}
      </div>
    </div>
  );
};
