import { useState, useEffect, useCallback, useRef } from 'react';
import type { Trend, ScannerBot, LogEntry, Platform } from '../types';
import { INITIAL_TRENDS, INITIAL_BOTS } from '../mockData';

export const useTrendSimulator = () => {
  const [trends, setTrends] = useState<Trend[]>(INITIAL_TRENDS);
  const [bots, setBots] = useState<ScannerBot[]>(INITIAL_BOTS);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const logIdCounter = useRef(0);

  // Helper to append a simulation log
  const addLog = useCallback((botId: string, botName: string, platform: Platform, message: string, type: 'info' | 'success' | 'alert' = 'info') => {
    const newLog: LogEntry = {
      id: `log_${Date.now()}_${logIdCounter.current++}`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      botId,
      botName,
      platform,
      message,
      type
    };

    setLogs(prev => [newLog, ...prev].slice(0, 80)); // Limit to 80 logs
  }, []);

  // Initialize with some starting logs
  useEffect(() => {
    bots.forEach((bot, index) => {
      setTimeout(() => {
        addLog(
          bot.id,
          bot.name,
          bot.platform,
          `Bot initialized. Monitoring keywords: [${bot.trackers.join(', ')}]`,
          'info'
        );
      }, index * 400);
    });
  }, []);

  // Background Simulator loop
  useEffect(() => {
    const interval = setInterval(() => {
      // Pick a random active bot
      const activeBots = bots.filter(b => b.status !== 'idle');
      if (activeBots.length === 0) return;

      const randomBot = activeBots[Math.floor(Math.random() * activeBots.length)];
      
      // Randomly change bot status between scanning and analyzing
      setBots(prevBots =>
        prevBots.map(b => {
          if (b.id === randomBot.id) {
            const nextStatus = Math.random() > 0.4 ? 'scanning' : 'analyzing';
            return {
              ...b,
              status: nextStatus,
              activityCount: b.activityCount + 1,
              lastScanned: 'Just now'
            };
          }
          return b;
        })
      );

      // Generate a simulated log message based on trackers
      const keyword = randomBot.trackers[Math.floor(Math.random() * randomBot.trackers.length)] || 'general activity';
      const logTemplates = [
        `Scraped new feed posts for query: "${keyword}". Analyzing engagement rates.`,
        `Analyzing sentiment index on comments mentioning "${keyword}"...`,
        `Extracted engagement stats: keyword "${keyword}" is gaining traction.`,
        `Matched community cluster for tracked topic: "${keyword}".`,
        `Processed metadata pipeline for "${keyword}". Sentiment skew: POSITIVE.`
      ];
      
      const isAlert = Math.random() > 0.90; // 10% chance of a spike alert
      let logMsg = logTemplates[Math.floor(Math.random() * logTemplates.length)];
      let type: 'info' | 'success' | 'alert' = 'info';

      if (isAlert) {
        logMsg = `🔥 ALERT: Search velocity for "${keyword}" spiked by +32% in the last 15 minutes!`;
        type = 'alert';
      } else if (Math.random() > 0.65) {
        logMsg = `Successfully parsed 100+ social records for "${keyword}" (Quality score: ${randomBot.efficiency}%).`;
        type = 'success';
      }

      addLog(randomBot.id, randomBot.name, randomBot.platform, logMsg, type);

      // Mutate trend volume slightly if keyword matches any part of a trend name or tracker
      setTrends(prevTrends =>
        prevTrends.map(trend => {
          const match = trend.name.toLowerCase().includes(keyword.toLowerCase()) || 
                        trend.category.toLowerCase().includes(keyword.toLowerCase()) ||
                        trend.whyTrending.toLowerCase().includes(keyword.toLowerCase());
          
          if (match) {
            const pct = isAlert ? 1.05 : (1 + (Math.random() * 0.015 - 0.005)); // -0.5% to +1% or +5% if alert
            const nextVolume = Math.round(trend.volume * pct);
            const updatedHistory = [...trend.volumeHistory.slice(1), nextVolume];
            
            // Adjust growth rate slightly
            const initialVol = trend.volumeHistory[0] || 1;
            const computedGrowth = Math.round(((nextVolume - initialVol) / initialVol) * 100);

            return {
              ...trend,
              volume: nextVolume,
              volumeHistory: updatedHistory,
              growth: computedGrowth
            };
          }
          return trend;
        })
      );

    }, 3800); // Trigger every 3.8 seconds

    return () => clearInterval(interval);
  }, [bots, addLog]);

  // Toggle Bot Status
  const toggleBot = useCallback((botId: string) => {
    setBots(prevBots =>
      prevBots.map(b => {
        if (b.id === botId) {
          const isNowIdle = b.status !== 'idle';
          const nextStatus = isNowIdle ? 'idle' : 'scanning';
          
          setTimeout(() => {
            addLog(
              b.id,
              b.name,
              b.platform,
              isNowIdle ? `Bot suspended manually by supervisor.` : `Bot resumed scanning sequence.`,
              isNowIdle ? 'info' : 'success'
            );
          }, 50);

          return {
            ...b,
            status: nextStatus
          };
        }
        return b;
      })
    );
  }, [addLog]);

  // Add a new tracker keyword to a bot
  const addTrackerToBot = useCallback((botId: string, keyword: string) => {
    if (!keyword.trim()) return;
    
    setBots(prevBots =>
      prevBots.map(b => {
        if (b.id === botId) {
          if (b.trackers.includes(keyword)) return b;
          
          setTimeout(() => {
            addLog(
              b.id,
              b.name,
              b.platform,
              `Added tracker keyword: "${keyword}". Scrapers updated.`,
              'success'
            );
          }, 50);

          return {
            ...b,
            trackers: [...b.trackers, keyword]
          };
        }
        return b;
      })
    );
  }, [addLog]);

  // Delete a tracker keyword from a bot
  const removeTrackerFromBot = useCallback((botId: string, keyword: string) => {
    setBots(prevBots =>
      prevBots.map(b => {
        if (b.id === botId) {
          setTimeout(() => {
            addLog(
              b.id,
              b.name,
              b.platform,
              `Removed tracker keyword: "${keyword}". Scrapers updated.`,
              'info'
            );
          }, 50);

          return {
            ...b,
            trackers: b.trackers.filter(t => t !== keyword)
          };
        }
        return b;
      })
    );
  }, [addLog]);

  // Create a brand new custom Trend
  const createCustomTrend = useCallback((newTrend: Omit<Trend, 'id' | 'volumeHistory' | 'sentiment' | 'platforms'>) => {
    const id = `t_custom_${Date.now()}`;
    const vol = newTrend.volume;
    const history = [
      Math.round(vol * 0.7),
      Math.round(vol * 0.75),
      Math.round(vol * 0.8),
      Math.round(vol * 0.88),
      Math.round(vol * 0.95),
      vol
    ];

    const trend: Trend = {
      ...newTrend,
      id,
      volumeHistory: history,
      sentiment: {
        positive: Math.floor(Math.random() * 40) + 40, // 40-80%
        neutral: Math.floor(Math.random() * 20) + 10,  // 10-30%
        negative: 10 // rest is negative
      },
      platforms: {
        twitter: Math.floor(Math.random() * 50) + 10,
        instagram: Math.floor(Math.random() * 50) + 10,
        youtube: Math.floor(Math.random() * 50) + 10
      }
    };
    
    // Normalize platforms to 100% total
    const total = trend.platforms.twitter + trend.platforms.instagram + trend.platforms.youtube;
    trend.platforms.twitter = Math.round((trend.platforms.twitter / total) * 100);
    trend.platforms.instagram = Math.round((trend.platforms.instagram / total) * 100);
    trend.platforms.youtube = 100 - (trend.platforms.twitter + trend.platforms.instagram);

    // Normalize sentiment to 100% total
    const totalSent = trend.sentiment.positive + trend.sentiment.neutral + trend.sentiment.negative;
    trend.sentiment.positive = Math.round((trend.sentiment.positive / totalSent) * 100);
    trend.sentiment.neutral = Math.round((trend.sentiment.neutral / totalSent) * 100);
    trend.sentiment.negative = 100 - (trend.sentiment.positive + trend.sentiment.neutral);

    setTrends(prev => [trend, ...prev]);

    // Send a success log of new custom trend added
    addLog(
      'system',
      'System Core',
      'twitter',
      `📈 Live Scanner integrated new custom tracker category: "${trend.name}". Searching historical feeds.`,
      'success'
    );
  }, [addLog]);

  return {
    trends,
    bots,
    logs,
    toggleBot,
    addTrackerToBot,
    removeTrackerFromBot,
    createCustomTrend
  };
};
