import type { Trend, ScannerBot, WatchedAccount, BusinessProfile } from './types';

// ─── Seed Watched Accounts ────────────────────────────────────────────────

const TWITTER_ACCOUNTS: WatchedAccount[] = [
  { id: 'wa_t1', handle: '@sama', displayName: 'Sam Altman', platform: 'twitter', followerCount: 3200000, tier: 'mega', niche: 'AI & Tech VC', avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=60&h=60', recentSignals: ['OpenAI GPT-5', 'AI governance'], signalStrength: 91, addedAt: '2h ago' },
  { id: 'wa_t2', handle: '@naval', displayName: 'Naval Ravikant', platform: 'twitter', followerCount: 2100000, tier: 'mega', niche: 'Tech Philosophy', avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=60&h=60', recentSignals: ['crypto cycles', 'AI agents'], signalStrength: 88, addedAt: '2h ago' },
  { id: 'wa_t3', handle: '@ProfGalloway', displayName: 'Scott Galloway', platform: 'twitter', followerCount: 890000, tier: 'macro', niche: 'Tech Culture', avatar: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=60&h=60', recentSignals: ['Big Tech regulation', 'startup valuations'], signalStrength: 84, addedAt: '2h ago' },
  { id: 'wa_t4', handle: '@TechCrunch', displayName: 'TechCrunch', platform: 'twitter', followerCount: 12400000, tier: 'mega', niche: 'Breaking Tech News', avatar: 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?auto=format&fit=crop&w=60&h=60', recentSignals: ['AI funding rounds', 'startup layoffs'], signalStrength: 79, addedAt: '2h ago' },
  { id: 'wa_t5', handle: '@cobie', displayName: 'Cobie', platform: 'twitter', followerCount: 1400000, tier: 'mega', niche: 'Crypto Alpha', avatar: 'https://images.unsplash.com/photo-1519345182560-3f2917c472ef?auto=format&fit=crop&w=60&h=60', recentSignals: ['ETH sentiment shift', 'whale movement'], signalStrength: 86, addedAt: '2h ago' },
];

const INSTAGRAM_ACCOUNTS: WatchedAccount[] = [
  { id: 'wa_i1', handle: '@brittany.broski', displayName: 'Brittany Broski', platform: 'instagram', followerCount: 2900000, tier: 'mega', niche: 'Gen Z Culture', avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=60&h=60', recentSignals: ['unhinged IG notes', 'filter funeral trend'], signalStrength: 93, addedAt: '2h ago' },
  { id: 'wa_i2', handle: '@highsnobiety', displayName: 'Highsnobiety', platform: 'instagram', followerCount: 4200000, tier: 'mega', niche: 'Fashion & Street Culture', avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=60&h=60', recentSignals: ['gorpcore revival', 'deinfluencing 2.0'], signalStrength: 87, addedAt: '2h ago' },
  { id: 'wa_i3', handle: '@complexstyle', displayName: 'Complex Style', platform: 'instagram', followerCount: 3100000, tier: 'mega', niche: 'Streetwear & Hype', avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=60&h=60', recentSignals: ['brand callout wave', 'Y2K accessories'], signalStrength: 82, addedAt: '2h ago' },
  { id: 'wa_i4', handle: '@studiomcgee', displayName: 'Studio McGee', platform: 'instagram', followerCount: 2800000, tier: 'mega', niche: 'Interior Design', avatar: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=60&h=60', recentSignals: ['coastal grandmother 2.0', 'warm minimalism'], signalStrength: 76, addedAt: '2h ago' },
];

const YOUTUBE_ACCOUNTS: WatchedAccount[] = [
  { id: 'wa_y1', handle: '@penguinz0', displayName: 'penguinz0 (Cr1TiKaL)', platform: 'youtube', followerCount: 14200000, tier: 'mega', niche: 'Commentary & Gaming', avatar: 'https://images.unsplash.com/photo-1628157582853-a796fa650a6a?auto=format&fit=crop&w=60&h=60', recentSignals: ['MrBeast controversy', 'copyright apocalypse'], signalStrength: 95, addedAt: '2h ago' },
  { id: 'wa_y2', handle: '@MKBHD', displayName: 'Marques Brownlee', platform: 'youtube', followerCount: 18900000, tier: 'mega', niche: 'Tech Reviews', avatar: 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=60&h=60', recentSignals: ['M4 MacBook Pro review', 'AI phone cameras'], signalStrength: 89, addedAt: '2h ago' },
  { id: 'wa_y3', handle: '@SunnyV2', displayName: 'SunnyV2', platform: 'youtube', followerCount: 3400000, tier: 'mega', niche: 'Creator Drama', avatar: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=60&h=60', recentSignals: ['AI comment farms exposé', 'drama channel accountability'], signalStrength: 91, addedAt: '2h ago' },
  { id: 'wa_y4', handle: '@GrahamStephan', displayName: 'Graham Stephan', platform: 'youtube', followerCount: 4800000, tier: 'mega', niche: 'Finance & Real Estate', avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=60&h=60', recentSignals: ['rate cuts impact', 'housing market shift'], signalStrength: 83, addedAt: '2h ago' },
];

// ─── Real Hot/Controversial Trends ────────────────────────────────────────

export const INITIAL_TRENDS: Trend[] = [
  {
    id: 't1',
    name: '#BlockTheBot',
    category: 'Tech & AI',
    volume: 892400,
    volumeHistory: [120000, 240000, 410000, 590000, 730000, 892400],
    growth: 643,
    sentiment: { positive: 24, neutral: 5, negative: 71 },
    platforms: { twitter: 82, instagram: 8, youtube: 10 },
    momentum: 'surging',
    description: 'A coordinated mass-blocking campaign on X where users are organising to report and block accounts detected as AI-operated posting bots flooding the timeline with synthetic content.',
    whyTrending: 'A viral thread by @twitterclean exposing 40 high-follower accounts as pure ChatGPT output farms triggered outrage. X\'s algorithm was found to be amplifying these accounts 4x more than human creators.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 44 },
        { label: '25-34 (Millennials)', percentage: 38 },
        { label: '35-44 (Gen X)', percentage: 14 },
        { label: '45+', percentage: 4 }
      ],
      region: [
        { label: 'North America', percentage: 51 },
        { label: 'Europe', percentage: 31 },
        { label: 'UK', percentage: 12 },
        { label: 'Rest of World', percentage: 6 }
      ]
    },
    marketingAdvice: 'Distance brand voice from AI-sounding copy immediately. Prioritise raw, unpolished human storytelling. Show real people behind your product. Controversy = opportunity to appear authentic.',
    samplePosts: [
      { platform: 'twitter', user: 'Tech Accountability', handle: '@techaccountability', avatar: 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=80&h=80', content: 'I\'ve just blocked 2,200 accounts in 3 days using @blockthebot\'s AI-detection list. The platform is absolutely infested. My timeline is finally human again. 🧵', engagement: '48.2k likes • 12.4k retweets', time: '41min ago' },
      { platform: 'twitter', user: 'Mara Solís', handle: '@marasolis_real', avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=80&h=80', content: 'The fact that the #BlockTheBot list has 3 accounts I actually trusted following for MONTHS is genuinely disturbing. These things are indistinguishable. This is not a drill.', engagement: '29.7k likes • 8.1k retweets', time: '1h 12min ago' },
    ],
    heatScore: 94,
    trendType: 'controversial',
    platformOrigin: 'twitter',
    controversyLevel: 88,
    alertCount: 7,
    firstSeenAt: '4h ago',
    firstSeenBy: ['@sama', '@naval', '@twitterclean'],
    amplificationChain: [
      { handle: '@sama', platform: 'twitter', tier: 'mega', timestamp: '4h ago', engagementMultiplier: 4.2 },
      { handle: '@naval', platform: 'twitter', tier: 'mega', timestamp: '3.5h ago', engagementMultiplier: 3.8 },
      { handle: '@ProfGalloway', platform: 'twitter', tier: 'macro', timestamp: '2h ago', engagementMultiplier: 2.1 },
    ],
    velocityScore: 74200,
    crossPlatformScore: 28,
    predictedPeak: 'In ~3 hours',
    signalAccountCount: 4,
    emergenceScore: 91,
  },
  {
    id: 't2',
    name: 'OpenAI Exodus',
    category: 'Tech & AI',
    volume: 620300,
    volumeHistory: [48000, 130000, 260000, 390000, 510000, 620300],
    growth: 1192,
    sentiment: { positive: 18, neutral: 32, negative: 50 },
    platforms: { twitter: 71, instagram: 6, youtube: 23 },
    momentum: 'surging',
    description: '4 senior OpenAI researchers and 2 VP-level executives resigned within a 48-hour window citing alignment disagreements and internal culture concerns. Leaked internal memos surfaced on X.',
    whyTrending: 'A leaked memo thread by a pseudonymous account claiming insider status went viral. @sama\'s response was seen as evasive, triggering massive community backlash about AI lab transparency.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 28 },
        { label: '25-34 (Millennials)', percentage: 52 },
        { label: '35-44 (Gen X)', percentage: 16 },
        { label: '45+', percentage: 4 }
      ],
      region: [
        { label: 'North America', percentage: 58 },
        { label: 'Europe', percentage: 24 },
        { label: 'East Asia', percentage: 12 },
        { label: 'Rest of World', percentage: 6 }
      ]
    },
    marketingAdvice: 'AI-adjacent brands should avoid promotional messaging during this 24h window. Position around human oversight, transparency, or safety to capture positive attention.',
    samplePosts: [
      { platform: 'twitter', user: 'AI Insider', handle: '@aiinsider_anon', avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=80&h=80', content: 'Thread: What is actually happening at OpenAI right now. I spoke with 3 people who left this week. The internal culture has fundamentally changed since the board drama. This is not a normal attrition cycle. 🧵1/', engagement: '112.4k likes • 38.2k retweets', time: '6h ago' },
      { platform: 'youtube', user: 'Cold Fusion', handle: 'ColdFusion', avatar: 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?auto=format&fit=crop&w=80&h=80', content: 'The OpenAI Employee Crisis: What\'s Actually Going On Inside (Full Documentary)', engagement: '2.1M views • 89k likes', time: '5h ago' },
    ],
    heatScore: 89,
    trendType: 'breaking',
    platformOrigin: 'twitter',
    controversyLevel: 76,
    alertCount: 5,
    firstSeenAt: '6h ago',
    firstSeenBy: ['@sama', '@TechCrunch', '@benedictevans'],
    amplificationChain: [
      { handle: '@TechCrunch', platform: 'twitter', tier: 'mega', timestamp: '6h ago', engagementMultiplier: 5.1 },
      { handle: '@naval', platform: 'twitter', tier: 'mega', timestamp: '5h ago', engagementMultiplier: 3.4 },
      { handle: '@MKBHD', platform: 'youtube', tier: 'mega', timestamp: '4.5h ago', engagementMultiplier: 4.8 },
    ],
    velocityScore: 51700,
    crossPlatformScore: 61,
    predictedPeak: 'In ~6 hours',
    signalAccountCount: 6,
    emergenceScore: 88,
  },
  {
    id: 't3',
    name: 'Deinfluencing 2.0',
    category: 'Creator Economy',
    volume: 448700,
    volumeHistory: [80000, 130000, 200000, 300000, 380000, 448700],
    growth: 461,
    sentiment: { positive: 61, neutral: 22, negative: 17 },
    platforms: { twitter: 22, instagram: 62, youtube: 16 },
    momentum: 'surging',
    description: 'A new wave of content creators on Instagram and TikTok are actively telling followers NOT to buy products they\'ve previously promoted, disclosing undisclosed sponsorships and calling out toxic brand culture.',
    whyTrending: '@brittany.broski\'s 3-part series about declining a $400k deal because the brand\'s ethics didn\'t align has gone mega-viral. It\'s triggered a wave of creators coming forward with their own brand refusals.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 68 },
        { label: '25-34 (Millennials)', percentage: 24 },
        { label: '35-44 (Gen X)', percentage: 6 },
        { label: '45+', percentage: 2 }
      ],
      region: [
        { label: 'North America', percentage: 44 },
        { label: 'UK & Europe', percentage: 32 },
        { label: 'Australia', percentage: 12 },
        { label: 'Rest of World', percentage: 12 }
      ]
    },
    marketingAdvice: 'Brands must proactively audit ethical practices before approaching Gen Z creators. Authenticity-first pitching, allowing creative freedom, and public ESG commitments are now table stakes.',
    samplePosts: [
      { platform: 'instagram', user: 'Jess Reyes', handle: '@jess.creates', avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=80&h=80', content: 'I\'ve been sitting on this for months. Last year a brand offered me $80k to push a product I genuinely think is harmful. I said no. Here\'s the email thread. This is what it actually looks like in the DMs. 📱👀', engagement: '284k likes • 12.8k comments', time: '14h ago' },
      { platform: 'twitter', user: 'Creator Rights Now', handle: '@creatorrights', avatar: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=80&h=80', content: 'The deinfluencing 2.0 wave isn\'t just a vibe. It\'s a systemic pushback against extractive brand partnerships that treat creators as paid billboards. And the audience is LOUDLY backing them up.', engagement: '18.4k likes • 4.2k retweets', time: '8h ago' },
    ],
    heatScore: 78,
    trendType: 'viral',
    platformOrigin: 'instagram',
    controversyLevel: 52,
    alertCount: 3,
    firstSeenAt: '14h ago',
    firstSeenBy: ['@brittany.broski', '@highsnobiety'],
    amplificationChain: [
      { handle: '@brittany.broski', platform: 'instagram', tier: 'mega', timestamp: '14h ago', engagementMultiplier: 6.2 },
      { handle: '@complexstyle', platform: 'instagram', tier: 'mega', timestamp: '11h ago', engagementMultiplier: 2.8 },
    ],
    velocityScore: 31400,
    crossPlatformScore: 48,
    predictedPeak: 'In ~18 hours',
    signalAccountCount: 3,
    emergenceScore: 76,
  },
  {
    id: 't4',
    name: 'MrBeast Production Leak',
    category: 'Creator Drama',
    volume: 1240800,
    volumeHistory: [180000, 390000, 680000, 920000, 1100000, 1240800],
    growth: 589,
    sentiment: { positive: 14, neutral: 12, negative: 74 },
    platforms: { twitter: 31, instagram: 19, youtube: 50 },
    momentum: 'surging',
    description: 'An alleged former MrBeast production team member began posting a multi-day exposé thread revealing extreme working conditions, unpaid overtime, psychological pressure on participants, and edited-out safety incidents.',
    whyTrending: '@penguinz0\'s 47-minute video response hit 8M views in 6 hours. YouTube\'s trending page was completely overtaken. Comment sections across the platform became battlegrounds. 3 major creators have now come forward with supporting statements.',
    demographics: {
      age: [
        { label: '13-17 (Gen Alpha)', percentage: 32 },
        { label: '18-24 (Gen Z)', percentage: 46 },
        { label: '25-34 (Millennials)', percentage: 16 },
        { label: '35+', percentage: 6 }
      ],
      region: [
        { label: 'North America', percentage: 52 },
        { label: 'Latin America', percentage: 18 },
        { label: 'Europe', percentage: 20 },
        { label: 'Rest of World', percentage: 10 }
      ]
    },
    marketingAdvice: 'YouTube-adjacent brands should hold any MrBeast-themed campaigns immediately. Opportunity exists in the commentary space — brands that support creator welfare standards will capture significant goodwill.',
    samplePosts: [
      { platform: 'youtube', user: 'penguinz0', handle: 'penguinz0', avatar: 'https://images.unsplash.com/photo-1628157582853-a796fa650a6a?auto=format&fit=crop&w=80&h=80', content: 'The MrBeast Situation Is Worse Than You Think (Full Response)', engagement: '8.2M views • 420k likes', time: '9h ago' },
      { platform: 'twitter', user: 'Production Insider', handle: '@prod_insider_yt', avatar: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=80&h=80', content: 'Day 3 of my thread. Today I\'m covering the contracts participants signed and what they weren\'t told. [PART 7]. The NDA language is... something. 🧵', engagement: '82.4k likes • 29.1k retweets', time: '4h ago' },
      { platform: 'instagram', user: 'Drama Recap Daily', handle: '@dramarecap.daily', avatar: 'https://images.unsplash.com/photo-1519345182560-3f2917c472ef?auto=format&fit=crop&w=80&h=80', content: 'RECAP: Everything that has come out about @MrBeast production in the last 72 hours. Swipe for the full timeline. 👀🔥', engagement: '1.2M likes • 89k comments', time: '2h ago' },
    ],
    heatScore: 97,
    trendType: 'controversial',
    platformOrigin: 'youtube',
    controversyLevel: 95,
    alertCount: 12,
    firstSeenAt: '18h ago',
    firstSeenBy: ['@penguinz0', '@SunnyV2'],
    amplificationChain: [
      { handle: '@penguinz0', platform: 'youtube', tier: 'mega', timestamp: '18h ago', engagementMultiplier: 8.4 },
      { handle: '@SunnyV2', platform: 'youtube', tier: 'mega', timestamp: '16h ago', engagementMultiplier: 5.1 },
    ],
    velocityScore: 103200,
    crossPlatformScore: 82,
    predictedPeak: 'Peaking NOW',
    signalAccountCount: 8,
    emergenceScore: 97,
  },
  {
    id: 't5',
    name: 'AI Slop Farm Exposé',
    category: 'Tech & AI',
    volume: 334600,
    volumeHistory: [28000, 64000, 120000, 210000, 276000, 334600],
    growth: 1095,
    sentiment: { positive: 12, neutral: 18, negative: 70 },
    platforms: { twitter: 55, instagram: 14, youtube: 31 },
    momentum: 'surging',
    description: 'A viral investigation thread identifying over 200 social accounts as AI content farms — generating millions of impressions daily using ChatGPT, Midjourney and automated scheduling with zero human involvement.',
    whyTrending: 'A data journalist published a methodology for detecting AI farms based on posting cadence, vocabulary repetition, and engagement anomalies. The thread named specific accounts with verification screenshots.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 35 },
        { label: '25-34 (Millennials)', percentage: 44 },
        { label: '35-44 (Gen X)', percentage: 16 },
        { label: '45+', percentage: 5 }
      ],
      region: [
        { label: 'North America', percentage: 48 },
        { label: 'Europe', percentage: 30 },
        { label: 'South Asia', percentage: 14 },
        { label: 'Rest of World', percentage: 8 }
      ]
    },
    marketingAdvice: 'Social media managers should audit their follower engagement quality immediately. Brands with AI-heavy content strategies face significant authenticity backlash. Pivot to creator partnerships over automated content.',
    samplePosts: [
      { platform: 'twitter', user: 'data.journalist', handle: '@datajournalist_x', avatar: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=80&h=80', content: 'I spent 3 weeks building a detector for AI content farms. My model found 214 accounts posting 40-60 times per day with >94% AI-written content. Total combined followers: 28 MILLION. Thread🧵', engagement: '94.7k likes • 48.2k retweets', time: '12h ago' },
    ],
    heatScore: 82,
    trendType: 'uprising',
    platformOrigin: 'twitter',
    controversyLevel: 71,
    alertCount: 4,
    firstSeenAt: '12h ago',
    firstSeenBy: ['@sama', '@ProfGalloway'],
    amplificationChain: [
      { handle: '@TechCrunch', platform: 'twitter', tier: 'mega', timestamp: '12h ago', engagementMultiplier: 3.9 },
    ],
    velocityScore: 27800,
    crossPlatformScore: 55,
    predictedPeak: 'In ~12 hours',
    signalAccountCount: 3,
    emergenceScore: 79,
  },
  {
    id: 't6',
    name: 'Crypto Whale Alert',
    category: 'Finance & Crypto',
    volume: 218900,
    volumeHistory: [40000, 70000, 110000, 155000, 188000, 218900],
    growth: 447,
    sentiment: { positive: 34, neutral: 28, negative: 38 },
    platforms: { twitter: 74, instagram: 8, youtube: 18 },
    momentum: 'surging',
    description: 'On-chain data showing unprecedented wallet movements from long-dormant Satoshi-era Bitcoin wallets combined with unusual options positioning ahead of a scheduled Fed announcement.',
    whyTrending: '@cobie shared on-chain analysis from @lookonchain showing coordinated movements across 14 whale wallets in the 6 hours before scheduled macro data. Crypto Twitter is in full alert mode.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 22 },
        { label: '25-34 (Millennials)', percentage: 54 },
        { label: '35-44 (Gen X)', percentage: 18 },
        { label: '45+', percentage: 6 }
      ],
      region: [
        { label: 'North America', percentage: 42 },
        { label: 'East Asia', percentage: 28 },
        { label: 'Europe', percentage: 22 },
        { label: 'Rest of World', percentage: 8 }
      ]
    },
    marketingAdvice: 'Finance-adjacent brands should watch this carefully. Crypto sentiment can flip violently — either a buying frenzy or panic sell narrative. Position conservative messaging until Fed announcement clears.',
    samplePosts: [
      { platform: 'twitter', user: 'Cobie', handle: '@cobie', avatar: 'https://images.unsplash.com/photo-1519345182560-3f2917c472ef?auto=format&fit=crop&w=80&h=80', content: 'Something is moving on-chain that doesn\'t happen very often. I\'m not going to speculate on what it means but @lookonchain data is worth checking right now. Clock is ticking before the Fed presser. 👀📊', engagement: '42.1k likes • 18.7k retweets', time: '2h ago' },
    ],
    heatScore: 74,
    trendType: 'breaking',
    platformOrigin: 'twitter',
    controversyLevel: 44,
    alertCount: 2,
    firstSeenAt: '2h ago',
    firstSeenBy: ['@cobie', '@naval'],
    amplificationChain: [
      { handle: '@cobie', platform: 'twitter', tier: 'mega', timestamp: '2h ago', engagementMultiplier: 4.4 },
    ],
    velocityScore: 18200,
    crossPlatformScore: 32,
    predictedPeak: 'In ~4 hours (Fed announcement)',
    signalAccountCount: 2,
    emergenceScore: 68,
  },
  {
    id: 't7',
    name: 'Unhinged IG Notes',
    category: 'Platform Culture',
    volume: 186400,
    volumeHistory: [22000, 48000, 84000, 124000, 158000, 186400],
    growth: 748,
    sentiment: { positive: 78, neutral: 16, negative: 6 },
    platforms: { twitter: 18, instagram: 74, youtube: 8 },
    momentum: 'surging',
    description: 'Instagram\'s Notes feature (short status updates visible to followers) is being weaponised for surrealist, confessional, and absurdist content that doesn\'t fit anywhere else. The more unhinged, the more viral.',
    whyTrending: '@brittany.broski\'s note reading "the chicken at Chipotle smells different today and I can\'t move on" got 180k likes on a screenshot tweet. Gen Z found the Notes feature\'s weird limitations creatively freeing.',
    demographics: {
      age: [
        { label: '13-17 (Gen Alpha)', percentage: 28 },
        { label: '18-24 (Gen Z)', percentage: 58 },
        { label: '25-34 (Millennials)', percentage: 12 },
        { label: '35+', percentage: 2 }
      ],
      region: [
        { label: 'North America', percentage: 40 },
        { label: 'UK', percentage: 22 },
        { label: 'Australia', percentage: 12 },
        { label: 'Rest of World', percentage: 26 }
      ]
    },
    marketingAdvice: 'Brands with young audiences should experiment with genuinely weird, low-effort Notes. The anti-polish aesthetic is exactly what performs. Don\'t over-produce it — the charm is the chaos.',
    samplePosts: [
      { platform: 'instagram', user: 'Gen Z Archive', handle: '@genzarchive', avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=80&h=80', content: 'screenshotting ig notes is my entire personality rn and I refuse to apologise. "going through something but don\'t want to talk about it but also I do" is the most relatable content ever made', engagement: '412k likes • 28k comments', time: '7h ago' },
    ],
    heatScore: 71,
    trendType: 'viral',
    platformOrigin: 'instagram',
    controversyLevel: 12,
    alertCount: 2,
    firstSeenAt: '22h ago',
    firstSeenBy: ['@brittany.broski', '@complexstyle'],
    amplificationChain: [
      { handle: '@brittany.broski', platform: 'instagram', tier: 'mega', timestamp: '22h ago', engagementMultiplier: 5.2 },
    ],
    velocityScore: 15500,
    crossPlatformScore: 36,
    predictedPeak: 'In ~2 days',
    signalAccountCount: 4,
    emergenceScore: 66,
  },
  {
    id: 't8',
    name: 'Filter Funeral',
    category: 'Creator Economy',
    volume: 142300,
    volumeHistory: [18000, 32000, 56000, 88000, 116000, 142300],
    growth: 690,
    sentiment: { positive: 84, neutral: 12, negative: 4 },
    platforms: { twitter: 14, instagram: 71, youtube: 15 },
    momentum: 'upcoming',
    description: 'A new Instagram trend where creators publicly "delete" their filter presets and Lightroom profiles in real-time videos, pledging to post only unedited content. Anti-perfection aesthetics going mainstream.',
    whyTrending: 'Backlash to the clinical "clean girl" aesthetic reached a tipping point. Multiple creators with 500k+ audiences held live "filter funerals" simultaneously. Authenticity fatigue from oversaturated, identical-looking content.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 62 },
        { label: '25-34 (Millennials)', percentage: 28 },
        { label: '35+', percentage: 10 }
      ],
      region: [
        { label: 'North America', percentage: 38 },
        { label: 'Europe', percentage: 34 },
        { label: 'Australia', percentage: 14 },
        { label: 'Rest of World', percentage: 14 }
      ]
    },
    marketingAdvice: 'Move campaign creative away from over-retouched visuals. Unpolished, real-light photography and video is the new aspirational. Test "behind the scenes" and "before the edit" content immediately.',
    samplePosts: [
      { platform: 'instagram', user: 'Raw & Real', handle: '@rawandreal_co', avatar: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=80&h=80', content: 'I deleted 3 years of Lightroom presets on camera. I am terrified. I am also liberated. This is what my skin ACTUALLY looks like in morning light. No warmth boost. No clarity slider. Just me. 📷🪟', engagement: '198k likes • 14.2k comments', time: '18h ago' },
    ],
    heatScore: 63,
    trendType: 'uprising',
    platformOrigin: 'instagram',
    controversyLevel: 18,
    alertCount: 1,
    firstSeenAt: '1 day ago',
    firstSeenBy: ['@brittany.broski', '@highsnobiety'],
    amplificationChain: [
      { handle: '@highsnobiety', platform: 'instagram', tier: 'mega', timestamp: '1 day ago', engagementMultiplier: 3.1 },
    ],
    velocityScore: 11800,
    crossPlatformScore: 28,
    predictedPeak: 'In ~3 days',
    signalAccountCount: 3,
    emergenceScore: 58,
  },
];

// ─── Seed Bots ─────────────────────────────────────────────────────────────

export const INITIAL_BOTS: ScannerBot[] = [
  {
    id: 'bot_t',
    name: 'X-Scraper-Alpha',
    platform: 'twitter',
    status: 'scanning',
    trackers: ['#BlockTheBot', 'OpenAI', 'crypto whale', 'AI slop', 'tech layoffs'],
    watchedAccounts: TWITTER_ACCOUNTS,
    lastScanned: 'Just now',
    efficiency: 94,
    activityCount: 148,
    signalsDetected: 12,
    emergingCount: 3,
    mode: 'trend',
  },
  {
    id: 'bot_i',
    name: 'InstaReel-Vision-V2',
    platform: 'instagram',
    status: 'analyzing',
    trackers: ['Deinfluencing', '#FilterFuneral', 'UnhingedNotes', 'brand callout'],
    watchedAccounts: INSTAGRAM_ACCOUNTS,
    lastScanned: '2 mins ago',
    efficiency: 89,
    activityCount: 232,
    signalsDetected: 8,
    emergingCount: 2,
    mode: 'trend',
  },
  {
    id: 'bot_y',
    name: 'YT-Semantic-Parser',
    platform: 'youtube',
    status: 'scanning',
    trackers: ['MrBeast controversy', 'AI comment farms', 'copyright claims', 'drama channels'],
    watchedAccounts: YOUTUBE_ACCOUNTS,
    lastScanned: 'Just now',
    efficiency: 97,
    activityCount: 184,
    signalsDetected: 15,
    emergingCount: 4,
    mode: 'trend',
  },
  {
    id: 'bot_lead',
    name: 'Lead-Radar-Bot-01',
    platform: 'twitter',
    status: 'scanning',
    trackers: ['laptop broke', 'phone died', 'looking for', 'anyone recommend', 'need a new'],
    watchedAccounts: [],
    lastScanned: 'Just now',
    efficiency: 91,
    activityCount: 312,
    signalsDetected: 28,
    emergingCount: 0,
    mode: 'intent',
  },
];

export const CATEGORIES = [
  'All',
  'Tech & AI',
  'Creator Economy',
  'Creator Drama',
  'Platform Culture',
  'Finance & Crypto',
];

// ─── Default Business Profile ─────────────────────────────────────────────

export const DEFAULT_BUSINESS_PROFILE: BusinessProfile = {
  id: 'biz_default',
  businessName: 'TechGear Store',
  category: 'Electronics & Tech',
  targetKeywords: ['laptop', 'phone', 'macbook', 'computer', 'tablet', 'earbuds', 'keyboard', 'monitor'],
  targetPlatforms: ['twitter', 'instagram'],
  minLeadScore: 30,
  minPurchasingPower: 0,
  outreachTemplates: {
    elite: "Hey @{handle}! 👋 We saw you might need a new {product}. At {business} we have same-day delivery on MacBook Pro M4 and premium setups — ready before your next meeting? 🚀",
    high: "Hey @{handle}! Looking for a great {product}? {business} has top-rated options with fast delivery and a 2-year warranty. Check us out! 💻",
    mid: "Hey @{handle}! We've got solid {product} options at great value — free next-day delivery and a price-match guarantee. Take a look! 😊",
    budget: "Hey @{handle}! Need a {product} that doesn't break the bank? {business} has certified-refurbished options from £199 with full warranty. Student discount available! 🎓"
  },
  createdAt: new Date().toISOString(),
};

// ─── Simulated Intent Post Pool ───────────────────────────────────────────

export interface SimulatedPost {
  id: string;
  platform: 'twitter' | 'instagram';
  userHandle: string;
  userDisplayName: string;
  userAvatar: string;
  userFollowers: number;
  isPublicAccount: boolean;
  postContent: string;
  postUrl: string;
  likes: number;
  reposts: number;
  replies: number;
  postedMinutesAgo: number;
  // Purchasing power profile seed data
  buyingFrequencyPerMonth: number;
  mentionedBrands: string[];
  lifestyleSignals: string[];
  priceSensitiveCount: number;
  hasVerifiedBadge: boolean;
  accountType: 'personal' | 'business' | 'creator';
  detectedProfession?: string;
  evidencePosts: string[];
}

export const SIMULATED_INTENT_POSTS: SimulatedPost[] = [
  // Replacement Intent — HIGH power
  { id: 'sp1', platform: 'twitter', userHandle: '@marcus_cto', userDisplayName: 'Marcus Chen', userAvatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=60&h=60', userFollowers: 8200, isPublicAccount: true, postContent: 'laptop died mid client call. absolutely done. need a replacement like yesterday — anyone running the new MacBook Pro M4?', postUrl: 'https://twitter.com/marcus_cto/status/1795001001001', likes: 42, reposts: 8, replies: 14, postedMinutesAgo: 12, buyingFrequencyPerMonth: 6, mentionedBrands: ['Apple', 'Bose', 'Tesla', 'Sony'], lifestyleSignals: ['business travel', 'fine dining', 'client meetings'], priceSensitiveCount: 0, hasVerifiedBadge: false, accountType: 'personal', detectedProfession: 'CTO', evidencePosts: ['just picked up the new AirPods Max (3 days ago)', 'M3 Mac Studio arrived today (2mo ago)', 'treating myself to a Sonos Arc (4mo ago)'] },
  
  // Replacement Intent — BUDGET power
  { id: 'sp2', platform: 'twitter', userHandle: '@student_jake99', userDisplayName: 'Jake Williams', userAvatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=60&h=60', userFollowers: 320, isPublicAccount: true, postContent: 'my laptop just died and i have a 3000 word essay due tomorrow help 😭 need something cheap asap', postUrl: 'https://twitter.com/student_jake99/status/1795002002002', likes: 6, reposts: 1, replies: 22, postedMinutesAgo: 28, buyingFrequencyPerMonth: 1, mentionedBrands: ['Amazon Basics', 'eBay', 'Argos'], lifestyleSignals: [], priceSensitiveCount: 3, hasVerifiedBadge: false, accountType: 'personal', detectedProfession: 'Student', evidencePosts: ['found this refurbished keyboard for £15 (1mo ago)', 'anyone know any discount codes for Argos? (2mo ago)'] },

  // Active Shopping — HIGH power
  { id: 'sp3', platform: 'twitter', userHandle: '@sarah_design', userDisplayName: 'Sarah Okafor', userAvatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=60&h=60', userFollowers: 12400, isPublicAccount: true, postContent: 'my laptop screen just cracked and i have a client presentation tomorrow omg 😭 does anyone know a quick fix or should I just get a new one?', postUrl: 'https://twitter.com/sarah_design/status/1795003003003', likes: 84, reposts: 12, replies: 48, postedMinutesAgo: 8, buyingFrequencyPerMonth: 4, mentionedBrands: ['Apple', 'Adobe', 'Lululemon'], lifestyleSignals: ['fitness', 'brunch', 'client work'], priceSensitiveCount: 0, hasVerifiedBadge: false, accountType: 'creator', detectedProfession: 'Designer', evidencePosts: ['new iPad Pro arrived (1mo ago)', 'splurged on the Apple Pencil Pro (2mo ago)'] },

  // Competitor Defection — MID power
  { id: 'sp4', platform: 'twitter', userHandle: '@dev_ramirez', userDisplayName: 'Carlos Ramirez', userAvatar: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=60&h=60', userFollowers: 2840, isPublicAccount: true, postContent: 'never buying Samsung again honestly. the battery bloated after 18 months and their support is completely useless. looking at Pixel 9 or iPhone 16 — what are people running?', postUrl: 'https://twitter.com/dev_ramirez/status/1795004004004', likes: 28, reposts: 4, replies: 31, postedMinutesAgo: 45, buyingFrequencyPerMonth: 3, mentionedBrands: ['Samsung', 'Google', 'Apple', 'Nike'], lifestyleSignals: ['gym', 'weekend travel'], priceSensitiveCount: 1, hasVerifiedBadge: false, accountType: 'personal', detectedProfession: 'Developer', evidencePosts: ['picked up the Samsung Galaxy Ultra (18mo ago)', 'new mechanical keyboard arrived (3mo ago)'] },

  // Active Shopping — ELITE power
  { id: 'sp5', platform: 'instagram', userHandle: '@eleanor_vc', userDisplayName: 'Eleanor Park', userAvatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=60&h=60', userFollowers: 34800, isPublicAccount: true, postContent: 'looking for the best noise-cancelling headphones for long-haul. have been using Bose QC45 for 2 years and thinking of upgrading — Sony XM5 or AirPods Max?', postUrl: 'https://instagram.com/p/eleanor_vc_headphones_2024', likes: 124, reposts: 0, replies: 89, postedMinutesAgo: 22, buyingFrequencyPerMonth: 8, mentionedBrands: ['Bose', 'Sony', 'Apple', 'Rimowa', 'Emirates'], lifestyleSignals: ['business class', 'Nobu', 'fine dining', 'wellness retreats', 'private events'], priceSensitiveCount: 0, hasVerifiedBadge: true, accountType: 'creator', detectedProfession: 'Venture Partner', evidencePosts: ['Rimowa set arrived for the Singapore trip (1mo ago)', 'AirTag for every bag obsession (2mo ago)', 'upgraded to Sonos Era 300 (3mo ago)', 'Tesla Model 3 picked up last week (4mo ago)'] },

  // Service Need — MID power
  { id: 'sp6', platform: 'twitter', userHandle: '@tom_freelance', userDisplayName: 'Tom Bradley', userAvatar: 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?auto=format&fit=crop&w=60&h=60', userFollowers: 1820, isPublicAccount: true, postContent: 'my work laptop is running so slow it\'s actually costing me money. anyone know a good IT repair shop in Manchester? or should I just replace it?', postUrl: 'https://twitter.com/tom_freelance/status/1795006006006', likes: 12, reposts: 2, replies: 18, postedMinutesAgo: 67, buyingFrequencyPerMonth: 2, mentionedBrands: ['Dell', 'Microsoft'], lifestyleSignals: ['freelance work', 'coffee shops'], priceSensitiveCount: 2, hasVerifiedBadge: false, accountType: 'personal', detectedProfession: 'Freelancer', evidencePosts: ['new monitor stand finally (5mo ago)', 'second hand Dell XPS 13 is actually great (8mo ago)'] },

  // Aspirational — LOW power
  { id: 'sp7', platform: 'twitter', userHandle: '@aspire_dan', userDisplayName: 'Daniel Ross', userAvatar: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=60&h=60', userFollowers: 610, isPublicAccount: true, postContent: 'dream purchase: MacBook Pro M4. someday when I\'m not completely broke. for now my 2017 HP is on life support 😅', postUrl: 'https://twitter.com/aspire_dan/status/1795007007007', likes: 18, reposts: 1, replies: 7, postedMinutesAgo: 140, buyingFrequencyPerMonth: 0, mentionedBrands: ['HP'], lifestyleSignals: [], priceSensitiveCount: 4, hasVerifiedBadge: false, accountType: 'personal', evidencePosts: ['payday can\'t come fast enough (2wk ago)', 'anyone know discount codes for tech? (1mo ago)'] },

  // Replacement — HIGH power
  { id: 'sp8', platform: 'instagram', userHandle: '@amira_fintech', userDisplayName: 'Amira Hassan', userAvatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=60&h=60', userFollowers: 5600, isPublicAccount: true, postContent: 'phone screen shattered in Lisbon 😭 dropped it getting off the flight. what are people getting as flagship Android right now? need same-day options', postUrl: 'https://instagram.com/p/amira_fintech_phone_2024', likes: 76, reposts: 0, replies: 34, postedMinutesAgo: 35, buyingFrequencyPerMonth: 5, mentionedBrands: ['Samsung', 'Google', 'Dyson', 'Le Creuset'], lifestyleSignals: ['business travel', 'international trips', 'premium restaurants'], priceSensitiveCount: 0, hasVerifiedBadge: false, accountType: 'personal', detectedProfession: 'Finance Director', evidencePosts: ['Dyson Airwrap arrived (2mo ago)', 'new Samsung Galaxy fold (6mo ago)', 'Le Creuset set finally (3mo ago)'] },
];
