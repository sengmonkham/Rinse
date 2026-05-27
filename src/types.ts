export type Platform = 'twitter' | 'instagram' | 'youtube';

export type MomentumType = 'surging' | 'upcoming' | 'stable';

export interface SentimentDistribution {
  positive: number;
  neutral: number;
  negative: number;
}

export interface PlatformDistribution {
  twitter: number;
  instagram: number;
  youtube: number;
}

export interface DemographicData {
  label: string;
  percentage: number;
}

export interface SamplePost {
  platform: Platform;
  user: string;
  handle: string;
  avatar: string;
  content: string;
  engagement: string;
  time: string;
  mediaUrl?: string;
}

export interface Trend {
  id: string;
  name: string;
  category: string;
  volume: number;
  volumeHistory: number[];
  growth: number;
  sentiment: SentimentDistribution;
  platforms: PlatformDistribution;
  momentum: MomentumType;
  description: string;
  whyTrending: string;
  demographics: {
    age: DemographicData[];
    region: DemographicData[];
  };
  marketingAdvice: string;
  samplePosts: SamplePost[];
}

export interface ScannerBot {
  id: string;
  name: string;
  platform: Platform;
  status: 'scanning' | 'analyzing' | 'idle';
  trackers: string[];
  lastScanned: string;
  efficiency: number;
  activityCount: number;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  botId: string;
  botName: string;
  platform: Platform;
  message: string;
  type: 'info' | 'success' | 'alert';
}

export type ViewType = 'dashboard' | 'directory' | 'bots' | 'reports';
