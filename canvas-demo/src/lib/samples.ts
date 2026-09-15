export interface SampleText {
  label: string;
  content: string;
  tag: "AI" | "Human";
}

export interface SampleImage {
  label: string;
  url: string;
  tag: "AI" | "Human";
}

export const SAMPLE_TEXTS: SampleText[] = [
  {
    label: "LinkedIn Broetry",
    tag: "AI",
    content: `🚀 Stop scrolling. This matters.

I spent 6 months building something that will revolutionize how we think about AI content.

Here's what most people don't understand:

The tapestry of AI-generated content is seamlessly weaving itself into every corner of the internet.

And here's the uncomfortable truth — it's no longer optional to address this.

💡 Key insights:

• **Innovation**: Cutting-edge solutions that foster collaboration and synergy across teams
• **Impact**: A testament to what happens when you elevate your approach to decision-making
• **Future**: Game-changing results that will uncover new possibilities for every stakeholder

This isn't just another tool. This is the beginning of a new era.

The question is — are you ready to dive in?

👉 Drop a comment if you agree. Let's start a conversation.

#AI #Innovation #Tech #FutureOfWork #Synergy`,
  },
  {
    label: "Corporate Marketing",
    tag: "AI",
    content: `In today's rapidly evolving digital landscape, businesses must seamlessly integrate cutting-edge AI solutions to stay ahead of the curve. Our state-of-the-art platform revolutionizes the way organizations approach content creation, fostering innovation and driving measurable results.

Here's why our solution stands out:

• **Advanced Analytics**: Leverage end-to-end machine learning pipelines that deliver real-time insights and cost-effective decision-making frameworks.
• **Scalable Architecture**: Built on a value-added microservices foundation that scales effortlessly from startup to enterprise — no longer optional in the AI era.
• **Proven ROI**: Our result-oriented approach has helped over 500 companies reduce content production time from 8 hours to zero, while maintaining the highest quality standards.

This is a testament to what happens when you foster synergy between human creativity and artificial intelligence. The uncomfortable truth is that businesses who underestimate this shift will find themselves struggling to catch up.

Ready to revolutionize your workflow? Let's connect. 🎯📈✨`,
  },
  {
    label: "AI Emoji Slop",
    tag: "AI",
    content: `🤖 The AI revolution is here, and most people are sleeping on it.

🧠 Here's what I learned after 10,000 hours of building with AI:

🚀 The future belongs to those who embrace change, not those who fear it.

💡 Key takeaways:

🎯 AI won't replace you — but someone using AI will replace you.

📈 The compound effect of AI tools is staggering.

🔥 We're seeing a 10x productivity boost across every team that adopts these workflows.

✅ Start now. Start small. But START.

The uncomfortable truth is that this technology is no longer optional. Those who underestimate this will find themselves left behind.

💬 What's your experience with AI tools? Drop your thoughts below! 👇

#ArtificialIntelligence #MachineLearning #TechLeadership #Innovation #FutureOfWork`,
  },
  {
    label: "AI Personal Narrative",
    tag: "AI",
    content: `Back in 2021, I was ready to choose Computer Science as my major because I really loved coding and building apps. Then AI started blowing up, and everyone kept saying it was going to replace programmers. I got spooked and decided programming was a dead end. So I bailed on the thing I loved most.

But here's the thing. I couldn't stay away. I started messing around with web dev tutorials, contributed to some open source projects on GitHub, and somehow landed an internship at a startup in Singapore. The passion was always there, just buried under all that fear.

That whole mess flipped my entire career trajectory. I don't want anyone else going through that same spiral, getting fooled by synthetic content until we can't tell what's real anymore. I genuinely care about making sure AI doesn't become something that harms people or chips away at the trust we have in what we see and read online. That matters to me more than anything else right now.

This led me to realize that the most important thing is to build tools that help people navigate this new world. Because of this, I decided to create something that would make a real difference.`,
  },
  {
    label: "Human Writing (Casual)",
    tag: "Human",
    content: `so I was thinking about this the other day — my roommate keeps sending me these LinkedIn posts that are clearly written by ChatGPT. you know the ones, they all start with "Stop scrolling" and end with some hashtag salad.

it's weird because a year ago I couldn't tell the difference. now I spot them instantly. the rhythm is off. every sentence is the same length, every paragraph starts with a bold header, and there's always this forced urgency that doesn't feel real.

I tried writing my own post last week and deleted it three times. kept catching myself using "seamlessly" and "leverage" — words I'd never use in normal conversation. turns out reading AI slop all day does seep into your writing.

the thing that bugs me most is when people share these obviously generated stories about "overcoming adversity" or "learning a hard lesson." like, did you actually experience that, or did you prompt an LLM to write it for you? there's something deeply weird about outsourcing your personal memories to a language model.

anyway, I signed up for this browser extension called RINSE that apparently scans pages for AI-generated content. haven't tried it yet but seems useful. will report back.`,
  },
  {
    label: "Human Writing (Opinion)",
    tag: "Human",
    content: `Hot take: most AI writing tools make your prose worse, not better.

I've been editing content for 12 years. Started at a local newspaper, moved to a tech magazine, now I freelance. The shift since late 2022 has been dramatic. Clients send me drafts that read like they were assembled by committee — every paragraph has the same rhythm, every transition uses "moreover" or "furthermore" or "it's worth noting that."

The worst part is the False Confidence. AI writes with total authority about everything. It never hedges naturally, never says "I think" or "maybe" or "this might be wrong." Real human writing is full of uncertainty because real life is uncertain.

I had a client last month who asked me to "make it sound more natural" and when I asked what they meant, they said "less like ChatGPT." The irony was that the original draft was 100% AI-generated. We spent three revision cycles undoing the smoothness.

My advice: if you're going to use AI as a starting draft, at least rewrite it in your own voice afterward. Read it out loud. If it sounds like a TED talk that never ends, start over.`,
  },
];

export const SAMPLE_IMAGES: SampleImage[] = [
  {
    label: "AI Neural Network Art",
    tag: "AI",
    url: "/images/ai-neural-network.svg",
  },
  {
    label: "AI Vibecoded Dashboard",
    tag: "AI",
    url: "/images/ai-vibecoded-dashboard.svg",
  },
  {
    label: "AI Landscape",
    tag: "AI",
    url: "/images/ai-landscape.svg",
  },
];
