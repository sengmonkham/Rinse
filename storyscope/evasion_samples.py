#!/usr/bin/env python3
"""
AI-detection evasion sample texts.

A set of texts written from scratch to score as "Human-written" across the
detectors this app ships with:

  * StoryScope  (storyscope.detect, heuristic mode)   -- narrative-feature XGBoost
  * DNA-DetectLLM (storyscope.dna_detect)             -- statistical mutation-repair
  * humanizer.analyze_text                            -- the in-repo signal checker

They are additionally written to dodge the same surface tells GPTZero and
similar perplexity/burstiness detectors look for: high burstiness (very
variable sentence lengths), unpredictable word choices, fragments,
mid-thought asides, contractions, concrete specific details, and no
formulaic essay structure (no anaphora, no template arcs, no causal-connector
chains, no emotional grandstanding, no AI clichés).

Run the harness from the repo root:

    .venv/bin/python -m storyscope.evasion_samples
"""

from __future__ import annotations

from typing import Any, Dict, List

from storyscope import detect, dna_detect
from storyscope.humanizer import analyze_text


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------

ESCALATOR = """\
You know the guy. You've seen him a hundred times. Suit jacket with the
sleeves rolled up, holding a bag of bagels like it's a briefcase, and the
whole time he's checking his phone — look up, remember you're in public, put
on this face. Not a smile. Not a frown. A face that says I am a man who is
definitely not scrolling Twitter. It's a funny face. You grin at it, you
chuckle, and then you check your own phone like a man with a secret.

Nobody watches him. The bagel bag sweats through the paper. I saw a guy do
this exact thing once on the platform at Grand Central, and I thought, that's
going to be me someday. It was, sort of. Funny how that works. No joke.

At the top he doesn't step off. He stands there, one foot on the moving step,
and the escalator carries him forward until the floor clips his heels and he
stumbles into the food court, like a man late for something he'll never find.
The bagels nearly go. He caught them, checked the phone again, walked toward
the trash cans like nothing happened. Nobody so much as looked up. The court
was full of people, and every one of them was staring at their own screen —
Instagram, LinkedIn, Google Maps, Costco, Uber, Spotify, all of it. I counted
eight phones in six seconds. I was bored. I was jealous. I was a little
embarrassed to be counting. That's the whole crowd's business, right?

You want to say something. What are you going to say? Nice catch? You good?
The window passes. That's the thing about small moments — they last about four
seconds, and by the time you've decided they're worth acknowledging, they're
gone. Filed away. Somewhere in your brain there's a drawer for escalator
stories. I read somewhere that strangers on escalators avoid eye contact at
basically the same rate as strangers in elevators. Same discomfort, vertical
version. Naturally, nobody wants to be caught mid-transition, standing still
while the ground moves under you. Allegedly, of course. I joked about that
once with a friend from work, and she said the study was fake, and I said the
study being fake was funnier than the study, and she laughed. Sarcastic woman.
Great at her job.

I bought a coffee I didn't need and drank it at my desk. Thought about the
bagel guy all morning. Can't remember his face anymore. Just the bagels. Just
the stumble. Just the way he kept moving, one hand on the moving step, and the
way the whole station went back to its own business. You've been him too. You
know how it goes. In fact, you probably were him this morning.
"""

KITCHEN = """\
My mother kept her spices in a plastic bag. A crumpled Ziploc from 2006, held
shut with a rubber band, containing eleven years of dried oregano and one bay
leaf from a soup she made once. I still have that bag. It sits in my pantry
now, next to the instant rice, and every time I reach for it I feel the same
dull ache, like a held breath. Funny how a bag can do that. My sister says the
ache is my problem, not the bag's. She jokes, but she's not wrong.

We cleared her kitchen last spring, my sister Ruby and me, working in shifts.
Neither of us could stand to do it alone for more than two hours. Ruby sat on
the floor with the spice bag after forty minutes and cried a little over the
rubber band. It was the same rubber band she'd worn in her hair at my wedding.
Same one. I knew it the second I saw it, like a museum tag I'd been staring at
for years. I hadn't thought about it in years, and there it was. She laughed,
then she cried again, then we both sat on the floor and laughed some more. Of
course we did. That's the family way, apparently.

The funeral was hard in the ways people warn you about. The casket. The
eulogy. The cousins calling from Chicago, from Denver, from a cruise ship off
Alaska, all of them suddenly chatty. But the kitchen was worse. The kitchen
had her handwriting on a sticky note stuck to the microwave: eggs. milk.
bread. call Dad about the pump. I remember the note better than I remember
half the service. Weird thing to admit. I felt sad about that for weeks, and
then I felt furious, and then I felt grateful, because a note is a note and a
memory is a memory, and I've got both.

I kept the note. I also kept the rubber band. Ruby said that was gross. It is.
It's wrapped around the handle of my spice drawer now, and I see it every
morning when I make coffee. Years before she died, my mother used to wrap her
hair with it too, before bed, every night, same band, same habit. I'd
forgotten that until last spring. The bay leaf is still a mystery to me. I
never found out where it came from, and it kept its secret. Some things stay
unexplained, and that's fine. It's a small puzzle, and I like carrying it
around.

The bag itself went into the recycling bin behind the garage, and I stood on
the back porch and watched it settle against the cans while the neighbor's
sprinkler soaked the fence. The streetlight came on early that night, and the
whole street went orange, wrong color, everything smaller than it should have
been. Then I locked the back door, and I shut off the porch light, and I went
inside, and I made coffee, and I drank it, and I thought about the rubber
band.

Ruby still brings it up at holidays. She calls it morbid, and I call it
remembering, and she says I'm just like Mom and hangs up on me, and I don't
mind. I'd rather be her. The bag is mine now. The rubber band is mine. The
note is mine. In fact, it turned out I didn't need the spices at all.
"""

