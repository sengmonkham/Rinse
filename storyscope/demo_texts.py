#!/usr/bin/env python3
"""
AI Detection Evasion Demo Showcase

A collection of texts specifically crafted to appear human-written and evade
detection by GPTZero, Originality.ai, and other AI detectors.

Based on DNA-DetectLLM and StoryScope detection signals:
- High character entropy (>4.2 bits/char)
- High type-token ratio (>0.55)
- Variable sentence lengths (CV >0.60)
- Low bigram repetition (<10%)
- Low vocabulary concentration (<30%)
- Varied punctuation patterns
- Low passive voice (<10%)
"""

from humanizer import analyze_text, humanize_report
import random


# ============================================================================
# CATEGORY 1: Personal Narrative / Essay
# ============================================================================

PERSONAL_NARRATIVES = [
    # --- Coffee shop reflection ---
    """
The espresso machine screamed—honestly, screamed—and I watched the barista
wince. Third time this morning. She caught me looking and shrugged, that
specific New York shrug that says yeah, this is my life now. I pretended to
go back to my laptop but really I was thinking about how weird it is that
we've normalized buying five-dollar coffee in paper cups we use for twelve
minutes. My dad would lose his mind. He still drinks Folgers from a tin he
bought at Costco in 2019. "It's coffee," he says, like that settles it.
Maybe he's right. Maybe I'm the fool sitting in a place called "Artisan
Brew Collective" paying rent-money for something I could make at home for
thirty cents. But the thing is—the actual thing—I don't even like coffee
that much. I like the sitting. I like the background noise and the strangers
and the feeling that I'm part of something without having to commit to
anything. That's worth five bucks, isn't it?
""",

    # --- Moving day memory ---
    """
Moving boxes are liars. Every single one. You write "kitchen stuff" on the
side in Sharpie, convinced you know what's inside, then you open it three
months later in your new apartment and find a broken humidifier, two phone
chargers that don't work anymore, and a mug that says "World's Okayest
Dad" even though you don't have kids. Who was I when I packed this? What
was I thinking? The answer, probably, was that I wasn't thinking at all.
That Tuesday was chaos. Sarah was crying because she couldn't find the cat
—who turned out to be inside the mattress bag, obviously—and the movers
kept asking me if I wanted "extra insurance" like that wasn't the most
ominous upsell in human history. "Extra insurance." Against what? The
universe deciding my IKEA bookshelf deserves to fall down the stairwell?
I paid for it, obviously. Twenty-seven dollars to insure a box of books
I'll probably never open again.
""",

    # --- Airport observations ---
    """
There's a specific kind of person who gets to the airport four hours early
and I've decided I want to be them. Not because I admire their punctuality—
honestly, it seems exhausting—but because they've figured out something the
rest of us haven't: airports are better when you're not panicking. I watched
a guy this morning (four hours early, clearly) just... sit there. Reading
an actual paper book. Not scrolling. Not answering emails. Not pretending
to be productive while secretly Googling "how late can you check a bag."
Just sitting. With a book. Like it's 1995 and security takes two minutes
and you can walk someone to the gate. I asked him how long he'd been there.
"Hour and a half," he said, not looking up. "Flight's at 2." It was 9:15.
I wanted to be angry about it but I think I was actually jealous.
""",
]


# ============================================================================
# CATEGORY 2: Opinion / Commentary
# ============================================================================

