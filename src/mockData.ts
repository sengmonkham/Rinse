import type { Trend, ScannerBot } from './types';

export const INITIAL_TRENDS: Trend[] = [
  {
    id: 't1',
    name: 'Generative Video AI',
    category: 'Tech & AI',
    volume: 384500,
    volumeHistory: [120000, 150000, 190000, 240000, 310000, 384500],
    growth: 220,
    sentiment: { positive: 65, neutral: 25, negative: 10 },
    platforms: { twitter: 45, instagram: 15, youtube: 40 },
    momentum: 'surging',
    description: 'The explosive rise of hyper-realistic generative video models (like Sora and Runway Gen-3) allowing users to create cinematic clips from single text prompts.',
    whyTrending: 'Major visual updates from prominent AI laboratories and viral video clips shared by content creators showing indistinguishable real-vs-synthetic video feeds.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 38 },
        { label: '25-34 (Millennials)', percentage: 46 },
        { label: '35-44 (Gen X)', percentage: 12 },
        { label: '45+', percentage: 4 }
      ],
      region: [
        { label: 'North America', percentage: 42 },
        { label: 'Europe', percentage: 28 },
        { label: 'East Asia', percentage: 20 },
        { label: 'Rest of World', percentage: 10 }
      ]
    },
    marketingAdvice: 'Integrate AI video transitions in short-form content. Emphasize the ease of drafting B-rolls, but maintain transparency to build community trust.',
    samplePosts: [
      {
        platform: 'twitter',
        user: 'Alex Rivers',
        handle: '@alex_tech_ai',
        avatar: 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=80&h=80',
        content: 'Unbelievable prompt-to-video capabilities released today. The physics of water and light reflection are virtually indistinguishable from real life. Visual creation is changing forever. 🎥💻',
        engagement: '14.2k likes • 2.4k retweets',
        time: '2h ago'
      },
      {
        platform: 'youtube',
        user: 'CineMinds AI',
        handle: 'CineMinds',
        avatar: 'https://images.unsplash.com/photo-1628157582853-a796fa650a6a?auto=format&fit=crop&w=80&h=80',
        content: 'How I Shot A Entire Sci-Fi Short Film Using ONLY Prompt Words (Step-by-Step Runway Tutorial)',
        engagement: '185k views • 9.8k likes',
        time: '1 day ago'
      },
      {
        platform: 'instagram',
        user: 'Future_Aesthetic',
        handle: '@future_aesthetic',
        avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=80&h=80',
        content: 'Created this dreamscape in 30 seconds using raw text. The age of prompt filmmaking is officially here. Let me know what dream you want visualised next! 👇✨',
        engagement: '45.1k likes • 800 comments',
        time: '5h ago'
      }
    ]
  },
  {
    id: 't2',
    name: 'Cozy Gaming RPGs',
    category: 'Gaming',
    volume: 182300,
    volumeHistory: [95000, 110000, 125000, 140000, 162000, 182300],
    growth: 92,
    sentiment: { positive: 88, neutral: 10, negative: 2 },
    platforms: { twitter: 20, instagram: 50, youtube: 30 },
    momentum: 'upcoming',
    description: 'Slow-paced, non-violent role-playing and farming simulation games focusing on relaxing aesthetics, community building, and cute visual design.',
    whyTrending: 'A wave of new releases on Nintendo Switch and PC designed specifically for mental relaxation, coupled with the "cozy desk setup" aesthetic taking over TikTok.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 54 },
        { label: '25-34 (Millennials)', percentage: 32 },
        { label: '35-44 (Gen X)', percentage: 10 },
        { label: '45+', percentage: 4 }
      ],
      region: [
        { label: 'North America', percentage: 35 },
        { label: 'East Asia (Japan/Korea)', percentage: 33 },
        { label: 'Europe', percentage: 22 },
        { label: 'Rest of World', percentage: 10 }
      ]
    },
    marketingAdvice: 'Partner with micro-influencers who film aesthetically pleasing cozy room tours. Utilize pastel, low-saturation color palettes and relaxing Lo-Fi background music in your ads.',
    samplePosts: [
      {
        platform: 'instagram',
        user: 'CozyLofiGamer',
        handle: '@cozylofigamer',
        avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=80&h=80',
        content: 'Rainy afternoon, warm matcha tea, and my new favorite farming sim game ☕️🍃 This is absolute peace. Comment your current cozy gaming setup! 👇',
        engagement: '29.3k likes • 450 comments',
        time: '4h ago'
      },
      {
        platform: 'twitter',
        user: 'Pixel & Petals Studio',
        handle: '@pixelpetals',
        avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=80&h=80',
        content: 'We are overjoyed to share that our little cozy greenhouse simulator just hit 500k downloads! Thank you all for finding comfort in our pixel flowers. 🌸✨',
        engagement: '8.4k likes • 920 retweets',
        time: '8h ago'
      }
    ]
  },
  {
    id: 't3',
    name: 'Quiet Luxury Interiors',
    category: 'Fashion & Beauty',
    volume: 245000,
    volumeHistory: [210000, 220000, 225000, 232000, 240000, 245000],
    growth: 17,
    sentiment: { positive: 58, neutral: 34, negative: 8 },
    platforms: { twitter: 10, instagram: 75, youtube: 15 },
    momentum: 'stable',
    description: 'An interior design movement emphasizing unbranded, high-quality, organic materials, neutral linen tones, and subtle custom finishes rather than flashy brand displays.',
    whyTrending: 'The logical evolution of the "Quiet Luxury" fashion trend moving from wardrobes into living rooms, lounges, and kitchen styling.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 15 },
        { label: '25-34 (Millennials)', percentage: 48 },
        { label: '35-44 (Gen X)', percentage: 25 },
        { label: '45+', percentage: 12 }
      ],
      region: [
        { label: 'Europe', percentage: 40 },
        { label: 'North America', percentage: 38 },
        { label: 'Middle East', percentage: 12 },
        { label: 'Rest of World', percentage: 10 }
      ]
    },
    marketingAdvice: 'Present your physical products in highly architectural, minimal backgrounds. Focus messaging on "longevity", "artisan craftsmanship", and "understated elegance".',
    samplePosts: [
      {
        platform: 'instagram',
        user: 'Atelier Minimal',
        handle: '@atelier_minimal',
        avatar: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=80&h=80',
        content: 'Texture over labels. Travertine stone, unbleached linen, and custom warm walnut details create a space that breathes quiet confidence. 🏷️❌✨',
        engagement: '35.4k likes • 120 comments',
        time: '12h ago'
      },
      {
        platform: 'youtube',
        user: 'Design Therapy',
        handle: 'DesignTherapy',
        avatar: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=80&h=80',
        content: 'How To Make A Simple Apartment Look Rich Without Using Big Brand Logos (Quiet Luxury Interior Guide)',
        engagement: '520k views • 24k likes',
        time: '4 days ago'
      }
    ]
  },
  {
    id: 't4',
    name: 'Zone 2 Heart-Rate Training',
    category: 'Fitness & Health',
    volume: 128900,
    volumeHistory: [52000, 68000, 84000, 99000, 112000, 128900],
    growth: 148,
    sentiment: { positive: 79, neutral: 18, negative: 3 },
    platforms: { twitter: 35, instagram: 30, youtube: 35 },
    momentum: 'surging',
    description: 'Exercising at a low intensity where your heart rate remains between 60-70% of maximum, facilitating cellular longevity, mitochondrial health, and fat oxidation.',
    whyTrending: 'A wave of endorsement from longevity podcasters and health-span optimization specialists (e.g. Peter Attia, Huberman) focusing on endurance rather than high-intensity burnouts.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 12 },
        { label: '25-34 (Millennials)', percentage: 44 },
        { label: '35-44 (Gen X)', percentage: 32 },
        { label: '45+', percentage: 12 }
      ],
      region: [
        { label: 'North America', percentage: 48 },
        { label: 'Europe', percentage: 34 },
        { label: 'Oceania', percentage: 10 },
        { label: 'Rest of World', percentage: 8 }
      ]
    },
    marketingAdvice: 'Target high-performance professionals. Align marketing copy around scientific research, aerobic base building, sustainable energy, and cognitive benefits of low-strain work.',
    samplePosts: [
      {
        platform: 'twitter',
        user: 'BioHacker Brad',
        handle: '@biohacker_brad',
        avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=80&h=80',
        content: 'Stop red-lining your heart every single workout. 45 mins of dedicated Zone 2 cardio (conversational pace) 3x a week does wonders for mitochondrial efficiency, insulin sensitivity, and long-term stamina. Science wins. 🧬🏃‍♂️',
        engagement: '6.2k likes • 840 retweets',
        time: '3h ago'
      },
      {
        platform: 'youtube',
        user: 'Science in Motion',
        handle: 'ScienceMotion',
        avatar: 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?auto=format&fit=crop&w=80&h=80',
        content: 'The Ultimate Guide To Zone 2 Cardio: Why Slowing Down Is Making You Faster',
        engagement: '310k views • 18k likes',
        time: '2 days ago'
      }
    ]
  },
  {
    id: 't5',
    name: 'Matcha Espresso Fusion',
    category: 'Food & Lifestyle',
    volume: 167800,
    volumeHistory: [60000, 78000, 95000, 120000, 142000, 167800],
    growth: 179,
    sentiment: { positive: 72, neutral: 20, negative: 8 },
    platforms: { twitter: 15, instagram: 70, youtube: 15 },
    momentum: 'surging',
    description: 'A striking layered drink consisting of sweetened ceremonial matcha green tea poured over milk, topped with a shot of dark espresso.',
    whyTrending: 'Highly photogenic "layer-pour" videos going viral on Instagram Reels and TikTok, combined with coffee shops expanding standard menus for tea/coffee enthusiasts.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 62 },
        { label: '25-34 (Millennials)', percentage: 28 },
        { label: '35-44 (Gen X)', percentage: 8 },
        { label: '45+', percentage: 2 }
      ],
      region: [
        { label: 'North America', percentage: 45 },
        { label: 'East Asia', percentage: 30 },
        { label: 'Europe', percentage: 15 },
        { label: 'Rest of World', percentage: 10 }
      ]
    },
    marketingAdvice: 'Focus entirely on visual content showing the "bleed-layer" pouring process. Run localized ads for cafes during late morning dips (10:30 AM - 12:00 PM) pointing to refreshing energy levels.',
    samplePosts: [
      {
        platform: 'instagram',
        user: 'Sip & Slice Cafe',
        handle: '@sipandslice',
        avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=80&h=80',
        content: 'Earth meets fire. 🍵☕️ Watch the espresso sink slowly into cold organic oat milk and bright stone-ground Uji matcha. The ultimate flavor transition. Available starting today! ✨',
        engagement: '58.2k likes • 1.2k comments',
        time: '6h ago'
      }
    ]
  },
  {
    id: 't6',
    name: 'AI Portfolio Rebalancing',
    category: 'Finance & Crypto',
    volume: 98500,
    volumeHistory: [40000, 51000, 63000, 75000, 86000, 98500],
    growth: 146,
    sentiment: { positive: 51, neutral: 39, negative: 10 },
    platforms: { twitter: 60, instagram: 10, youtube: 30 },
    momentum: 'upcoming',
    description: 'Algorithmic investment applications using localized macro models to dynamically adjust stock and digital asset allocations based on real-time volatility thresholds.',
    whyTrending: 'The democratization of quantitative finance trading APIs allowing retail investors to deploy custom automated bots that mimic high-frequency trading desks.',
    demographics: {
      age: [
        { label: '18-24 (Gen Z)', percentage: 25 },
        { label: '25-34 (Millennials)', percentage: 55 },
        { label: '35-44 (Gen X)', percentage: 15 },
        { label: '45+', percentage: 5 }
      ],
      region: [
        { label: 'North America', percentage: 50 },
        { label: 'Europe', percentage: 25 },
        { label: 'East Asia', percentage: 15 },
        { label: 'Rest of World', percentage: 10 }
      ]
    },
    marketingAdvice: 'Emphasize risk reduction and protection during downside events. Avoid hyping "get rich quick" angles; write copy focusing on stability and mathematical capital conservation.',
    samplePosts: [
      {
        platform: 'twitter',
        user: 'FinTech Quant',
        handle: '@fintech_quant',
        avatar: 'https://images.unsplash.com/photo-1519345182560-3f2917c472ef?auto=format&fit=crop&w=80&h=80',
        content: 'My algorithmic micro-balancer just automatically hedged into treasury bonds 12 minutes before the inflation press conference triggered a stock market pullback. The code doesn\'t panic, it calculates. 📈📉💻',
        engagement: '4.8k likes • 620 retweets',
        time: '5h ago'
      }
    ]
  }
];

