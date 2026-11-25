// Backend targets shared by the extension UI. The service worker keeps its own
// copy (public/background.js is plain JS and is not bundled).
export const DEPLOYED_API_URL = 'https://senkmonkham-rinse-detector.hf.space';
export const LOCAL_API_URL = 'http://localhost:5001';

export interface BackendTargetSettings {
  apiTarget?: string;
  apiUrl?: string;
}

/**
 * Resolve the backend base URL for the selected target. "deployed" (the
 * default) uses settings.apiUrl, falling back to the hosted Space; "local"
 * always uses the developer server on this machine. A `/predict...` suffix and
 * trailing slashes are stripped, so a pasted endpoint works too.
 */
export function resolveApiBase(settings?: BackendTargetSettings | null): string {
  const s = settings || {};
  const target =
    s.apiTarget === 'local' || (!s.apiTarget && /localhost|127\.0\.0\.1/.test(s.apiUrl || ''))
      ? 'local'
      : 'deployed';
  const fallback = target === 'local' ? LOCAL_API_URL : DEPLOYED_API_URL;
  const raw = (target === 'local' ? LOCAL_API_URL : s.apiUrl || DEPLOYED_API_URL).trim();
  return raw.replace(/\/predict(\/.*)?$/, '').replace(/\/+$/, '') || fallback;
}