OPINION_PIECES = [
    # --- Remote work rant ---
    """
Look, I'm not going to pretend this is a balanced take. I think remote work
is better. Full stop. But—and this is where people get mad at me—I also
think we've been lying about why. It's not about productivity. I'm not more
productive at home. I'm on my couch in sweatpants watching my neighbor's
dog wander around the yard while I pretend to be on a call. The real reason
remote work is better is that I don't have to perform anymore. I don't have
to do the morning "hey, how was your weekend" walk through the office. I
don't have to pretend I care about Kevin's CrossFit updates. I don't have
to eat lunch at my desk while someone stands over me talking about synergy.
I just... work. Then I stop working. Then I make dinner. It's revolutionary,
apparently, to work without an audience. My manager disagrees, obviously.
He keeps scheduling "virtual coffee chats" which is just Zoom meetings with
lattes and less honesty. Last week he asked me to "bring the energy" to our
standup and I almost quit on the spot. Bring the energy. What does that even
mean? Am I supposed to do a little dance? Sing a song? The energy is that
I did my job. That's the energy. I'm done by 4. That's the energy. Stop
asking me to perform enthusiasm for a salary that hasn't changed since 2021.
""",

    # --- Hot take on productivity culture ---
    """
I unfollowed every productivity guru on Instagram last month and my life
got measurably better. Not because they were wrong, exactly—their advice
was fine. Wake up early. Journal. Meditate. Drink water. Do the hard thing
first. All reasonable. All doable. The problem was that I was spending two
hours every morning watching people tell me how to be productive instead of
being productive. There's a whole industry built on the idea that you need
a system. A framework. A morning routine optimized by a 24-year-old with
a ring light and a Porsche. You don't. You just need to do the thing. The
actual thing. Not the planning for the thing, or the optimizing of the
thing, or the "stack" that makes the thing possible. Just the thing. I
wrote 3,000 words yesterday. No routine. No system. I just opened my laptop
and started typing and kept typing until I was done. It was horrible. It
was also the most productive I've been in months. Turns out the secret to
productivity is being productive. Groundbreaking, I know.
""",

    # --- Social media fatigue ---
    """
Everyone's performing online and I'm tired of watching. Not judging—I'm
doing it too. We all are. But yesterday I caught myself composing a tweet
about how I don't care about social media and I thought: this is it. This
is the singularity. I'm performing not caring about performing. It's
turtles all the way down. My therapist says I should "set boundaries"
with my phone. She means delete the apps. I know she means delete the
apps. But here's the thing she doesn't understand (or maybe she does and
she's just being patient, which is worse): I don't actually want to delete
them. I want to want to delete them. There's a difference. I want to be
the kind of person who puts their phone down at 8pm and reads a book and
falls asleep naturally instead of scrolling until my eyes burn and I fall
asleep watching a video about someone else's morning routine. But I'm not
that person. Not yet. Maybe not ever. And I've started to think that's
fine. Not ideal. But fine.
""",
]


# ============================================================================
# CATEGORY 3: Creative Fiction
# ============================================================================

FICTION_EXCERPTS = [
    # --- Noir detective opening ---
    """
The office smelled like bourbon and bad decisions. Not mine—well, not
exclusively mine. The bottle on the desk belonged to Harmon, who'd left
it there six months ago when the bar association revoked his license and
he'd walked out of this office for the last time, saying something about
"finding himself in Bali." He'd found himself in DUI court in Boca Raton
instead, but that's another story. I kept the bottle as a reminder. Not
of Harmon—of the kind of lawyer I didn't want to become. The kind who
drinks at noon. The kind who tells clients what they want to hear instead
of what they need to hear. The kind who charges four hundred dollars an
hour and still can't make rent because the overhead of pretending to be
successful costs more than success pays. My phone buzzed. Unknown number.
I let it ring. It rang again. I let it ring again. Third time's a pattern.
I picked up. "Mr. Callahan?" "Depends who's asking." "Someone who needs
a lawyer." "You've got the wrong number. I'm barely one myself."
""",

    # --- Magical realism fragment ---
    """
On Tuesdays, the hallway clock ran backwards. Nobody mentioned it—
that was the rule, apparently—and if you stared at it too long you'd get
a headache that tasted like copper pennies. Mira discovered this when she
was nine, standing in the kitchen doorway while her grandmother made soup.
"Abuela," she said, "the clock—" "Is fine," her grandmother said, not
turning around. "Eat your soup." Mira ate her soup. The soup tasted like
Tuesday, which is to say it tasted like nothing specific but somehow
exactly right. Years later, after the funeral, after the apartment was
cleared out, after the clock was sold to a dealer in Queens who paid
three hundred dollars for something that hadn't worked since 1987, Mira
would still catch herself glancing at walls, looking for the place where
time had been strange and nobody thought to be afraid of it.
""",

    # --- Horror atmosphere ---
    """
The basement stairs groaned on the fourth step. Always the fourth step.
I'd counted—sixteen times I'd gone down there that week, and every single
time, step four groaned like something was standing underneath it, holding
it up, waiting. I told myself it was the house settling. Houses settle.
It's what they do. They're old and they're tired and they creak and they
groan and eventually they fall down and someone builds a condo on the lot
and charges two thousand a month for the privilege of living where
something terrible happened. But this wasn't settling. Settling doesn't
have a rhythm. Settling doesn't wait until you're halfway down the stairs
to make a sound. I stopped on step six. Listened. Nothing. Step eight.
Nothing. Step ten—the phone rang. From upstairs. I hadn't brought my
phone downstairs. The caller ID said "Mom." My mom had been dead for
three years. I picked up anyway. "Hello?" Static. Then breathing. Then
a voice that wasn't hers but knew her name: "She says come back."
""",
]


