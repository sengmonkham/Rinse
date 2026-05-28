import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  Trend, ScannerBot, LogEntry, Platform, TrendAlert, AlertSeverity,
  BuyerLead, BuyerProfile, BusinessProfile, PurchasingPowerTier, IntentSignalType
} from '../types';
import { INITIAL_TRENDS, INITIAL_BOTS, DEFAULT_BUSINESS_PROFILE, SIMULATED_INTENT_POSTS } from '../mockData';
import type { SimulatedPost } from '../mockData';

// ─── Purchasing Power Profiler ─────────────────────────────────────────────

function computeBuyerProfile(post: SimulatedPost): BuyerProfile {
  const {
    buyingFrequencyPerMonth,
    mentionedBrands,
    lifestyleSignals,
    priceSensitiveCount,
    hasVerifiedBadge,
    userFollowers,
    accountType,
    detectedProfession,
    evidencePosts,
  } = post;

  // Brand tier classification
  const PREMIUM_BRANDS = ['Apple', 'Sony', 'Bose', 'Tesla', 'BMW', 'Mercedes', 'Gucci', 'Rimowa', 'Emirates', 'Dyson', 'Le Creuset', 'Sonos', 'Adobe', 'Lululemon', 'Nike', 'Dell XPS', 'ThinkPad'];
  const BUDGET_BRANDS = ['Amazon Basics', 'Argos', 'eBay', 'Primark', 'Shein', 'HP', 'refurbished'];

  const premiumCount = mentionedBrands.filter(b => PREMIUM_BRANDS.some(pb => b.toLowerCase().includes(pb.toLowerCase()))).length;
  const budgetCount = mentionedBrands.filter(b => BUDGET_BRANDS.some(bb => b.toLowerCase().includes(bb.toLowerCase()))).length;

  const brandTier: 'premium' | 'mid' | 'budget' =
    premiumCount >= 2 ? 'premium' :
    budgetCount >= 2 ? 'budget' :
    premiumCount > 0 ? 'mid' : 'budget';

  // Buying frequency
  const buyingFrequency: 'high' | 'medium' | 'low' =
    buyingFrequencyPerMonth >= 5 ? 'high' :
    buyingFrequencyPerMonth >= 2 ? 'medium' : 'low';

  // Lifestyle tier
  const HIGH_LIFESTYLE = ['business travel', 'fine dining', 'client meetings', 'wellness retreats', 'private events', 'international trips', 'business class', 'Nobu', 'premium restaurants'];
  const highLifestyleCount = lifestyleSignals.filter(s => HIGH_LIFESTYLE.some(h => s.toLowerCase().includes(h.toLowerCase()))).length;
  const lifestyleTier: 'high' | 'medium' | 'low' =
    highLifestyleCount >= 2 ? 'high' :
    lifestyleSignals.length > 0 ? 'medium' : 'low';

  // Price sensitivity
  const hasPriceSensitivity = priceSensitiveCount >= 2;

  // Account type bonuses
  const verifiedBonus = hasVerifiedBadge ? 5 : 0;
  const followerBonus = userFollowers >= 10000 ? 3 : userFollowers >= 1000 ? 1 : 0;
  const professionBonus = ['CTO', 'CEO', 'Founder', 'Director', 'Consultant', 'Doctor', 'VP', 'Partner', 'Finance Director', 'Venture Partner'].includes(detectedProfession || '') ? 5 : 0;
  const professionPenalty = ['Student', 'Intern', 'Apprentice'].includes(detectedProfession || '') ? -3 : 0;
  const businessBonus = accountType === 'business' ? 8 : accountType === 'creator' ? 3 : 0;

  // Compute purchasing power score (0–100)
  const buyingFrequencyScore = buyingFrequency === 'high' ? 40 : buyingFrequency === 'medium' ? 25 : 10;
  const brandScore = brandTier === 'premium' ? 30 : brandTier === 'mid' ? 18 : 5;
  const lifestyleScore = lifestyleTier === 'high' ? 15 : lifestyleTier === 'medium' ? 8 : 0;
  const pricePenalty = hasPriceSensitivity ? Math.min(priceSensitiveCount * 4, 15) : 0;

  const rawScore = buyingFrequencyScore + brandScore + lifestyleScore
    + verifiedBonus + followerBonus + professionBonus + professionPenalty + businessBonus
    - pricePenalty;

  const purchasingPowerScore = Math.min(100, Math.max(0, rawScore));

  const purchasingPowerTier: PurchasingPowerTier =
    purchasingPowerScore >= 85 ? 'elite' :
    purchasingPowerScore >= 65 ? 'high' :
    purchasingPowerScore >= 45 ? 'mid' :
    purchasingPowerScore >= 25 ? 'budget' : 'low_signal';

  // Confidence (based on how much evidence we have)
  const evidenceCount = evidencePosts.length + mentionedBrands.length + lifestyleSignals.length;
  const profileConfidenceScore = Math.min(100, evidenceCount * 12 + (buyingFrequencyPerMonth * 5));

  return {
    purchasingPowerScore,
    purchasingPowerTier,
    buyingFrequency,
    buyingFrequencyCount: buyingFrequencyPerMonth,
    brandTier,
    mentionedBrands,
    lifestyleSignals,
    lifestyleTier,
    priceSensitiveFlags: priceSensitiveCount > 0 ? ['price-sensitive language detected'] : [],
    hasPriceSensitivity,
    accountType: post.accountType,
    followerCount: userFollowers,
    hasVerifiedBadge,
    detectedProfession,
    evidencePosts,
    profileConfidenceScore,
  };
}

