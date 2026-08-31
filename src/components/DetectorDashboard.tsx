import { Scan, Eye, EyeOff, FileText, Image as ImageIcon, Video, HelpCircle, AlertTriangle } from 'lucide-react';
import type { ScanResults } from '../App';

interface DashboardProps {
  scanResults: ScanResults;
  scanning: boolean;
  onScanQuick: () => void;
  onScanDeep: () => void;
  disabled: boolean;
  aiHidden: boolean;
  onToggleHideAI: () => void;
}

export default function DetectorDashboard({ scanResults, scanning, onScanQuick, onScanDeep, disabled, aiHidden, onToggleHideAI }: DashboardProps) {
  const { score, text, images, videos } = scanResults;

  // Calculate stroke parameters for progress circle (Radius = 50, Circumference = 314.16)
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  // Determine integrity category
  const getIntegrityStatus = (scoreValue: number) => {
    if (scoreValue >= 80) return { label: "Human Authentic", color: "var(--success)", bg: "var(--success-glow)", desc: "This page shows high indicators of natural human authorship. Low generative density." };
    if (scoreValue >= 45) return { label: "Mixed Integrity", color: "var(--warning)", bg: "var(--warning-glow)", desc: "This page contains a blend of human writing and potential AI-assisted copy or imagery." };
    return { label: "Synthetic / AI Heavy", color: "var(--danger)", bg: "var(--danger-glow)", desc: "High density of generative AI writing, automated content, or synthetic visual assets." };
  };

  // Before any scan has run, show a neutral state instead of a misleading 100%
  const hasScanned = scanResults.scannedAt != null;
  const status = hasScanned
    ? getIntegrityStatus(score)
    : { label: 'Awaiting Scan', color: 'var(--text-muted)', bg: 'transparent', desc: 'Trigger a scan to evaluate this page authenticity.' };
  const displayOffset = hasScanned ? strokeDashoffset : circumference;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: '1' }}>

      {/* Vibecoded Warning Card */}
      {scanResults.vibecoded?.isVibecoded && (
        <div
          className="glass"
          style={{
            padding: '12px 14px',
            borderRadius: '10px',
            background: '#fef3c7',
            border: '1px solid rgba(245, 158, 11, 0.35)',
            boxShadow: '0 4px 12px rgba(245, 158, 11, 0.08)',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
            <AlertTriangle size={20} color="#b45309" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <h4 style={{ fontSize: '12px', fontWeight: '600', color: '#78350f', lineHeight: '1.4', margin: 0 }}>
                This website might be VibeCoded.
              </h4>
              {scanResults.vibecoded.reasons && scanResults.vibecoded.reasons.length > 0 && (
                <ul style={{ paddingLeft: '14px', margin: '4px 0 0 0', fontSize: '11px', color: '#92400e', lineHeight: '1.4' }}>
                  {scanResults.vibecoded.reasons.map((reason, idx) => (
                    <li key={idx} style={{ marginBottom: '2px' }}>{reason}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Circular Gauge Card */}
      <div className={`glass ${scanning ? 'scan-animation' : ''}`} style={{ padding: '20px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
        <h3 style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)', fontWeight: '600' }}>
          Authenticity Evaluation
        </h3>

        <div className="gauge-wrapper">
          <svg className="gauge-svg" viewBox="0 0 120 120">
            <circle className="gauge-bg" cx="60" cy="60" r={radius} />
            <circle
              className="gauge-fill"
              cx="60"
              cy="60"
              r={radius}
              stroke={status.color}
              strokeDasharray={circumference}
              strokeDashoffset={displayOffset}
              style={{
                filter: `drop-shadow(0 0 6px ${status.color})`
              }}
            />
          </svg>
          <div className="gauge-label">
            <span className="gauge-value" style={{ color: status.color }}>
              {scanning ? '...' : hasScanned ? `${score}%` : '--'}
            </span>
            <span className="gauge-desc">Integrity</span>
          </div>
        </div>

        <div>
          <span
            style={{
              display: 'inline-block',
              padding: '3px 10px',
              borderRadius: '20px',
              fontSize: '12px',
              fontWeight: '600',
              color: status.color,
              background: status.bg,
              border: hasScanned ? `1px solid ${status.color}33` : '1px solid var(--border-color)',
              marginBottom: '6px'
            }}
          >
            {scanning ? 'Analyzing...' : status.label}
          </span>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', maxWidth: '360px', margin: '0 auto', lineHeight: '1.5' }}>
            {scanning ? 'Scanning DOM text, file headers, and framerate stability.' : status.desc}
          </p>
        </div>
      </div>

      {/* Grid Stats */}
      <div className="dashboard-grid">
        <div className="glass stat-card" style={{ borderLeft: `3px solid ${text.length > 0 ? 'var(--warning)' : 'var(--border-color)'}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px', color: 'var(--text-muted)' }}>
            <FileText size={13} />
            <span style={{ fontSize: '11px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.04em' }}>AI Text</span>
          </div>
          <div className="stat-val" style={{ color: text.length > 0 ? 'var(--warning)' : 'var(--text-primary)' }}>
            {text.length}
          </div>
        </div>

        <div className="glass stat-card" style={{ borderLeft: `3px solid ${images.length > 0 ? 'var(--danger)' : 'var(--border-color)'}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px', color: 'var(--text-muted)' }}>
            <ImageIcon size={13} />
            <span style={{ fontSize: '11px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.04em' }}>AI Images</span>
          </div>
          <div className="stat-val" style={{ color: images.length > 0 ? 'var(--danger)' : 'var(--text-primary)' }}>
            {images.length}
          </div>
        </div>

        <div className="glass stat-card" style={{ borderLeft: `3px solid ${videos.length > 0 ? 'var(--danger)' : 'var(--border-color)'}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px', color: 'var(--text-muted)' }}>
            <Video size={13} />
            <span style={{ fontSize: '11px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.04em' }}>AI Videos</span>
          </div>
          <div className="stat-val" style={{ color: videos.length > 0 ? 'var(--danger)' : 'var(--text-primary)' }}>
            {videos.length}
          </div>
        </div>
      </div>

      {/* Primary Scanning Actions */}
      <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <button
          onClick={onScanDeep}
          disabled={scanning || disabled}
          className="btn btn-primary"
          style={{ width: '100%', padding: '10px' }}
        >
          <Eye size={16} />
          <span>{scanning ? 'Laser Sweeping Webpage...' : 'Trigger Visual Deep Scan'}</span>
        </button>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={onScanQuick}
            disabled={scanning || disabled}
            className="btn btn-secondary"
            style={{ flex: '1', padding: '8px' }}
          >
            <Scan size={14} />
            <span>Re-Scan Page</span>
          </button>
        </div>

        <button
          onClick={onToggleHideAI}
          disabled={disabled}
          className={`btn ${aiHidden ? 'btn-primary' : 'btn-secondary'}`}
          style={{ 
            width: '100%', 
            padding: '8px', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center', 
            gap: '8px',
            background: aiHidden ? '#EF4444' : '',
            borderColor: aiHidden ? '#EF4444' : ''
          }}
        >
          <EyeOff size={14} style={{ color: aiHidden ? 'white' : 'var(--text-secondary)' }} />
          <span style={{ color: aiHidden ? 'white' : 'var(--text-primary)', fontWeight: '700', fontSize: '12px' }}>
            {aiHidden ? 'Show Hidden AI Content' : 'Hide AI Generated Content'}
          </span>
        </button>

        {disabled && (
          <p style={{ fontSize: '11px', color: 'var(--danger)', textAlign: 'center', marginTop: '2px' }}>
            Chrome extension API is locked on this browser tab.
          </p>
        )}
      </div>

      {/* Quick guide */}
      <div style={{ display: 'flex', gap: '8px', padding: '0 2px', fontSize: '12px', color: 'var(--text-muted)', lineHeight: '1.5' }}>
        <HelpCircle size={14} style={{ flexShrink: 0, marginTop: '1px' }} />
        <span>Hover or click tags on the webpage to inspect text heuristics and image markers in real-time.</span>
      </div>

    </div>
  );
}