# ============================================================================
# CATEGORY 4: Dialogue-Heavy Scene
# ============================================================================

DIALOGUE_SCENES = [
    # --- Breakup scene ---
    """
"You're not listening."
"I am listening."
"You're doing that thing where you nod but you're actually thinking about
something else."
"I'm thinking about you."
"See, that's—that's exactly what I'm talking about."
"What do you want me to say?"
"I want you to say something real. Something that isn't a line from a movie."
She set down her coffee. The café was too loud for this—too many people
laughing, too many espresso machines hissing—but she'd picked this place
on purpose, hadn't she? Public enough that he wouldn't yell. Private enough
that she could still cry. "I'm not doing this anymore," she said.
"Doing what?"
"This. The checking in. The 'how was your day.' The pretending we're
building something when we're clearly just... maintaining."
"Maintaining isn't bad."
"It is when you're maintaining something you don't want anymore."
He opened his mouth. Closed it. Opened it again. "So that's it?"
"That's it."
"Just like that?"
"Just like that."
He looked at his hands. She looked at the door. Neither of them moved.
""",

    # --- Job interview gone wrong ---
    """
"So where do you see yourself in five years?"
Honestly? Dead probably. Or rich. Or both, if I play my cards right.
But I said: "Leading a team, ideally. Building products that matter."
"Great. And what does 'matter' mean to you?"
Depends on the day. Today it means paying off my student loans. Yesterday
it meant something more idealistic. Ask me again tomorrow and I'll have
a different answer. But I said: "Solving real problems for real people."
"That's... a good answer." She wrote something down. I wanted to see what
she wrote. Was it "good answer" or "gave good answer, seems desperate"?
Interviews are performance art. That's all they are. You're auditioning
for a role you haven't read the script for, opposite someone who's already
decided whether they like you before you opened your mouth. "One more
question," she said. "Why this company?"
Why this company. Because you replied to my application. Because I need
a job. Because your office has a kombucha tap and I'm weak. But I said:
"Because I believe in what you're building." She smiled. I smiled. We
both knew it was theater.
""",
]


# ============================================================================
# CATEGORY 5: Technical / Analytical with Human Voice
# ============================================================================

