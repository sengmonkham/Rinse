import { useEffect, useState } from 'react';
import { History, Trash2, ExternalLink, Calendar } from 'lucide-react';

interface PageHistoryProps {
  history: ScanHistoryEntry[];
  onClear: () => void;
  onSelectUrl: (url: string) => void;
}

export default function PageHistory({ history, onClear, onSelectUrl }: PageHistoryProps) {
  // Track "now" so relative times stay fresh without calling Date.now() during render
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(timer);
  }, []);

  // Calculate statistics
  const totalScans = history.length;
  const avgScore = totalScans > 0 
    ? Math.round(history.reduce((a, b) => a + b.score, 0) / totalScans) 
    : 100;

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'var(--success)';
    if (score >= 45) return 'var(--warning)';
    return 'var(--danger)';
  };

  const getRelativeTime = (timestamp: number, current: number) => {
    const diff = current - timestamp;
    const mins = Math.floor(diff / 60000);
    const hours = Math.floor(mins / 60);
    const days = Math.floor(hours / 24);

    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flex: '1', minHeight: '0' }}>
      
      {/* Statistics Header */}
      <div className="glass" style={{ padding: '14px', display: 'flex', justifyContent: 'space-around', alignItems: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: '600' }}>Pages Scanned</div>
          <div style={{ fontSize: '24px', fontWeight: '800', color: 'var(--primary)', fontFamily: 'Space Grotesk' }}>{totalScans}</div>
        </div>
        
        <div style={{ height: '30px', width: '1px', background: 'var(--border-color)' }}></div>
        
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: '600' }}>Avg. Authenticity</div>
          <div style={{ fontSize: '24px', fontWeight: '800', color: getScoreColor(avgScore), fontFamily: 'Space Grotesk' }}>{avgScore}%</div>
        </div>
      </div>

      {/* History list */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '12px', fontWeight: '700', color: 'var(--text-secondary)' }}>Recent Scan Log</span>
        {totalScans > 0 && (
          <button 
            onClick={onClear} 
            className="btn btn-secondary" 
            style={{ padding: '4px 10px', fontSize: '11px', color: 'var(--danger)', borderColor: 'rgba(244, 63, 94, 0.15)' }}
          >
            <Trash2 size={12} />
            <span>Clear Log</span>
          </button>
        )}
      </div>

      <div style={{ flex: '1', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', paddingRight: '2px' }}>
        {totalScans === 0 ? (
          <div className="glass" style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <History size={36} style={{ margin: '0 auto 12px' }} />
            <h4 style={{ color: 'var(--text-secondary)', marginBottom: '4px' }}>No History Found</h4>
            <p style={{ fontSize: '11.5px' }}>Once you start scanning active tabs, the log will populate here.</p>
          </div>
        ) : (
          history.map((item, idx) => (
            <div 
              key={idx} 
              className="glass glass-interactive" 
              style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px', cursor: 'pointer' }}
              onClick={() => onSelectUrl(item.url)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                <div style={{ overflow: 'hidden', flex: '1' }}>
                  <h4 style={{ fontSize: '13px', fontWeight: '700', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', color: 'var(--text-primary)' }}>
                    {item.title}
                  </h4>
                  <div style={{ fontSize: '10.5px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.url}
                  </div>
                </div>
                
                <span style={{ fontSize: '14px', fontWeight: '800', color: getScoreColor(item.score), alignSelf: 'center', padding: '2px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px', border: `1px solid ${getScoreColor(item.score)}22` }}>
                  {item.score}%
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '10.5px', color: 'var(--text-muted)', borderTop: '1px solid rgba(255,255,255,0.03)', paddingTop: '6px' }}>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <span>T: <strong>{item.stats.textCount}</strong></span>
                  <span>I: <strong>{item.stats.imageCount}</strong></span>
                  <span>V: <strong>{item.stats.videoCount}</strong></span>
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Calendar size={10} />
                  <span>{getRelativeTime(item.timestamp, now)}</span>
                  <ExternalLink size={10} style={{ marginLeft: '4px' }} />
                </div>
              </div>
            </div>
          ))
        )}
      </div>

    </div>
  );
}
