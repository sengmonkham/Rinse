import React, { useState, useMemo } from 'react';
import type { Trend, LogEntry } from '../types';
import { CATEGORIES } from '../mockData';
import { 
  FileText, 
  Sparkles, 
  Download, 
  Bell, 
  ArrowUpRight, 
  CheckCircle,
  FileSpreadsheet,
  AlertCircle
} from 'lucide-react';

interface ReportsViewProps {
  trends: Trend[];
  logs: LogEntry[];
}

interface ReportDoc {
  title: string;
  category: string;
  generatedAt: string;
  brief: string;
  metrics: {
    buzzRate: string;
    sentimentScore: string;
    alertRate: string;
  };
  recommendations: string[];
}

export const ReportsView: React.FC<ReportsViewProps> = ({ trends, logs }) => {
  const [selectedCat, setSelectedCat] = useState('Tech & AI');
  const [reportType, setReportType] = useState('Strategic Briefing');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedReport, setGeneratedReport] = useState<ReportDoc | null>(null);
  const [savedReports, setSavedReports] = useState<Omit<ReportDoc, 'brief' | 'recommendations' | 'metrics'>[]>([
    { title: 'Gaming Cozy Trends Q3 Outline', category: 'Gaming', generatedAt: '2026-05-20' },
    { title: 'Generative AI Shortform Video Playbook', category: 'Tech & AI', generatedAt: '2026-05-24' }
  ]);

  // Filter high priority spike alerts from logs
  const spikeAlerts = useMemo(() => {
    return logs.filter(l => l.type === 'alert').slice(0, 10);
  }, [logs]);

  // Core intelligence generator logic based on actual active trends!
  const handleGenerateReport = () => {
    setIsGenerating(true);
    
    setTimeout(() => {
      // Find trends matching category
      const categoryTrends = trends.filter(t => t.category === selectedCat);
      const trendNames = categoryTrends.map(t => t.name).join(', ') || 'Niche Keywords';
      const maxGrowth = categoryTrends.length > 0 ? Math.max(...categoryTrends.map(t => t.growth)) : 85;
      
      const briefDoc: ReportDoc = {
        title: `${selectedCat} Intelligence Briefing (${reportType})`,
        category: selectedCat,
        generatedAt: new Date().toLocaleDateString([], { year: 'numeric', month: 'long', day: 'numeric' }),
        metrics: {
          buzzRate: `${(categoryTrends.reduce((acc, curr) => acc + curr.volume, 0)).toLocaleString()} mentions`,
          sentimentScore: `${categoryTrends.length > 0 ? Math.round(categoryTrends.reduce((acc, curr) => acc + curr.sentiment.positive, 0) / categoryTrends.length) : 75}% Positive`,
          alertRate: `+${maxGrowth}% High Velocity Peak`
        },
        brief: `ANALYSIS DIRECTIVE: Social scanning algorithms detect strong momentum shift within ${selectedCat} communities. The emergence of key pillars (including ${trendNames}) suggests audience behavior is centering on practical integration, aesthetic minimalism, and self-optimization. \n\nVOLUME DATA: Scanner bots tracked significant volume spikes across Twitter/X and YouTube comments. The audience shows strong micro-engagement, meaning followers are actively creating community offshoots, remixing tags, and requesting user guides. Neutral-to-negative sentiment holds below 12%, signaling low community friction and high receptive buy-in for related campaigns.`,
        recommendations: categoryTrends.length > 0 
          ? categoryTrends.map(t => `Leverage "${t.name}": ${t.marketingAdvice}`)
          : ['Initiate multi-platform seeding campaigns targeting niche keyword adopters.', 'Repurpose short-form visuals highlighting workflow automation and cost saving ratios.']
      };

      setGeneratedReport(briefDoc);
      setSavedReports(prev => [
        { title: briefDoc.title, category: briefDoc.category, generatedAt: 'Just Now' },
        ...prev
      ]);
      setIsGenerating(false);
    }, 1500); // 1.5s simulated loader
  };

  const handleDownload = () => {
    alert("📄 Downloader Initiated: trendscanner_briefing_pdf generated successfully!");
  };

  return (
    <div className="reports-layout">
      
      {/* Left Column: Report Builder Panel */}
      <div className="glass-panel report-builder-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FileText size={18} className="color-twitter" /> AI-Briefing Intelligence Builder
        </h3>

        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          Compile aggregated trend statistics, sentiment ratios, and visual scrapings into highly polished, executive briefings formatted for social media strategists.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="form-group">
            <label>Community Segment</label>
            <select 
              className="form-select"
              value={selectedCat}
              onChange={(e) => setSelectedCat(e.target.value)}
            >
              {CATEGORIES.filter(c => c !== 'All').map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Report Structure</label>
            <select 
              className="form-select"
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
            >
              <option value="Strategic Briefing">Strategic Briefing</option>
              <option value="Competitive Landscape Outline">Competitive Landscape Outline</option>
              <option value="Viral Hook Guide">Viral Hook Guide</option>
            </select>
          </div>
        </div>

        <button 
          className="btn btn-primary" 
          style={{ width: '100%', padding: '0.75rem', marginTop: '0.5rem' }}
          onClick={handleGenerateReport}
          disabled={isGenerating}
        >
          {isGenerating ? (
            <>
              <Sparkles size={16} className="status-dot-pulse" style={{ backgroundColor: '#fff' }} /> Generating AI Briefing...
            </>
          ) : (
            <>
              <Sparkles size={16} /> Compile Briefing Report
            </>
          )}
        </button>

        {/* Generated Document Output */}
        {generatedReport ? (
          <div className="report-doc-preview" style={{ animation: 'fade-slide-in 0.3s ease-out' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', paddingBottom: '0.5rem' }}>
              <div>
                <span className="trend-category-tag" style={{ fontSize: '0.7rem' }}>{generatedReport.category}</span>
                <h4 style={{ fontSize: '1.1rem', fontWeight: 750, marginTop: '0.15rem' }}>{generatedReport.title}</h4>
              </div>
              <button 
                className="btn btn-secondary" 
                style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem', display: 'flex', gap: '0.25rem' }}
                onClick={handleDownload}
              >
                <Download size={12} /> Download PDF
              </button>
            </div>

            {/* Quick Brief Statistics */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', margin: '0.5rem 0' }}>
              <div className="drawer-metric-card" style={{ background: 'rgba(255,255,255,0.03)', padding: '0.5rem' }}>
                <span className="drawer-metric-lbl" style={{ fontSize: '0.65rem' }}>Category Volume</span>
                <div style={{ fontSize: '0.85rem', fontWeight: 800, marginTop: '0.1rem' }}>{generatedReport.metrics.buzzRate}</div>
              </div>
              <div className="drawer-metric-card" style={{ background: 'rgba(255,255,255,0.03)', padding: '0.5rem' }}>
                <span className="drawer-metric-lbl" style={{ fontSize: '0.65rem' }}>Avg. Sentiment</span>
                <div style={{ fontSize: '0.85rem', fontWeight: 800, marginTop: '0.1rem', color: 'var(--success)' }}>{generatedReport.metrics.sentimentScore}</div>
              </div>
              <div className="drawer-metric-card" style={{ background: 'rgba(255,255,255,0.03)', padding: '0.5rem' }}>
                <span className="drawer-metric-lbl" style={{ fontSize: '0.65rem' }}>Peak Velocity</span>
                <div style={{ fontSize: '0.85rem', fontWeight: 800, marginTop: '0.1rem', color: 'var(--accent-pink)' }}>{generatedReport.metrics.alertRate}</div>
              </div>
            </div>

            <div style={{ fontSize: '0.85rem', lineHeight: 1.5, color: '#d1d5db', whiteSpace: 'pre-line' }}>
              {generatedReport.brief}
            </div>

            <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <h5 style={{ fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Tactical Action Items</h5>
              <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.4rem', paddingLeft: '0.2rem' }}>
                {generatedReport.recommendations.map((rec, idx) => (
                  <li key={idx} style={{ fontSize: '0.8rem', color: '#9ca3af', display: 'flex', alignItems: 'flex-start', gap: '0.4rem' }}>
                    <CheckCircle size={12} style={{ color: 'var(--success)', marginTop: '0.15rem', flexShrink: 0 }} />
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <div style={{ border: '1px dashed rgba(255,255,255,0.06)', borderRadius: 'var(--radius-sm)', padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <FileSpreadsheet size={32} style={{ opacity: 0.25, marginBottom: '0.75rem' }} />
            <p style={{ fontSize: '0.85rem' }}>Select category parameters above to compile your live trend intelligence briefing.</p>
          </div>
        )}
      </div>

      {/* Right Column: Alerts and Historical Reports */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        
        {/* Active Alerts Panel */}
        <div className="glass-panel report-history-panel">
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.75rem' }}>
            <Bell size={15} style={{ color: 'var(--danger)' }} /> Scanner Alert Log
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '250px', overflowY: 'auto', paddingRight: '0.25rem' }}>
            {spikeAlerts.length === 0 ? (
              <p style={{ fontSize: '0.75rem', fontStyle: 'italic', color: 'var(--text-muted)', textAlign: 'center', padding: '1rem' }}>
                No high-velocity alerts detected yet. Simulator running checks...
              </p>
            ) : (
              spikeAlerts.map((alert) => (
                <div 
                  key={alert.id} 
                  className="glass-card" 
                  style={{ 
                    padding: '0.75rem', 
                    borderLeft: '3px solid var(--danger)', 
                    display: 'flex', 
                    alignItems: 'flex-start', 
                    gap: '0.5rem',
                    animation: 'fade-slide-in 0.2s ease-out'
                  }}
                >
                  <AlertCircle size={14} style={{ color: '#fca5a5', flexShrink: 0, marginTop: '0.1rem' }} />
                  <div>
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{alert.timestamp} • {alert.platform.toUpperCase()}</span>
                    <p style={{ fontSize: '0.75rem', color: '#fca5a5', fontWeight: 500, marginTop: '0.1rem', lineHeight: 1.3 }}>
                      {alert.message.replace('🔥 ALERT: ', '')}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Saved/Recent Briefs */}
        <div className="glass-panel report-history-panel">
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.75rem' }}>
            <FileText size={15} style={{ color: 'var(--primary-bright)' }} /> Historical Briefings
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {savedReports.map((report, idx) => (
              <div 
                key={idx} 
                className="glass-card" 
                style={{ padding: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                <div style={{ overflow: 'hidden', maxWidth: '80%' }}>
                  <h4 style={{ fontSize: '0.8rem', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {report.title}
                  </h4>
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                    {report.category} • {report.generatedAt}
                  </span>
                </div>
                <ArrowUpRight size={14} style={{ color: 'var(--text-muted)', cursor: 'pointer' }} onClick={handleDownload} />
              </div>
            ))}
          </div>
        </div>

      </div>

    </div>
  );
};