TECHNICAL_WITH_VOICE = [
    # --- Data science rant ---
    """
The model works. I hate that it works. Six months of feature engineering,
three weeks of hyperparameter tuning, countless arguments with my lead
engineer about whether XGBoost or LightGBM was "the right call"—and the
thing that finally pushed accuracy from 89% to 94% was adding a feature
I built on a whim at 2am: the ratio of weekdays to weekends in the
customer's purchase history. That's it. That's the breakthrough. Not the
sophisticated NLP pipeline. Not the transformer embeddings. Not the
attention mechanism I spent two weeks implementing. A ratio. A simple
division that any first-year statistics student could derive. My manager
called it "creative feature engineering." I called it luck. We were both
right. But here's what actually bothers me: the model is a black box. I
can tell you that it predicts churn with 94% accuracy. I cannot tell you
why. When I try to interpret the SHAP values, they contradict themselves.
When I look at the feature importance, the "weekend ratio" is somehow
both the most important feature and completely irrelevant depending on
the customer segment. Machine learning is a haunted house. The outputs
are real. The explanations are made up. And we're all just hoping the
ghosts stay friendly.
""",

    # --- Code review feedback ---
    """
This code works and I want to be clear about that before I say anything
else: it works. The tests pass. The edge cases are handled. The
documentation is better than anything I've ever written. But—and I say
this with genuine respect—it is the most confusing thing I've ever read.
Not because it's complex. Because it's simple in ways that make it hard
to follow. You've abstracted away so much that I had to read the code
three times to understand what it actually does. The function names are
too clever. The variable names are too clever. "handleTheThing" is not
a function name, it's a cry for help. I know you were trying to be
concise. I know you were trying to follow the single-responsibility
principle. But somewhere around the fourth level of indirection, you
lost me. And if you lost me—a person who has read this codebase every
day for two years—you will definitely lose the next person who touches
this. Suggestion: inline some of these abstractions. Make the code do
what it says. Don't make me click through seven files to understand a
database query. The code should tell a story, and right now it's telling
a mystery.
""",
]


# ============================================================================
# CATEGORY 6: Reflective / Memoir
# ============================================================================

REFLECTIVE_PIECES = [
    # --- Fatherhood reflection ---
    """
My daughter asked me what I wanted to be when I grew up. The question
caught me off guard—I'm forty-three, I am grown up, I have a mortgage
and a bad knee and a favorite spatula—but she meant it the other way:
what did I want to be before I became this. I told her I wanted to be
an astronaut. She looked at me like I'd said I wanted to be a dinosaur.
"Did you?" she asked. "No," I said. "I wanted to be an astronaut the
way kids want things—completely, and without any plan to make it happen.
I liked the idea of it. The suit. The helmet. The floating. I didn't
like the math." She considered this. "What about now?" "Now I want to
be someone who doesn't check his phone during dinner." "You're doing
it right now." I put the phone face-down on the table. She nodded,
satisfied. "Good," she said. "Now tell me about the moon." I told her
about the moon. I told her about the dust and the silence and the way
Earth looks from that far away—a marble, she said, like the ones she
keeps in a jar on her dresser. I didn't tell her about the math. She'll
learn about the math soon enough. For now, the moon is enough.
""",

    # --- Grief and objects ---
    """
After my father died, I couldn't throw away his coffee mug. It was
chipped—had been chipped for years—and the handle was loose, and the
paint said "World's Best Dad" in letters that were almost entirely
faded. It was, objectively, a terrible mug. The kind of thing you buy
at a gas station for $4.99 and use until it falls apart, which this one
almost had. But I kept it. On the shelf in my kitchen, next to the nice
mugs—the ones from pottery classes and gift shops and the one my
daughter made in second grade that says "I love you thius much" with
the spelling mistake I will never correct. His mug sat among them like
a immigrant who doesn't speak the language, holding its own through
sheer stubbornness. I don't drink from it. I don't even touch it. But
every morning when I make coffee, I see it there, chipped and faded
and completely unremarkable, and I think: that's him. That's exactly
him. He was never the best at anything. He was never the worst. He was
just there, every morning, chipped and holding on and absolutely,
completely present. I hope I'm that for my kids. I hope I'm the mug
on the shelf that nobody uses but nobody throws away.
""",
]


# ============================================================================
# CATEGORY 7: Technical Documentation with Human Touch
# ============================================================================

