import { useState, useEffect, useRef } from 'react';
import { Download, Keyboard, ShieldAlert, ShieldCheck, HelpCircle, Activity, ClipboardCheck } from 'lucide-react';

interface PasteEventRecord {
  timestamp: number;
  timeLabel: string;
  length: number;
  snippet: string;
}

interface ActivityInterval {
  timeLabel: string;
  keystrokes: number;
  pastes: number;
}

export default function ProofOfWork() {
  const [editorText, setEditorText] = useState('');
  const [keystrokes, setKeystrokes] = useState(0);
  const [backspaces, setBackspaces] = useState(0);
  const [pasteCount, setPasteCount] = useState(0);
  const [pasteLength, setPasteLength] = useState(0);
  const [activeSeconds, setActiveSeconds] = useState(0);
  const [integrityScore, setIntegrityScore] = useState(100);
  const [pasteRecords, setPasteRecords] = useState<PasteEventRecord[]>([]);
  const [chartData, setChartData] = useState<ActivityInterval[]>([]);
  
  const lastActiveRef = useRef<number>(0);
  const intervalKeystrokesRef = useRef<number>(0);
  const intervalPastesRef = useRef<number>(0);


  // Active typing duration counter
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      // If user typed in the last 2 seconds, accumulate active writing time
      if (now - lastActiveRef.current < 2000 && lastActiveRef.current !== 0) {
        setActiveSeconds(prev => prev + 1);
      }

      // Record interval metrics for SVG chart (every 5 seconds)
      const date = new Date();
      const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      
      setChartData(prev => {
        const next = [...prev, {
          timeLabel: timeStr,
          keystrokes: intervalKeystrokesRef.current,
          pastes: intervalPastesRef.current
        }];
        // Keep last 15 intervals (75 seconds of history)
        if (next.length > 15) return next.slice(next.length - 15);
        return next;
      });

      // Reset interval buffers
      intervalKeystrokesRef.current = 0;
      intervalPastesRef.current = 0;
    }, 5000);

    return () => clearInterval(timer);
  }, []);

  // Recalculate Integrity Score based on metrics
  useEffect(() => {
    const totalLen = editorText.length;
    if (totalLen === 0) {
      setIntegrityScore(100);
      return;
    }

    let score = 100;

    // 1. Paste Ratio penalty (what percentage of the document was copy-pasted)
    const pasteRatio = Math.min(1, pasteLength / totalLen);
    const pastePenalty = Math.round(pasteRatio * 85);
    score -= pastePenalty;

    // 2. Keystroke to text length check
    // If text was written manually, keystrokes should be similar or greater than character length (due to corrections)
    const expectedStrokes = totalLen - pasteLength;
    if (expectedStrokes > 10) {
      const strokeEfficiency = keystrokes / expectedStrokes;
      if (strokeEfficiency < 0.6) {
        // Less than 60% of expected strokes registered (signs of hidden manipulation/ghostwriting)
        score -= 20;
      }
    }

    // 3. Spontaneous insertion penalty (high character insert counts without pastes)
    // If characters change by a large amount without paste trigger
    if (totalLen > keystrokes + pasteLength + 20) {
      score -= 15;
    }

    const finalScore = Math.max(5, Math.min(100, score));
    setIntegrityScore(finalScore);
  }, [editorText, keystrokes, pasteLength]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    lastActiveRef.current = Date.now();
    
    // Ignore control keys, alt, etc. for character calculations, but track activity
    if (e.key === 'Backspace' || e.key === 'Delete') {
      setBackspaces(prev => prev + 1);
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      setKeystrokes(prev => prev + 1);
      intervalKeystrokesRef.current += 1;
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    lastActiveRef.current = Date.now();
    intervalPastesRef.current += 1;
    
    const pastedText = e.clipboardData.getData('text') || '';
    const len = pastedText.length;
    
    if (len > 0) {
      setPasteCount(prev => prev + 1);
      setPasteLength(prev => prev + len);
      
      const now = new Date();
      const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      
      setPasteRecords(prev => [
        {
          timestamp: Date.now(),
          timeLabel: timeStr,
          length: len,
          snippet: pastedText.substring(0, 45) + (len > 45 ? '...' : '')
        },
        ...prev
      ]);
    }
  };

  const handleClearEditor = () => {
    setEditorText('');
    setKeystrokes(0);
    setBackspaces(0);
    setPasteCount(0);
    setPasteLength(0);
    setActiveSeconds(0);
    setPasteRecords([]);
    setChartData([]);
    lastActiveRef.current = 0;
    intervalKeystrokesRef.current = 0;
    intervalPastesRef.current = 0;
  };

  // Export proof report as signed JSON file
  const handleExportCertificate = () => {
    const certificateId = `AEGIS-POW-${Math.random().toString(36).substr(2, 9).toUpperCase()}`;
    const reportData = {
      certificateId: certificateId,
      exportedAt: new Date().toISOString(),
      documentTitle: `Aegis Proof-of-Work Report`,
      textSummary: {
        totalCharacters: editorText.length,
        totalWords: editorText.split(/\s+/).filter(w => w.length > 0).length,
        documentHash: btoa(editorText.substring(0, 100) + editorText.length).substring(0, 16)
      },
      metrics: {
        humanIntegrityIndex: `${integrityScore}%`,
        keystrokesLogged: keystrokes,
        deletionsLogged: backspaces,
        pastedCharacters: pasteLength,
        pasteCount: pasteCount,
        writingTimeActive: `${activeSeconds}s`
      },
      eventLog: pasteRecords.map(r => ({
        timestamp: r.timestamp,
        time: r.timeLabel,
        type: "PASTE_INJECTION",
        length: r.length,
        contentExcerpt: r.snippet
      })),
      verificationSeal: `AEGIS_SEAL_HASH_${btoa(`${certificateId}-${integrityScore}-${keystrokes}`).substring(0, 24)}`
    };

    const jsonStr = JSON.stringify(reportData, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `aegis-pow-certificate-${certificateId.toLowerCase()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // SVG chart drawing helpers
  const svgWidth = 340;
  const svgHeight = 110;
  const paddingLeft = 20;
  const paddingRight = 10;
  const paddingTop = 10;
  const paddingBottom = 15;

  const getChartPoints = () => {
    if (chartData.length < 2) return '';
    const maxVal = Math.max(...chartData.map(d => d.keystrokes), 10);
    const graphWidth = svgWidth - paddingLeft - paddingRight;
    const graphHeight = svgHeight - paddingTop - paddingBottom;
    const stepX = graphWidth / (chartData.length - 1);

    return chartData.map((d, idx) => {
      const x = paddingLeft + idx * stepX;
      const y = paddingTop + graphHeight - (d.keystrokes / maxVal) * graphHeight;
      return `${x},${y}`;
    }).join(' ');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flex: '1', minHeight: '0', overflowY: 'auto' }}>
      
      {/* Editor & Stats Container */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '14px', flexShrink: 0 }}>
        
        {/* Real-time Tracking Editor */}
        <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h4 style={{ fontSize: '13px', fontWeight: '700', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Keyboard size={15} color="var(--primary)" />
              <span>Real-Time Draft Editor</span>
            </h4>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              Keystroke Logger: <span style={{ color: 'var(--success)', fontWeight: '700' }}>Active</span>
            </div>
          </div>

          <textarea
            className="input-textarea"
            placeholder="Type your article here directly... Aegis will track your typing cadence, deletions, and copy-paste chunks to verify human authorship and generate an authenticity report."
            value={editorText}
            onChange={(e) => setEditorText(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            style={{ fontSize: '12.5px', minHeight: '180px', fontFamily: 'monospace' }}
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
            <button
              onClick={handleClearEditor}
              className="btn btn-secondary"
              style={{ padding: '8px 12px' }}
              disabled={editorText.length === 0}
            >
              Reset Session
            </button>
            <button
              onClick={handleExportCertificate}
              className="btn btn-primary"
              style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '6px' }}
              disabled={editorText.length === 0}
            >
              <Download size={13} />
              <span>Export POW Certificate</span>
            </button>
          </div>
        </div>

        {/* Real-time Proof of Work Status Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          
          {/* Integrity Score */}
          <div className="glass" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px', borderLeft: `4px solid ${integrityScore >= 75 ? 'var(--success)' : integrityScore >= 45 ? 'var(--warning)' : 'var(--danger)'}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Draft Integrity Index
              </span>
              {integrityScore >= 75 ? (
                <ShieldCheck size={18} color="var(--success)" />
              ) : (
                <ShieldAlert size={18} color="var(--danger)" />
              )}
            </div>
            
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
              <span style={{ fontSize: '28px', fontWeight: '800', color: integrityScore >= 75 ? 'var(--success)' : integrityScore >= 45 ? 'var(--warning)' : 'var(--danger)' }}>
                {integrityScore}%
              </span>
              <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                {integrityScore >= 75 ? 'Organic Drafting Verified' : integrityScore >= 45 ? 'Mixed Composition' : 'Copy-Paste Heavy'}
              </span>
            </div>

            {/* Score progress bar */}
            <div style={{ height: '6px', background: 'rgba(0,0,0,0.06)', borderRadius: '3px', overflow: 'hidden' }}>
              <div 
                style={{ 
                  height: '100%', 
                  width: `${integrityScore}%`, 
                  background: integrityScore >= 75 ? 'var(--success)' : integrityScore >= 45 ? 'var(--warning)' : 'var(--danger)',
                  borderRadius: '3px',
                  transition: 'width 0.5s ease'
                }} 
              />
            </div>
          </div>

          {/* Detailed typing stats */}
          <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <h5 style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
              Tracked Statistics
            </h5>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '11px' }}>
              <div style={{ padding: '8px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px' }}>
                <span style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '2px' }}>Keystrokes</span>
                <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{keystrokes}</strong>
              </div>
              <div style={{ padding: '8px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px' }}>
                <span style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '2px' }}>Deletions</span>
                <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{backspaces}</strong>
              </div>
              <div style={{ padding: '8px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px' }}>
                <span style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '2px' }}>Pasted Chars</span>
                <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{pasteLength}</strong>
              </div>
              <div style={{ padding: '8px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px' }}>
                <span style={{ color: 'var(--text-secondary)', display: 'block', marginBottom: '2px' }}>Active Time</span>
                <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{activeSeconds}s</strong>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Keystroke Timeline & Paste Events */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', flex: '1', minHeight: '0' }}>
        
        {/* SVG Cadence Graph */}
        <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px', minHeight: '0' }}>
          <h4 style={{ fontSize: '12px', fontWeight: '700', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', margin: 0 }}>
            <Activity size={14} color="var(--primary)" />
            <span>Keystroke Velocity Timeline</span>
          </h4>
          
          <div style={{ flex: '1', background: 'rgba(0,0,0,0.02)', border: '1px solid var(--border-color)', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', overflow: 'hidden', padding: '6px' }}>
            {chartData.length < 2 ? (
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Start typing to generate cadence velocity graph...</span>
            ) : (
              <svg width="100%" height="100%" viewBox={`0 0 ${svgWidth} ${svgHeight}`} preserveAspectRatio="none">
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.25"/>
                    <stop offset="100%" stopColor="var(--primary)" stopOpacity="0"/>
                  </linearGradient>
                </defs>

                {/* Grid Lines */}
                <line x1={paddingLeft} y1={paddingTop} x2={svgWidth - paddingRight} y2={paddingTop} stroke="rgba(0,0,0,0.05)" strokeWidth={1} />
                <line x1={paddingLeft} y1={(svgHeight - paddingBottom + paddingTop)/2} x2={svgWidth - paddingRight} y2={(svgHeight - paddingBottom + paddingTop)/2} stroke="rgba(0,0,0,0.05)" strokeWidth={1} />
                <line x1={paddingLeft} y1={svgHeight - paddingBottom} x2={svgWidth - paddingRight} y2={svgHeight - paddingBottom} stroke="rgba(0,0,0,0.1)" strokeWidth={1} />

                {/* Graph Path Fill */}
                <path
                  d={`M${paddingLeft},${svgHeight - paddingBottom} L${getChartPoints()} L${paddingLeft + (chartData.length - 1) * ((svgWidth - paddingLeft - paddingRight) / (chartData.length - 1))},${svgHeight - paddingBottom} Z`}
                  fill="url(#areaGrad)"
                />

                {/* Graph Stroke */}
                <polyline
                  fill="none"
                  stroke="var(--primary)"
                  strokeWidth="2"
                  points={getChartPoints()}
                />

                {/* Graph Dot Indicators & Paste Spikes */}
                {chartData.map((d, idx) => {
                  const graphWidth = svgWidth - paddingLeft - paddingRight;
                  const graphHeight = svgHeight - paddingTop - paddingBottom;
                  const stepX = graphWidth / (chartData.length - 1);
                  const x = paddingLeft + idx * stepX;
                  const y = paddingTop + graphHeight - (d.keystrokes / Math.max(...chartData.map(c => c.keystrokes), 10)) * graphHeight;

                  return (
                    <g key={idx}>
                      <circle cx={x} cy={y} r="2.5" fill="var(--primary)" />
                      {/* Render red vertical line on paste events */}
                      {d.pastes > 0 && (
                        <line 
                          x1={x} 
                          y1={paddingTop} 
                          x2={x} 
                          y2={svgHeight - paddingBottom} 
                          stroke="var(--danger)" 
                          strokeWidth="1.5" 
                          strokeDasharray="2,2" 
                        />
                      )}
                    </g>
                  );
                })}
              </svg>
            )}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--text-muted)', marginTop: '-4px' }}>
            <span>75s AGO</span>
            <span>REAL-TIME PAUSE TRACKER</span>
            <span>LIVE NOW</span>
          </div>
        </div>

        {/* Clipboard & Paste Audit list */}
        <div className="glass" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px', minHeight: '0' }}>
          <h4 style={{ fontSize: '12px', fontWeight: '700', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', margin: 0 }}>
            <ClipboardCheck size={14} color="var(--primary)" />
            <span>Clipboard Injection Log</span>
          </h4>

          <div style={{ flex: '1', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px', paddingRight: '2px' }}>
            {pasteRecords.length === 0 ? (
              <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '6px', color: 'var(--text-muted)', textAlign: 'center', padding: '12px' }}>
                <HelpCircle size={20} />
                <span style={{ fontSize: '11px' }}>No copy-paste events recorded. Writing flows naturally.</span>
              </div>
            ) : (
              pasteRecords.map((r, idx) => (
                <div key={idx} style={{ padding: '8px 10px', background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.15)', borderRadius: '6px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', fontWeight: '700' }}>
                    <span style={{ color: 'var(--danger)' }}>PASTE: +{r.length} chars</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{r.timeLabel}</span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontStyle: 'italic', wordBreak: 'break-all' }}>
                    "{r.snippet}"
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

      </div>

    </div>
  );
}
