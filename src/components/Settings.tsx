import { useState } from 'react';
import { Settings as SettingsIcon, Save, RefreshCw, Eye, Sparkles } from 'lucide-react';
import type { AppSettings } from '../App';

interface SettingsProps {
  settings: AppSettings;
  onSave: (settings: AppSettings) => void;
}

export default function Settings({ settings, onSave }: SettingsProps) {
  const [enableText, setEnableText] = useState(settings.enableTextScan);
  const [enableImage, setEnableImage] = useState(settings.enableImageScan);
  const [enableVideo, setEnableVideo] = useState(settings.enableVideoScan);
  const [sensitivity, setSensitivity] = useState(settings.sensitivity);
  const [inlineBadges, setInlineBadges] = useState(settings.showInlineBadges);
  const [apiMode, setApiMode] = useState(settings.apiMode);
  const [apiUrl, setApiUrl] = useState(settings.apiUrl);
  const [apiKey, setApiKey] = useState(settings.apiKey);
  
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSave = () => {
    onSave({
      enableTextScan: enableText,
      enableImageScan: enableImage,
      enableVideoScan: enableVideo,
      sensitivity: sensitivity,
      showInlineBadges: inlineBadges,
      apiMode: apiMode,
      apiUrl: apiUrl,
      apiKey: apiKey
    });

    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2000);
  };

  const handleReset = () => {
    setEnableText(true);
    setEnableImage(true);
    setEnableVideo(true);
    setSensitivity(50);
    setInlineBadges(true);
    setApiMode('local');
    setApiUrl('');
    setApiKey('');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flex: '1', minHeight: '0', overflowY: 'auto', paddingRight: '2px' }}>
      
      {/* Content Scanners */}
      <div className="glass" style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <SettingsIcon size={14} color="var(--primary)" />
          <h4 style={{ fontSize: '13px', fontWeight: '700' }}>Active Content Scanning</h4>
        </div>
        
        <div className="switch-row">
          <div>
            <div style={{ fontSize: '12px', fontWeight: '700' }}>Scan Page Text</div>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Runs semantic and pattern heuristics on text blocks</div>
          </div>
          <label className="switch">
            <input 
              type="checkbox" 
              checked={enableText} 
              onChange={(e) => setEnableText(e.target.checked)} 
            />
            <span className="slider"></span>
          </label>
        </div>

        <div className="switch-row">
          <div>
            <div style={{ fontSize: '12px', fontWeight: '700' }}>Scan Page Images</div>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Audits EXIF tags and runs visual noise assessments</div>
          </div>
          <label className="switch">
            <input 
              type="checkbox" 
              checked={enableImage} 
              onChange={(e) => setEnableImage(e.target.checked)} 
            />
            <span className="slider"></span>
          </label>
        </div>

        <div className="switch-row">
          <div>
            <div style={{ fontSize: '12px', fontWeight: '700' }}>Scan Page Videos</div>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Flags synthetic structures and deepfake patterns</div>
          </div>
          <label className="switch">
            <input 
              type="checkbox" 
              checked={enableVideo} 
              onChange={(e) => setEnableVideo(e.target.checked)} 
            />
            <span className="slider"></span>
          </label>
        </div>
      </div>

      {/* Interface options */}
      <div className="glass" style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Eye size={14} color="var(--primary)" />
          <h4 style={{ fontSize: '13px', fontWeight: '700' }}>Display Preferences</h4>
        </div>

        <div className="switch-row">
          <div>
            <div style={{ fontSize: '12px', fontWeight: '700' }}>Show Inline Badges & HUD</div>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Injects floating overlays and badge tags on scanned assets</div>
          </div>
          <label className="switch">
            <input 
              type="checkbox" 
              checked={inlineBadges} 
              onChange={(e) => setInlineBadges(e.target.checked)} 
            />
            <span className="slider"></span>
          </label>
        </div>

        {/* Sensitivity slider */}
        <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: '700' }}>Heuristic Sensitivity</span>
            <span style={{ fontSize: '12px', fontWeight: '700', color: 'var(--primary)' }}>{sensitivity}%</span>
          </div>
          <input 
            type="range" 
            min="10" 
            max="90" 
            value={sensitivity} 
            onChange={(e) => setSensitivity(parseInt(e.target.value))}
            style={{ 
              width: '100%', 
              accentColor: 'var(--primary)', 
              background: 'rgba(255,255,255,0.1)', 
              height: '4px', 
              borderRadius: '2px',
              outline: 'none',
              cursor: 'pointer'
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--text-muted)' }}>
            <span>CONSERVATIVE</span>
            <span>BALANCED</span>
            <span>AGGRESSIVE</span>
          </div>
        </div>
      </div>

      {/* Cloud Model / API Configuration */}
      <div className="glass" style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Sparkles size={14} color="var(--primary)" />
          <h4 style={{ fontSize: '13px', fontWeight: '700' }}>Engine Core Settings</h4>
        </div>

        <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setApiMode('local')}
              className={`btn ${apiMode === 'local' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ flex: '1', padding: '6px 12px', fontSize: '11px', boxShadow: 'none' }}
            >
              Heuristics (Offline)
            </button>
            <button
              onClick={() => setApiMode('cloud')}
              className={`btn ${apiMode === 'cloud' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ flex: '1', padding: '6px 12px', fontSize: '11px', boxShadow: 'none' }}
            >
              Cloud Detector (API)
            </button>
          </div>

          {apiMode === 'cloud' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
              <input
                type="text"
                className="input-text"
                placeholder="https://api.aegis-detector.ai/v1"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                style={{ fontSize: '11.5px' }}
              />
              <input
                type="password"
                className="input-text"
                placeholder="Enter API Key / Bearer Token"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                style={{ fontSize: '11.5px' }}
              />
            </div>
          )}
        </div>
      </div>

      {/* Footer controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginTop: 'auto', paddingTop: '10px' }}>
        <button 
          onClick={handleReset} 
          className="btn btn-secondary"
          style={{ padding: '8px 14px' }}
        >
          <RefreshCw size={13} />
          <span>Reset Default</span>
        </button>
        
        <button 
          onClick={handleSave} 
          className="btn btn-primary"
          style={{ padding: '8px 20px', background: savedSuccess ? 'var(--success)' : '' }}
        >
          <Save size={13} />
          <span>{savedSuccess ? 'Settings Saved!' : 'Save Settings'}</span>
        </button>
      </div>

    </div>
  );
}
