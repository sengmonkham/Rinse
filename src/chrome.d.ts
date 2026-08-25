// Minimal typed surface for the Chrome extension APIs used by the app.
// These APIs only exist when running as an unpacked extension; the app
// detects their absence and falls back to standalone preview mode.

interface ChromeLastError {
  message?: string;
}

interface ChromeRuntime {
  readonly id: string | undefined;
  readonly lastError: ChromeLastError | undefined;
  sendMessage(message: unknown, callback?: (response: MessageResponse) => void): void;
}

interface ChromeTabInfo {
  id?: number;
  url?: string;
  title?: string;
}

interface ChromeQueryInfo {
  active?: boolean;
  currentWindow?: boolean;
}

interface ScanHistoryEntry {
  url: string;
  title: string;
  score: number;
  stats: {
    textCount: number;
    imageCount: number;
    videoCount: number;
  };
  timestamp: number;
  vibecoded?: {
    isVibecoded: boolean;
    reasons: string[];
    hasPurpleGradient: boolean;
    hasBubbleHeader: boolean;
  };
}

interface MessageResponse {
  status?: string;
  data?: unknown;
  isHidden?: boolean;
  history?: ScanHistoryEntry[];
}

interface ChromeTabs {
  query(queryInfo: ChromeQueryInfo, callback: (tabs: ChromeTabInfo[]) => void): void;
  sendMessage(tabId: number, message: unknown, callback?: (response: MessageResponse) => void): void;
}

interface ChromeStorageLocal {
  get(keys: string | string[], callback: (items: Record<string, unknown>) => void): void;
  set(items: Record<string, unknown>, callback?: () => void): void;
}

interface ChromeStorage {
  local: ChromeStorageLocal;
}

declare const chrome: {
  runtime: ChromeRuntime;
  tabs: ChromeTabs;
  storage: ChromeStorage;
};

interface Window {
  chrome?: typeof chrome;
}
