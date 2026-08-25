"""
Pure-logic narrative feature extraction for StoryScope.

Replaces the LLM annotation step (10 per-dimension API calls per story) with
deterministic, rule-based analysis of the story text. Standard library only —
no API keys, no network, no model downloads; a full 304-feature extraction
runs in a few milliseconds.

How it works
------------
1. The story is tokenized (sentences + words) and reduced to ~90 hand-built
   statistics: sentence/word length distributions, pronoun and verb-tense
   counts, dialogue proportion, sensory/emotion/time/place word frequencies,
   alliteration, repetition, discourse-connector rates, per-third intensity
   curves, and so on.
2. Each covered feature maps those statistics onto the taxonomy's *canonical*
   value space (the exact strings the classifier's encoder was trained on).
3. Features that require literary judgment a rule cannot approximate (e.g.
   "Narrator reliability", "Ontological play") are emitted as ``n/a`` — the
   same bucket the LLM pipeline uses for condition-gated features, which the
   classifier handles natively.

The output dict has the same shape as `features.extract_story_features` and
feeds the same encoder + XGBoost scorer, so `detect.detect(mode="heuristic")`
is the only wiring needed.

Accuracy caveat
---------------
This is intentionally a *proxy* of the paper's LLM extraction: values are
estimates, and roughly half the features are left as ``n/a``. Measured on the
paper's released 61,575-story matrix (see ``eval_heuristic.py``), the
heuristic variant retains a large share of the full model's accuracy but is
not a replacement for the LLM pipeline when maximum precision matters. The
LLM mode remains available via ``STORYSCOPE_MODE=llm``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Sequence

from .taxonomy import Feature, Taxonomy

MISSING = "n/a"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    """ASCII lowercase underscore form (mirrors features._normalize_str)."""
    s = str(s).strip().lower()
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _pick(feat: Feature, idx: int) -> str:
    """Canonical value at 0-based index (clamped). Handles int and long-string scales."""
    vals = [str(v) for v in feat.values]
    if not vals:
        return MISSING
    return vals[min(max(idx, 0), len(vals) - 1)]


def _find(feat: Feature, *keywords: str) -> Optional[str]:
    """First canonical value whose normalized form contains any keyword."""
    nk = [_norm(k) for k in keywords if _norm(k)]
    for v in feat.values:
        nv = _norm(v)
        if any(nk_ in nv for nk_ in nk):
            return str(v)
    return None


def _findi(feat: Feature, *keywords: str) -> int:
    """0-based index of the canonical value matching any keyword (-1 if none)."""
    nk = [_norm(k) for k in keywords if _norm(k)]
    for i, v in enumerate(feat.values):
        nv = _norm(v)
        if any(nk_ in nv for nk_ in nk):
            return i
    return -1


def _multi(st: "Stats", feat: Feature, mapping: Dict[str, Sequence[str]]) -> List[str]:
    """Multi-select: include a canonical value only when one of its text search
    words actually appears in the story (checked against the word set)."""
    picked: List[str] = []
    for key, words in mapping.items():
        v = _find(feat, key)
        if v is None:
            continue
        if any(w in st.word_set for w in words):
            if _norm(v) not in [_norm(p) for p in picked]:
                picked.append(v)
    return picked


def _bucket(x: float, thresholds: Sequence[float]) -> int:
    """Index of the first threshold x is below; len(thresholds) if above all."""
    for i, t in enumerate(thresholds):
        if x < t:
            return i
    return len(thresholds)


def _bucketed(feat: Feature, x: float, thresholds: Sequence[float]) -> str:
    return _pick(feat, _bucket(x, thresholds))


def _rate(n: int, denom: int) -> float:
    return n / denom if denom else 0.0


# ---------------------------------------------------------------------------
# Word lists (curated, lowercase)
# ---------------------------------------------------------------------------

FIRST_PRON = frozenset("i me my mine myself we us our ours ourselves".split())
SECOND_PRON = frozenset("you your yours yourself yourselves".split())
THIRD_PRON = frozenset(
    "he him his himself she her hers herself they them their theirs themselves it its itself".split()
)

_PAST_IRREG = frozenset(
    """was were had did said went came saw made took knew thought felt told became began found left
    gave put ran sat stood woke turned looked spoke heard kept got met asked replied answered seemed
    wanted tried called started stopped happened continued decided realized remembered watched waited
    returned arrived reached opened closed moved raised lowered smiled laughed cried shouted whispered
    murmured nodded shook grabbed pulled pushed threw caught held set read wrote paid brought fought
    slept ate drank drove rode flew sang rang froze broke chose stole won lost sent shut stuck swung
    understood wore taught spent stuck rode drove woke hung fell lay chose meant led built sold grew
    drew drank fed spoke stood lent kept dealt dug hid crept knelt""".split()
)
_PAST_REG_SUFFIX = "ed"
_PRESENT_IRREG = frozenset("is are am has does says goes makes takes knows thinks feels".split())
_FUTURE = frozenset("will shall gonna".split())

SUBORDINATORS = frozenset(
    """because although though while since unless until if when before after whereas as that which who
    whose whom where how whether once""".split()
)
COORDINATORS = frozenset("and but or nor yet so for".split())
CAUSAL = frozenset(
    """because therefore thus hence consequently since resulting resulted caused leads led so
    thereby""".split()
)
TIME_MARKERS = frozenset(
    """later earlier meanwhile then next soon suddenly immediately eventually finally afterwards
    meantime when before after during while once now today tonight yesterday tomorrow still already
    yet never always sometimes often usually frequently rarely occasionally meanwhile afterward""".split()
)
TIME_SPAN_WORDS = frozenset(
    """hour hours minute minutes day days week weeks month months year years decade decades
    generation generations century centuries season seasons""".split()
)
TIME_OF_DAY = frozenset(
    """morning afternoon evening night noon midnight dawn dusk sunrise sunset twilight daybreak
    nighttime midday""".split()
)
SEASONS = frozenset("spring summer autumn fall winter".split())
MONTHS = frozenset(
    """january february march april may june july august september october november december""".split()
)
DAYS = frozenset("monday tuesday wednesday thursday friday saturday sunday".split())
FLASHBACK_MARKERS = frozenset(
    """flashback remembered recalled back_then years_before had_once used_to in_the_old_days long_ago
    earlier_that the_day_before before_the memories memory recollection""".split()
)
DREAM_WORDS = frozenset("dream dreamed dreamt nightmare vision hallucination reverie".split())
LOOP_WORDS = frozenset(
    """loop reset relive repeat repeated again_and_again same_day rewind restart time_loop""".split()
)
DEADLINE_WORDS = frozenset(
    """deadline countdown by_dawn by_midnight before_midnight in_three_days time_was_running running_out
    of_time due_date last_chance""".split()
)
HABITUAL_WORDS = frozenset(
    """used_to would every_day each_morning every_night regularly habitually always often daily""".split()
)

THOUGHT_VERBS = frozenset(
    """thought wondered felt realized knew remembered considered reflected imagined hoped wished feared
    understood sensed suspected recalled contemplated""".split()
)
DIALOGUE_VERBS = frozenset(
    """said asked replied whispered shouted murmured answered responded yelled cried muttered added
    began continued interjected agreed argued explained told""".split()
)

EMOTION_LABELS = frozenset(
    """angry happy sad afraid scared frightened terrified anxious nervous worried excited thrilled
    joyful miserable depressed lonely ashamed guilty jealous envious proud relieved hopeful hopeless
    frustrated disappointed disgusted surprised shocked confused embarrassed furious delighted grateful
    content peaceful uneasy restless melancholy nostalgic bitter resentful regret longing desire fear
    joy grief sorrow anger rage hatred hate envy pride shame guilt worry dread panic horror excitement
    happiness sadness terror calm fury love pain""".split()
)
EMOTION_BODILY = frozenset(
    """heart heartbeat pounding breath breathing trembled trembling shiver shudder sweat flushed
    blushed churned knot chest stomach nausea dizzy tears cried wept sobbed shaking skin goosebumps
    trembling limbs cold_sweat""".split()
)
EMOTION_FACIAL = frozenset(
    """smile smiled frown frowned grin grimaced scowled laughed laughter eyes blinked stared gaze
    expression face jaw clenched lips mouth tears""".split()
)
EMOTION_ACTION = frozenset(
    """slammed stormed withdrew avoided paced fidgeted hugged embraced flinched backed collapsed
    clutched gripped punched kicked threw slammed shouted""".split()
)
EMOTION_REFLECTIVE = frozenset(
    """felt emotions feelings feeling realized understood aware conscious reflected introspection
    examined_his analyzed""".split()
)

MORAL_WORDS = frozenset(
    """lesson learned moral should must ought good evil justice virtue sin forgive redemption wisdom
    truth honor duty conscience guilt teach learn meaning purpose destiny fate sacrifice cherish
    understand understand""".split()
)
EARNEST_WORDS = frozenset(
    """dream hope wonder beauty light gentle quiet tender soft glow bright warmth peace love
    longing""".split()
)
META_WORDS = frozenset(
    """story narrator tale reader chapter plot author telling narrative beginning ending write story
    told this_story the_story""".split()
)
DOCUMENT_WORDS = frozenset(
    """letter diary journal log email transcript report note document file record entry post message
    memo memo text_message case_file recording""".split()
)
FRAME_WORDS = frozenset(
    """looking_back i_remember years_later_i when_i_was back_then i_recall i_remember_when
    recount""".split()
)
AGING_WORDS = frozenset(
    """years_later decades later grew_up grew_old old_age as_he_grew as_she_grew aged aging
    childhood adulthood""".split()
)
REVEAL_WORDS = frozenset(
    """realized discovered found_out revealed secret truth figured_out understood at_last knew_the
    truth the_truth unveiled uncovered exposed""".split()
)
SUSPENSE_WORDS = frozenset(
    """suddenly suspense tension danger mysterious inexplicable ominous lurking dread unknown
    lurking""".split()
)
TWIST_WORDS = frozenset(
    """twist turned_out it_wasn't it_was_not plot_twist unexpected shocking_revelation reveal
    everything_changed in_fact but_the_truth""".split()
)
IRONY_MARKERS = frozenset(
    """of_course as_if little_did naturally supposedly allegedly ironically conveniently""".split()
)
HUMOR_WORDS = frozenset(
    """laugh laughed joke funny amusing humor witty chuckle grinned grinned banter sarcastic
    sarcasm""".split()
)
MYSTERY_WORDS = frozenset(
    """mystery mysterious secret hidden puzzle clue suspect investigate investigation detective crime
    unknown enigma unexplained strange""".split()
)

GENRE_LISTS: Dict[str, frozenset] = {
    "science_fiction": frozenset(
        """space ship planet alien robot android technology future machine laser galaxy star
        science experiment lab clone cyber virtual computer program data satellite orbit""".split()
    ),
    "fantasy": frozenset(
        """magic magical wizard witch dragon sword castle kingdom spell elf dwarf sorcerer enchanted
        mythical legend prophecy quest power destiny hero chosen ancient realm throne""".split()
    ),
    "horror": frozenset(
        """blood scream dark shadow ghost horror terrifying nightmare corpse dead death evil monster
        haunted fear dread grave haunting creepy""".split()
    ),
    "mystery_detective": frozenset(
        """detective murder mystery clue suspect investigate crime secret hidden puzzle case alibi
        evidence inspector""".split()
    ),
    "romance": frozenset(
        """love kiss romance heart marriage wedding boyfriend girlfriend husband wife beloved
        passion""".split()
    ),
    "thriller_suspense": frozenset(
        """chase race tension suspense danger hostage assassin spy conspiracy escape pursuit
        hunt""".split()
    ),
    "historical_realist": frozenset(
        """war king queen castle empire medieval ancient century soldier kingdom dynasty battle
        general""".split()
    ),
    "realist_contemporary": frozenset(
        """city apartment office job school phone car street modern everyday ordinary""".split()
    ),
    "myth_fable_fairy_tale": frozenset(
        """fairy tale forest cottage wolf witch once_upon king kingdom spell enchant""".split()
    ),
}
GENRE_KEYS = list(GENRE_LISTS.keys())

THEME_DOMAINS: Dict[str, frozenset] = {
    "survival": frozenset(
        """survive survival hunger starve death die danger threat prey shelter food water
        desperate""".split()
    ),
    "power": frozenset(
        """power control king queen ruler empire authority rule command domination wealth throne
        corrupt""".split()
    ),
    "justice": frozenset(
        """justice law crime court judge punishment innocent guilty revenge trial police truth""".split()
    ),
    "love": frozenset(
        """love lover romance kiss heart beloved affection passion marriage wedding devotion""".split()
    ),
    "identity": frozenset(
        """identity self belong alienation mirror name purpose meaning who_am_i become change""".split()
    ),
    "family": frozenset(
        """family mother father sister brother parent child son daughter home heritage lineage
        blood""".split()
    ),
}
THEME_KEYS = list(THEME_DOMAINS.keys())

CONFLICT_LISTS: Dict[str, frozenset] = {
    "person_vs_person": frozenset(
        """enemy fought battle opponent rival attack defend war soldier fight quarrel argument
        duel""".split()
    ),
    "person_vs_society": frozenset(
        """society law rules government class tradition conformity authority rebellion protest""".split()
    ),
    "person_vs_nature": frozenset(
        """storm sea wilderness wild animal flood drought earthquake blizzard forest winter cold""".split()
    ),
    "person_vs_self": frozenset(
        """doubt fear himself herself conscience temptation inner struggled wrestled mind guilt""".split()
    ),
    "person_vs_supernatural_or_tech": frozenset(
        """ghost spirit magic curse demon god prophecy vampire werewolf alien machine ai robot""".split()
    ),
    "person_vs_fate_or_time": frozenset(
        """fate destiny destined inevitable doomed prophecy luck chance fortune time death""".split()
    ),
}
CONFLICT_KEYS = list(CONFLICT_LISTS.keys())

STAKES_DOMAINS: Dict[str, frozenset] = {
    "physical_survival": frozenset(
        """survive death die danger hurt injury blood wound starve shelter food safety""".split()
    ),
    "relationships": frozenset(
        """family mother father sister brother wife husband lover friend marriage love""".split()
    ),
    "social_order": frozenset(
        """society community town kingdom city law order government rule power""".split()
    ),
    "identity": frozenset(
        """identity self who_am_i sanity mind soul purpose meaning become change""".split()
    ),
    "moral": frozenset(
        """morals soul redemption forgiveness sin conscience virtue good evil salvation""".split()
    ),
    "cosmic": frozenset(
        """world reality universe existence everything cosmos fate destiny god""".split()
    ),
}
STAKES_KEYS = list(STAKES_DOMAINS.keys())

MOTIVE_LISTS: Dict[str, frozenset] = {
    "desire": frozenset("wanted wished dreamed hoped longed craved ambition desire goal".split()),
    "ethical": frozenset("should duty moral principles conscience honor justice right wrong".split()),
    "family": frozenset("family mother father son daughter parent obligation blood home".split()),
    "trauma": frozenset("memory past trauma hurt wound scar remembered haunted childhood".split()),
    "survival": frozenset("survive survival money food shelter necessity desperate work job".split()),
    "supernatural": frozenset("curse prophecy god fate magic compelled forced".split()),
}
MOTIVE_KEYS = list(MOTIVE_LISTS.keys())

MOTIVE_DOMAINS: Dict[str, frozenset] = {
    "survival": frozenset("survive survival safety food shelter danger protect".split()),
    "family": frozenset("family mother father wife husband child love relationship marriage".split()),
    "ideological": frozenset("principle belief justice truth freedom faith honor duty".split()),
    "curiosity": frozenset("curious curiosity discover know understand mystery question explore".split()),
    "ambition": frozenset("ambition power success wealth status prove win achieve".split()),
    "atonement": frozenset("guilt shame forgive forgiveness atone redeem redemption regret".split()),
}
MOTIVE_DOMAIN_KEYS = list(MOTIVE_DOMAINS.keys())

RELATION_LISTS: Dict[str, frozenset] = {
    "familial_kinship": frozenset(
        """mother father mom dad sister brother aunt uncle cousin grandmother grandfather son daughter
        wife husband family parent child""".split()
    ),
    "romantic": frozenset(
        """love girlfriend boyfriend wife husband lover fiance kiss romance married""".split()
    ),
    "friendship": frozenset("friend buddy pal best_friend friendship mate comrade".split()),
    "professional": frozenset(
        """colleague boss manager employee coworker team partner client customer firm company""".split()
    ),
    "mentorship": frozenset("mentor teacher student apprentice coach guide disciple training".split()),
    "adversarial": frozenset("enemy rival opponent adversary nemesis foe antagonist".split()),
}
RELATION_KEYS = list(RELATION_LISTS.keys())

NON_HUMAN_REL = frozenset(
    """ai robot computer machine ship god goddess spirit ghost angel demon entity system company
    corporation""".split()
)

COLLECTIVE_WORDS = frozenset(
    """villagers crowd mob people society community nation church government army public family team
    group organization company citizens townsfolk the_people""".split()
)
AUTHORITY_WORDS = frozenset(
    """king queen lord ruler government boss commander captain chief president officer judge priest
    principal manager authority rule order law hierarchy general colonel director""".split()
)
ABUSE_WORDS = frozenset(
    """abuse abused hit slapped beat manipulated manipulation control coercion neglect exploited""".split()
)
VIOLENCE_WORDS = frozenset(
    """hit punch kick stab shoot gun knife blood fight attack kill murder violence war battle
    scream""".split()
)
FORGIVE_WORDS = frozenset(
    """forgive forgiveness reconcile reconciliation apologize apology made_up made_peace forgive""".split()
)
GOSSIP_WORDS = frozenset("gossip rumor rumour whispered hearsay scandal idle_talk".split())
RITUAL_WORDS = frozenset(
    """ritual ceremony toast prayer tradition rite offering festival holiday feast gathering""".split()
)
BROKER_WORDS = frozenset(
    """mediator negotiator translator go_between intermediary emissary ambassador liaison""".split()
)
CROSS_BOUNDARY = frozenset(
    """rich poor lord servant master slave noble peasant king commoner class rank status
    immigrant""".split()
)

PLACE_LISTS: Dict[str, frozenset] = {
    "domestic_private": frozenset(
        """house home room kitchen bedroom living_room apartment door window hallway stairs couch
        bed table""".split()
    ),
    "public_social": frozenset(
        """street city town market cafe restaurant bar square park station shop store plaza avenue
        crowd""".split()
    ),
    "natural_outdoor": frozenset(
        """forest river mountain ocean sea field garden woods hill desert sky sun wind rain tree grass
        lake valley snow""".split()
    ),
    "institutional": frozenset(
        """office school hospital church factory government court prison laboratory university bank
        police station building""".split()
    ),
    "virtual_digital": frozenset(
        """screen computer internet phone digital virtual code network ai chat app data""".split()
    ),
}
PLACE_KEYS = list(PLACE_LISTS.keys())

SENSORY_LISTS: Dict[str, frozenset] = {
    "visual": frozenset(
        """saw looked light bright dark color red blue green black white glint shimmer glow shadow
        glimpse sight""".split()
    ),
    "auditory": frozenset(
        """heard sound voice noise whisper scream music silence footsteps loud quiet rang echo
        shout""".split()
    ),
    "olfactory": frozenset(
        """smell smelled scent odor perfume stench aroma fragrant stale smoke""".split()
    ),
    "tactile": frozenset(
        """touch cold warm hot soft hard rough smooth wet dry pain ache trembling shiver skin hand
        felt""".split()
    ),
    "gustatory": frozenset("taste tasted sweet bitter sour salty flavor delicious bitter".split()),
    "kinesthetic": frozenset(
        """ran walked moved climbed jumped crawled pushed pulled lifted carried motion movement""".split()
    ),
}
SENSORY_KEYS = list(SENSORY_LISTS.keys())

WEATHER_WORDS = frozenset(
    """rain snow wind storm thunder lightning fog mist cloud sky sun heat cold ice frost drizzle""".split()
)
DECAY_WORDS = frozenset(
    """rust rot decay dust mold cracked peeling stained grime broken worn faded""".split()
)
TECH_WORDS = frozenset(
    """screen computer phone technology machine digital device code network robot ai""".split()
)

CLICHES = [
    "in the end",
    "little did he know",
    "little did she know",
    "heart racing",
    "took a deep breath",
    "out of nowhere",
    "all of a sudden",
    "in the blink of an eye",
    "a sense of",
    "in that moment",
    "for the first time in years",
    "the world seemed",
    "as if",
    "deep down",
    "in the back of his mind",
    "in the back of her mind",
    "he couldn't help but",
    "she couldn't help but",
    "at that moment",
    "it was then that",
    "one last time",
    "time seemed to stand still",
]

LATINATE_SUFFIXES = ("tion", "sion", "ment", "ity", "ance", "ence", "ous", "ism", "ize", "isation", "ization")
ONOMATOPOEIA = frozenset("bang crash boom buzz hiss splash creak thud clang pop screech roar".split())

PROPER_STOP = frozenset(
    """the a an and but or for nor of in on at to from by with about against between into through
    during before after above below up down out off over under again further then once here there
    when where why how all any both each few more most other some such no nor not only own same so
    than too very can will just should now i he she it we they you that this these those is are was
    were be been being have has had do does did""".split()
)

# ---------------------------------------------------------------------------
# Tokenization + statistics
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.replace("\n", " "))
    return [p.strip() for p in parts if p.strip()]


class Stats:
    """All statistics computed from the story text, in one pass."""

    def __init__(self, text: str):
        self.raw = text
        self.n_chars = len(text)
        self.sentences = _split_sentences(text)
        self.n_sentences = max(1, len(self.sentences))
        self.tokens = re.findall(r"[A-Za-z']+", text)
        self.words = [w.lower() for w in self.tokens]
        self.n_words = len(self.words)
        self.lower = text.lower()

        self.sent_lens = [len(re.findall(r"[A-Za-z']+", s)) for s in self.sentences]
        self.mean_sent_len = sum(self.sent_lens) / self.n_sentences
        self.std_sent_len = (
            math.sqrt(sum((l - self.mean_sent_len) ** 2 for l in self.sent_lens) / self.n_sentences)
            if self.n_sentences > 1
            else 0.0
        )
        self.mean_word_len = sum(len(w) for w in self.words) / max(1, self.n_words)

        sample = self.words[:3000]
        self.ttr = len(set(sample)) / max(1, len(sample))

        # dialogue: fraction of characters inside double OR single quotes
        spans = re.findall(r'"([^"]*)"', text) + re.findall(r"'([^']*)'", text)
        self.utterances = len(spans)
        self.quote_chars = sum(len(s) for s in spans)
        self.quote_ratio = self.quote_chars / max(1, self.n_chars)

        self.exclamations = self.lower.count("!") / max(1, self.n_chars)
        self.questions = self.lower.count("?") / max(1, self.n_chars)
        self.em_dashes = text.count("—") + len(re.findall(r"\s--\s", text))
        self.parens = text.count("(") + text.count(")")
        self.ellipses = self.lower.count("…") + self.lower.count("...")
        self.apostrophes = text.count("'")

        self.fragments = sum(1 for l in self.sent_lens if 0 < l <= 4)
        self.fragment_ratio = self.fragments / self.n_sentences

        wset = set(self.words)
        self.word_set = wset

        # verb tense proxies
        past = 0
        present = 0
        future = 0
        for w in self.words:
            if w in _PAST_IRREG or w.endswith("ed"):
                past += 1
            if w in _PRESENT_IRREG or w.endswith("s"):
                present += 1
            if w in _FUTURE:
                future += 1
        self.past_rate = past / max(1, self.n_words)
        self.present_rate = present / max(1, self.n_words)
        self.future_rate = future / max(1, self.n_words)
        self.past_verbs = past

        # pronouns
        # Pronoun rates are computed on the narration only (quoted speech
        # excluded) so that dialogue-heavy scenes don't misread as second
        # person or skew narrative-person detection.
        narration = re.sub(r'"([^"]*)"', " ", text)
        narration = re.sub(r"'([^']*)'", " ", narration)
        nwords = [w.lower() for w in re.findall(r"[A-Za-z']+", narration)]
        self.first = sum(1 for w in nwords if w in FIRST_PRON)
        self.second = sum(1 for w in nwords if w in SECOND_PRON)
        self.third = sum(1 for w in nwords if w in THIRD_PRON)
        self.pronouns = self.first + self.second + self.third
        self.first_rate = self.first / max(1, self.pronouns)
        self.second_rate = self.second / max(1, self.pronouns)
        self.third_rate = self.third / max(1, self.pronouns)
        # you_rate / reader_rate: also narration-only for direct-address detection
        self.you_rate = self.second / max(1, len(nwords))
        self.reader_rate = self.lower.count("reader") / max(1, self.n_words)

        # connectors / discourse markers
        self.coord = sum(1 for w in self.words if w in COORDINATORS)
        self.subord = sum(1 for w in self.words if w in SUBORDINATORS)
        self.causal = sum(1 for w in self.words if w in CAUSAL)
        self.coord_rate = self.coord / max(1, self.n_words)
        self.subord_rate = self.subord / max(1, self.n_words)
        self.causal_rate = self.causal / max(1, self.n_words)

        # passive-ish: be-verb followed by a past participle-ish token
        passive = 0
        for i, w in enumerate(self.words[:-1]):
            if w in ("was", "were", "been", "being", "is", "are") and (
                self.words[i + 1] in _PAST_IRREG or self.words[i + 1].endswith("ed")
            ):
                passive += 1
        self.passive_rate = passive / max(1, self.n_words)

        # proper nouns
        proper: List[str] = []
        for si, s in enumerate(self.sentences):
            toks = re.findall(r"[A-Za-z']+", s)
            for ti, t in enumerate(toks):
                if (
                    ti > 0
                    and t[:1].isupper()
                    and t[1:].islower()
                    and t.lower() not in PROPER_STOP
                    and t.lower() not in ("i",)
                ):
                    proper.append(t.lower())
        self.proper_nouns = proper
        self.unique_proper = len(set(proper))
        self.proper_rate = len(proper) / max(1, self.n_words)

        def _rate_of(words: Sequence[str], wset: frozenset) -> float:
            return _rate(sum(1 for w in self.words if w in wset), self.n_words)

        self.thought_rate = _rate_of(self.words, THOUGHT_VERBS)
        self.dialogue_verb_rate = _rate_of(self.words, DIALOGUE_VERBS)
        self.emotion_label_rate = _rate_of(self.words, EMOTION_LABELS)
        self.emotion_bodily_rate = _rate_of(self.words, EMOTION_BODILY)
        self.emotion_facial_rate = _rate_of(self.words, EMOTION_FACIAL)
        self.emotion_action_rate = _rate_of(self.words, EMOTION_ACTION)
        self.moral_rate = _rate_of(self.words, MORAL_WORDS)
        self.meta_rate = _rate_of(self.words, META_WORDS)
        self.doc_rate = _rate_of(self.words, DOCUMENT_WORDS)
        self.time_marker_rate = _rate_of(self.words, TIME_MARKERS)
        self.time_of_day_rate = _rate_of(self.words, TIME_OF_DAY)
        self.season_rate = _rate_of(self.words, SEASONS)
        self.time_span_rate = _rate_of(self.words, TIME_SPAN_WORDS)
        self.flashback_rate = _rate_of(self.words, FLASHBACK_MARKERS)
        self.dream_rate = _rate_of(self.words, DREAM_WORDS)
        self.loop_rate = _rate_of(self.words, LOOP_WORDS)
        self.deadline_rate = _rate_of(self.words, DEADLINE_WORDS)
        self.habitual_rate = _rate_of(self.words, HABITUAL_WORDS)
        self.reveal_rate = _rate_of(self.words, REVEAL_WORDS)
        self.suspense_rate = _rate_of(self.words, SUSPENSE_WORDS)
        self.twist_rate = _rate_of(self.words, TWIST_WORDS)
        self.irony_rate = _rate_of(self.words, IRONY_MARKERS)
        self.humor_rate = _rate_of(self.words, HUMOR_WORDS)
        self.mystery_rate = _rate_of(self.words, MYSTERY_WORDS)
        self.collective_rate = _rate_of(self.words, COLLECTIVE_WORDS)
        self.authority_rate = _rate_of(self.words, AUTHORITY_WORDS)
        self.abuse_rate = _rate_of(self.words, ABUSE_WORDS)
        self.violence_rate = _rate_of(self.words, VIOLENCE_WORDS)
        self.forgive_rate = _rate_of(self.words, FORGIVE_WORDS)
        self.gossip_rate = _rate_of(self.words, GOSSIP_WORDS)
        self.ritual_rate = _rate_of(self.words, RITUAL_WORDS)
        self.broker_rate = _rate_of(self.words, BROKER_WORDS)
        self.nonhuman_rel_rate = _rate_of(self.words, NON_HUMAN_REL)
        self.cross_boundary_rate = _rate_of(self.words, CROSS_BOUNDARY)
        self.onomatopoeia_rate = _rate_of(self.words, ONOMATOPOEIA)

        # place / sensory / genre / theme / conflict / stakes / motive / relation counts
        self.places = {k: _rate_of(self.words, v) for k, v in PLACE_LISTS.items()}
        self.sensory = {k: _rate_of(self.words, v) for k, v in SENSORY_LISTS.items()}
        self.genre = {k: _rate_of(self.words, v) for k, v in GENRE_LISTS.items()}
        self.themes = {k: _rate_of(self.words, v) for k, v in THEME_DOMAINS.items()}
        self.conflicts = {k: _rate_of(self.words, v) for k, v in CONFLICT_LISTS.items()}
        self.stakes = {k: _rate_of(self.words, v) for k, v in STAKES_DOMAINS.items()}
        self.motives = {k: _rate_of(self.words, v) for k, v in MOTIVE_LISTS.items()}
        self.motive_domains = {k: _rate_of(self.words, v) for k, v in MOTIVE_DOMAINS.items()}
        self.relations = {k: _rate_of(self.words, v) for k, v in RELATION_LISTS.items()}

        self.weather_rate = _rate_of(self.words, WEATHER_WORDS)
        self.decay_rate = _rate_of(self.words, DECAY_WORDS)
        self.tech_rate = _rate_of(self.words, TECH_WORDS)

        # tone words for earnest/lyrical vs detached register
        self.earnest_rate = _rate_of(self.words, EARNEST_WORDS)

        # clichés (multiword stock phrases)
        cliche_hits = sum(1 for c in CLICHES if c in self.lower)
        self.cliche_rate = cliche_hits / max(1, self.n_sentences)

        # latinate flavor
        latinate = sum(1 for w in self.words if w.endswith(LATINATE_SUFFIXES))
        self.latinate_rate = latinate / max(1, self.n_words)
        long_words = sum(1 for w in self.words if len(w) >= 13)
        self.long_word_rate = long_words / max(1, self.n_words)

        # alliteration: adjacent in-sentence word pairs sharing initial, both >= 4 chars
        pairs = 0
        for s in self.sentences:
            toks = [t.lower() for t in re.findall(r"[A-Za-z']+", s) if len(t) >= 4]
            for a, b in zip(toks, toks[1:]):
                if a and b and a[0] == b[0] and a[0] not in "st":
                    pairs += 1
        self.alliteration_rate = pairs / self.n_sentences

        # end-rhyme: adjacent sentences ending in the same 2-char tail
        rhyme = 0
        tails = [re.findall(r"[A-Za-z']+", s) for s in self.sentences]
        for a, b in zip(tails, tails[1:]):
            if a and b and a[-1].lower()[-2:] == b[-1].lower()[-2:] and len(a[-1]) > 3 and len(b[-1]) > 3:
                rhyme += 1
        self.rhyme_rate = rhyme / max(1, self.n_sentences)

        # repetition: repeated content bigrams
        bigrams = [self.words[i] + " " + self.words[i + 1] for i in range(len(self.words) - 1)]
        bigrams = [b for b in bigrams if not any(t in ("the", "a", "an", "and", "of", "to", "in") for t in b.split())]
        counts = Counter(bigrams)
        repeated = sum(c - 1 for c in counts.values() if c > 1)
        self.repetition_rate = repeated / max(1, len(bigrams))

        # per-third intensity curves (sentence length + event verbs)
        third = max(1, self.n_sentences // 3)
        thirds = [self.sentences[i * third : (i + 1) * third] for i in range(3)]
        self.third_events: List[float] = []
        self.third_emotion: List[float] = []
        self.third_sent_len: List[float] = []
        for chunk in thirds:
            tw = [w.lower() for s in chunk for w in re.findall(r"[A-Za-z']+", s)]
            n = max(1, len(tw))
            ev = sum(1 for w in tw if w in _PAST_IRREG or w.endswith("ed") or w in _PRESENT_IRREG)
            self.third_events.append(ev / n)
            emo = sum(1 for w in tw if w in EMOTION_LABELS or w in EMOTION_BODILY)
            self.third_emotion.append(emo / n)
            lens = [len(re.findall(r"[A-Za-z']+", s)) for s in chunk]
            self.third_sent_len.append(sum(lens) / max(1, len(lens)))

        self.event_rate = sum(self.third_events) / 3
        self.climax_third = int(self.third_events.index(max(self.third_events))) if self.n_sentences >= 6 else 1

        self.opening = " ".join(self.sentences[:2])
        self.ending = " ".join(self.sentences[-2:])

        # dates / clock references
        self.date_count = sum(1 for w in self.words if w in MONTHS or w in DAYS)
        self.clock_count = self.lower.count("o'clock") + len(re.findall(r"\d{1,2}:\d{2}", text))


# ---------------------------------------------------------------------------
# Per-feature extractors
# ---------------------------------------------------------------------------

# Each extractor: (stats, feature) -> canonical value (str | int | list[str]) or MISSING.


def _dom(feat: Feature, scores: Dict[str, float], fallback: Optional[str] = None) -> str:
    """Pick the canonical value whose search key has the highest score."""
    best_key, best_v = max(scores.items(), key=lambda kv: kv[1])
    if best_v <= 0.0 and fallback:
        return fallback
    return _find(feat, best_key) or fallback or MISSING


# --- style -----------------------------------------------------------------

def sty_cpx_002(st, f):
    m = st.mean_sent_len
    return _bucketed(f, m, [11, 21, 36, 51])


def sty_cpx_010(st, f):
    m = st.mean_sent_len
    return _bucketed(f, m, [12, 21, 31])


def sty_cpx_004(st, f):
    # paratactic vs hypotactic on a 5-point scale
    hyp = st.subord_rate
    idx = _bucket(hyp, [0.01, 0.02, 0.035, 0.05])
    return _pick(f, idx)


def sty_cpx_005(st, f):
    if st.subord_rate > 0.03 and st.coord_rate < st.subord_rate * 1.2:
        return _find(f, "hypotactic")
    if st.coord_rate > st.subord_rate * 1.5:
        return _find(f, "paratactic")
    return _find(f, "balanced") or MISSING


def sty_cpx_003(st, f):
    return _find(f, "present") if st.fragment_ratio >= 0.10 else _find(f, "absent") or MISSING


def sty_cpx_011(st, f):
    return _bucketed(f, st.subord_rate, [0.012, 0.024, 0.038, 0.055])


def sty_cpx_013(st, f):
    d = (st.em_dashes + st.parens) / max(1, st.n_sentences)
    return _bucketed(f, d, [0.15, 0.6])


def sty_cpx_012(st, f):
    out = []
    if st.fragment_ratio >= 0.10:
        v = _find(f, "frequent_fragments")
        if v:
            out.append(v)
    if st.repetition_rate >= 0.04:
        v = _find(f, "frequent_parallel")
        if v:
            out.append(v)
    if st.em_dashes / max(1, st.n_sentences) >= 0.4 or st.parens / max(1, st.n_sentences) >= 0.5:
        v = _find(f, "frequent_parenthetical")
        if v:
            out.append(v)
    if st.subord_rate >= 0.045:
        v = _find(f, "frequent_loose")
        if v:
            out.append(v)
    return out if out else MISSING


def sty_fig_001(st, f):
    simile = len(re.findall(r"\b(?:like|as if|as though)\b", st.lower)) / max(1, st.n_sentences)
    fig = simile + st.meta_rate * 2
    return _bucketed(f, fig, [0.05, 0.12, 0.25, 0.45])


def sty_fig_002(st, f):
    simile = len(re.findall(r"\b(?:like|as if|as though)\b", st.lower)) / max(1, st.n_sentences)
    meta = st.meta_rate
    if simile > 0.25 and simile > meta * 2:
        return _find(f, "simile") or MISSING
    if meta > 0.04 and meta > simile * 2:
        return _find(f, "metaphor") or MISSING
    if st.personification_rate if hasattr(st, "personification_rate") else False:
        return _find(f, "personification") or MISSING
    return _find(f, "mixed") or _find(f, "mostly_literal") or MISSING


def sty_fig_003(st, f):
    # cliché vs fresh only applies when figurative language is actually present;
    # with no figuration the feature is undeterminable -> n/a
    fig = (len(re.findall(r"\b(?:like|as if|as though)\b", st.lower)) + st.meta_rate * 2) / max(1, st.n_sentences)
    if fig < 0.10:
        return MISSING
    if st.cliche_rate > 0.20:
        return _pick(f, 0)
    if st.cliche_rate > 0.05:
        return _pick(f, 1)
    return _pick(f, 2)


def sty_fig_007(st, f):
    concrete = sum(st.sensory.values()) + st.places.get("natural_outdoor", 0)
    return _bucketed(f, concrete * 60, [1.0, 2.5, 5.0, 9.0])


def sty_fig_009(st, f):
    concrete = sum(st.sensory.values())
    abstract = st.latinate_rate * 10
    score = 3.0 + (concrete * 80 - abstract * 40) / 2.0
    return _bucketed(f, score, [1.0, 2.2, 3.8, 4.8])


def sty_ton_001(st, f):
    scores = {
        "comic_or_ironic": st.humor_rate + st.irony_rate,
        "dark_or_gothic": st.genre.get("horror", 0) + st.emotion_bodily_rate * 0.5,
        "lyrical_or_meditative": st.sensory.get("auditory", 0) + st.sensory.get("visual", 0) + st.thought_rate,
        "hardboiled_or_noir": st.genre.get("mystery_detective", 0) + st.suspense_rate,
        "academic_or_analytic": st.long_word_rate + st.latinate_rate,
        "neutral_reportorial": 0.03,
    }
    return _dom(f, scores, fallback="neutral_reportorial")


def sty_ton_021(st, f):
    scores = {
        "earnest_or_lyrical": st.sensory.get("auditory", 0) + st.sensory.get("visual", 0) + st.earnest_rate * 3,
        "ironic_or_wry": st.irony_rate * 2,
        "comic_or_satirical": st.humor_rate * 2,
        "gothic_or_horror": st.genre.get("horror", 0),
        "detached_or_clinical": st.latinate_rate + st.long_word_rate - st.emotion_label_rate * 4,
    }
    return _dom(f, scores, fallback="highly_variable_no_single_dominant_tone")


def sty_ton_002(st, f):
    return _bucketed(f, st.moral_rate * 180, [1.2, 2.6, 4.2, 6.5])


def sty_ton_020(st, f):
    return _bucketed(f, st.moral_rate * 180 + st.emotion_label_rate * 60, [1.2, 2.6, 4.2, 6.5])


def sty_ton_005(st, f):
    dialect = st.apostrophes / max(1, st.n_words) + st.humor_rate
    if st.ttr < 0.35 or dialect > 0.10:
        return _find(f, "highly_idiosyncratic") or MISSING
    if st.ttr < 0.5 or dialect > 0.04:
        return _find(f, "moderately_marked") or MISSING
    return _find(f, "plain_neutral") or MISSING


def sty_ton_006(st, f):
    return _bucketed(f, st.alliteration_rate + st.rhyme_rate, [0.15, 0.5, 1.2])


def sty_ton_024(st, f):
    return _bucketed(f, st.alliteration_rate * 3 + st.rhyme_rate + st.std_sent_len / 12, [0.8, 1.5, 2.5, 3.8])


def sty_ton_007(st, f):
    if st.std_sent_len > 9 and st.mean_sent_len > 15:
        return _find(f, "strong_contrast") or MISSING
    if st.mean_sent_len > 25:
        return _find(f, "mostly_long_periodic") or MISSING
    if st.mean_sent_len < 12:
        return _find(f, "mostly_short_punchy") or MISSING
    return _find(f, "mostly_even") or MISSING


def sty_ton_023(st, f):
    return _bucketed(f, st.humor_rate * 40 + st.irony_rate * 30, [0.8, 2.5])


def sty_ton_025(st, f):
    out = []
    if st.alliteration_rate >= 0.4:
        v = _find(f, "alliteration_prominent")
        if v:
            out.append(v)
    if st.rhyme_rate >= 0.2:
        v = _find(f, "occasional_internal_or_end_rhyme")
        if v:
            out.append(v)
    if st.onomatopoeia_rate >= 0.004:
        v = _find(f, "onomatopoeia_or_sound_imitations")
        if v:
            out.append(v)
    if not out:
        v = _find(f, "no_conscious_sound_patterning")
        if v:
            out.append(v)
    return out


def sty_ton_027(st, f):
    return _find(f, "present") if st.meta_rate >= 0.008 else _find(f, "absent") or MISSING


def sty_ton_029(st, f):
    return _bucketed(f, st.mean_sent_len, [11, 16, 22, 30])


def sty_all_015(st, f):
    if st.apostrophes / max(1, st.n_words) > 0.02 and st.long_word_rate < 0.01:
        return _find(f, "consistently_colloquial") or MISSING
    if st.long_word_rate > 0.03 and st.latinate_rate > 0.12:
        return _find(f, "consistently_elevated") or MISSING
    return _find(f, "consistently_neutral") or MISSING


def sty_all_016(st, f):
    return _bucketed(f, st.latinate_rate * 60 + st.long_word_rate * 40, [2.0, 4.0, 6.5, 9.5])


def sty_all_017(st, f):
    return _bucketed(f, st.proper_rate * 100, [1.0, 3.0, 8.0, 16.0])


def sty_all_018(st, f):
    mapping = {
        "religious_or_mythological": ["god", "angel", "heaven", "soul", "prayer", "myth", "bible", "church"],
        "historical_or_political": ["king", "empire", "war", "revolution", "soldier", "queen", "battle"],
        "literary_or_high_cultural": ["book", "novel", "poet", "poetry", "literature", "shakespeare"],
        "pop_culture_or_brand": ["movie", "film", "song", "celebrity", "tv", "band"],
        "scientific_or_technical": ["science", "physics", "machine", "data", "lab", "experiment"],
        "self_referential_or_meta": ["story", "narrator", "tale", "telling", "chapter"],
    }
    return _multi(st, f, mapping)


def sty_all_019(st, f):
    return _bucketed(f, st.long_word_rate * 40 + st.tech_rate * 20, [1.5, 4.0, 9.0])


# --- temporal structure ----------------------------------------------------

def tmp_dur_011(st, f):
    if st.past_rate > st.present_rate * 1.3 and st.past_rate > 0.03:
        return _find(f, "past") or MISSING
    if st.present_rate > st.past_rate * 1.3 and st.present_rate > 0.03:
        return _find(f, "present") or MISSING
    if st.future_rate > 0.01 and st.future_rate > st.past_rate and st.future_rate > st.present_rate:
        return _find(f, "future") or MISSING
    return _find(f, "mixed_or_shifted") or MISSING


def tmp_dur_009(st, f):
    return _bucketed(f, st.time_marker_rate * 60, [1.5, 3.0, 5.0, 8.0])


def tmp_dur_019(st, f):
    return _bucketed(f, st.time_of_day_rate * 80, [0.8, 2.0, 4.5, 9.0])


def tmp_dur_008(st, f):
    d = st.date_count / max(1, st.n_sentences) * 10 + st.clock_count
    return _bucketed(f, d, [0.3, 1.0, 3.0])


def tmp_dur_010(st, f):
    jumps = len(re.findall(r"\b(?:days|weeks|months|years) (?:later|before)\b", st.lower))
    j = jumps / max(1, st.n_sentences)
    if j >= 0.06:
        return _find(f, "months_or_longer") or MISSING
    if j >= 0.02:
        return _find(f, "multi_day") or MISSING
    if st.time_span_rate * 30 > 1.0:
        return _find(f, "hours_to_single_day") or MISSING
    return _find(f, "continuous_or_near_continuous") or MISSING


def tmp_dur_007(st, f):
    jumps = len(re.findall(r"\b(?:days|weeks|months|years|hours) (?:later|passed|before)\b", st.lower)) / max(1, st.n_sentences)
    return _bucketed(f, jumps, [0.03, 0.10])


def tmp_dur_002(st, f):
    jumps = len(re.findall(r"\b(?:days|weeks|months|years|decades) (?:later|passed|before|after)\b", st.lower)) / max(1, st.n_sentences)
    return _bucketed(f, jumps * 25 + st.time_span_rate * 10, [1.5, 3.0, 5.5, 9.0])


def tmp_dur_006(st, f):
    return _find(f, "yes") if st.habitual_rate > 0.01 else _find(f, "no") or MISSING


def tmp_dur_013(st, f):
    return _find(f, "yes") if st.deadline_rate > 0.002 else _find(f, "no") or MISSING


def tmp_dur_018(st, f):
    return _bucketed(f, st.season_rate * 100, [1.5, 4.0, 10.0, 20.0])


def tmp_dur_021(st, f):
    if st.aging_rate if hasattr(st, "aging_rate") else False:
        return _find(f, "single_character_across_multiple_life_stages") or MISSING
    if len(re.findall(r"\b(?:years|decades) (?:later|passed)\b", st.lower)) / max(1, st.n_sentences) > 0.02:
        return _find(f, "single_character_across_multiple_life_stages") or MISSING
    if st.time_span_rate * 100 > 20:
        return _find(f, "multi_generational") or MISSING
    return _find(f, "no_significant_aging") or MISSING


def tmp_ord_001(st, f):
    fb = st.flashback_rate
    if fb >= 0.02:
        return _find(f, "chronological_spine_with_frequent_flashbacks") or MISSING
    if fb >= 0.008:
        return _find(f, "mostly_chronological_with_rare_flashbacks") or MISSING
    return _find(f, "strictly_chronological") or MISSING


def tmp_ord_002(st, f):
    return _bucketed(f, st.flashback_rate * 100, [0.8, 2.5, 6.0, 12.0])


def tmp_ord_004(st, f):
    fb = st.flashback_rate
    if fb >= 0.02:
        return _find(f, "multi_level_nested_flashbacks") or MISSING
    if fb >= 0.006:
        return _find(f, "single_level_flashbacks_only") or MISSING
    return _find(f, "no_flashbacks") or MISSING


def tmp_ord_010(st, f):
    return _bucketed(f, st.flashback_rate * 100 + st.loop_rate * 60, [1.5, 3.5, 7.0, 14.0])


def tmp_ord_005(st, f):
    if st.flashback_rate < 0.004:
        return _find(f, "minimal_or_implict_backstory_only") or MISSING
    pos = st.lower.find("flashback")
    if pos == -1:
        pos = st.lower.find("remembered")
    if pos == -1:
        return _find(f, "evenly_interleaved") or MISSING
    rel = pos / max(1, st.n_chars)
    if rel < 0.15:
        return _find(f, "front_loaded_exposition") or MISSING
    if rel > 0.7:
        return _find(f, "withheld_until_late_reveal") or MISSING
    return _find(f, "evenly_interleaved") or MISSING


def tmp_ord_008(st, f):
    if st.loop_rate < 0.002:
        v = _find(f, "no_explicit_temporal_loop")
        return [v] if v else MISSING
    mapping = {
        "same_day_or_hour_resets": ["reset", "relive", "same day", "again"],
        "simulation_or_experiment_resets": ["simulation", "experiment", "simulated"],
        "branching_restarts": ["restart", "branching", "started over"],
        "structure_as_infinite_or_unresolved_loop": ["infinite", "unresolved", "forever", "endless"],
    }
    return _multi(st, f, mapping)


def tmp_ord_009(st, f):
    if st.habitual_rate > 0.012:
        return _find(f, "iterative") or MISSING
    if st.loop_rate > 0.002 or st.repetition_rate > 0.06:
        return _find(f, "repeating") or MISSING
    return _find(f, "singulative") or MISSING


def tmp_ord_011(st, f):
    return _find(f, "significant_dream_or_vision_time") if st.dream_rate > 0.004 else _find(f, "no_significant_dream_time") or MISSING


def tmp_ord_012(st, f):
    return _find(f, "yes") if st.loop_rate > 0.002 else _find(f, "no") or MISSING


def tmp_ord_014(st, f):
    ending = st.ending.lower()
    if any(w in ending for w in ("later", "years after", "eventually", "years later", "in the end", "finally")):
        return _find(f, "ends_with_brief_forward_epilogue") or _find(f, "ends_at_distant_future") or MISSING
    if any(w in ending for w in ("unknown", "unanswered", "unresolved", "didn't know", "never", "cliffhanger")):
        return _find(f, "ends_before_external_resolution_mid_arc_or_cliffhanger") or MISSING
    return _find(f, "ends_at_or_just_after_main_climax_no_forward_jump") or MISSING


def tmp_dur_004(st, f):
    if st.quote_ratio > 0.35:
        return _find(f, "scene_dominant") or MISSING
    if st.time_span_rate * 40 > 2.0 and st.quote_ratio < 0.1:
        return _find(f, "summary_dominant") or MISSING
    return _find(f, "mixed_no_clear_dominant") or MISSING


def tmp_dur_012(st, f):
    if any(w in st.lower for w in ("looking back", "i remember", "years later", "back then", "long ago")):
        return _find(f, "distant_retrospective") or MISSING
    if st.present_rate > st.past_rate:
        return _find(f, "simultaneous_or_ongoing") or MISSING
    return _find(f, "slightly_retrospective") or MISSING


# --- perspective -----------------------------------------------------------

def per_pov_001(st, f):
    if st.first_rate > 0.55:
        return _find(f, "first_person") or MISSING
    if st.second_rate > 0.35:
        return _find(f, "second_person") or MISSING
    if st.third_rate > 0.55:
        return _find(f, "third_person") or MISSING
    return _find(f, "mixed_no_dominant") or MISSING


def per_pov_009(st, f):
    d = st.you_rate + st.reader_rate
    return _bucketed(f, d * 100, [1.0, 4.0])


def per_pov_003(st, f):
    if st.first_rate > 0.55 and st.event_rate > 0.05:
        return _find(f, "autodiegetic_protagonist") or MISSING
    if st.third_rate > 0.6:
        return _find(f, "heterodiegetic_external") or MISSING
    return _find(f, "homodiegetic_minor_character") or MISSING


def per_pov_007(st, f):
    return _find(f, "present") if st.doc_rate > 0.01 else _find(f, "absent") or MISSING


def per_foc_001(st, f):
    return _bucketed(f, st.thought_rate * 200, [1.5, 3.0, 5.5, 9.0])


def per_foc_003(st, f):
    closeness = st.first_rate + st.thought_rate * 10 + st.emotion_label_rate * 5
    return _bucketed(f, closeness, [0.4, 0.7, 1.1, 1.6])


def per_foc_005(st, f):
    return _bucketed(f, st.thought_rate * 200, [0.8, 2.5, 5.0])


def per_foc_008(st, f):
    return _bucketed(f, st.first_rate * 2 + st.meta_rate * 40 + st.em_dashes / max(1, st.n_sentences), [0.6, 1.2, 2.0, 3.0])


def per_foc_009(st, f):
    return _bucketed(f, st.moral_rate * 180 + st.emotion_label_rate * 60, [1.2, 2.6, 4.2, 6.5])


def per_dia_001(st, f):
    return _bucketed(f, st.quote_ratio * 100, [4.0, 12.0, 22.0, 34.0])


def per_dia_002(st, f):
    tags = st.dialogue_verb_rate * 100
    if st.quote_ratio > 0.15 and tags < 0.6:
        return _find(f, "sparse_or_minimal_tagging") or MISSING
    return _find(f, "standard_speech_tags") or MISSING


def per_dia_005(st, f):
    report = len(re.findall(r"\b(?:said that|told him|told her|asked if|said she|said he)\b", st.lower)) / max(1, st.n_sentences)
    if st.quote_ratio > 0.25 and report < 0.02:
        return _find(f, "primarily_direct_quoted_speech") or MISSING
    if st.quote_ratio < 0.05 and report > 0.02:
        return _find(f, "primarily_indirect_or_summary_of_speech") or MISSING
    return _find(f, "mixed_direct_and_indirect_speech") or MISSING


def per_dia_006(st, f):
    alt = len(re.findall(r"\b(?:text|chat|message|email|tweet|post)\s*[:—]", st.lower)) + st.lower.count(">>")
    return _find(f, "yes") if alt > 0 else _find(f, "no") or MISSING


# --- plot ------------------------------------------------------------------

def plt_thm_004(st, f):
    mapping = {k: list(v) for k, v in THEME_DOMAINS.items()}
    return _multi(st, f, mapping)


def plt_thm_001(st, f):
    n = sum(1 for k in THEME_KEYS if st.themes[k] > 0.002)
    if n >= 3:
        return _find(f, "multiple_disparate_themes") or MISSING
    if n == 2:
        return _find(f, "two_primary_themes") or MISSING
    return _find(f, "single_central_theme") or MISSING


def plt_thm_003(st, f):
    psych = st.thought_rate + st.emotion_label_rate
    concrete = st.places.get("natural_outdoor", 0) + st.places.get("domestic_private", 0)
    if psych > concrete * 2 and psych > 0.01:
        return _find(f, "psychological") or MISSING
    if concrete > psych * 2:
        return _find(f, "concrete_social") or MISSING
    return _find(f, "balanced_mix") or MISSING


def plt_thm_005(st, f):
    ending = st.ending.lower()
    if any(w in ending for w in ("learned", "understood", "realized", "in the end", "finally", "resolved", "peace")):
        return _find(f, "resolved") or MISSING
    if any(w in ending for w in ("unresolved", "unknown", "never", "still", "couldn't", "uncertain")):
        return _find(f, "unresolved") or MISSING
    return _find(f, "partially_resolved") or MISSING


def plt_mor_001(st, f):
    moral = st.moral_rate * 80 + len(re.findall(r"\b(?:lesson|moral|learned)\b", st.lower)) / max(1, st.n_sentences)
    if moral > 2.0:
        return _find(f, "explicit_didactic_moral") or MISSING
    if moral > 0.8:
        return _find(f, "implicit_moral") or MISSING
    return _find(f, "no_discernible_moral") or MISSING


def plt_mor_003(st, f):
    ending = st.ending.lower()
    if any(w in ending for w in ("finally", "at last", "resolved", "together", "peace", "home", "married")):
        return _find(f, "closed_resolution") or MISSING
    if any(w in ending for w in ("unknown", "unanswered", "never", "didn't know", "open", "uncertain")):
        return _find(f, "open_or_ambiguous") or MISSING
    return _find(f, "partially_closed") or MISSING


def plt_con_001(st, f):
    internal = st.conflicts.get("person_vs_self", 0) + st.thought_rate
    external = (
        st.conflicts.get("person_vs_person", 0)
        + st.conflicts.get("person_vs_nature", 0)
        + st.conflicts.get("person_vs_society", 0)
        + st.violence_rate
    )
    if internal > external * 1.5 and internal > 0.008:
        return _find(f, "internal") or MISSING
    if external > internal * 1.5 and external > 0.008:
        return _find(f, "external") or MISSING
    return _find(f, "balanced_internal_external") or MISSING


def plt_con_002(st, f):
    mapping = {k: list(v) for k, v in CONFLICT_LISTS.items()}
    return _multi(st, f, mapping)


def plt_con_003(st, f):
    mapping = {k: list(v) for k, v in STAKES_DOMAINS.items()}
    return _multi(st, f, mapping)


def plt_str_002(st, f):
    opening = st.opening.lower()
    if any(w in opening for w in ("once upon", "when", "before", "in the beginning", "long ago", "had always")):
        return _find(f, "chronological_from_earliest_relevant_event") or MISSING
    if any(w in opening for w in ("i remember", "looking back", "years later", "back then")):
        return _find(f, "framed_or_retrospective_narration") or MISSING
    return _find(f, "in_medias_res_with_backstory_revealed_later") or MISSING


def plt_str_003(st, f):
    n = st.unique_proper
    if n >= 6:
        return _find(f, "multiple_interwoven_subplots") or MISSING
    if n >= 3:
        return _find(f, "one_or_two_minor_subplots") or MISSING
    return _find(f, "no_significant_subplots") or MISSING


def plt_str_005(st, f):
    if st.mystery_rate > 0.015:
        return _find(f, "mystery_or_investigation_driven") or MISSING
    if st.twist_rate > 0.008:
        return _find(f, "twist_or_reversal_focused") or MISSING
    return _find(f, "transparent_exposition_minimal_secrets") or MISSING


def plt_str_006(st, f):
    if st.n_sentences < 6:
        return _find(f, "no_clear_climactic_peak") or MISSING
    peaks = [i for i, v in enumerate(st.third_events) if v == max(st.third_events)]
    if len(peaks) >= 2 and st.third_events.count(max(st.third_events)) > 1:
        return _find(f, "multiple_climactic_peaks") or MISSING
    if st.climax_third == 2:
        return _find(f, "late_climax_near_end") or MISSING
    if st.climax_third == 0:
        return _find(f, "central_climax_mid_story") or MISSING
    return _find(f, "central_climax_mid_story") or MISSING


# --- events ----------------------------------------------------------------

def evt_typ_001(st, f):
    return _bucketed(f, st.event_rate * 100, [7.0, 10.0, 13.0, 16.0])


def evt_typ_003(st, f):
    if st.quote_ratio > 0.3:
        return _find(f, "scene_based") or MISSING
    if st.time_span_rate * 40 > 3.0:
        return _find(f, "summary_based") or MISSING
    return _find(f, "hybrid") or MISSING


def evt_typ_004(st, f):
    verbs = {w for w in st.words if w in _PAST_IRREG or w.endswith("ed")}
    n = len(verbs)
    if n >= 60:
        return _find(f, "high_diversity") or MISSING
    if n >= 20:
        return _find(f, "medium_diversity") or MISSING
    return _find(f, "low_diversity") or MISSING


def evt_typ_008(st, f):
    span = _time_span_level(st)
    if span >= 4:
        return _find(f, "nonlinear_or_deep_time") or _find(f, "multiple_years") or MISSING
    return _pick(f, min(span, 4))


def evt_typ_009(st, f):
    if st.flashback_rate > 0.012 or (st.past_rate > st.present_rate and st.flashback_rate > 0.004):
        return _find(f, "mostly_past_or_recollected_events") or MISSING
    if st.present_rate > st.past_rate * 1.2:
        return _find(f, "mostly_present_progression") or MISSING
    return _find(f, "balanced_present_and_past") or MISSING


def evt_cau_001(st, f):
    c = st.causal_rate
    if c > 0.018:
        return _find(f, "predominantly_explicit_causation") or MISSING
    if c > 0.007:
        return _find(f, "mixed_explicit_and_implicit") or MISSING
    return _find(f, "predominantly_implicit_or_inferred") or MISSING


def evt_cau_002(st, f):
    return _bucketed(f, st.causal_rate * 250, [1.5, 3.0, 5.0, 8.0])


def evt_cau_003(st, f):
    cons = len(re.findall(r"\b(?:but|however|yet) (?:it|he|she|they|this) (?:had|would|didn't|hadn't)\b", st.lower)) / max(1, st.n_sentences)
    return _find(f, "prominent_unintended_consequences") if cons > 0.02 else _find(f, "no_salient_unintended_consequences") or MISSING


def evt_cau_004(st, f):
    fate = st.conflicts.get("person_vs_fate_or_time", 0)
    if fate > 0.006:
        return _find(f, "strongly_fated_or_inevitable") or MISSING
    if st.mystery_rate > 0.01 or st.loop_rate > 0.002:
        return _find(f, "highly_contingent_or_random_feeling") or MISSING
    return _find(f, "mixed_fate_and_contingency") or MISSING


def evt_cau_008(st, f):
    if st.causal_rate > 0.012:
        return _find(f, "strict_cause_effect") or MISSING
    if st.flashback_rate > 0.01:
        return _find(f, "nonlinear_fragmented") or MISSING
    return _find(f, "chronological_sequence") or MISSING


def evt_cau_016(st, f):
    span = _time_span_level(st)
    idx = min(span, 4)
    return _pick(f, idx)


def evt_cau_017(st, f):
    nov = st.twist_rate * 60 + st.suspense_rate * 30 + st.genre.get("science_fiction", 0) * 40 + st.loop_rate * 40
    if nov < 2.0:
        return MISSING  # no novelty signals to judge
    return _bucketed(f, nov, [3.0, 6.0, 10.0, 15.0])


def evt_cau_018(st, f):
    return _find(f, "yes") if st.repetition_rate > 0.05 or st.loop_rate > 0.002 else _find(f, "no") or MISSING


def evt_sch_002(st, f):
    ending = st.ending.lower()
    if any(w in ending for w in ("finally", "resolved", "at last", "in the end", "peace", "home")):
        return _find(f, "full_arc_to_local_resolution") or MISSING
    if any(w in ending for w in ("unknown", "never", "unanswered", "didn't", "open")):
        return _find(f, "partial_arc_with_cliffhanger") or MISSING
    return _find(f, "full_arc_to_local_resolution") or MISSING


def evt_sch_003(st, f):
    rise = st.third_events[2] - st.third_events[0] if len(st.third_events) == 3 else 0.0
    return _bucketed(f, rise * 200 + st.event_rate * 20, [1.5, 3.0, 5.0, 8.0])


def evt_sch_004(st, f):
    ending = st.ending.lower()
    if any(w in ending for w in ("accept", "understood", "realized", "accepted", "peace")):
        return _find(f, "resolved_through_internal_understanding") or MISSING
    if any(w in ending for w in ("fled", "escaped", "killed", "won", "defeated", "fought", "destroyed")):
        return _find(f, "resolved_through_external_action") or MISSING
    if any(w in ending for w in ("unknown", "unresolved", "never", "open", "uncertain")):
        return _find(f, "open_or_ambiguously_unresolved") or MISSING
    return _find(f, "partial_or_compromise_resolution") or MISSING


def evt_sch_006(st, f):
    frame = any(w in st.lower for w in ("i remember", "looking back", "years later", "back then", "this story", "let me tell"))
    return _find(f, "has_explicit_frame_story") if frame else _find(f, "no_frame_or_minimal_metacommentary") or MISSING


def evt_sch_010(st, f):
    mapping = {
        "quest/journey": ["quest", "journey", "travel", "adventure", "set out"],
        "investigation/mystery": ["mystery", "investigate", "investigation", "detective", "clue", "case"],
        "transformation/redemption": ["transform", "transformed", "redemption", "changed", "become", "growth", "evolve"],
        "siege/ordeal": ["siege", "ordeal"],
        "slice_of_life": ["routine", "everyday", "ordinary", "mundane", "daily"],
        "trial/test/game": ["trial", "test", "game", "contest", "challenge", "prove"],
        "heist/caper": ["heist", "caper"],
        "frame_confession/memoir": ["memoir", "confession", "confess", "recount"],
    }
    return _multi(st, f, mapping)


def evt_sch_011(st, f):
    ending = st.ending.lower()
    if any(w in ending for w in ("finally", "resolved", "in the end", "at last", "peace", "home", "won")):
        return _find(f, "full_arc_with_resolution") or MISSING
    if any(w in ending for w in ("unknown", "never", "unanswered", "unresolved")):
        return _find(f, "partial_arc") or MISSING
    return _find(f, "full_arc_with_resolution") or MISSING


def evt_sch_013(st, f):
    if st.n_sentences < 9:
        return _find(f, "flat_low_tension") or MISSING
    e = st.third_events
    if e[2] > e[0] + 0.02:
        return _find(f, "rising_tension_to_climax") or MISSING
    if max(e) - min(e) < 0.01:
        return _find(f, "flat_low_tension") or MISSING
    if e[0] > e[1] and e[1] < e[2]:
        return _find(f, "episodic_peaks") or MISSING
    return _find(f, "episodic_peaks") or MISSING


def evt_sch_014(st, f):
    if st.n_sentences < 6:
        return _find(f, "no") or MISSING
    peak = max(st.third_events)
    rest = (sum(st.third_events) - peak) / 2
    return _find(f, "yes") if peak > rest * 1.6 and peak > 0.02 else _find(f, "no") or MISSING


def _time_span_level(st: Stats) -> int:
    """0=hours, 1=days, 2=months, 3=years, 4=decades+"""
    lower = st.lower
    if re.search(r"\b(?:decades|generations|centuries)\b", lower) or re.search(r"\b(?:years|decades) (?:later|passed)\b", lower) and re.search(r"\b(?:years|decades)\b", lower):
        pass
    if re.search(r"\b(?:decades|generations|centuries)\b", lower):
        return 4
    if re.search(r"\b(?:year|years)\b", lower):
        return 3
    if re.search(r"\b(?:week|weeks|month|months)\b", lower):
        return 2
    if re.search(r"\b(?:day|days)\b", lower):
        return 1
    return 0


# --- situatedness ----------------------------------------------------------

def sit_gen_001(st, f):
    scores = dict(st.genre)
    scores["realist_contemporary"] += 0.002
    best_key, best_v = max(scores.items(), key=lambda kv: kv[1])
    if best_v < 0.004:
        return _find(f, "realist_contemporary") or MISSING
    return _find(f, best_key) or MISSING


def sit_gen_003(st, f):
    if st.n_chars < 200:
        return MISSING
    # position of first genre keyword
    first_pos = st.n_chars
    for key, words in GENRE_LISTS.items():
        for w in words:
            p = st.lower.find(" " + w + " ")
            if p != -1 and p < first_pos:
                first_pos = p
    if first_pos == st.n_chars:
        return _find(f, "late/ambiguous") or MISSING
    rel = first_pos / st.n_chars
    if rel < 0.05:
        return _find(f, "immediate (within opening paragraph)") or MISSING
    if rel < 0.2:
        return _find(f, "early (within the first scene/page)") or MISSING
    if rel < 0.6:
        return _find(f, "mid-story (after some neutral buildup)") or MISSING
    return _find(f, "late/ambiguous (genre only clear near the end or never fully fixed)") or MISSING


def sit_gen_006(st, f):
    plotness = st.event_rate * 40 + st.causal_rate * 30
    atm = sum(st.sensory.values()) * 40 + st.weather_rate * 20
    return _bucketed(f, atm / max(plotness, 0.5), [0.12, 0.22, 0.35, 0.55])


def sit_gen_010(st, f):
    return _bucketed(f, st.moral_rate * 240, [1.5, 3.0, 5.5, 9.0])


def sit_met_002(st, f):
    direct = st.you_rate * 100 > 0.8 or st.reader_rate > 0.001
    return _find(f, "yes, direct address present") if direct else _find(f, "no direct address") or MISSING


def sit_met_004(st, f):
    d = st.you_rate * 100 + st.reader_rate * 100
    return _bucketed(f, d, [1.0, 3.0, 6.0])


def sit_met_006(st, f):
    docs = st.doc_rate * 100
    if docs > 1.5:
        return _find(f, "3-Extensive") or _pick(f, 3)
    if docs > 0.5:
        return _pick(f, 2)
    if docs > 0.1:
        return _pick(f, 1)
    return _pick(f, 0)


def sit_met_103(st, f):
    docs = st.doc_rate * 100
    if docs > 1.5:
        return _find(f, "multiple_embedded") or MISSING
    if docs > 0.3:
        return _find(f, "single_embedded") or MISSING
    return _find(f, "none") or MISSING


def sit_met_104(st, f):
    if st.reader_rate > 0.002:
        return _find(f, "direct_address_to_actual_reader") or MISSING
    if st.you_rate > 0.004:
        return _find(f, "generic_second_person_as_generalization") or MISSING
    return _find(f, "no_direct_address") or MISSING


def sit_met_102(st, f):
    ending = st.ending.lower()
    meta = any(w in ending for w in ("story", "tale", "narrator", "ending", "chapter", "told"))
    return _find(f, "yes") if meta else _find(f, "no") or MISSING


def sit_met_501(st, f):
    return _find(f, "yes") if st.moral_rate > 0.012 else _find(f, "no") or MISSING


def sit_met_303(st, f):
    return _bucketed(f, st.moral_rate * 240 + st.themes["justice"] * 150, [1.5, 3.0, 5.5, 9.0])


def sit_met_301(st, f):
    ambition = st.mean_word_len * 3 + st.std_sent_len + st.latinate_rate * 20 + st.thought_rate * 30
    return _bucketed(f, ambition, [8.0, 10.0, 12.5, 15.0])


def sit_met_302(st, f):
    frag = st.fragment_ratio + st.flashback_rate * 5
    if frag > 0.45:
        return _find(f, "strongly_fragmented") or MISSING
    if frag > 0.2:
        return _find(f, "framed_or_mildly_non_linear") or MISSING
    return _find(f, "simple_linear_single_strand") or MISSING


def sit_met_402(st, f):
    return _bucketed(f, st.proper_rate * 100 + st.allusion_rate if hasattr(st, "allusion_rate") else st.proper_rate * 100, [2.0, 6.0])


def sit_met_403(st, f):
    return _bucketed(f, st.long_word_rate * 40 + st.tech_rate * 20, [0.8, 2.0, 4.5])


# --- setting ---------------------------------------------------------------

def set_loc_005(st, f):
    p = st.places
    if p.get("natural_outdoor", 0) > p.get("domestic_private", 0) * 1.5 and p["natural_outdoor"] > 0.01:
        return _find(f, "planetary_or_cosmic") if p.get("natural_outdoor", 0) > 0.02 else _find(f, "urban_or_regional") or MISSING
    if p.get("domestic_private", 0) > p.get("public_social", 0) and p["domestic_private"] > 0.008:
        return _find(f, "household_or_local_block") or MISSING
    if p.get("public_social", 0) > p.get("domestic_private", 0):
        return _find(f, "urban_or_regional") or MISSING
    if p.get("virtual_digital", 0) > 0.006:
        return _find(f, "planetary_or_cosmic") or MISSING
    return _find(f, "multi_scale_mixed") or MISSING


def set_loc_008(st, f):
    mapping = {k: list(v) for k, v in PLACE_LISTS.items()}
    return _multi(st, f, mapping)


def set_loc_015(st, f):
    mapping = {
        "domestic_private": list(PLACE_LISTS["domestic_private"]),
        "public_urban_or_commercial": ["street", "city", "town", "market", "cafe", "shop", "store", "square", "station", "bar", "restaurant"],
        "rural_or_wild_natural": list(PLACE_LISTS["natural_outdoor"]),
        "formal_institutional": list(PLACE_LISTS["institutional"]),
        "liminal_edges_and_transit": ["road", "train", "airport", "border", "doorway", "threshold", "bridge", "highway", "platform"],
    }
    return _multi(st, f, mapping)


def set_loc_012(st, f):
    indoor = st.places.get("domestic_private", 0) + st.places.get("institutional", 0)
    outdoor = st.places.get("natural_outdoor", 0)
    if indoor > outdoor * 2 and indoor > 0.01:
        return _find(f, "mostly_indoor_built") or MISSING
    if outdoor > indoor * 2 and outdoor > 0.01:
        return _find(f, "mostly_outdoor_natural") or MISSING
    return _find(f, "mixed_built_and_natural") or MISSING


def set_loc_002(st, f):
    return _bucketed(f, sum(st.places.values()) * 100, [1.2, 3.0, 6.0])


def set_loc_011(st, f):
    n = sum(1 for k in PLACE_KEYS if st.places[k] > 0.004)
    if n >= 4:
        return _pick(f, 4)
    if n == 3:
        return _pick(f, 2)
    if n == 2:
        return _pick(f, 1)
    return _pick(f, 0)


def set_loc_007(st, f):
    travel = len(re.findall(r"\b(?:travel|journey|went to|headed to|moved to|fled to|came to|arrived in)\b", st.lower)) / max(1, st.n_sentences)
    n = sum(1 for k in PLACE_KEYS if st.places[k] > 0.004)
    if travel > 0.05 or n >= 4:
        return _find(f, "travel_between_distant_regions") or MISSING
    if n >= 2:
        return _find(f, "multiple_locations_within_one_area") or MISSING
    return _find(f, "single_primary_location") or MISSING


def set_loc_004(st, f):
    opening = st.opening.lower()
    place_hits = sum(1 for k, v in PLACE_LISTS.items() for w in v if w in opening)
    if place_hits >= 3:
        return _find(f, "clear_local_setting_but_limited_global_context") or MISSING
    if place_hits >= 1:
        return _find(f, "minimal_local_details_only") or MISSING
    return _find(f, "none_or_very_vague") or MISSING


def set_loc_013(st, f):
    spec = st.genre.get("fantasy", 0) + st.genre.get("science_fiction", 0) + st.tech_rate
    return _bucketed(f, spec * 60, [1.5, 3.0, 5.5, 9.0])


def set_loc_014(st, f):
    return _bucketed(f, st.places.get("natural_outdoor", 0) * 80 + st.weather_rate * 40, [1.5, 3.5, 6.0, 10.0])


def set_loc_017(st, f):
    return _find(f, "yes") if st.places.get("virtual_digital", 0) > 0.005 else _find(f, "no") or MISSING


def set_tim_015(st, f):
    lower = st.lower
    if re.search(r"\b(?:19\d\d|18\d\d|medieval|ancient|century)\b", lower):
        return _find(f, "explicit_historical_past") or MISSING
    if st.genre.get("science_fiction", 0) > 0.008:
        return _find(f, "near_future_speculative") or MISSING
    if re.search(r"\b(?:phone|car|email|internet|smartphone)\b", lower):
        return _find(f, "contemporary_realistic") or MISSING
    return _find(f, "timeless_or_mythic") or MISSING


def set_tim_002(st, f):
    d = st.date_count / max(1, st.n_sentences) * 10 + st.clock_count * 3 + st.time_of_day_rate * 20
    return _bucketed(f, d, [0.8, 2.0, 6.0])


def set_tim_016(st, f):
    return _bucketed(f, st.time_marker_rate * 60 + st.flashback_rate * 80, [2.0, 4.0, 7.0, 11.0])


def set_atm_005(st, f):
    return _bucketed(f, sum(st.sensory.values()) * 80, [1.2, 2.6, 5.0, 9.0])


def set_atm_017(st, f):
    mapping = {k: list(v) for k, v in SENSORY_LISTS.items()}
    return _multi(st, f, mapping)


def set_atm_020(st, f):
    mapping = {
        "weather_and_light": list(WEATHER_WORDS) + ["light", "dark"],
        "architecture_and_objects": ["room", "building", "wall", "house", "stone", "window", "door", "floor"],
        "nature_and_landscape": list(PLACE_LISTS["natural_outdoor"]),
        "crowds_and_noise": ["crowd", "crowds", "noise", "voices", "people", "street"],
        "decay_and_dirt": list(DECAY_WORDS),
        "technology_and_media": list(TECH_WORDS) + ["screen", "media"],
    }
    return _multi(st, f, mapping)


def set_atm_004(st, f):
    mood = {
        "cozy_safe": st.places.get("domestic_private", 0) + st.emotion_label_rate * 0.3,
        "bleak_or_oppressive": st.genre.get("horror", 0) * 0.5 + st.decay_rate,
        "uncanny_or_haunted": st.genre.get("horror", 0) + st.suspense_rate * 0.5,
        "noir_or_gritty": st.genre.get("mystery_detective", 0) * 0.5 + st.violence_rate,
        "sublime_or_awe_inspiring": st.places.get("natural_outdoor", 0) * 0.8,
        "neutral_or_matter_of_fact": 0.002,
    }
    picked = [k for k, v in mood.items() if v > 0.003]
    if not picked:
        return [_find(f, "neutral_or_matter_of_fact")] if _find(f, "neutral_or_matter_of_fact") else MISSING
    return [_find(f, k) for k in picked if _find(f, k)]


def set_atm_013(st, f):
    neg = st.violence_rate * 2 + st.abuse_rate * 2 + st.conflicts.get("person_vs_person", 0) * 2 + st.suspense_rate * 0.5
    mood = {
        "cozy_or_idyllic": st.places.get("domestic_private", 0) * 0.6 + st.emotion_label_rate * 0.2 - neg * 3,
        "bleak_or_desolate": st.decay_rate + st.genre.get("horror", 0) * 0.4 + neg * 0.5,
        "uncanny_or_haunted": st.genre.get("horror", 0) + st.suspense_rate * 0.5,
        "wondrous_or_sublime": st.places.get("natural_outdoor", 0) * 0.8 + st.genre.get("fantasy", 0),
        "satirical_or_grotesque": st.humor_rate + st.irony_rate,
        "mundane_realist": 0.002,
    }
    return _dom(f, mood, fallback="mundane_realist")


# --- agents ----------------------------------------------------------------

def agent_id_001(st, f):
    n = st.unique_proper
    if n >= 7:
        return _find(f, "7+") or "7+"
    if n >= 4:
        return _find(f, "4-6") or "4-6"
    if n >= 2:
        return _find(f, "2-3") or "2-3"
    return _find(f, "1") or "1"


def agent_id_002(st, f):
    n = st.unique_proper
    if n >= 8:
        return _find(f, "many") or MISSING
    if n >= 4:
        return _find(f, "moderate") or MISSING
    if n >= 2:
        return _find(f, "few") or MISSING
    return _find(f, "none or almost none") or _find(f, "none_or_almost_none") or MISSING


def agent_id_003(st, f):
    named = st.proper_rate
    if named > 0.05:
        return _find(f, "almost all recurring") or MISSING
    if named > 0.02:
        return _find(f, "only major characters") or MISSING
    if named > 0.008:
        return _find(f, "mix of proper names") or MISSING
    return _find(f, "few or no characters") or MISSING


def agent_id_004(st, f):
    mapping = {
        "anthropomorphized animals": ["animal", "animals", "dog", "cat", "wolf", "bear", "bird", "horse"],
        "sentient supernatural": ["spirit", "god", "ghost", "demon", "curse", "angel", "spirits", "gods"],
        "AI or digital systems": ["ai", "robot", "computer", "machine", "digital", "system", "android"],
        "institutions/personified": ["institution", "corporation", "church", "company", "government", "organization"],
        "collective human groups": ["villagers", "crowd", "mob", "townspeople", "the people", "citizens"],
    }
    return _multi(st, f, mapping)


def agent_id_005(st, f):
    if st.first_rate > 0.55:
        return _find(f, "unnamed but specific") or MISSING
    if st.unique_proper >= 1 and st.proper_rate > 0.01:
        return _find(f, "named personal name") or MISSING
    if st.proper_rate <= 0.01:
        return _find(f, "role/descriptor") or MISSING
    return _find(f, "multiple or shifting") or MISSING


def agent_id_022(st, f):
    return _find(f, "yes") if st.nonhuman_rel_rate > 0.006 else _find(f, "no") or MISSING


def agent_id_023(st, f):
    if st.collective_rate > 0.02:
        return _find(f, "foregrounded as major agents") or MISSING
    if st.collective_rate > 0.008:
        return _find(f, "present but background") or MISSING
    return _find(f, "absent or negligible") or MISSING


def agent_id_024(st, f):
    if st.third_rate > 0.5 and st.thought_rate < 0.01:
        return _find(f, "zero") or MISSING
    if st.first_rate > 0.5:
        return _find(f, "one POV character") or MISSING
    if st.thought_rate > 0.03:
        return _find(f, "two POV characters") or MISSING
    return _find(f, "one POV character") or MISSING


def agent_attr_002(st, f):
    app = len(re.findall(r"\b(?:hair|eyes|face|tall|short|wore|dressed|beard|glasses|skin|looked like)\b", st.lower)) / max(1, st.n_sentences)
    return _bucketed(f, app, [0.15, 0.6])


def agent_attr_003(st, f):
    mapping = {
        "family roles": ["mother", "father", "mom", "dad", "sister", "brother", "son", "daughter", "aunt", "uncle"],
        "occupation or specific skill": ["detective", "doctor", "teacher", "soldier", "scientist", "lawyer", "engineer", "pilot", "chef", "writer", "nurse"],
        "class, wealth, ethnicity": ["rich", "poor", "wealthy", "noble", "immigrant", "lord", "servant"],
        "psychological label": ["autistic", "depressive", "anxious", "sensitive", "diagnosed", "depression"],
        "mythic or archetypal title": ["chosen", "prophet", "hero", "paladin", "trickster", "savior"],
        "legal or institutional status": ["suspect", "prisoner", "veteran", "agent", "officer", "inmate"],
    }
    return _multi(st, f, mapping)


def agent_attr_004(st, f):
    traits = len(re.findall(r"\b(?:brave|cowardly|kind|cruel|selfish|generous|honest|clever|foolish|loyal|stubborn|wise)\b", st.lower)) / max(1, st.n_sentences)
    return _find(f, "yes") if traits > 0.01 else _find(f, "no") or MISSING


def agent_attr_005(st, f):
    if st.first_rate > 0.5:
        return _find(f, "first-person direct reporting") or MISSING
    if st.thought_rate > 0.03:
        return _find(f, "free indirect discourse") or MISSING
    if st.thought_rate > 0.012:
        return _find(f, "summary thought-report") or MISSING
    return _find(f, "no direct access") or MISSING


def agent_attr_010(st, f):
    if st.first_rate > 0.5:
        return _find(f, "first-person narration") or MISSING
    if st.thought_rate > 0.025:
        return _find(f, "reported thought summaries") or MISSING
    if st.thought_rate > 0.01:
        return _find(f, "close or free indirect third-person") or MISSING
    return _find(f, "no direct interiority") or MISSING


def agent_emo_001(st, f):
    return _bucketed(f, st.emotion_label_rate * 160, [1.5, 4.0])


def agent_emo_002(st, f):
    mapping = {
        "explicit emotion words": list(EMOTION_LABELS),
        "bodily sensations or physiology": list(EMOTION_BODILY),
        "metaphorical or environmental imagery": ["weather", "storm", "rain", "dark", "light", "mirror", "wind", "shadow"],
        "actions and choices": list(EMOTION_ACTION),
        "dialogue content or tone": list(DIALOGUE_VERBS),
    }
    return _multi(st, f, mapping)


def agent_emo_003(st, f):
    if st.n_sentences < 9:
        return _find(f, "largely single-tone") or MISSING
    e = st.third_emotion
    spread = max(e) - min(e)
    if spread > 0.02 and e[2] != e[0]:
        return _find(f, "multi-phase or conflicted") or MISSING
    if spread > 0.008:
        return _find(f, "some distinct shifts") or MISSING
    return _find(f, "largely single-tone") or MISSING


def agent_emo_004(st, f):
    refl = len(re.findall(r"\b(?:i felt|i realized|he felt|she felt|i was feeling|emotions|feelings)\b", st.lower)) / max(1, st.n_sentences)
    return _find(f, "yes") if refl > 0.01 else _find(f, "no") or MISSING


def agent_emo_009(st, f):
    scores = {
        "explicit_emotion_labels": st.emotion_label_rate,
        "embodied_sensations_and_metaphors": st.emotion_bodily_rate + st.sensory.get("tactile", 0) * 0.3,
        "behavioral_cues_and_action_only": st.emotion_action_rate + st.emotion_facial_rate * 0.5,
        "consistently_ambiguous_or_suppressed": 0.0,
    }
    return _dom(f, scores, fallback="behavioral_cues_and_action_only")


def agent_emo_012(st, f):
    mapping = {
        "bodily sensations or physiology": list(EMOTION_BODILY),
        "facial expressions or gestures": list(EMOTION_FACIAL),
        "action choices and behavior": list(EMOTION_ACTION),
        "metaphorical or environmental mirroring": ["weather", "storm", "rain", "dark", "light", "mirror", "wind", "shadow"],
        "dialogue content and tone": list(DIALOGUE_VERBS),
    }
    return _multi(st, f, mapping)


def agent_mot_011(st, f):
    mot = len(re.findall(r"\b(?:wanted|needed|hoped|wished|because he|because she|decided to)\b", st.lower)) / max(1, st.n_sentences)
    return _bucketed(f, mot, [0.015, 0.04])


def agent_mot_003(st, f):
    mapping = {
        "desire": list(MOTIVE_LISTS["desire"]),
        "ethical": list(MOTIVE_LISTS["ethical"]),
        "familial": list(MOTIVE_LISTS["family"]),
        "trauma": list(MOTIVE_LISTS["trauma"]),
        "survival": list(MOTIVE_LISTS["survival"]),
        "supernatural": list(MOTIVE_LISTS["supernatural"]),
    }
    return _multi(st, f, mapping)


def agent_mot_012(st, f):
    mapping = {k: list(v) for k, v in MOTIVE_DOMAINS.items()}
    return _multi(st, f, mapping)


def agent_mot_004(st, f):
    if st.n_sentences < 10:
        return _find(f, "no") or MISSING
    early = st.lower[: max(1, st.n_chars // 4)]
    late = st.lower[-max(1, st.n_chars // 4):]
    m = re.findall(r"\b(?:wanted|needed|hoped|dreamed|longed|wished)\b", early), re.findall(r"\b(?:wanted|needed|hoped|dreamed|longed|wished)\b", late)
    return _find(f, "yes") if m[0] and m[1] else _find(f, "no") or MISSING


def agent_mot_014(st, f):
    conflict = len(re.findall(r"\b(?:but|yet|torn|conflicted|struggled|between)\b", st.lower)) / max(1, st.n_sentences)
    n = sum(1 for k in MOTIVE_KEYS if st.motives[k] > 0.002)
    if conflict > 0.06 and n >= 2:
        return _find(f, "conflicted or ambivalent") or MISSING
    if n >= 2:
        return _find(f, "multiple but largely compatible") or MISSING
    return _find(f, "single, relatively stable goal") or MISSING


def agent_mot_016(st, f):
    change = len(re.findall(r"\b(?:changed|became|learned|realized|transformed|grew)\b", st.lower)) / max(1, st.n_sentences)
    if change < 0.008:
        return _find(f, "no substantial change") or MISSING
    scores = {
        "moral or ethical shift": st.moral_rate,
        "psychological self-understanding": st.thought_rate + st.emotion_label_rate * 0.3,
        "relational role shift": st.relations.get("familial_kinship", 0) * 0.5,
        "status or power change": st.authority_rate * 0.5,
        "ontological or metaphysical transformation": st.genre.get("fantasy", 0) * 0.5 + st.nonhuman_rel_rate,
    }
    best_k, best_v = max(scores.items(), key=lambda kv: kv[1])
    if best_v < 0.004:
        return _find(f, "no substantial change") or MISSING
    return _find(f, best_k) or MISSING


def agent_role_003(st, f):
    active = st.event_rate
    passive_words = len(re.findall(r"\b(?:watched|observed|noticed|felt|waited|listened)\b", st.lower)) / max(1, st.n_sentences)
    if active > passive_words * 2.5 and active > 0.03:
        return _find(f, "mostly active") or MISSING
    if passive_words > active * 2:
        return _find(f, "mostly passive") or MISSING
    return _find(f, "mixed") or MISSING


def agent_role_004(st, f):
    return _find(f, "yes") if st.collective_rate > 0.015 else _find(f, "no") or MISSING


def agent_role_005(st, f):
    social = st.dialogue_verb_rate * 40 + st.relations["friendship"] * 60 + st.unique_proper
    return _bucketed(f, social, [3.0, 7.0])


def agent_role_015(st, f):
    n = st.unique_proper
    if n >= 4 and st.third_rate > 0.5:
        return _find(f, "ensemble_multiple_equally_central") or MISSING
    if n >= 2:
        return _find(f, "dual_protagonists_or_pair") or MISSING
    return _find(f, "single_central_protagonist") or MISSING


def agent_role_018(st, f):
    rel = sum(st.relations.values())
    n = st.unique_proper
    if n >= 6 and rel > 0.01:
        return _find(f, "dense_network") or MISSING
    if n >= 3:
        return _find(f, "moderate_web") or MISSING
    return _find(f, "very_simple_few_relationships") or MISSING


def agent_role_019(st, f):
    if st.collective_rate > 0.02 or st.nonhuman_rel_rate > 0.02:
        return _find(f, "non-human or system-level forces dominate") or MISSING
    if st.unique_proper >= 3 and st.third_rate > 0.4:
        return _find(f, "shared among multiple human characters") or MISSING
    return _find(f, "single human protagonist") or MISSING


def agent_role_020(st, f):
    init = len(re.findall(r"\b(?:decided|chose|began to|started to|set out|determined)\b", st.lower)) / max(1, st.n_sentences)
    react = len(re.findall(r"\b(?:had to|forced to|had no choice|watched as|waited for)\b", st.lower)) / max(1, st.n_sentences)
    if init > react * 2 and init > 0.02:
        return _find(f, "mostly initiates") or MISSING
    if react > init * 2:
        return _find(f, "mostly reactive") or MISSING
    return _find(f, "mixed balance") or MISSING


def agent_role_021(st, f):
    rel = sum(st.relations.values()) * 40 + st.dialogue_verb_rate * 30
    n = st.unique_proper
    if n >= 6 and rel > 1.0:
        return _find(f, "dense") or MISSING
    if n >= 3 or rel > 0.5:
        return _find(f, "moderate") or MISSING
    return _find(f, "minimal") or MISSING


def agent_trp_001(st, f):
    tropes = len(re.findall(r"\b(?:chosen one|archetype|trope|hero's journey|damsel|mentor figure)\b", st.lower))
    return _find(f, "yes") if tropes > 0 else _find(f, "no") or MISSING


# --- social networks -------------------------------------------------------

def soc_str_001(st, f):
    n = st.unique_proper
    if n >= 13:
        return _find(f, "ensemble") or MISSING
    if n >= 8:
        return _find(f, "large") or MISSING
    if n >= 5:
        return _find(f, "medium") or MISSING
    if n >= 3:
        return _find(f, "small") or MISSING
    return _find(f, "very_small") or MISSING


def soc_str_003(st, f):
    inst = st.places.get("institutional", 0)
    return _find(f, "yes") if inst > 0.008 else _find(f, "no") or MISSING


def soc_str_004(st, f):
    if st.collective_rate > 0.025:
        return _find(f, "collective protagonist") or _find(f, "active secondary agent") or MISSING
    if st.collective_rate > 0.01:
        return _find(f, "active secondary agent") or MISSING
    if st.collective_rate > 0.004:
        return _find(f, "background") or MISSING
    return _find(f, "none") or MISSING


def soc_str_016(st, f):
    if st.collective_rate > 0.025:
        return _find(f, "community_as_active_collective_actor") or MISSING
    if st.collective_rate > 0.008:
        return _find(f, "supporting_minor_roles") or MISSING
    if st.collective_rate > 0.003:
        return _find(f, "background_mentioned_only") or MISSING
    return _find(f, "none") or MISSING


def soc_str_005(st, f):
    return _find(f, "yes") if st.cross_boundary_rate > 0.005 else _find(f, "no") or MISSING


def soc_str_018(st, f):
    crowd_action = len(re.findall(r"\b(?:the crowd|crowds|the mob|the villagers)\s+(?:moved|surged|stormed|cheered|attacked|rose)\b", st.lower))
    return _find(f, "yes") if crowd_action > 0 else _find(f, "no") or MISSING


def soc_rel_005(st, f):
    hist = len(re.findall(r"\b(?:since childhood|years together|old friend|grew up together|long history|shared)\b", st.lower)) / max(1, st.n_sentences)
    return _bucketed(f, hist, [0.03, 0.12, 0.3])


def soc_rel_006(st, f):
    return _bucketed(f, st.nonhuman_rel_rate * 100, [0.5, 3.0])


def soc_rel_007(st, f):
    mapping = {k: list(v) for k, v in RELATION_LISTS.items()}
    return _multi(st, f, mapping)


def soc_rel_009(st, f):
    return _bucketed(f, st.nonhuman_rel_rate * 100, [0.5, 3.0])


def soc_rel_012(st, f):
    return _find(f, "salient_gossip_or_rumor_dynamics") if st.gossip_rate > 0.003 else _find(f, "minimal_or_no_gossip") or MISSING


def soc_rel_013(st, f):
    mapping = {
        "face_to_face_dialogue": list(DIALOGUE_VERBS),
        "letters_notes_or_diaries": ["letter", "diary", "note", "log", "journal", "email"],
        "digital_or_broadcast_media": ["phone", "email", "screen", "text", "online", "message", "call"],
        "ritual_or_ceremonial_actions": list(RITUAL_WORDS),
        "telepathic_or_supernatural_contact": ["telepathy", "telepathic", "mind", "psychic", "dream"],
        "indirect_via_objects_spaces_or_environment": ["gift", "object", "left", "note", "room"],
    }
    return _multi(st, f, mapping)


def soc_rel_016(st, f):
    kin = st.relations.get("familial_kinship", 0) + st.relations.get("professional", 0)
    if kin > 0.015:
        return _find(f, "mostly_labeled_by_role_or_kin_term") or MISSING
    if kin > 0.006:
        return _find(f, "mixed_labeled_and_inferred") or MISSING
    return _find(f, "mostly_inferred_from_behavior") or MISSING


def soc_rel_018(st, f):
    if st.authority_rate > 0.02 or st.cross_boundary_rate > 0.008:
        return _find(f, "strongly_asymmetric") or MISSING
    if st.authority_rate > 0.008:
        return _find(f, "moderately_asymmetric") or MISSING
    return _find(f, "largely_peer_like") or MISSING


def soc_rel_022(st, f):
    if st.quote_ratio > 0.2:
        return _find(f, "direct_spoken_dialogue") or MISSING
    if st.doc_rate > 0.01:
        return _find(f, "written_or_recorded_media") or MISSING
    if st.thought_rate > 0.03:
        return _find(f, "internal_monologue_or_fantasy") or MISSING
    return _find(f, "shared_actions_and_routines") or MISSING


def soc_rel_023(st, f):
    return _find(f, "yes") if st.ritual_rate > 0.004 else _find(f, "no") or MISSING


def soc_dyn_007(st, f):
    if st.authority_rate > 0.02:
        return _find(f, "formalized_and_explicit_hierarchies") or MISSING
    if st.authority_rate > 0.008:
        return _find(f, "informal_or_implied_hierarchies") or MISSING
    return _find(f, "minimal_or_flat_relations") or MISSING


def soc_dyn_010(st, f):
    if st.authority_rate > 0.02:
        return _find(f, "vertical_hierarchy") or MISSING
    if st.collective_rate > 0.02:
        return _find(f, "diffuse_systemic_power") or MISSING
    return _find(f, "egalitarian_peers") or MISSING


def soc_dyn_012(st, f):
    return _find(f, "yes") if st.abuse_rate > 0.004 else _find(f, "no") or MISSING


def soc_dyn_019(st, f):
    if st.violence_rate > 0.012:
        return _find(f, "open_confrontation") or MISSING
    if st.abuse_rate > 0.006:
        return _find(f, "covert_manipulation_or_abuse") or MISSING
    if st.gossip_rate > 0.003:
        return _find(f, "avoidance_or_silence") or MISSING
    if st.authority_rate > 0.015:
        return _find(f, "structural_or_institutional_conflict") or MISSING
    return _find(f, "avoidance_or_silence") or MISSING


def soc_dyn_020(st, f):
    return _find(f, "yes") if st.violence_rate > 0.008 else _find(f, "no") or MISSING


def soc_dyn_021(st, f):
    if st.forgive_rate > 0.006:
        return _find(f, "yes_substantial_reconciliation") or MISSING
    if st.forgive_rate > 0.002 or st.relations.get("familial_kinship", 0) > 0.01:
        return _find(f, "partial_or_ambiguous") or MISSING
    return _find(f, "no_reconciliation") or MISSING


def soc_com_017(st, f):
    if st.quote_ratio > 0.2:
        return _find(f, "face-to-face spoken dialogue") or MISSING
    if st.doc_rate > 0.01:
        return _find(f, "written or recorded media") or MISSING
    if st.ritual_rate > 0.005:
        return _find(f, "ritual/action/gesture") or MISSING
    if st.tech_rate > 0.01:
        return _find(f, "mediated/technological") or MISSING
    return _find(f, "internal/imagined") or MISSING


def soc_com_018(st, f):
    return _find(f, "yes") if st.collective_rate > 0.015 else _find(f, "no") or MISSING


# --- revelation ------------------------------------------------------------

def rev_sus_001(st, f):
    return _bucketed(f, st.suspense_rate * 80 + st.mystery_rate * 40, [2.0, 4.5, 8.0])


def rev_sus_002(st, f):
    if st.mystery_rate > 0.02 or st.suspense_rate > 0.02:
        return _find(f, "framed_as_overt_mystery_or_case") or MISSING
    if st.mystery_rate > 0.008:
        return _find(f, "explicit_gaps_with_vague_clues") or MISSING
    return _find(f, "no_major_withholding") or MISSING


def rev_sus_008(st, f):
    if st.mystery_rate > 0.025:
        return _find(f, "ongoing_central_mystery") or MISSING
    if st.mystery_rate > 0.008:
        return _find(f, "localized_puzzle_only") or MISSING
    return _find(f, "none") or MISSING


def rev_sus_009(st, f):
    ending = st.ending.lower()
    if st.mystery_rate < 0.006:
        return _find(f, "yes") or MISSING
    if any(w in ending for w in ("revealed", "discovered", "understood", "the truth", "figured out", "realized")):
        return _find(f, "yes") or MISSING
    return _find(f, "no") or MISSING


def rev_sur_007(st, f):
    if st.twist_rate < 0.004:
        return _find(f, "no_twist") or MISSING
    pos = st.lower.find("twist")
    if pos == -1:
        pos = st.lower.find("turned out")
    if pos == -1:
        return _find(f, "distributed_multiple_twists") or MISSING
    rel = pos / max(1, st.n_chars)
    if rel < 0.2:
        return _find(f, "early_twist") or MISSING
    if rel > 0.75:
        return _find(f, "climactic_end_twist") or MISSING
    if rel > 0.4:
        return _find(f, "mid_story_twist") or MISSING
    return _find(f, "distributed_multiple_twists") or MISSING


def rev_sur_010(st, f):
    red = len(re.findall(r"\b(?:red herring|false lead|mislead|dead end|wrong direction|turned out to be wrong)\b", st.lower))
    return _find(f, "yes") if red > 0 else _find(f, "no") or MISSING


def rev_dis_001(st, f):
    if st.n_chars < 400:
        return _find(f, "evenly_layered_throughout") or MISSING
    first = st.lower[: st.n_chars // 3]
    last = st.lower[-st.n_chars // 3:]
    early = len(re.findall(r"\b(?:revealed|explained|learned|discovered)\b", first))
    late = len(re.findall(r"\b(?:revealed|explained|learned|discovered|realized)\b", last))
    if late > early * 2 and late > 0:
        return _find(f, "back_loaded_key_revelations_near_end") or MISSING
    if early > late * 2:
        return _find(f, "front_loaded_exposition_early") or MISSING
    return _find(f, "evenly_layered_throughout") or MISSING


def rev_dis_003(st, f):
    return _bucketed(f, st.flashback_rate * 100, [1.0, 3.0, 6.0, 11.0])


def rev_dis_006(st, f):
    if st.mystery_rate > 0.02:
        return _find(f, "backward_mystery_what_really_happened") or MISSING
    if st.suspense_rate > 0.02:
        return _find(f, "forward_suspense_what_will_happen") or MISSING
    if st.irony_rate > 0.01 or st.you_rate > 0.005:
        return _find(f, "dramatic_irony_reader_knows_more") or MISSING
    return _find(f, "low_info_tension_character_or_atmosphere_driven") or MISSING


def rev_dis_014(st, f):
    ending = st.ending.lower()
    if any(w in ending for w in ("revealed", "answered", "understood", "the truth", "finally knew", "resolved", "clear")):
        return _find(f, "clear_and_explicit_answers") or MISSING
    if any(w in ending for w in ("unknown", "unanswered", "never", "open", "ambiguous", "uncertain")):
        return _find(f, "key_questions_left_open") or MISSING
    return _find(f, "partial_or_tentative_answers") or MISSING


def rev_dis_017(st, f):
    meta = len(re.findall(r"\b(?:this story|the story itself|narrative|a story about stories|tale about)\b", st.lower))
    return _find(f, "yes") if meta > 0 and st.meta_rate > 0.01 else _find(f, "no") or MISSING


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FEATURE_EXTRACTORS: Dict[str, Callable[[Stats, Feature], Any]] = {
    # style
    "STY_CPX_002": sty_cpx_002,
    "STY_CPX_010": sty_cpx_010,
    "STY_CPX_004": sty_cpx_004,
    "STY_CPX_005": sty_cpx_005,
    "STY_CPX_003": sty_cpx_003,
    "STY_CPX_011": sty_cpx_011,
    "STY_CPX_013": sty_cpx_013,
    "STY_CPX_012": sty_cpx_012,
    "STY_FIG_001": sty_fig_001,
    "STY_FIG_002": sty_fig_002,
    "STY_FIG_003": sty_fig_003,
    "STY_FIG_007": sty_fig_007,
    "STY_FIG_009": sty_fig_009,
    "STY_TON_001": sty_ton_001,
    "STY_TON_021": sty_ton_021,
    "STY_TON_002": sty_ton_002,
    "STY_TON_020": sty_ton_020,
    "STY_TON_005": sty_ton_005,
    "STY_TON_006": sty_ton_006,
    "STY_TON_024": sty_ton_024,
    "STY_TON_007": sty_ton_007,
    "STY_TON_023": sty_ton_023,
    "STY_TON_025": sty_ton_025,
    "STY_TON_027": sty_ton_027,
    "STY_TON_029": sty_ton_029,
    "STY_ALL_015": sty_all_015,
    "STY_ALL_016": sty_all_016,
    "STY_ALL_017": sty_all_017,
    "STY_ALL_018": sty_all_018,
    "STY_ALL_019": sty_all_019,
    # temporal
    "TMP_DUR_011": tmp_dur_011,
    "TMP_DUR_009": tmp_dur_009,
    "TMP_DUR_019": tmp_dur_019,
    "TMP_DUR_008": tmp_dur_008,
    "TMP_DUR_010": tmp_dur_010,
    "TMP_DUR_007": tmp_dur_007,
    "TMP_DUR_002": tmp_dur_002,
    "TMP_DUR_006": tmp_dur_006,
    "TMP_DUR_013": tmp_dur_013,
    "TMP_DUR_018": tmp_dur_018,
    "TMP_DUR_021": tmp_dur_021,
    "TMP_DUR_004": tmp_dur_004,
    "TMP_DUR_012": tmp_dur_012,
    "TMP_ORD_001": tmp_ord_001,
    "TMP_ORD_002": tmp_ord_002,
    "TMP_ORD_004": tmp_ord_004,
    "TMP_ORD_010": tmp_ord_010,
    "TMP_ORD_005": tmp_ord_005,
    "TMP_ORD_008": tmp_ord_008,
    "TMP_ORD_009": tmp_ord_009,
    "TMP_ORD_011": tmp_ord_011,
    "TMP_ORD_012": tmp_ord_012,
    "TMP_ORD_014": tmp_ord_014,
    # perspective
    "PER_POV_001": per_pov_001,
    "PER_POV_009": per_pov_009,
    "PER_POV_003": per_pov_003,
    "PER_POV_007": per_pov_007,
    "PER_FOC_001": per_foc_001,
    "PER_FOC_003": per_foc_003,
    "PER_FOC_005": per_foc_005,
    "PER_FOC_008": per_foc_008,
    "PER_FOC_009": per_foc_009,
    "PER_DIA_001": per_dia_001,
    "PER_DIA_002": per_dia_002,
    "PER_DIA_005": per_dia_005,
    "PER_DIA_006": per_dia_006,
    # plot
    "PLT_THM_004": plt_thm_004,
    "PLT_THM_001": plt_thm_001,
    "PLT_THM_003": plt_thm_003,
    "PLT_THM_005": plt_thm_005,
    "PLT_MOR_001": plt_mor_001,
    "PLT_MOR_003": plt_mor_003,
    "PLT_CON_001": plt_con_001,
    "PLT_CON_002": plt_con_002,
    "PLT_CON_003": plt_con_003,
    "PLT_STR_002": plt_str_002,
    "PLT_STR_003": plt_str_003,
    "PLT_STR_005": plt_str_005,
    "PLT_STR_006": plt_str_006,
    # events
    "EVT_TYP_001": evt_typ_001,
    "EVT_TYP_003": evt_typ_003,
    "EVT_TYP_004": evt_typ_004,
    "EVT_TYP_008": evt_typ_008,
    "EVT_TYP_009": evt_typ_009,
    "EVT_CAU_001": evt_cau_001,
    "EVT_CAU_002": evt_cau_002,
    "EVT_CAU_003": evt_cau_003,
    "EVT_CAU_004": evt_cau_004,
    "EVT_CAU_008": evt_cau_008,
    "EVT_CAU_016": evt_cau_016,
    "EVT_CAU_017": evt_cau_017,
    "EVT_CAU_018": evt_cau_018,
    "EVT_SCH_002": evt_sch_002,
    "EVT_SCH_003": evt_sch_003,
    "EVT_SCH_004": evt_sch_004,
    "EVT_SCH_006": evt_sch_006,
    "EVT_SCH_010": evt_sch_010,
    "EVT_SCH_011": evt_sch_011,
    "EVT_SCH_013": evt_sch_013,
    "EVT_SCH_014": evt_sch_014,
    # situatedness
    "SIT_GEN_001": sit_gen_001,
    "SIT_GEN_003": sit_gen_003,
    "SIT_GEN_006": sit_gen_006,
    "SIT_GEN_010": sit_gen_010,
    "SIT_MET_002": sit_met_002,
    "SIT_MET_004": sit_met_004,
    "SIT_MET_006": sit_met_006,
    "SIT_MET_103": sit_met_103,
    "SIT_MET_104": sit_met_104,
    "SIT_MET_102": sit_met_102,
    "SIT_MET_501": sit_met_501,
    "SIT_MET_303": sit_met_303,
    "SIT_MET_301": sit_met_301,
    "SIT_MET_302": sit_met_302,
    "SIT_MET_402": sit_met_402,
    "SIT_MET_403": sit_met_403,
    # setting
    "SET_LOC_005": set_loc_005,
    "SET_LOC_008": set_loc_008,
    "SET_LOC_015": set_loc_015,
    "SET_LOC_012": set_loc_012,
    "SET_LOC_002": set_loc_002,
    "SET_LOC_011": set_loc_011,
    "SET_LOC_007": set_loc_007,
    "SET_LOC_004": set_loc_004,
    "SET_LOC_013": set_loc_013,
    "SET_LOC_014": set_loc_014,
    "SET_LOC_017": set_loc_017,
    "SET_TIM_015": set_tim_015,
    "SET_TIM_002": set_tim_002,
    "SET_TIM_016": set_tim_016,
    "SET_ATM_005": set_atm_005,
    "SET_ATM_017": set_atm_017,
    "SET_ATM_020": set_atm_020,
    "SET_ATM_004": set_atm_004,
    "SET_ATM_013": set_atm_013,
    # agents
    "AGENT_ID_001": agent_id_001,
    "AGENT_ID_002": agent_id_002,
    "AGENT_ID_003": agent_id_003,
    "AGENT_ID_004": agent_id_004,
    "AGENT_ID_005": agent_id_005,
    "AGENT_ID_022": agent_id_022,
    "AGENT_ID_023": agent_id_023,
    "AGENT_ID_024": agent_id_024,
    "AGENT_ATTR_002": agent_attr_002,
    "AGENT_ATTR_003": agent_attr_003,
    "AGENT_ATTR_004": agent_attr_004,
    "AGENT_ATTR_005": agent_attr_005,
    "AGENT_ATTR_010": agent_attr_010,
    "AGENT_EMO_001": agent_emo_001,
    "AGENT_EMO_002": agent_emo_002,
    "AGENT_EMO_003": agent_emo_003,
    "AGENT_EMO_004": agent_emo_004,
    "AGENT_EMO_009": agent_emo_009,
    "AGENT_EMO_012": agent_emo_012,
    "AGENT_MOT_011": agent_mot_011,
    "AGENT_MOT_003": agent_mot_003,
    "AGENT_MOT_012": agent_mot_012,
    "AGENT_MOT_004": agent_mot_004,
    "AGENT_MOT_014": agent_mot_014,
    "AGENT_MOT_016": agent_mot_016,
    "AGENT_ROLE_003": agent_role_003,
    "AGENT_ROLE_004": agent_role_004,
    "AGENT_ROLE_005": agent_role_005,
    "AGENT_ROLE_015": agent_role_015,
    "AGENT_ROLE_018": agent_role_018,
    "AGENT_ROLE_019": agent_role_019,
    "AGENT_ROLE_020": agent_role_020,
    "AGENT_ROLE_021": agent_role_021,
    "AGENT_TRP_001": agent_trp_001,
    # social networks
    "SOC_STR_001": soc_str_001,
    "SOC_STR_003": soc_str_003,
    "SOC_STR_004": soc_str_004,
    "SOC_STR_016": soc_str_016,
    "SOC_STR_005": soc_str_005,
    "SOC_STR_018": soc_str_018,
    "SOC_REL_005": soc_rel_005,
    "SOC_REL_006": soc_rel_006,
    "SOC_REL_007": soc_rel_007,
    "SOC_REL_009": soc_rel_009,
    "SOC_REL_012": soc_rel_012,
    "SOC_REL_013": soc_rel_013,
    "SOC_REL_016": soc_rel_016,
    "SOC_REL_018": soc_rel_018,
    "SOC_REL_022": soc_rel_022,
    "SOC_REL_023": soc_rel_023,
    "SOC_DYN_007": soc_dyn_007,
    "SOC_DYN_010": soc_dyn_010,
    "SOC_DYN_012": soc_dyn_012,
    "SOC_DYN_019": soc_dyn_019,
    "SOC_DYN_020": soc_dyn_020,
    "SOC_DYN_021": soc_dyn_021,
    "SOC_COM_017": soc_com_017,
    "SOC_COM_018": soc_com_018,
    # revelation
    "REV_SUS_001": rev_sus_001,
    "REV_SUS_002": rev_sus_002,
    "REV_SUS_008": rev_sus_008,
    "REV_SUS_009": rev_sus_009,
    "REV_SUR_007": rev_sur_007,
    "REV_SUR_010": rev_sur_010,
    "REV_DIS_001": rev_dis_001,
    "REV_DIS_003": rev_dis_003,
    "REV_DIS_006": rev_dis_006,
    "REV_DIS_014": rev_dis_014,
    "REV_DIS_017": rev_dis_017,
}

COVERED_FEATURES = frozenset(FEATURE_EXTRACTORS)


def extract_heuristic_features(taxonomy: Taxonomy, story_text: str) -> Dict[str, Any]:
    """Extract narrative features with pure rule-based analysis (no API).

    Returns a normalized feature dict (feature id -> canonical value or list of
    values) in the same shape as `features.extract_story_features`. Features
    the rules cannot estimate are emitted as ``n/a``.
    """
    stats = Stats(story_text or "")
    out: Dict[str, Any] = {}
    for fid, fn in FEATURE_EXTRACTORS.items():
        try:
            feat = taxonomy.feature(fid)
        except KeyError:
            continue
        try:
            value = fn(stats, feat)
        except Exception:  # noqa: BLE001 - a bad heuristic must never break detection
            value = MISSING
        if value is None:
            value = MISSING
        elif isinstance(value, (list, tuple)):
            value = [v for v in value if v is not None]
            value = value if value else MISSING
        elif isinstance(value, bool):
            value = "yes" if value else "no"
        out[fid] = value
    return out