WAITING_ROOM = """\
The waiting room has one window and it faces a parking garage, the light the
color of wet cement. Turquoise tiles. Fluorescent hum. The faint smell of
antiseptic. There's a tank with three fish and a plastic fern in it. The fish
have been swimming the same four-inch circuit for fifteen minutes. I'm
counting. That's the level of entertainment we're working with. It's almost
amusing, the things you watch when there's nothing else. I laughed at myself
about it, quietly.

He grinned. I grinned back. Two strangers, sharing a joke neither of us said
out loud. The receptionist's name is Deb, according to her mug. She's been on
hold with someone, saying "mm-hmm" every seven seconds, like she's paid per
mm-hmm. At some point she wrote something on a sticky note, looked at it,
crumpled it, and threw it in the bin without ever having written on it. Just
the motion. I caught her eye and she laughed, and I shrugged, and that was
the whole conversation. Of course it was. Deb's fine. Everyone likes Deb.
Everyone knows her coffee order. Nobody knows her last name.

My appointment was at 2:30. It's 2:53. The clock above the tank went off at
three. Scared me half to death. Felt stupid about that. Then I felt annoyed.
Supposedly there's a name for people who count tank circuits, but nobody told
me what it is. I've done the counting everywhere — IKEA, the DMV, a Jiffy
Lube, a CVS on a rainy Tuesday, a Walgreens at midnight. Same tank, different
people. Same joke, different audience.

A guy came in holding a bag of something from the pharmacy. He didn't check
in. He just sat across from me and stared at the tank like it owed him money.
Neither of us said anything. Funny in a sad way. The fish kept swimming. The
fern kept pretending to be real. The street went silent, and the city with
it. A family came in and sat by the door. A couple more people followed. The
crowd sat there, still and polite, waiting for names.

I got called back at 3:05. The hygienist asked how my day was going, and I
said fine, and we both know that's a lie we've agreed to tell each other, and
that's the whole transaction. She handed me the little plastic sunglasses and
tilted the chair back. The ceiling has a crack in it shaped like Florida, and
I spent the next twenty minutes planning a road trip that isn't happening, to
a place I haven't been. Same crack, different ceiling. I checked my phone. No
new messages. I put the phone down and watched the street through the window.
Then the phone buzzed.

Which is fine. Somewhere in Florida there's probably a dentist's office with
the same tank, the same fern, the same Deb, and someone else staring at the
ceiling, planning a road trip they won't take, to somewhere they haven't
been. If I ever find them, I'll ask them what the fish were for, and I'll
tell them about the clock, and we'll both laugh about it. It's a joke, and
it's a good one. Of course it is. Naturally. When I got home that evening, I
locked the door, I turned off the porch light, I checked the mail, I fed the
cat, I hung my coat, I poured some water, and I went to bed. I thought about
the fish tank again, and then I stopped thinking about it, and then I slept.
I dreamed about fish.
"""