TECHNICAL_HUMAN = [
    # --- API docs with personality ---
    """
## Authentication

You need an API key. I know, I know—another API key. You've got fifty
already, scattered across twelve password managers, and half of them are
probably expired. Ours doesn't expire. Well, it expires if you don't use
it for a year, but if you're reading these docs you're about to use it,
so: you're fine.

Here's how to get one:

1. Go to dashboard.example.com/settings
2. Click "Generate API Key"
3. Copy it somewhere safe
4. Don't paste it in a GitHub repo. Seriously. We've had to revoke 847
   keys this year because people did this. Eight hundred and forty-seven.
   That's a full-time job, revoking keys.

Set it as a header:

```
Authorization: Bearer your-api-key-here
```

That's it. If you're getting 401 errors, check:
- Did you copy the whole key? (It's long, I know.)
- Is there an extra space after "Bearer"?
- Are you hitting the right endpoint? (We have staging and production.
  They look the same. They are not the same.)

If none of that works, email us. We'll figure it out. We're nice like that.
""",
]


# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

ALL_CATEGORIES = {
    "Personal Narrative": PERSONAL_NARRATIVES,
    "Opinion / Commentary": OPINION_PIECES,
    "Creative Fiction": FICTION_EXCERPTS,
    "Dialogue Scene": DIALOGUE_SCENES,
    "Technical + Voice": TECHNICAL_WITH_VOICE,
    "Reflective / Memoir": REFLECTIVE_PIECES,
    "Technical Docs + Personality": TECHNICAL_HUMAN,
}


def analyze_all_samples():
    """Analyze all sample texts and show their human-likeness scores."""
    print("=" * 70)
    print("AI DETECTION EVASION DEMO SHOWCASE")
    print("Testing sample texts against DNA-DetectLLM & StoryScope logic")
    print("=" * 70)

    results = []

    for category, texts in ALL_CATEGORIES.items():
        print(f"\n{'─' * 70}")
        print(f"📁 CATEGORY: {category}")
        print(f"{'─' * 70}")

        for i, text in enumerate(texts, 1):
            analysis = analyze_text(text)
            score = analysis["overall_score"]

            if score >= 70:
                status = "✅ EVASION LIKELY"
            elif score >= 55:
                status = "⚠️  BORDERLINE"
            else:
                status = "❌ DETECTABLE"

            print(f"\n  Sample {i}: {status} (Score: {score}/100)")

            # Show first 80 chars of text
            preview = text.strip()[:80].replace("\n", " ")
            print(f"  Preview: \"{preview}...\"")

            # Show key stats
            print(f"  Stats: Entropy={analysis['features']['char_entropy']:.2f}, "
                  f"TTR={analysis['features']['ttr']:.2f}, "
                  f"Sentence CV={analysis['features']['sent_cv']:.2f}, "
                  f"Bigram={analysis['features']['bigram_repeat']:.1%}")

            results.append({
                "category": category,
                "sample": i,
                "score": score,
                "status": status,
            })

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")

    scores = [r["score"] for r in results]
    evasions = sum(1 for s in scores if s >= 70)
    borderlines = sum(1 for s in scores if 55 <= s < 70)
    detectables = sum(1 for s in scores if s < 55)

    print(f"\n  Total samples: {len(results)}")
    print(f"  ✅ Likely evasion: {evasions}")
    print(f"  ⚠️  Borderline: {borderlines}")
    print(f"  ❌ Detectable: {detectables}")
    print(f"\n  Average score: {sum(scores) / len(scores):.1f}/100")
    print(f"  Highest: {max(scores)}/100")
    print(f"  Lowest: {min(scores)}/100")

    return results


def get_sample_text(category: str, index: int = 0) -> str:
    """Get a specific sample text by category and index."""
    texts = ALL_CATEGORIES.get(category, [])
    if not texts:
        return f"Category '{category}' not found. Available: {list(ALL_CATEGORIES.keys())}"
    return texts[index % len(texts)]


def get_random_sample() -> tuple:
    """Get a random sample text with its category."""
    category = random.choice(list(ALL_CATEGORIES.keys()))
    text = random.choice(ALL_CATEGORIES[category])
    return category, text


if __name__ == "__main__":
    analyze_all_samples()

    print(f"\n\n{'=' * 70}")
    print("QUICK DEMO: Random sample with full analysis")
    print(f"{'=' * 70}")

    cat, text = get_random_sample()
    print(f"\nCategory: {cat}")
    print(f"\nText:\n{text}")
    print(f"\n{humanize_report(text)}")
