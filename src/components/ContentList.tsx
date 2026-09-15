import { useState } from 'react';
import { FileText, Image as ImageIcon, Video, CheckCircle2, ChevronRight, AlertTriangle } from 'lucide-react';
import type { ScanResults } from '../App';

interface ContentListProps {
  scanResults: ScanResults;
}

export default function ContentList({ scanResults }: ContentListProps) {
  const { text, images, videos } = scanResults;
  const [subTab, setSubTab] = useState<'text' | 'images' | 'videos'>('text');

  const getScoreColor = (score: number) => {
    if (score >= 75) return 'var(--danger)';
    if (score >= 45) return 'var(--warning)';
    return 'var(--success)';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: '1', minHeight: '0' }}>
      
      {/* Sub tabs */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', paddingBottom: '8px' }}>
        <button
          onClick={() => setSubTab('text')}
          style={{
            background: 'none',
            border: 'none',
            color: subTab === 'text' ? 'var(--text-primary)' : 'var(--text-secondary)',
            fontWeight: subTab === 'text' ? '700' : '500',
            fontSize: '12px',
            padding: '6px 12px',
            cursor: 'pointer',
            borderBottom: subTab === 'text' ? '2px solid var(--primary)' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <FileText size={14} />
          <span>Text ({text.length})</span>
        </button>

        <button
          onClick={() => setSubTab('images')}
          style={{
            background: 'none',
            border: 'none',
            color: subTab === 'images' ? 'var(--text-primary)' : 'var(--text-secondary)',
            fontWeight: subTab === 'images' ? '700' : '500',
            fontSize: '12px',
            padding: '6px 12px',
            cursor: 'pointer',
            borderBottom: subTab === 'images' ? '2px solid var(--primary)' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <ImageIcon size={14} />
          <span>Images ({images.length})</span>
        </button>

        <button
          onClick={() => setSubTab('videos')}
          style={{
            background: 'none',
            border: 'none',
            color: subTab === 'videos' ? 'var(--text-primary)' : 'var(--text-secondary)',
            fontWeight: subTab === 'videos' ? '700' : '500',
            fontSize: '12px',
            padding: '6px 12px',
            cursor: 'pointer',
            borderBottom: subTab === 'videos' ? '2px solid var(--primary)' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <Video size={14} />
          <span>Videos ({videos.length})</span>
        </button>
      </div>

      {/* List Container */}
      <div style={{ flex: '1', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', paddingRight: '2px' }}>
        
        {/* TEXT SUB TAB */}
        {subTab === 'text' && (
          text.length === 0 ? (
            <div className="glass" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <CheckCircle2 size={36} color="var(--success)" style={{ margin: '0 auto 12px' }} />
              <h4 style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>No Suspicious Text</h4>
              <p style={{ fontSize: '12px' }}>All parsed paragraphs look naturally composed and structured.</p>
            </div>
          ) : (
            text.map((item) => (
              <div key={item.id} className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: '700', background: 'rgba(255,255,255,0.03)', padding: '2px 6px', borderRadius: '4px' }}>
                    HTML &lt;{item.tagName}&gt; Node
                  </span>
                  <span style={{ fontSize: '12px', fontWeight: '700', color: getScoreColor(item.score) }}>
                    AI Likelihood: {item.score}%
                  </span>
                </div>
                
                <p style={{ fontSize: '12px', color: 'var(--text-primary)', background: 'rgba(0,0,0,0.15)', padding: '8px 12px', borderRadius: '6px', fontStyle: 'italic', borderLeft: `2px solid ${getScoreColor(item.score)}`, lineHeight: '1.4' }}>
                  "{item.snippet}"
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ fontSize: '10px', fontWeight: '700', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Diagnostic Flags:
                  </div>
                  {item.reasons.map((reason, idx) => (
                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                      <AlertTriangle size={10} color="var(--warning)" style={{ flexShrink: '0' }} />
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )
        )}

        {/* IMAGES SUB TAB */}
        {subTab === 'images' && (
          images.length === 0 ? (
            <div className="glass" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <CheckCircle2 size={36} color="var(--success)" style={{ margin: '0 auto 12px' }} />
              <h4 style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>No AI Images Found</h4>
              <p style={{ fontSize: '12px' }}>Exposed web images match standard web compression and EXIF metadata tags.</p>
            </div>
          ) : (
            images.map((item) => (
              <div key={item.id} className="glass" style={{ padding: '12px', display: 'flex', gap: '12px' }}>
                <div style={{ width: '80px', height: '80px', borderRadius: '8px', overflow: 'hidden', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', display: 'flex', justifyContent: 'center', alignItems: 'center', flexShrink: '0' }}>
                  <img src={item.src} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="Scanned thumbnail" />
                </div>
                
                <div style={{ flex: '1', display: 'flex', flexDirection: 'column', gap: '6px', minWidth: '0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', maxWidth: '140px' }}>
                      {item.width} x {item.height} px
                    </span>
                    <span style={{ fontSize: '12px', fontWeight: '700', color: getScoreColor(item.score), whiteSpace: 'nowrap' }}>
                      AI: {item.score}%
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    {item.reasons.map((reason, idx) => (
                      <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '4px', fontSize: '10.5px', color: 'var(--text-secondary)', lineHeight: '1.3' }}>
                        <AlertTriangle size={10} color="var(--danger)" style={{ flexShrink: '0', marginTop: '2px' }} />
                        <span>{reason}</span>
                      </div>
                    ))}
                  </div>
                  
                  <a 
                    href={item.src} 
                    target="_blank" 
                    rel="noreferrer"
                    style={{ fontSize: '10px', color: 'var(--primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '2px', alignSelf: 'flex-end', marginTop: 'auto' }}
                  >
                    <span>View Image</span>
                    <ChevronRight size={10} />
                  </a>
                </div>
              </div>
            ))
          )
        )}

        {/* VIDEOS SUB TAB */}
        {subTab === 'videos' && (
          videos.length === 0 ? (
            <div className="glass" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-secondary)' }}>
              <CheckCircle2 size={36} color="var(--success)" style={{ margin: '0 auto 12px' }} />
              <h4 style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>No Suspicious Videos</h4>
              <p style={{ fontSize: '12px' }}>Embedded video streams match normal camera artifacts and audio timing.</p>
            </div>
          ) : (
            videos.map((item) => (
              <div key={item.id} className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '220px' }} title={item.src}>
                    Source: {item.src?.substring(item.src?.lastIndexOf('/') + 1) || 'Embedded Stream'}
                  </span>
                  {item.score === 0 ? (
                    <span style={{ fontSize: '12px', fontWeight: '700', color: 'var(--warning)' }}>
                      NOT ANALYZED
                    </span>
                  ) : (
                    <span style={{ fontSize: '12px', fontWeight: '700', color: getScoreColor(item.score) }}>
                      AI: {item.score}%
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {item.reasons.map((reason, idx) => (
                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                      <AlertTriangle size={10} color="var(--danger)" style={{ flexShrink: '0' }} />
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )
        )}

      </div>
    </div>
  );
}
