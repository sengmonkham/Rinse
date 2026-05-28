import React, { useState, useMemo } from 'react';
import type { Trend, SamplePost } from '../types';
import { 
  Search, 
  TrendingUp, 
  TrendingDown, 
  X, 
  Sparkles,
  BarChart,
  Megaphone,
  UserCheck
} from 'lucide-react';
import { BrandIcon } from './BrandIcon';

const PLATFORM_FILTERS = [
  { value: 'all', label: '🌐 All Platforms' },
  { value: 'twitter', label: '🐦 X / Twitter' },
  { value: 'instagram', label: '📸 Instagram' },
  { value: 'youtube', label: '📺 YouTube' },
];

const TYPE_FILTERS = [
  { value: 'all', label: 'All Types' },
  { value: 'breaking', label: '🔴 Breaking' },
  { value: 'controversial', label: '⚡ Controversial' },
  { value: 'viral', label: '🚀 Viral' },
  { value: 'uprising', label: '📡 Uprising' },
  { value: 'fading', label: '📉 Fading' },
];

interface DirectoryViewProps {
  trends: Trend[];
  activeTrend: Trend | null;
  setActiveTrend: (trend: Trend | null) => void;
}

// Sparkline Component using inline SVG
const Sparkline: React.FC<{ data: number[]; growth: number }> = ({ data, growth }) => {
  if (!data || data.length < 2) return null;
  const width = 120;
  const height = 36;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  
  const points = data.map((val, index) => {
    const x = (index / (data.length - 1)) * width;
    const y = height - ((val - min) / range) * (height - 8) - 4;
    return `${x},${y}`;
  }).join(' ');

  const strokeColor = growth > 100 ? 'var(--accent-pink)' : 'var(--success)';

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
      {/* Glow effect */}
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.15"
        points={points}
        style={{ filter: 'blur(2px)' }}
      />
    </svg>
  );
};