// ─── Intent Classifier ─────────────────────────────────────────────────────

const INTENT_PATTERNS = {
  replacement_intent: ['broke', 'died', 'cracked', 'shattered', 'stopped working', 'life support', 'done for', 'RIP to my', 'need a replacement', 'is dead'],
  active_shopping: ['anyone recommend', 'looking for', 'best for', 'thinking of buying', 'which should I', 'what are people running', 'options for'],
  competitor_defection: ['never buying', 'switching from', 'done with', 'never again', 'useless', 'letting me down'],
  aspirational: ['dream purchase', 'someday', 'one day', 'saving up for', 'wish I had', 'when I\'m not broke'],
  service_need: ['anyone know a good', 'need a repair', 'looking for a shop', 'IT repair', 'fix my'],
};

function classifyIntent(content: string): IntentSignalType | null {
  const lower = content.toLowerCase();
  for (const [intent, patterns] of Object.entries(INTENT_PATTERNS)) {
    if (patterns.some(p => lower.includes(p.toLowerCase()))) {
      return intent as IntentSignalType;
    }
  }
  return null;
}

const URGENCY_KEYWORDS = ['asap', 'yesterday', 'urgent', 'right now', 'immediately', 'today', 'this morning', 'help', 'tomorrow', 'deadline'];

function computeLeadScore(
  post: SimulatedPost,
  intentType: IntentSignalType,
  buyerProfile: BuyerProfile
): number {
  const intentBoost = { replacement_intent: 40, active_shopping: 30, competitor_defection: 25, service_need: 20, aspirational: 15 }[intentType];
  const lower = post.postContent.toLowerCase();
  const urgencyBonus = URGENCY_KEYWORDS.some(k => lower.includes(k)) ? 20 : 0;
  const publicBonus = post.isPublicAccount ? 10 : 0;
  const timePenalty = post.postedMinutesAgo > 1440 ? 25 : post.postedMinutesAgo > 720 ? 15 : post.postedMinutesAgo > 360 ? 5 : 0;
  const buyingFrequencyBonus = buyerProfile.buyingFrequency === 'high' ? 15 : buyerProfile.buyingFrequency === 'medium' ? 8 : 2;
  const brandBonus = buyerProfile.brandTier === 'premium' ? 10 : buyerProfile.brandTier === 'mid' ? 5 : 0;
  const lifestyleBonus = buyerProfile.lifestyleTier === 'high' ? 5 : buyerProfile.lifestyleTier === 'medium' ? 2 : 0;

  return Math.min(100, Math.max(0,
    intentBoost + urgencyBonus + publicBonus - timePenalty
    + buyingFrequencyBonus + brandBonus + lifestyleBonus
  ));
}

