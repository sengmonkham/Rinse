import React, { useState, useMemo } from 'react';
import type { Trend, MomentumType, SamplePost } from '../types';
import { CATEGORIES } from '../mockData';
import { 
  Search, 
  TrendingUp, 
  TrendingDown, 
  Globe, 
  X, 
  Plus, 
  Sparkles,
  BarChart,
  Megaphone,
  UserCheck
} from 'lucide-react';
import { BrandIcon } from './BrandIcon';

interface DirectoryViewProps {
  trends: Trend[];
  onCreateCustomTrend: (trend: Omit<Trend, 'id' | 'volumeHistory' | 'sentiment' | 'platforms'>) => void;
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
  onCreateCustomTrend,
  activeTrend,
  setActiveTrend
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedMomentum, setSelectedMomentum] = useState<MomentumType | 'All'>('All');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  // Form states for creating custom trend
  const [newTrendName, setNewTrendName] = useState('');
  const [newTrendCategory, setNewTrendCategory] = useState('Tech & AI');
  const [newTrendVolume, setNewTrendVolume] = useState(120000);
  const [newTrendDescription, setNewTrendDescription] = useState('');
  const [newTrendWhy, setNewTrendWhy] = useState('');
  const [newTrendAdvice, setNewTrendAdvice] = useState('');

  // Handle new trend submit
  const handleAddTrend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTrendName.trim()) return;

    onCreateCustomTrend({
      name: newTrendName.trim(),
      category: newTrendCategory,
      volume: Number(newTrendVolume) || 50000,
      growth: Math.floor(Math.random() * 150) + 30, // 30-180%
      momentum: 'upcoming',
      description: newTrendDescription.trim() || 'Custom monitored niche.',
      whyTrending: newTrendWhy.trim() || 'Triggered by custom user scanner rule and social volume increases.',
      demographics: {
        age: [
          { label: '18-24 (Gen Z)', percentage: 40 },
          { label: '25-34 (Millennials)', percentage: 40 },
          { label: '35-44 (Gen X)', percentage: 15 },
          { label: '45+', percentage: 5 }
        ],
        region: [
          { label: 'North America', percentage: 45 },
          { label: 'Europe', percentage: 35 },
          { label: 'Rest of World', percentage: 20 }
        ]
      },
      marketingAdvice: newTrendAdvice.trim() || 'Ride the keyword spike in seasonal newsletters. Craft responsive shorts linking product offerings.',
      samplePosts: [
        {
          platform: 'twitter',
          user: 'TrendScanner Core',
          handle: '@trend_core_bot',
          avatar: 'https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?auto=format&fit=crop&w=80&h=80',
          content: `Initial scanner spike detected for "${newTrendName}". Early adopters showing high sentiment. 📈`,
          engagement: '450 likes • 32 retweets',
          time: 'Just now'
        }
      ]
    });

    // Reset Form
    setNewTrendName('');
    setNewTrendDescription('');
    setNewTrendWhy('');
    setNewTrendAdvice('');
    setIsAddModalOpen(false);
  };

  // Filter trends
  const filteredTrends = useMemo(() => {
    return trends.filter(trend => {
      const matchesSearch = trend.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            trend.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            trend.description.toLowerCase().includes(searchTerm.toLowerCase());
      
      const matchesCategory = selectedCategory === 'All' || trend.category === selectedCategory;
      const matchesMomentum = selectedMomentum === 'All' || trend.momentum === selectedMomentum;

      return matchesSearch && matchesCategory && matchesMomentum;
    });
  }, [trends, searchTerm, selectedCategory, selectedMomentum]);

  const renderSocialIcon = (platform: 'twitter' | 'instagram' | 'youtube') => {
    return <BrandIcon platform={platform} size={14} className={`color-${platform}`} />;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      
      {/* Top Filter and Search Bar Row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div className="search-input-wrapper">
          <Search size={16} className="search-icon-svg" />
          <input 
            type="text" 
            placeholder="Search active trends..." 
            className="search-input"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {/* Momentum filter dropdown */}
          <select 
            className="form-select" 
            style={{ width: 'auto', padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.03)', color: 'var(--text-secondary)' }}
            value={selectedMomentum}
            onChange={(e) => setSelectedMomentum(e.target.value as any)}
          >
            <option value="All">All Momentum</option>
            <option value="surging">Surging</option>
            <option value="upcoming">Upcoming</option>
            <option value="stable">Stable</option>
          </select>

          {/* Add trend button */}
          <button className="btn btn-primary" onClick={() => setIsAddModalOpen(true)}>
            <Plus size={16} /> Track New Topic
          </button>
        </div>
      </div>

      {/* Category filter tabs */}
      <div className="filter-tabs">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            className={`filter-tab ${selectedCategory === cat ? 'active' : ''}`}
            onClick={() => setSelectedCategory(cat)}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Main Grid View */}
      {filteredTrends.length === 0 ? (
        <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <Sparkles size={32} style={{ marginBottom: '1rem', opacity: 0.5 }} />
          <h3>No trends match your query</h3>
          <p style={{ fontSize: '0.875rem', marginTop: '0.25rem' }}>Try clearing filters or add a new tracking topic.</p>
        </div>
      ) : (
        <div className="trend-grid">
          {filteredTrends.map((trend) => (
            <div 
              key={trend.id} 
              className="glass-panel trend-card"
              onClick={() => setActiveTrend(trend)}
            >
              <div className="trend-card-glow"></div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="trend-category-tag">{trend.category}</span>
                <span className={`momentum-badge ${trend.momentum}`}>{trend.momentum}</span>
              </div>

              <h3 className="trend-name">{trend.name}</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '0.5rem', lineBreak: 'strict', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                {trend.description}
              </p>

              {/* Sparkline visualization */}
              <div className="trend-sparkline">
                <Sparkline data={trend.volumeHistory} growth={trend.growth} />
              </div>

              <div className="trend-stats">
                <div className="trend-stat-item">
                  <span className="trend-stat-lbl">Mentions</span>
                  <span className="trend-stat-val">{(trend.volume).toLocaleString()}</span>
                </div>
                <div className="trend-stat-item" style={{ textAlign: 'right' }}>
                  <span className="trend-stat-lbl">Growth</span>
                  <span className="trend-stat-val" style={{ color: trend.growth > 0 ? 'var(--success)' : 'var(--danger)', display: 'flex', alignItems: 'center', gap: '0.15rem' }}>
                    {trend.growth > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                    +{trend.growth}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Custom Trend Modal */}
      {isAddModalOpen && (
        <div className="modal-overlay" onClick={() => setIsAddModalOpen(false)}>
          <div className="glass-panel modal" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.75rem' }}>
              <h2 style={{ fontSize: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Sparkles size={18} className="color-twitter" /> Track Custom Social Niche
              </h2>
              <button 
                className="drawer-close-btn" 
                style={{ position: 'relative', top: 'auto', right: 'auto', width: '28px', height: '28px' }}
                onClick={() => setIsAddModalOpen(false)}
              >
                <X size={14} />
              </button>
            </div>

            <form onSubmit={handleAddTrend} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-group">
                <label>Topic / Hashtag Name</label>
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="e.g. #SlowLiving, Plant-Based Jerky" 
                  value={newTrendName}
                  onChange={(e) => setNewTrendName(e.target.value)}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label>Category</label>
                  <select 
                    className="form-select"
                    value={newTrendCategory}
                    onChange={(e) => setNewTrendCategory(e.target.value)}
                  >
                    <option value="Tech & AI">Tech & AI</option>
                    <option value="Gaming">Gaming</option>
                    <option value="Fashion & Beauty">Fashion & Beauty</option>
                    <option value="Fitness & Health">Fitness & Health</option>
                    <option value="Food & Lifestyle">Food & Lifestyle</option>
                    <option value="Finance & Crypto">Finance & Crypto</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Est. Monthly Mentions</label>
                  <input 
                    type="number" 
                    className="form-input" 
                    value={newTrendVolume}
                    onChange={(e) => setNewTrendVolume(Number(e.target.value))}
                    min="1000"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Niche Description</label>
                <textarea 
                  className="form-textarea" 
                  style={{ minHeight: '60px', resize: 'vertical' }}
                  placeholder="Explain what this trend is..."
                  value={newTrendDescription}
                  onChange={(e) => setNewTrendDescription(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Why is it trending?</label>
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="e.g. Viral video on TikTok, endorsement by..."
                  value={newTrendWhy}
                  onChange={(e) => setNewTrendWhy(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Action Plan for Brands (Suggested)</label>
                <textarea 
                  className="form-textarea" 
                  style={{ minHeight: '60px', resize: 'vertical' }}
                  placeholder="Suggested response for marketing teams..."
                  value={newTrendAdvice}
                  onChange={(e) => setNewTrendAdvice(e.target.value)}
                />
              </div>

              <button type="submit" className="btn btn-primary" style={{ marginTop: '0.5rem', width: '100%' }}>
                Initialize Simulator Scrapers
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Details Slide-out Drawer */}
      {activeTrend && (
        <div className="drawer-backdrop" onClick={() => setActiveTrend(null)}>
          <div className="drawer" onClick={(e) => e.stopPropagation()}>
            <button className="drawer-close-btn" onClick={() => setActiveTrend(null)}>
              <X size={16} />
            </button>

            <div className="drawer-header">
              <span className="trend-category-tag">{activeTrend.category}</span>
              <h2 style={{ fontSize: '1.85rem', fontWeight: 800, marginTop: '0.25rem' }}>{activeTrend.name}</h2>
              
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.75rem', alignItems: 'center' }}>
                <span className={`momentum-badge ${activeTrend.momentum}`}>{activeTrend.momentum}</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <Globe size={14} /> Global Buzz
                </span>
              </div>
            </div>

            {/* Quick Metrics */}
            <div className="drawer-metric-grid">
              <div className="drawer-metric-card">
                <span className="drawer-metric-lbl">Est. Mentions</span>
                <div className="drawer-metric-val">{(activeTrend.volume).toLocaleString()}</div>
              </div>
              <div className="drawer-metric-card">
                <span className="drawer-metric-lbl">Weekly Spike</span>
                <div className="drawer-metric-val" style={{ color: 'var(--success)' }}>+{activeTrend.growth}%</div>
              </div>
              <div className="drawer-metric-card">
                <span className="drawer-metric-lbl">Pos. Sentiment</span>
                <div className="drawer-metric-val" style={{ color: 'var(--success)' }}>{activeTrend.sentiment.positive}%</div>
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