export const DirectoryView: React.FC<DirectoryViewProps> = ({
  trends,
  activeTrend,
  setActiveTrend
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [platformFilter, setPlatformFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortBy, setSortBy] = useState<'heat' | 'volume' | 'growth' | 'controversy'>('heat');

  // Filter + sort trends
  const filteredTrends = useMemo(() => {
    return trends
      .filter(trend => {
        const matchesSearch = trend.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                              trend.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
                              trend.description.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesPlatform = platformFilter === 'all' || trend.platformOrigin === platformFilter ||
          trend.platforms[platformFilter as keyof typeof trend.platforms] >= 25;
        const matchesType = typeFilter === 'all' || trend.trendType === typeFilter;
        return matchesSearch && matchesPlatform && matchesType;
      })
      .sort((a, b) => {
        if (sortBy === 'heat') return b.heatScore - a.heatScore;
        if (sortBy === 'volume') return b.volume - a.volume;
        if (sortBy === 'growth') return b.growth - a.growth;
        if (sortBy === 'controversy') return b.controversyLevel - a.controversyLevel;
        return 0;
      });
  }, [trends, searchTerm, platformFilter, typeFilter, sortBy]);

  const renderSocialIcon = (platform: 'twitter' | 'instagram' | 'youtube') => {
    return <BrandIcon platform={platform} size={14} className={`color-${platform}`} />;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      
      {/* Top Filter and Search Bar Row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.5rem' }}>
        <div className="search-input-wrapper">
          <Search size={16} className="search-icon-svg" />
          <input 
            type="text" 
            placeholder="Search trends, categories..." 
            className="search-input"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Sort:</span>
          {(['heat', 'volume', 'growth', 'controversy'] as const).map(s => (
            <button key={s} className={`filter-tab${sortBy === s ? ' active' : ''}`} style={{ fontSize: '0.75rem', padding: '0.3rem 0.7rem' }} onClick={() => setSortBy(s)}>
              {s === 'heat' ? '🌡️ Heat' : s === 'volume' ? '📊 Volume' : s === 'growth' ? '📈 Growth' : '⚡ Controversy'}
            </button>
          ))}
        </div>
      </div>

      {/* Platform filter tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
        {PLATFORM_FILTERS.map(f => (
          <button key={f.value} className={`filter-tab${platformFilter === f.value ? ' active' : ''}`} onClick={() => setPlatformFilter(f.value)}>{f.label}</button>
        ))}
        <div style={{ width: '1px', background: 'rgba(255,255,255,0.08)', margin: '0 0.25rem' }} />
        {TYPE_FILTERS.map(f => (
          <button key={f.value} className={`filter-tab${typeFilter === f.value ? ' active' : ''}`} onClick={() => setTypeFilter(f.value)}>{f.label}</button>
        ))}
      </div>

      {/* Main Grid View */}
      {filteredTrends.length === 0 ? (
        <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <Sparkles size={32} style={{ marginBottom: '1rem', opacity: 0.5 }} />
          <h3>No trends match your filters</h3>
          <p style={{ fontSize: '0.875rem', marginTop: '0.25rem' }}>Try adjusting the platform or type filters.</p>
        </div>
      ) : (
        <div className="trend-grid">
          {filteredTrends.map((trend) => (
            <div 
              key={trend.id} 
              className={`glass-panel trend-card ${trend.heatScore >= 90 ? 'heat-critical' : trend.heatScore >= 75 ? 'heat-high' : trend.heatScore >= 55 ? 'heat-medium' : ''}`}
              onClick={() => setActiveTrend(trend)}
            >
              <div className="trend-card-glow" style={{ background: trend.trendType === 'breaking' ? 'linear-gradient(90deg,#ef4444,#f97316)' : trend.trendType === 'controversial' ? 'linear-gradient(90deg,#f97316,#fbbf24)' : trend.trendType === 'viral' ? 'linear-gradient(90deg,#8b5cf6,#ec4899)' : 'linear-gradient(90deg,var(--primary),var(--accent-blue))' }} />
              
              {/* Header row: type badge + heat badge */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className={`trend-type-badge ${trend.trendType}`}>
                  {trend.trendType === 'breaking' ? '🔴' : trend.trendType === 'controversial' ? '⚡' : trend.trendType === 'viral' ? '🚀' : trend.trendType === 'uprising' ? '📡' : '📉'} {trend.trendType}
                </span>
                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    <BrandIcon platform={trend.platformOrigin} size={11} />
                    {trend.platformOrigin}
                  </span>
                  <span className={`heat-badge ${trend.heatScore >= 90 ? 'fire' : trend.heatScore >= 75 ? 'hot' : trend.heatScore >= 55 ? 'rising' : 'cool'}`}>
                    🌡️ {trend.heatScore}
                  </span>
                </div>
              </div>

              <h3 className="trend-name">{trend.name}</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '0.5rem', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                {trend.description}
              </p>

              {/* First seen by */}
              {trend.firstSeenBy.length > 0 && (
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  <span>First spotted by</span>
                  <span style={{ color: 'var(--primary-bright)', fontWeight: 600 }}>{trend.firstSeenBy[0]}</span>
                  {trend.firstSeenBy.length > 1 && <span>+{trend.firstSeenBy.length - 1} others</span>}
                </div>
              )}

              {/* Controversy bar */}
              {trend.controversyLevel > 20 && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>
                    <span>⚡ Controversy</span>
                    <span>{trend.controversyLevel}%</span>
                  </div>
                  <div style={{ height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '9999px', overflow: 'hidden' }}>
                    <div style={{ width: `${trend.controversyLevel}%`, height: '100%', background: trend.controversyLevel > 70 ? 'linear-gradient(90deg,#ef4444,#f97316)' : 'linear-gradient(90deg,#f97316,#fbbf24)', borderRadius: '9999px' }} />
                  </div>
                </div>
              )}

              {/* Sparkline visualization */}
              <div className="trend-sparkline">
                <Sparkline data={trend.volumeHistory} growth={trend.growth} />
              </div>

              <div className="trend-stats">
                <div className="trend-stat-item">
                  <span className="trend-stat-lbl">Mentions</span>
                  <span className="trend-stat-val">{(trend.volume).toLocaleString()}</span>
                </div>
                <div className="trend-stat-item" style={{ textAlign: 'center' }}>
                  <span className="trend-stat-lbl">Emergence</span>
                  <span className="trend-stat-val" style={{ color: 'var(--accent-blue)' }}>{trend.emergenceScore}</span>
                </div>
                <div className="trend-stat-item" style={{ textAlign: 'right' }}>
                  <span className="trend-stat-lbl">Growth</span>
                  <span className="trend-stat-val" style={{ color: trend.growth > 0 ? 'var(--success)' : 'var(--danger)', display: 'flex', alignItems: 'center', gap: '0.15rem', justifyContent: 'flex-end' }}>
                    {trend.growth > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                    +{trend.growth.toLocaleString()}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

        <div className="modal-overlay" style={{ display: 'none' }} />

      {/* Details Slide-out Drawer */}
      {activeTrend && (
        <div className="drawer-backdrop" onClick={() => setActiveTrend(null)}>
          <div className="drawer" onClick={(e) => e.stopPropagation()}>
            <button className="drawer-close-btn" onClick={() => setActiveTrend(null)}>
              <X size={16} />
            </button>

            <div className="drawer-header">
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <span className={`trend-type-badge ${activeTrend.trendType}`}>
                  {activeTrend.trendType === 'breaking' ? '🔴' : activeTrend.trendType === 'controversial' ? '⚡' : activeTrend.trendType === 'viral' ? '🚀' : activeTrend.trendType === 'uprising' ? '📡' : '📉'} {activeTrend.trendType}
                </span>
                <span className={`heat-badge ${activeTrend.heatScore >= 90 ? 'fire' : activeTrend.heatScore >= 75 ? 'hot' : activeTrend.heatScore >= 55 ? 'rising' : 'cool'}`}>
                  🌡️ Heat: {activeTrend.heatScore}
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  <BrandIcon platform={activeTrend.platformOrigin} size={12} />
                  Origin: {activeTrend.platformOrigin}
                </span>
              </div>
              <h2 style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '0.5rem' }}>{activeTrend.name}</h2>
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <span className={`momentum-badge ${activeTrend.momentum}`}>{activeTrend.momentum}</span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  📡 Emergence: <strong style={{ color: 'var(--accent-blue)' }}>{activeTrend.emergenceScore}</strong>
                </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  ⚡ Controversy: <strong style={{ color: activeTrend.controversyLevel > 70 ? '#f87171' : '#fbbf24' }}>{activeTrend.controversyLevel}%</strong>
                </span>
              </div>
              {activeTrend.firstSeenBy.length > 0 && (
                <div style={{ marginTop: '0.5rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  First seen by: {activeTrend.firstSeenBy.map(h => <span key={h} style={{ color: 'var(--primary-bright)', marginRight: '0.4rem', fontWeight: 600 }}>{h}</span>)}
                  · {activeTrend.firstSeenAt}
                </div>
              )}
            </div>

            {/* Quick Metrics */}
            <div className="drawer-metric-grid">
              <div className="drawer-metric-card">
                <span className="drawer-metric-lbl">Mentions</span>
                <div className="drawer-metric-val">{(activeTrend.volume).toLocaleString()}</div>
              </div>
              <div className="drawer-metric-card">
                <span className="drawer-metric-lbl">Growth</span>
                <div className="drawer-metric-val" style={{ color: 'var(--success)' }}>+{activeTrend.growth.toLocaleString()}%</div>
              </div>
              <div className="drawer-metric-card">
                <span className="drawer-metric-lbl">Velocity/hr</span>
                <div className="drawer-metric-val" style={{ color: '#fb923c' }}>{activeTrend.velocityScore.toLocaleString()}</div>
              </div>
            </div>

            {/* Peak prediction */}
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 8, padding: '0.75rem' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>PREDICTED PEAK</div>
                <div style={{ fontWeight: 700, marginTop: '0.2rem', fontSize: '0.9rem' }}>{activeTrend.predictedPeak}</div>
              </div>
              <div style={{ flex: 1, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 8, padding: '0.75rem' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>CROSS-PLATFORM</div>
                <div style={{ fontWeight: 700, marginTop: '0.2rem', color: 'var(--accent-blue)', fontSize: '0.9rem' }}>{activeTrend.crossPlatformScore}%</div>
              </div>
              <div style={{ flex: 1, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 8, padding: '0.75rem' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>SIGNAL ACCOUNTS</div>
                <div style={{ fontWeight: 700, marginTop: '0.2rem', color: 'var(--primary-bright)', fontSize: '0.9rem' }}>{activeTrend.signalAccountCount}</div>
              </div>
            </div>

            {/* Why Trending */}
            <div className="drawer-section">
              <span className="drawer-section-title">
                <Sparkles size={14} className="color-twitter" /> Driver Breakdown
              </span>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {activeTrend.whyTrending}
              </p>
            </div>

            {/* Amplification Chain */}
            {activeTrend.amplificationChain.length > 0 && (
              <div className="drawer-section">
                <span className="drawer-section-title">⚡ Amplification Chain</span>
                {activeTrend.amplificationChain.map((ev, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', padding: '0.4rem 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <BrandIcon platform={ev.platform} size={12} />
                      <span style={{ color: 'var(--primary-bright)', fontWeight: 700 }}>{ev.handle}</span>
                      <span className={`account-chip-tier ${ev.tier}`}>{ev.tier}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '1rem', color: 'var(--text-muted)' }}>
                      <span>×{ev.engagementMultiplier} amplification</span>
                      <span>{ev.timestamp}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Marketing Strategy */}
            <div className="drawer-section">
              <span className="drawer-section-title">
                <Megaphone size={14} className="color-instagram" /> Campaign Action Guide
              </span>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {activeTrend.marketingAdvice}
              </p>
            </div>

            {/* Sentiment Breakdown */}
            <div className="drawer-section">
              <span className="drawer-section-title">
                <BarChart size={14} className="color-youtube" /> Sentiment Analytics
              </span>
              
              <div className="sentiment-bar-container">
                <div className="sentiment-seg positive" style={{ width: `${activeTrend.sentiment.positive}%` }}></div>
                <div className="sentiment-seg neutral" style={{ width: `${activeTrend.sentiment.neutral}%` }}></div>
                <div className="sentiment-seg negative" style={{ width: `${activeTrend.sentiment.negative}%` }}></div>
              </div>
              
              <div className="sentiment-legend">
                <span className="sentiment-leg-item">
                  <span className="sentiment-dot pos"></span>
                  Positive ({activeTrend.sentiment.positive}%)
                </span>
                <span className="sentiment-leg-item">
                  <span className="sentiment-dot neu"></span>
                  Neutral ({activeTrend.sentiment.neutral}%)
                </span>
                <span className="sentiment-leg-item">
                  <span className="sentiment-dot neg"></span>
                  Negative ({activeTrend.sentiment.negative}%)
                </span>
              </div>
            </div>

            {/* Audience Demographics */}
            <div className="drawer-section">
              <span className="drawer-section-title">
                <UserCheck size={14} style={{ color: 'var(--accent-blue)' }} /> Target Demographic Share
              </span>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                <div className="demog-list">
                  <h4 style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Age Group</h4>
                  {activeTrend.demographics.age.map((item) => (
                    <div key={item.label} className="demog-item">
                      <div className="demog-label-row">
                        <span>{item.label}</span>
                        <span style={{ fontWeight: 700 }}>{item.percentage}%</span>
                      </div>
                      <div className="demog-bar-outer">
                        <div className="demog-bar-inner" style={{ width: `${item.percentage}%` }}></div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="demog-list">
                  <h4 style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Top Markets</h4>
                  {activeTrend.demographics.region.map((item) => (
                    <div key={item.label} className="demog-item">
                      <div className="demog-label-row">
                        <span>{item.label}</span>
                        <span style={{ fontWeight: 700 }}>{item.percentage}%</span>
                      </div>
                      <div className="demog-bar-outer">
                        <div className="demog-bar-inner" style={{ width: `${item.percentage}%`, background: 'linear-gradient(90deg, var(--accent-pink) 0%, var(--primary) 100%)' }}></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Social Posts Feed */}
            <div className="drawer-section" style={{ background: 'transparent', border: 'none', padding: 0 }}>
              <span className="drawer-section-title" style={{ marginBottom: '0.75rem' }}>
                Recent Scraped Posts
              </span>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {activeTrend.samplePosts.map((post: SamplePost, index) => (
                  <div key={index} className="social-card">
                    <div className="social-card-header">
                      <div className="social-author-info">
                        <img src={post.avatar} alt={post.user} className="social-avatar" />
                        <div className="social-names">
                          <span className="social-name">{post.user}</span>
                          <span className="social-handle">{post.handle}</span>
                        </div>
                      </div>
                      <div className="social-icon-wrapper">
                        {renderSocialIcon(post.platform)}
                      </div>
                    </div>
                    
                    <p className="social-content">{post.content}</p>
                    
                    <div className="social-footer">
                      <span>{post.engagement}</span>
                      <span>{post.time}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
