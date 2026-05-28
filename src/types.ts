// ─── Platform & Base Types ─────────────────────────────────────────────────

export type Platform = 'twitter' | 'instagram' | 'youtube';

export type MomentumType = 'surging' | 'upcoming' | 'stable' | 'fading';

export type TrendType = 'viral' | 'controversial' | 'uprising' | 'breaking' | 'fading';

export type ViewType = 'dashboard' | 'directory' | 'bots' | 'reports' | 'leads';

// ─── Shared Sub-types ──────────────────────────────────────────────────────

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

// ─── Account Watchlist ──────────────────────────────────────────────────────

export interface WatchedAccount {
  id: string;
  handle: string;           // "@sama", "@MKBHD"
  displayName: string;
  platform: Platform;
  followerCount: number;    // for influence weighting
  tier: 'mega' | 'macro' | 'micro'; // >5M, 100k–5M, <100k
  niche: string;            // "Tech VC", "Gen Z Beauty", "Crypto"
  avatar: string;
  recentSignals: string[];  // topics this account has posted about recently
  signalStrength: number;   // 0–100, prediction accuracy score
  addedAt: string;
}

// ─── Trend Intelligence ────────────────────────────────────────────────────

export interface AmplificationEvent {
  handle: string;
  platform: Platform;
  tier: 'mega' | 'macro' | 'micro';
  timestamp: string;
  engagementMultiplier: number;
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

  // New intelligence fields
  heatScore: number;              // 0–100 composite score
  trendType: TrendType;
  platformOrigin: Platform;       // where it started
  controversyLevel: number;       // 0–100
  alertCount: number;
  firstSeenAt: string;
  firstSeenBy: string[];          // account handles who first posted
  amplificationChain: AmplificationEvent[];
  velocityScore: number;          // mentions/hour
  crossPlatformScore: number;     // 0–100
  predictedPeak: string;          // estimated peak time label
  signalAccountCount: number;     // watched accounts talking about it
  emergenceScore: number;         // 0–100, early signal strength
}

// ─── Alert System ──────────────────────────────────────────────────────────

export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical';

export type AlertType =
  | 'early_signal'
  | 'velocity_spike'
  | 'cross_platform'
  | 'controversy_escalation'
  | 'breaking'
  | 'hot_lead';

export interface TrendAlert {
  id: string;
  type: AlertType;
  title: string;
  message: string;
  trend?: Trend;
  leadId?: string;
  triggeredAt: string;
  accountsInvolved: string[];
  severity: AlertSeverity;
  dismissed: boolean;
}

// ─── Scanner Bot ───────────────────────────────────────────────────────────

export interface ScannerBot {
  id: string;
  name: string;
  platform: Platform;
  status: 'scanning' | 'analyzing' | 'idle';
  trackers: string[];
  watchedAccounts: WatchedAccount[];
  lastScanned: string;
  efficiency: number;
  activityCount: number;
  signalsDetected: number;
  emergingCount: number;
  mode: 'trend' | 'intent';      // which engine this bot runs
}

// ─── Log System ───────────────────────────────────────────────────────────

export interface LogEntry {
  id: string;
  timestamp: string;
  botId: string;
  botName: string;
  platform: Platform;
  message: string;
  type: 'info' | 'success' | 'alert';
}

// ─── Lead Radar / Buyer Intent ────────────────────────────────────────────

export type IntentSignalType =
  | 'replacement_intent'
  | 'active_shopping'
  | 'competitor_defection'
  | 'aspirational'
  | 'service_need';

export type PurchasingPowerTier = 'elite' | 'high' | 'mid' | 'budget' | 'low_signal';

export interface LeadPost {
  id: string;
  platform: Platform;
  userHandle: string;
  userDisplayName: string;
  userAvatar: string;
  userFollowers: number;
  isPublicAccount: boolean;
  postContent: string;
  postUrl: string;
  postedAt: string;
  likes: number;
  reposts: number;
  replies: number;
}

export interface BuyerProfile {
  purchasingPowerScore: number;       // 0–100
  purchasingPowerTier: PurchasingPowerTier;

  buyingFrequency: 'high' | 'medium' | 'low';
  buyingFrequencyCount: number;       // estimated purchases/month

  brandTier: 'premium' | 'mid' | 'budget';
  mentionedBrands: string[];

  lifestyleSignals: string[];         // e.g. ['travel', 'dining', 'fitness']
  lifestyleTier: 'high' | 'medium' | 'low';

  priceSensitiveFlags: string[];
  hasPriceSensitivity: boolean;

  accountType: 'personal' | 'business' | 'creator';
  followerCount: number;
  hasVerifiedBadge: boolean;
  detectedProfession?: string;

  evidencePosts: string[];            // snippets of purchase posts found
  profileConfidenceScore: number;     // 0–100
}

export interface BuyerLead {
  id: string;
  post: LeadPost;
  buyerProfile: BuyerProfile;
  intentType: IntentSignalType;
  productCategory: string;
  detectedKeywords: string[];
  leadScore: number;                  // 0–100 composite (intent + purchasing power)
  purchasingPowerScore: number;       // 0–100 sub-score
  urgencyLevel: 'critical' | 'high' | 'medium' | 'low';
  detectedAt: string;
  matchedBusinessTypes: string[];
  suggestedOutreach: string;          // auto-adapted to buyer tier
  status: 'new' | 'viewed' | 'contacted' | 'dismissed';
  isHot: boolean;                     // leadScore > 80
}

export interface BusinessProfile {
  id: string;
  businessName: string;
  category: string;
  targetKeywords: string[];
  targetPlatforms: Platform[];
  targetLocation?: string;
  minLeadScore: number;
  minPurchasingPower: number;         // 0–100, filter out weak buyers
  outreachTemplates: {
    elite: string;
    high: string;
    mid: string;
    budget: string;
  };
  createdAt: string;
}