export const INITIAL_BOTS: ScannerBot[] = [
  {
    id: 'bot_t',
    name: 'X-Scraper-Alpha',
    platform: 'twitter',
    status: 'scanning',
    trackers: ['#GenerativeVideo', 'AI', 'Zone 2 cardio', 'quant rebalancer'],
    lastScanned: 'Just now',
    efficiency: 94,
    activityCount: 148
  },
  {
    id: 'bot_i',
    name: 'InstaReel-Vision-V2',
    platform: 'instagram',
    status: 'analyzing',
    trackers: ['#CozyDeskSetup', 'QuietLuxury', '#MatchaEspresso', 'AestheticDrinks'],
    lastScanned: '2 mins ago',
    efficiency: 89,
    activityCount: 232
  },
  {
    id: 'bot_y',
    name: 'YT-Comment-Semantic-Parser',
    platform: 'youtube',
    status: 'idle',
    trackers: ['AI video tutorial', 'longevity cardio', 'Sora film reaction'],
    lastScanned: '12 mins ago',
    efficiency: 97,
    activityCount: 84
  }
];

export const CATEGORIES = [
  'All',
  'Tech & AI',
  'Gaming',
  'Fashion & Beauty',
  'Fitness & Health',
  'Food & Lifestyle',
  'Finance & Crypto'
];
