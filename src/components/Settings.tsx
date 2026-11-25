import { useState } from 'react';
import { 
  Settings as SettingsIcon, 
  Save, 
  RefreshCw, 
  Eye, 
  Sparkles, 
  User, 
  ExternalLink, 
  CreditCard, 
  CheckCircle2, 
  AlertCircle,
  Key
} from 'lucide-react';
import type { AppSettings, SubscriptionState } from '../App';
import { DEPLOYED_API_URL, LOCAL_API_URL } from '../backend';

interface SettingsProps {
  settings: AppSettings;
  onSave: (settings: AppSettings) => void;
  subscription?: SubscriptionState;
  onSyncSubscription?: () => Promise<SubscriptionState>;
}

export default function Settings({ settings, onSave, subscription, onSyncSubscription }: SettingsProps) {
  const [enableText, setEnableText] = useState(settings.enableTextScan);
  const [enableImage, setEnableImage] = useState(settings.enableImageScan);
  const [enableVideo, setEnableVideo] = useState(settings.enableVideoScan);
  const [sensitivity, setSensitivity] = useState(settings.sensitivity);
  const [inlineBadges, setInlineBadges] = useState(settings.showInlineBadges);
  const [autoImageOverlays, setAutoImageOverlays] = useState(settings.autoImageOverlays !== undefined ? settings.autoImageOverlays : false);
  const [showVibecodedAlert, setShowVibecodedAlert] = useState(settings.showVibecodedAlert !== undefined ? settings.showVibecodedAlert : false);
  const [apiMode, setApiMode] = useState(settings.apiMode);
  const [apiTarget, setApiTarget] = useState(settings.apiTarget || 'deployed');
  const [apiUrl, setApiUrl] = useState(settings.apiUrl || DEPLOYED_API_URL);
  const [apiKey, setApiKey] = useState(settings.apiKey);
  const [webAppUrl, setWebAppUrl] = useState(settings.webAppUrl || 'http://localhost:3000');
  const [authToken, setAuthToken] = useState(settings.authToken || '');
  
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleSave = () => {
    onSave({
      enableTextScan: enableText,
      enableImageScan: enableImage,
      enableVideoScan: enableVideo,
      sensitivity: sensitivity,
      showInlineBadges: inlineBadges,
      autoImageOverlays: autoImageOverlays,
      showVibecodedAlert: showVibecodedAlert,
      apiMode: apiMode,
      apiTarget: apiTarget,
      apiUrl: apiUrl,
      apiKey: apiKey,
      webAppUrl: webAppUrl,
      authToken: authToken
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
    setAutoImageOverlays(false);
    setShowVibecodedAlert(false);
    setApiMode('cloud');
    setApiTarget('deployed');
    setApiUrl(DEPLOYED_API_URL);
    setApiKey('');
    setWebAppUrl('http://localhost:3000');
    setAuthToken('');
  };

  const handleSync = async () => {
    if (!onSyncSubscription) return;
    setSyncing(true);
    setSyncResult(null);
    try {
      // First save the current auth token / webAppUrl
      onSave({
        enableTextScan: enableText,
        enableImageScan: enableImage,
        enableVideoScan: enableVideo,
        sensitivity: sensitivity,
        showInlineBadges: inlineBadges,
        autoImageOverlays: autoImageOverlays,
        showVibecodedAlert: showVibecodedAlert,
        apiMode: apiMode,
        apiTarget: apiTarget,
        apiUrl: apiUrl,
        apiKey: apiKey,
        webAppUrl: webAppUrl,
        authToken: authToken
      });

      const updated = await onSyncSubscription();
      if (updated.isPaying) {
        setSyncResult({
          type: 'success',
          message: `Synced: ${updated.plan.toUpperCase()} Plan active`
        });
      } else if (authToken) {
        setSyncResult({
          type: 'success',
          message: 'Connected (Free Tier)'
        });
      } else {
        setSyncResult({
          type: 'success',
          message: 'Status checked (Free Tier)'
        });
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to connect to web app';
      setSyncResult({
        type: 'error',
        message: msg
      });
    } finally {
      setSyncing(false);
      setTimeout(() => setSyncResult(null), 4000);
    }
  };

  const isPaying = Boolean(subscription?.isPaying);
  const currentPlan = subscription?.plan || 'free';
  const expiresAt = subscription?.expiresAt ? new Date(subscription.expiresAt).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  }) : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flex: '1', minHeight: '0', overflowY: 'auto', paddingRight: '2px' }}>
      
      {/* Account & Subscription Section */}
      <div className="glass" style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <User size={14} color="var(--primary)" />
            <h4 style={{ fontSize: '13px', fontWeight: '700' }}>Account & Subscription</h4>
          </div>
          <span 
            style={{ 
              fontSize: '10px', 
              fontWeight: '700',
              padding: '2px 8px',
              borderRadius: '9999px',
              background: isPaying ? 'rgba(5, 150, 105, 0.12)' : 'rgba(15, 23, 42, 0.05)',
              color: isPaying ? '#059669' : 'var(--text-muted)',
              border: isPaying ? '1px solid rgba(5, 150, 105, 0.25)' : '1px solid rgba(15, 23, 42, 0.08)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px'
            }}
          >
            {isPaying ? <Sparkles size={10} color="#059669" /> : null}
            {isPaying ? `${currentPlan.toUpperCase()} ACTIVE` : 'FREE PLAN'}
          </span>
        </div>

        <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Plan Status Banner */}
          <div 
            style={{ 
              padding: '12px', 
              borderRadius: '10px', 
              background: isPaying ? 'rgba(5, 150, 105, 0.06)' : 'rgba(15, 23, 42, 0.02)',
              border: isPaying ? '1px solid rgba(5, 150, 105, 0.2)' : '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}
          >
            <div>
              <div style={{ fontSize: '12px', fontWeight: '700', color: isPaying ? '#059669' : 'var(--text-primary)' }}>
                {isPaying ? `${currentPlan.toUpperCase()} Member` : 'Free Tier'}
              </div>
              <div style={{ fontSize: '10.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {isPaying && expiresAt 
                  ? `Renews / valid until ${expiresAt}`
                  : isPaying
                  ? 'Unlimited scanning active'
                  : 'Standard offline heuristics enabled'}
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: '6px' }}>
              {isPaying ? (
                <a
                  href={`${webAppUrl}/account`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-secondary"
                  style={{ padding: '5px 10px', fontSize: '11px', textDecoration: 'none' }}
                >
                  <CreditCard size={12} />
                  <span>Manage</span>
                </a>
              ) : (
                <a
                  href={`${webAppUrl}/pricing`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-primary"
                  style={{ padding: '5px 12px', fontSize: '11px', textDecoration: 'none' }}
                >
                  <Sparkles size={12} />
                  <span>Upgrade</span>
                </a>
              )}
            </div>
          </div>

          {/* Web App Pairing / Auth Token */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontSize: '11.5px', fontWeight: '600', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Key size={12} />
                <span>Web Account Token / License Key</span>
              </label>
              <a
                href={`${webAppUrl}/account`}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: '10.5px', color: 'var(--primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '3px' }}
              >
                <span>Get token from web</span>
                <ExternalLink size={10} />
              </a>
            </div>

            <input
              type="password"
              className="input-text"
              placeholder="Paste Bearer session token or license key..."
              value={authToken}
              onChange={(e) => setAuthToken(e.target.value)}
              style={{ fontSize: '11.5px' }}
            />

            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                type="text"
                className="input-text"
                placeholder="Web App URL (e.g. http://localhost:3000)"
                value={webAppUrl}
                onChange={(e) => setWebAppUrl(e.target.value)}
                style={{ fontSize: '11px', flex: '1' }}
              />
              <button
                type="button"
                onClick={handleSync}
                disabled={syncing}
                className="btn btn-secondary"
                style={{ padding: '8px 12px', fontSize: '11px', whiteSpace: 'nowrap' }}
              >
                <RefreshCw size={11} className={syncing ? 'pulse-glow' : ''} />
                <span>{syncing ? 'Checking...' : 'Check Status'}</span>
              </button>
            </div>

            {syncResult && (
              <div 
                style={{ 
                  fontSize: '11px', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '6px',
                  color: syncResult.type === 'success' ? 'var(--success)' : 'var(--danger)',
                  marginTop: '2px'
                }}
              >
                {syncResult.type === 'success' ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
                <span>{syncResult.message}</span>
              </div>
            )}
          </div>
        </div>
      </div>

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

        <div className="switch-row">
          <div>
            <div style={{ fontSize: '12px', fontWeight: '700' }}>Show Image Overlays Automatically</div>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Displays AI image boxes on load (if off, hold Option/Alt key to show)</div>
          </div>
          <label className="switch">
            <input 
              type="checkbox" 
              checked={autoImageOverlays} 
              onChange={(e) => setAutoImageOverlays(e.target.checked)} 
            />
            <span className="slider"></span>
          </label>
        </div>

        <div className="switch-row">
          <div>
            <div style={{ fontSize: '12px', fontWeight: '700' }}>Show VibeCoded Alerts</div>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>Displays top banner alert warning when visiting VibeCoded websites</div>
          </div>
          <label className="switch">
            <input 
              type="checkbox" 
              checked={showVibecodedAlert} 
              onChange={(e) => setShowVibecodedAlert(e.target.checked)} 
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
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => setApiTarget('deployed')}
                  className={`btn ${apiTarget === 'deployed' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ flex: '1', padding: '6px 10px', fontSize: '11px', boxShadow: 'none' }}
                >
                  Deployed Server
                </button>
                <button
                  onClick={() => setApiTarget('local')}
                  className={`btn ${apiTarget === 'local' ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ flex: '1', padding: '6px 10px', fontSize: '11px', boxShadow: 'none' }}
                >
                  Local Server
                </button>
              </div>

              {apiTarget === 'deployed' ? (
                <input
                  type="text"
                  className="input-text"
                  placeholder={DEPLOYED_API_URL}
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  style={{ fontSize: '11.5px' }}
                  title="Deployed server URL"
                />
              ) : (
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  Local server:{' '}
                  <code style={{ background: 'rgba(0,0,0,0.25)', padding: '1px 4px', borderRadius: '3px' }}>{LOCAL_API_URL}</code>
                </div>
              )}

              <input
                type="password"
                className="input-text"
                placeholder="Enter API Key / Bearer Token"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                style={{ fontSize: '11.5px' }}
              />

              <div style={{ fontSize: '10px', color: 'var(--text-muted)', lineHeight: 1.45 }}>
                The deployed Space requires its <strong>API_KEY</strong> secret as the bearer token above.
                A local server accepts any token when it runs without <code style={{ background: 'rgba(0,0,0,0.25)', padding: '1px 4px', borderRadius: '3px' }}>API_KEY</code> set.
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', lineHeight: 1.45 }}>
                Text sandbox uses the <strong>StoryScope</strong> narrative detector (arXiv:2604.03136) via
                <code style={{ background: 'rgba(0,0,0,0.25)', padding: '1px 4px', borderRadius: '3px' }}> /predict/storyscope</code>.
                The server runs an <strong>offline rule-based engine by default</strong> — no API key needed, ~10 ms per story.
                For higher accuracy, set <code style={{ background: 'rgba(0,0,0,0.25)', padding: '1px 4px', borderRadius: '3px' }}>STORYSCOPE_MODE=llm</code> and
                <code style={{ background: 'rgba(0,0,0,0.25)', padding: '1px 4px', borderRadius: '3px' }}>STORYSCOPE_LLM_API_KEY</code> (or OPENAI/ANTHROPIC/GOOGLE key) on the server.
              </div>
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
