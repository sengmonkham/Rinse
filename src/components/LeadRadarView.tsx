import React, { useState, useMemo } from 'react';
import type { BuyerLead, BusinessProfile } from '../types';
import { BrandIcon } from './BrandIcon';

const TIER_EMOJI: Record<string, string> = {
  elite: '💎', high: '💳', mid: '🛍️', budget: '💰', low_signal: '🪙',
};

const INTENT_LABELS: Record<string, string> = {
  replacement_intent: '🔴 Replace',
  active_shopping: '🟢 Shopping',
  competitor_defection: '🟠 Switch',
  aspirational: '🔵 Aspire',
  service_need: '🩵 Service',
};

const SCORE_LABEL = (score: number) =>
  score >= 80 ? { label: '🔴 HOT LEAD', cls: 'critical' } :
  score >= 60 ? { label: '🟠 WARM', cls: 'high' } :
  score >= 40 ? { label: '🟡 LUKEWARM', cls: 'medium' } :
               { label: '🔵 COLD', cls: 'low' };

interface LeadCardProps {
  lead: BuyerLead;
  onUpdateStatus: (id: string, status: BuyerLead['status']) => void;
  onCopy: (text: string) => void;
}

const LeadCard: React.FC<LeadCardProps> = ({ lead, onUpdateStatus, onCopy }) => {
  const [expanded, setExpanded] = useState(lead.isHot);
  const { label: scoreLabel, cls: scoreCls } = SCORE_LABEL(lead.leadScore);
  const bp = lead.buyerProfile;

  return (
    <div className={`lead-card${lead.isHot ? ' hot-lead' : ''}`}>
      <div className={`lead-score-strip ${scoreCls}`} />

      {/* Header */}
      <div className="lead-card-header">
        <div className="lead-user-info">
          <img src={lead.post.userAvatar} alt="" className="lead-avatar" />
          <div>
            <div className="lead-username">
              {lead.post.userHandle}
              {bp.hasVerifiedBadge && <span style={{ color: '#60a5fa', marginLeft: '0.3rem', fontSize: '0.8rem' }}>✓</span>}
            </div>
            <div className="lead-followers">
              {lead.post.userFollowers.toLocaleString()} followers
              {bp.detectedProfession && ` · ${bp.detectedProfession}`}
            </div>
          </div>
        </div>
        <div className="lead-badges">
          <span className={`pp-badge ${bp.purchasingPowerTier.replace('_', '-')}`}>
            {TIER_EMOJI[bp.purchasingPowerTier]} {bp.purchasingPowerTier.replace('_', ' ')}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 700, color: scoreCls === 'critical' ? '#f87171' : scoreCls === 'high' ? '#fb923c' : scoreCls === 'medium' ? '#fbbf24' : '#a5b4fc' }}>
            {scoreLabel}
          </span>
        </div>
      </div>

      {/* Platform + Intent badges */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          <BrandIcon platform={lead.post.platform} size={12} />
          {lead.post.platform.charAt(0).toUpperCase() + lead.post.platform.slice(1)}
        </span>
        <span className={`intent-badge ${lead.intentType.replace(/_/g, '-')}`}>
          {INTENT_LABELS[lead.intentType]}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
          {lead.post.postedAt} · {lead.detectedAt}
        </span>
      </div>

      {/* Post content */}
      <div className="lead-post-text">"{lead.post.postContent}"</div>

      {/* Purchasing Power Section */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            💰 Purchasing Power — {bp.purchasingPowerScore}/100
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <div style={{
              width: '80px', height: '6px', borderRadius: '9999px', overflow: 'hidden',
              background: 'rgba(255,255,255,0.05)'
            }}>
              <div style={{
                width: `${bp.purchasingPowerScore}%`, height: '100%', borderRadius: '9999px',
                background: bp.purchasingPowerScore >= 85 ? '#fbbf24' :
                  bp.purchasingPowerScore >= 65 ? '#a5b4fc' :
                  bp.purchasingPowerScore >= 45 ? '#34d399' : '#6b7280',
              }} />
            </div>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              {bp.profileConfidenceScore}% conf.
            </span>
          </div>
        </div>

        <div className="pp-grid">
          <div className="pp-cell">
            <div className="pp-cell-label">Buys/mo</div>
            <div className="pp-cell-value" style={{ color: bp.buyingFrequency === 'high' ? '#34d399' : bp.buyingFrequency === 'medium' ? '#fbbf24' : '#6b7280' }}>
              {bp.buyingFrequencyCount}×
            </div>
          </div>
          <div className="pp-cell">
            <div className="pp-cell-label">Brand tier</div>
            <div className="pp-cell-value" style={{ color: bp.brandTier === 'premium' ? '#fbbf24' : bp.brandTier === 'mid' ? '#a5b4fc' : '#6b7280' }}>
              {bp.brandTier.charAt(0).toUpperCase() + bp.brandTier.slice(1)}
            </div>
          </div>
          <div className="pp-cell">
            <div className="pp-cell-label">Lifestyle</div>
            <div className="pp-cell-value" style={{ color: bp.lifestyleTier === 'high' ? '#34d399' : bp.lifestyleTier === 'medium' ? '#fbbf24' : '#6b7280' }}>
              {bp.lifestyleTier.charAt(0).toUpperCase() + bp.lifestyleTier.slice(1)}
            </div>
          </div>
        </div>

        {bp.mentionedBrands.length > 0 && (
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            Brands: <span style={{ color: 'var(--text-secondary)' }}>{bp.mentionedBrands.join(', ')}</span>
          </div>
        )}

        {bp.lifestyleSignals.length > 0 && (
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            Lifestyle signals: <span style={{ color: 'var(--text-secondary)' }}>{bp.lifestyleSignals.join(' · ')}</span>
          </div>
        )}

        {/* Evidence toggle */}
        {bp.evidencePosts.length > 0 && (
          <div>
            <button
              onClick={() => setExpanded(e => !e)}
              style={{ background: 'none', border: 'none', color: 'var(--primary-bright)', cursor: 'pointer', fontSize: '0.75rem', padding: 0, fontWeight: 600 }}
            >
              {expanded ? '▾' : '▸'} {expanded ? 'Hide' : 'Show'} purchase history ({bp.evidencePosts.length} signals)
            </button>
            {expanded && (
              <ul className="evidence-list" style={{ marginTop: '0.35rem' }}>
                {bp.evidencePosts.map((e, i) => (
                  <li key={i} className="evidence-item">{e}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {bp.hasPriceSensitivity && (
          <div style={{ fontSize: '0.72rem', color: '#fbbf24', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            ⚠️ Price-sensitive language detected — budget messaging recommended
          </div>
        )}
      </div>

      {/* Outreach */}
      <div>
        <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.4rem' }}>
          💬 Suggested outreach ({TIER_EMOJI[bp.purchasingPowerTier]} {bp.purchasingPowerTier} angle)
        </div>
        <div className="outreach-box">{lead.suggestedOutreach}</div>
      </div>

      {/* Actions */}
      <div className="lead-actions">
        <button
          className="btn btn-primary"
          style={{ fontSize: '0.78rem', padding: '0.4rem 0.9rem' }}
          onClick={() => { onCopy(lead.suggestedOutreach); onUpdateStatus(lead.id, 'viewed'); }}
        >
          📋 Copy Outreach
        </button>
        <a
          href={lead.post.postUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary"
          style={{ fontSize: '0.78rem', padding: '0.4rem 0.9rem', textDecoration: 'none' }}
          onClick={() => onUpdateStatus(lead.id, 'viewed')}
        >
          ↗ View Post
        </a>
        {lead.status !== 'contacted' && (
          <button
            className="btn btn-secondary"
            style={{ fontSize: '0.78rem', padding: '0.4rem 0.9rem', color: 'var(--success)' }}
            onClick={() => onUpdateStatus(lead.id, 'contacted')}
          >
            ✓ Contacted
          </button>
        )}
        {lead.status === 'contacted' && (
          <span style={{ fontSize: '0.75rem', color: 'var(--success)', alignSelf: 'center', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            ✓ Outreach sent
          </span>
        )}
        <button
          className="btn btn-secondary"
          style={{ marginLeft: 'auto', fontSize: '0.78rem', padding: '0.4rem 0.9rem', color: 'var(--text-muted)' }}
          onClick={() => onUpdateStatus(lead.id, 'dismissed')}
        >
          ✕
        </button>
      </div>
    </div>
  );
};

// ─── Business Profile Setup ────────────────────────────────────────────────

const BUSINESS_VERTICALS = [
  { label: '💻 Electronics & Tech', keywords: ['laptop', 'phone', 'tablet', 'earbuds', 'keyboard', 'monitor', 'MacBook', 'gaming', 'PC'] },
  { label: '☕ Food & Beverage', keywords: ['coffee machine', 'espresso', 'cafe', 'restaurant', 'food'] },
  { label: '🏋️ Fitness & Wellness', keywords: ['gym', 'membership', 'protein', 'treadmill', 'workout', 'personal trainer'] },
  { label: '💆 Beauty & Skincare', keywords: ['moisturiser', 'foundation', 'serum', 'skincare', 'haircare'] },
  { label: '🚗 Automotive', keywords: ['car', 'tyre', 'mechanic', 'service', 'MOT', 'EV'] },
  { label: '🏠 Home & Furniture', keywords: ['sofa', 'mattress', 'desk', 'shelving', 'interior'] },
  { label: '📚 Education', keywords: ['course', 'tutor', 'certification', 'bootcamp', 'training'] },
  { label: '✈️ Travel', keywords: ['hotel', 'flight', 'holiday', 'trip', 'vacation', 'airport'] },
];

interface BusinessSetupProps {
  profile: BusinessProfile;
  onSave: (p: BusinessProfile) => void;
  onClose: () => void;
}

const BusinessSetup: React.FC<BusinessSetupProps> = ({ profile, onSave, onClose }) => {
  const [form, setForm] = useState({ ...profile });
  const [kwInput, setKwInput] = useState('');

  const addKw = () => {
    if (!kwInput.trim() || form.targetKeywords.includes(kwInput.trim())) return;
    setForm(f => ({ ...f, targetKeywords: [...f.targetKeywords, kwInput.trim()] }));
    setKwInput('');
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal glass-panel" onClick={e => e.stopPropagation()}>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>🎯 Business Profile Setup</h3>

        <div className="form-group">
          <label>Business Name</label>
          <input className="form-input" value={form.businessName} onChange={e => setForm(f => ({ ...f, businessName: e.target.value }))} />
        </div>

        <div className="form-group">
          <label>Category Preset</label>
          <select className="form-select" onChange={e => {
            const v = BUSINESS_VERTICALS.find(bv => bv.label === e.target.value);
            if (v) setForm(f => ({ ...f, category: v.label, targetKeywords: v.keywords }));
          }}>
            <option>— Select preset —</option>
            {BUSINESS_VERTICALS.map(v => <option key={v.label}>{v.label}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label>Target Keywords</label>
          <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.5rem' }}>
            <input
              className="form-input"
              placeholder="Add keyword..."
              value={kwInput}
              onChange={e => setKwInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addKw()}
              style={{ flex: 1 }}
            />
            <button className="btn btn-secondary" onClick={addKw}>+ Add</button>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {form.targetKeywords.map(kw => (
              <span key={kw} className="bot-tracker-tag">
                {kw}
                <span className="bot-tracker-del" onClick={() => setForm(f => ({ ...f, targetKeywords: f.targetKeywords.filter(k => k !== kw) }))}>×</span>
              </span>
            ))}
          </div>
        </div>

        <div className="form-group">
          <label>Min Lead Score (0–100): {form.minLeadScore}</label>
          <input type="range" min={0} max={100} value={form.minLeadScore}
            onChange={e => setForm(f => ({ ...f, minLeadScore: +e.target.value }))}
            style={{ width: '100%', accentColor: 'var(--primary)' }}
          />
        </div>

        <div className="form-group">
          <label>Min Purchasing Power (0–100): {form.minPurchasingPower}</label>
          <input type="range" min={0} max={100} value={form.minPurchasingPower}
            onChange={e => setForm(f => ({ ...f, minPurchasingPower: +e.target.value }))}
            style={{ width: '100%', accentColor: 'var(--primary)' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
          <button className="btn btn-primary" onClick={() => { onSave(form); onClose(); }}>Save Profile</button>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
};

// ─── Main LeadRadarView ────────────────────────────────────────────────────

interface LeadRadarViewProps {
  leads: BuyerLead[];
  businessProfile: BusinessProfile;
  onUpdateStatus: (id: string, status: BuyerLead['status']) => void;
  onUpdateBusinessProfile: (p: BusinessProfile) => void;
}

export const LeadRadarView: React.FC<LeadRadarViewProps> = ({
  leads,
  businessProfile,
  onUpdateStatus,
  onUpdateBusinessProfile,
}) => {
  const [intentFilter, setIntentFilter] = useState<string>('all');
  const [ppFilter, setPpFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('active');
  const [showSetup, setShowSetup] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(text.slice(0, 20));
      setTimeout(() => setCopied(null), 2000);
    });
  };

  const filtered = useMemo(() => {
    return leads.filter(l => {
      if (statusFilter === 'active' && (l.status === 'dismissed')) return false;
      if (statusFilter === 'hot' && !l.isHot) return false;
      if (intentFilter !== 'all' && l.intentType !== intentFilter) return false;
      if (ppFilter !== 'all' && l.buyerProfile.purchasingPowerTier !== ppFilter) return false;
      return true;
    });
  }, [leads, intentFilter, ppFilter, statusFilter]);

  const hotCount = leads.filter(l => l.isHot && l.status !== 'dismissed').length;
  const warmCount = leads.filter(l => l.leadScore >= 60 && !l.isHot && l.status !== 'dismissed').length;
  const totalActive = leads.filter(l => l.status !== 'dismissed').length;

  const INTENT_FILTERS = [
    { value: 'all', label: 'All Intent' },
    { value: 'replacement_intent', label: '🔴 Replace' },
    { value: 'active_shopping', label: '🟢 Shopping' },
    { value: 'competitor_defection', label: '🟠 Switch' },
    { value: 'aspirational', label: '🔵 Aspire' },
    { value: 'service_need', label: '🩵 Service' },
  ];

  const PP_FILTERS = [
    { value: 'all', label: 'All Wallets' },
    { value: 'elite', label: '💎 Elite' },
    { value: 'high', label: '💳 High' },
    { value: 'mid', label: '🛍️ Mid' },
    { value: 'budget', label: '💰 Budget' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {showSetup && (
        <BusinessSetup
          profile={businessProfile}
          onSave={onUpdateBusinessProfile}
          onClose={() => setShowSetup(false)}
        />
      )}

      {/* Stats Strip */}
      <div className="lead-stats-strip">
        <div className="lead-stat-card hot">
          <div className="lead-stat-number">{hotCount}</div>
          <div className="lead-stat-label">🔴 Hot Leads</div>
        </div>
        <div className="lead-stat-card warm">
          <div className="lead-stat-number">{warmCount}</div>
          <div className="lead-stat-label">🟠 Warm Leads</div>
        </div>
        <div className="lead-stat-card">
          <div className="lead-stat-number">{totalActive}</div>
          <div className="lead-stat-label">Total Active</div>
        </div>
      </div>

      {copied && (
        <div style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.25)', borderRadius: '8px', padding: '0.5rem 1rem', fontSize: '0.8rem', color: 'var(--success)' }}>
          ✓ Outreach message copied to clipboard
        </div>
      )}

      <div className="lead-radar-layout">
        {/* Main Feed */}
        <div>
          {/* Filter Bar */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.25rem', alignItems: 'center' }}>
            {/* Status filter */}
            <div style={{ display: 'flex', gap: '0.4rem' }}>
              {[{ v: 'active', l: 'Active' }, { v: 'hot', l: '🔴 Hot Only' }, { v: 'all', l: 'All' }].map(f => (
                <button key={f.v} className={`filter-tab${statusFilter === f.v ? ' active' : ''}`}
                  onClick={() => setStatusFilter(f.v)}>{f.l}</button>
              ))}
            </div>
            <div style={{ width: '1px', height: '24px', background: 'rgba(255,255,255,0.08)' }} />
            {/* Intent filter */}
            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
              {INTENT_FILTERS.map(f => (
                <button key={f.value} className={`filter-tab${intentFilter === f.value ? ' active' : ''}`}
                  onClick={() => setIntentFilter(f.value)}>{f.label}</button>
              ))}
            </div>
            <div style={{ width: '1px', height: '24px', background: 'rgba(255,255,255,0.08)' }} />
            {/* PP filter */}
            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
              {PP_FILTERS.map(f => (
                <button key={f.value} className={`filter-tab${ppFilter === f.value ? ' active' : ''}`}
                  onClick={() => setPpFilter(f.value)}>{f.label}</button>
              ))}
            </div>
          </div>

          {/* Lead Cards */}
          {filtered.length === 0 ? (
            <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>🎯</div>
              <div style={{ fontWeight: 600 }}>Lead Radar is scanning...</div>
              <div style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
                Bots are processing social feeds. Leads will appear here when buyer intent is detected.
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {filtered.map(lead => (
                <LeadCard
                  key={lead.id}
                  lead={lead}
                  onUpdateStatus={onUpdateStatus}
                  onCopy={handleCopy}
                />
              ))}
            </div>
          )}
        </div>

        {/* Sidebar: Business Profile */}
        <div className="lead-radar-sidebar">
          <div className="glass-panel" style={{ padding: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)' }}>
                🏢 Business Profile
              </h3>
              <button
                className="btn btn-secondary"
                style={{ fontSize: '0.72rem', padding: '0.25rem 0.6rem' }}
                onClick={() => setShowSetup(true)}
              >
                Edit
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '1rem' }}>{businessProfile.businessName}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>{businessProfile.category}</div>
              </div>

              <div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Tracking</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                  {businessProfile.targetKeywords.slice(0, 8).map(k => (
                    <span key={k} className="bot-tracker-tag" style={{ fontSize: '0.7rem' }}>{k}</span>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Min Lead Score</span>
                <span style={{ fontWeight: 700 }}>{businessProfile.minLeadScore}+</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Min Power</span>
                <span style={{ fontWeight: 700 }}>{businessProfile.minPurchasingPower}+</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Hot leads today</span>
                <span style={{ fontWeight: 700, color: '#f87171' }}>{hotCount}</span>
              </div>
            </div>
          </div>

          {/* Quick tip box */}
          <div className="glass-panel" style={{ padding: '1rem', fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            <div style={{ fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>💡 How leads are scored</div>
            <div>Intent type + urgency signals + public account bonus + purchasing power (buying frequency, brand tier, lifestyle signals)</div>
          </div>
        </div>
      </div>
    </div>
  );
};