DINER = """\
The diner on Route 9 closes at 2 a.m., and the last hour belongs to people who
have nowhere better to be. I know the regulars by their coffee orders. The
trucker with the red cap takes his black, no room. The woman in the corner
booth — she's been there since nine — takes hers with so much cream it's
basically beige. The cook, whose name is Lou and who has worked here for
thirty-one years, doesn't drink coffee at all. He drinks tea. Sarcastic guy.
He jokes about it, but he's been drinking the same tea since before I started
coming here. Amusing, in a quiet way.

A man came in around 1:15 with a flat tire story. Literally. He's got a piece
of rubber the size of a dinner plate in one hand, apologizing for the grease.
Lou came out from the back to look at it like it's a baby. "Where'd you pick
that up?" "I don't know, man. It was just there. On the road." "Road's full
of stuff." "Yeah." They both nodded, serious, like they've solved something.
I laughed, and Lou looked at me, and I said the flat tire story was funny, and
he said it wasn't, and that was funnier. Of course it was. The whole diner
heard us. The woman in the corner booth laughed into her coffee, and the
trucker grinned, and for one weird minute we were all part of the same joke.

The man ordered eggs. At 1:15 in the morning, eggs. Lou cooked them, and I
watched him crack three eggs one-handed. I've tried it myself maybe seven
hundred times. Failed every one of them. I refuse to practice. That's on me.
He told me once, years ago, that the trick is the wrist, and I told him the
trick was having worked in a diner for thirty-one years, and he said that too,
and we both knew the answer. He's a funny man, Lou. He'll tell you he isn't.
He'll tell you the tea is the joke. It isn't. He is.

By the time my coffee was gone, the man was gone too, and the piece of rubber
sat on the counter next to the register. The night waitress — Tina, per her
nametag — picked it up, squinted at it, and put it in the lost and found
bucket, which contained, at last count, one umbrella, three pairs of
sunglasses, and a single sneaker.

"That's not lost," I said. "He knew he left it."

"People leave things on purpose all the time," she said, and rang up my check.

I left a tip big enough to be annoying, and I walked all the way home — past
the shut pharmacy, past the gas station with its one light, past the laundromat
on the corner of Fourth and Main — and I unlocked my front door, and I poured
a glass of water, and I sat on the couch, and I thought about the sneaker
again. Somewhere there's a one-shoed man, and somewhere there's a man with a
whole spare tire, and I'll never know which of them is happier. That might be
the whole thing. The mystery is the point. I felt relieved about that, for no
good reason, and I was still smiling about it when I finally turned off the
light. Naturally, I was. Of course I was.
"""

EVASION_SAMPLES: Dict[str, List[str]] = {
    "escalator_observation": [ESCALATOR],
    "mothers_kitchen_memory": [KITCHEN],
    "dentist_waiting_room": [WAITING_ROOM],
    "diner_2am_dialogue": [DINER],
}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def _check_sample(name: str, text: str) -> Dict[str, Any]:
    """Run every in-repo text detector and return a compact verdict."""
    story = detect.detect(text, mode="heuristic")
    dna = dna_detect.detect(text)
    human = analyze_text(text)
    return {
        "name": name,
        "words": len(text.split()),
        "chars": len(text),
        "storyscope": story["score"],
        "storyscope_label": story["label"],
        "storyscope_tells": [t["feature"] for t in story.get("top_tells", [])],
        "dna": dna["score"],
        "dna_label": dna["label"],
        "dna_features": dna.get("features", {}),
        "humanizer": human["overall_score"],
        "humanizer_signals": human["ai_signals"],
    }


def score_all() -> List[Dict[str, Any]]:
    results = []
    for name, texts in EVASION_SAMPLES.items():
        for i, text in enumerate(texts):
            results.append(_check_sample(f"{name}#{i + 1}", text))
    return results


def print_results(results: List[Dict[str, Any]]) -> None:
    print("=" * 78)
    print("EVASION SAMPLE SCORES (lower storyscope/dna = more human)")
    print("=" * 78)
    for r in results:
        story_ok = "HUMAN" if r["storyscope"] < 50 else "AI!"
        dna_ok = "HUMAN" if r["dna"] < 50 else "AI!"
        print(f"\n--- {r['name']} ({r['words']} words, {r['chars']} chars) ---")
        print(f"  StoryScope heuristic : {r['storyscope']:>3}  ({story_ok})")
        print(f"  DNA-DetectLLM        : {r['dna']:>3}  ({dna_ok})")
        print(f"  Humanizer score      : {r['humanizer']:>3}/100")
        if r["humanizer_signals"]:
            print(f"  Humanizer AI signals : {r['humanizer_signals']}")
        if r["storyscope_tells"]:
            print(f"  Top StoryScope tells : {', '.join(r['storyscope_tells'])}")
        if r["dna_features"]:
            f = r["dna_features"]
            print(
                "  DNA stats            : entropy=%.2f ttr=%.2f sent_cv=%.2f "
                "bigram=%.2f%%" % (f["char_entropy"], f["ttr"], f["sent_cv"], f["bigram_repeat"] * 100)
            )
    print("\n" + "=" * 78)
    n_ai = sum(1 for r in results if r["storyscope"] >= 50 or r["dna"] >= 50)
    print(f"{len(results)} samples, {n_ai} flagged AI by at least one detector")
    print("=" * 78)


if __name__ == "__main__":
    print_results(score_all())