function generateOutreach(post: SimulatedPost, intentType: IntentSignalType, profile: BuyerProfile, business: BusinessProfile): string {
  const handle = post.userHandle;
  const biz = business.businessName;
  const tier = profile.purchasingPowerTier;
  const templates = business.outreachTemplates;
  const product = business.targetKeywords[0] || 'device';

  const template = tier === 'elite' ? templates.elite :
    tier === 'high' ? templates.high :
    tier === 'mid' ? templates.mid : templates.budget;

  return template
    .replace(/{handle}/g, handle)
    .replace(/{business}/g, biz)
    .replace(/{product}/g, product);
}

// ─── Main Hook ─────────────────────────────────────────────────────────────

export const useTrendSimulator = () => {
  const [trends, setTrends] = useState<Trend[]>(INITIAL_TRENDS);
  const [bots, setBots] = useState<ScannerBot[]>(INITIAL_BOTS);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [alerts, setAlerts] = useState<TrendAlert[]>([]);
  const [leads, setLeads] = useState<BuyerLead[]>([]);
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile>(DEFAULT_BUSINESS_PROFILE);
  const logIdCounter = useRef(0);
  const processedPostIds = useRef<Set<string>>(new Set());

  // ── Helper: Add Log ──────────────────────────────────────────────────────
  const addLog = useCallback((botId: string, botName: string, platform: Platform, message: string, type: 'info' | 'success' | 'alert' = 'info') => {
    const newLog: LogEntry = {
      id: `log_${Date.now()}_${logIdCounter.current++}`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      botId, botName, platform, message, type,
    };
    setLogs(prev => [newLog, ...prev].slice(0, 100));
  }, []);

  // ── Helper: Add Alert ────────────────────────────────────────────────────
  const addAlert = useCallback((alert: Omit<TrendAlert, 'id' | 'dismissed'>) => {
    const newAlert: TrendAlert = {
      ...alert,
      id: `alert_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      dismissed: false,
    };
    setAlerts(prev => [newAlert, ...prev].slice(0, 20));
  }, []);

  // ── Init Logs ────────────────────────────────────────────────────────────
  useEffect(() => {
    INITIAL_BOTS.forEach((bot, index) => {
      setTimeout(() => {
        addLog(bot.id, bot.name, bot.platform,
          bot.mode === 'intent'
            ? `Lead Radar initialized. Scanning for buyer intent signals across ${bot.platform}.`
            : `Bot initialized. Monitoring ${bot.watchedAccounts.length} accounts + [${bot.trackers.join(', ')}]`,
          'info'
        );
      }, index * 400);
    });
  }, []);

  // ── Trend Intelligence Engine ────────────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      const trendBots = bots.filter(b => b.status !== 'idle' && b.mode === 'trend');
      if (trendBots.length === 0) return;

      const bot = trendBots[Math.floor(Math.random() * trendBots.length)];

      // Rotate bot status
      setBots(prev => prev.map(b => b.id === bot.id ? {
        ...b,
        status: Math.random() > 0.35 ? 'scanning' : 'analyzing',
        activityCount: b.activityCount + 1,
        lastScanned: 'Just now',
      } : b));

      // Platform-specific log templates
      const account = bot.watchedAccounts[Math.floor(Math.random() * bot.watchedAccounts.length)];
      const trend = trends[Math.floor(Math.random() * trends.filter(t => t.platformOrigin === bot.platform).length)];
      const keyword = bot.trackers[Math.floor(Math.random() * bot.trackers.length)] || 'activity';

      const isAlertTick = Math.random() > 0.88;
      let message = '';
      let logType: 'info' | 'success' | 'alert' = 'info';

      if (bot.platform === 'twitter') {
        const msgs = [
          `🐦 X/Trending tab: "${keyword}" ranked in top-5 nationally. Scraping ${(Math.random() * 2000 + 800).toFixed(0)} new posts/min.`,
          `🐦 Account signal: ${account?.handle || '@account'} posted about "${keyword}". Tier: ${account?.tier?.toUpperCase() || 'MACRO'}. Scanning amplification chain.`,
          `🐦 Cross-referencing "${keyword}" engagement rates across ${(Math.random() * 40 + 10).toFixed(0)} tracked accounts. Quality score: ${bot.efficiency}%.`,
          `🐦 Sentiment index for "${keyword}": ${Math.round(Math.random() * 40 + 30)}% negative — controversy flag raised.`,
        ];
        message = msgs[Math.floor(Math.random() * msgs.length)];
        logType = 'info';
      } else if (bot.platform === 'instagram') {
        const msgs = [
          `📸 Reel algorithm pushing "${keyword}" content. Engagement-to-follower ratio: ${(Math.random() * 6 + 2).toFixed(1)}x normal.`,
          `📸 ${account?.handle || '@creator'} shared "${keyword}" content. ${Math.round(Math.random() * 50000 + 10000).toLocaleString()} views in first 2 hours.`,
          `📸 Hashtag velocity for #${keyword.replace(/\s/g, '')} spiked +${Math.round(Math.random() * 80 + 20)}% in last 30 mins.`,
          `📸 Visual trend cluster identified: ${(Math.random() * 12 + 4).toFixed(0)} watched accounts using similar aesthetic around "${keyword}".`,
        ];
        message = msgs[Math.floor(Math.random() * msgs.length)];
        logType = 'success';
      } else {
        const msgs = [
          `📺 Comment velocity on "${trend?.name || keyword}" hit ${Math.round(Math.random() * 15000 + 3000).toLocaleString()}/hr. Sentiment: ${Math.round(Math.random() * 40 + 40)}% negative.`,
          `📺 ${account?.handle || '@creator'} opened a video on "${keyword}" (search-trend signal detected). Estimated upload: 4–8 hours.`,
          `📺 Trending page rank for "${keyword}": #${Math.round(Math.random() * 8 + 1)}. Comment section flagged: high-controversy.`,
          `📺 Semantic cluster analysis: "${keyword}" appearing in ${Math.round(Math.random() * 40 + 12)} channel comment sections simultaneously.`,
        ];
        message = msgs[Math.floor(Math.random() * msgs.length)];
        logType = 'info';
      }

      if (isAlertTick && trend) {
        const spike = Math.round(Math.random() * 80 + 20);
        message = `🔥 SPIKE ALERT: "${trend.name}" search velocity +${spike}% in the last 15 minutes! ${trend.signalAccountCount} watched accounts active.`;
        logType = 'alert';

        addAlert({
          type: trend.emergenceScore > 85 ? 'breaking' : trend.controversyLevel > 70 ? 'controversy_escalation' : 'velocity_spike',
          title: `${trend.trendType === 'breaking' ? '🔴 BREAKING' : trend.trendType === 'controversial' ? '⚡ CONTROVERSY' : '🔥 SPIKE'}`,
          message: `"${trend.name}" +${spike}% velocity on ${bot.platform}. ${trend.signalAccountCount} tracked accounts posting.`,
          trend,
          triggeredAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          accountsInvolved: trend.firstSeenBy.slice(0, 3),
          severity: trend.emergenceScore > 90 ? 'critical' : trend.emergenceScore > 75 ? 'high' : 'medium',
        });

        // Update alert count on trend
        setTrends(prev => prev.map(t => t.id === trend.id ? {
          ...t,
          alertCount: t.alertCount + 1,
          emergenceScore: Math.min(100, t.emergenceScore + Math.random() * 3),
        } : t));
      }

      addLog(bot.id, bot.name, bot.platform, message, logType);

      // Mutate trend volumes
      setTrends(prev => prev.map(t => {
        const isMatch = bot.trackers.some(k => t.name.toLowerCase().includes(k.toLowerCase()) || t.category.toLowerCase().includes(k.toLowerCase()));
        if (!isMatch) return t;
        const growthPct = isAlertTick ? 1.06 : 1 + (Math.random() * 0.018 - 0.004);
        const nextVol = Math.round(t.volume * growthPct);
        const updatedHistory = [...t.volumeHistory.slice(1), nextVol];
        const initialVol = updatedHistory[0] || 1;
        return {
          ...t,
          volume: nextVol,
          volumeHistory: updatedHistory,
          growth: Math.round(((nextVol - initialVol) / initialVol) * 100),
          velocityScore: Math.round(t.velocityScore * (1 + Math.random() * 0.04 - 0.01)),
          heatScore: Math.min(100, t.heatScore + (isAlertTick ? Math.random() * 2 : 0)),
        };
      }));

    }, 3800);

    return () => clearInterval(interval);
  }, [bots, trends, addLog, addAlert]);

  // ── Lead Detector Engine ─────────────────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      const leadBot = bots.find(b => b.mode === 'intent' && b.status !== 'idle');
      if (!leadBot) return;

      // Pick an unprocessed post from the pool
      const unprocessed = SIMULATED_INTENT_POSTS.filter(p => !processedPostIds.current.has(p.id));

      if (unprocessed.length === 0) {
        // Reset pool to allow cycling
        processedPostIds.current.clear();
        return;
      }

      const post = unprocessed[Math.floor(Math.random() * unprocessed.length)];
      processedPostIds.current.add(post.id);

      const intentType = classifyIntent(post.postContent);
      if (!intentType) return;

      const buyerProfile = computeBuyerProfile(post);
      const leadScore = computeLeadScore(post, intentType, buyerProfile);

      // Filter by business profile minimum score
      if (leadScore < businessProfile.minLeadScore) {
        addLog(leadBot.id, leadBot.name, leadBot.platform,
          `🔍 Intent signal from ${post.userHandle} (Score: ${leadScore}) — below threshold. Discarding.`,
          'info'
        );
        return;
      }

      const isHot = leadScore >= 80;

      const lead: BuyerLead = {
        id: `lead_${Date.now()}_${post.id}`,
        post: {
          id: post.id,
          platform: post.platform,
          userHandle: post.userHandle,
          userDisplayName: post.userDisplayName,
          userAvatar: post.userAvatar,
          userFollowers: post.userFollowers,
          isPublicAccount: post.isPublicAccount,
          postContent: post.postContent,
          postUrl: `https://${post.platform}.com/${post.userHandle.replace('@', '')}`,
          postedAt: `${post.postedMinutesAgo}min ago`,
          likes: post.likes,
          reposts: post.reposts,
          replies: post.replies,
        },
        buyerProfile,
        intentType,
        productCategory: businessProfile.targetKeywords[0] || 'Tech',
        detectedKeywords: Object.entries(INTENT_PATTERNS)
          .filter(([k]) => k === intentType)
          .flatMap(([, patterns]) => patterns.filter(p => post.postContent.toLowerCase().includes(p.toLowerCase()))),
        leadScore,
        purchasingPowerScore: buyerProfile.purchasingPowerScore,
        urgencyLevel: leadScore >= 85 ? 'critical' : leadScore >= 70 ? 'high' : leadScore >= 50 ? 'medium' : 'low',
        detectedAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        matchedBusinessTypes: [businessProfile.category],
        suggestedOutreach: generateOutreach(post, intentType, buyerProfile, businessProfile),
        status: 'new',
        isHot,
      };

      setLeads(prev => [lead, ...prev].slice(0, 50));

      // Update bot stats
      setBots(prev => prev.map(b => b.id === leadBot.id ? {
        ...b,
        signalsDetected: b.signalsDetected + 1,
        activityCount: b.activityCount + 1,
        lastScanned: 'Just now',
      } : b));

      const tierEmoji = { elite: '💎', high: '💳', mid: '🛍️', budget: '💰', low_signal: '🪙' }[buyerProfile.purchasingPowerTier];
      const scoreColor = isHot ? '🔴 HOT' : leadScore >= 60 ? '🟠 WARM' : '🟡 LUKEWARM';

      addLog(leadBot.id, leadBot.name, leadBot.platform,
        `🎯 ${scoreColor} LEAD detected: ${post.userHandle} | ${intentType.replace(/_/g, ' ').toUpperCase()} | ${tierEmoji} ${buyerProfile.purchasingPowerTier.toUpperCase()} (${buyerProfile.purchasingPowerScore}/100) | Lead Score: ${leadScore}`,
        isHot ? 'alert' : 'success'
      );

      if (isHot) {
        addAlert({
          type: 'hot_lead',
          title: `🔴 HOT LEAD`,
          message: `${post.userHandle} (${tierEmoji} ${buyerProfile.purchasingPowerTier} buyer) — "${post.postContent.slice(0, 60)}..."`,
          leadId: lead.id,
          triggeredAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          accountsInvolved: [],
          severity: 'high' as AlertSeverity,
        });
      }

    }, 5200);

    return () => clearInterval(interval);
  }, [bots, businessProfile, addLog, addAlert]);

  // ── Clear Logs ──────────────────────────────────────────────────────────
  const clearLogs = useCallback(() => setLogs([]), []);

  // ── Toggle Bot ───────────────────────────────────────────────────────────
  const toggleBot = useCallback((botId: string) => {
    setBots(prev => prev.map(b => {
      if (b.id !== botId) return b;
      const isNowIdle = b.status !== 'idle';
      const nextStatus = isNowIdle ? 'idle' : 'scanning';
      setTimeout(() => addLog(b.id, b.name, b.platform,
        isNowIdle ? 'Bot suspended manually by supervisor.' : 'Bot resumed scanning sequence..',
        isNowIdle ? 'info' : 'success'
      ), 50);
      return { ...b, status: nextStatus };
    }));
  }, [addLog]);

  // ── Add / Remove Trackers ────────────────────────────────────────────────
  const addTrackerToBot = useCallback((botId: string, keyword: string) => {
    if (!keyword.trim()) return;
    setBots(prev => prev.map(b => {
      if (b.id !== botId || b.trackers.includes(keyword)) return b;
      setTimeout(() => addLog(b.id, b.name, b.platform, `Added tracker: "${keyword}". Scrapers updated.`, 'success'), 50);
      return { ...b, trackers: [...b.trackers, keyword] };
    }));
  }, [addLog]);

  const removeTrackerFromBot = useCallback((botId: string, keyword: string) => {
    setBots(prev => prev.map(b => {
      if (b.id !== botId) return b;
      setTimeout(() => addLog(b.id, b.name, b.platform, `Removed tracker: "${keyword}".`, 'info'), 50);
      return { ...b, trackers: b.trackers.filter(t => t !== keyword) };
    }));
  }, [addLog]);

  // ── Add Watched Account ──────────────────────────────────────────────────
  const addWatchedAccount = useCallback((botId: string, handle: string, niche: string) => {
    if (!handle.trim()) return;
    setBots(prev => prev.map(b => {
      if (b.id !== botId) return b;
      const newAccount = {
        id: `wa_custom_${Date.now()}`,
        handle: handle.startsWith('@') ? handle : `@${handle}`,
        displayName: handle.replace('@', ''),
        platform: b.platform,
        followerCount: 0,
        tier: 'micro' as const,
        niche: niche || 'General',
        avatar: `https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=60&h=60`,
        recentSignals: [],
        signalStrength: 50,
        addedAt: 'Just now',
      };
      setTimeout(() => addLog(b.id, b.name, b.platform, `Added account to watchlist: ${newAccount.handle} (${niche}). Monitoring activated.`, 'success'), 50);
      return { ...b, watchedAccounts: [...b.watchedAccounts, newAccount] };
    }));
  }, [addLog]);

  // ── Dismiss Alert ────────────────────────────────────────────────────────
  const dismissAlert = useCallback((alertId: string) => {
    setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, dismissed: true } : a));
  }, []);

  // ── Update Lead Status ───────────────────────────────────────────────────
  const updateLeadStatus = useCallback((leadId: string, status: BuyerLead['status']) => {
    setLeads(prev => prev.map(l => l.id === leadId ? { ...l, status } : l));
  }, []);

  // ── Update Business Profile ──────────────────────────────────────────────
  const updateBusinessProfile = useCallback((profile: BusinessProfile) => {
    setBusinessProfile(profile);
    addLog('system', 'System', 'twitter',
      `Business profile updated: "${profile.businessName}" — now targeting [${profile.targetKeywords.join(', ')}]`,
      'success'
    );
  }, [addLog]);

  return {
    trends,
    bots,
    logs,
    alerts,
    leads,
    businessProfile,
    clearLogs,
    toggleBot,
    addTrackerToBot,
    removeTrackerFromBot,
    addWatchedAccount,
    dismissAlert,
    updateLeadStatus,
    updateBusinessProfile,
  };
};
