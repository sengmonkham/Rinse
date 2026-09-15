"""
AI Text Humanizer - Uses StoryScope detection logic to help write text
that appears human-written rather than AI-generated.

Based on DNA-DetectLLM (Zhu et al., NeurIPS 2025) and StoryScope
304-feature narrative analysis.

Key principles:
1. Vary character entropy (use rarer characters)
2. Increase type-token ratio (diverse vocabulary)
3. Vary sentence lengths significantly
4. Reduce bigram/trigram repetition
5. Use less common words
6. Mix active and passive voice
7. Vary punctuation patterns
8. Add natural imperfections
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from typing import Any, Dict, List, Tuple



# ---------------------------------------------------------------------------
# Reference baselines from DNA-DetectLLM
# ---------------------------------------------------------------------------
AI_REF_CHAR_ENTROPY = 3.7
HUMAN_REF_CHAR_ENTROPY = 4.3
AI_REF_TTR = 0.45
HUMAN_REF_TTR = 0.60
AI_REF_SENT_CV = 0.30
HUMAN_REF_SENT_CV = 0.70
AI_REF_NGRAM_REPEAT = 0.20
HUMAN_REF_NGRAM_REPEAT = 0.08
AI_REF_VOCAB_CONCENTRATION = 0.35
HUMAN_REF_VOCAB_CONCENTRATION = 0.25


# ---------------------------------------------------------------------------
# Feature extraction functions (from DNA-DetectLLM)
# ---------------------------------------------------------------------------

def _char_entropy(text: str) -> float:
    """Shannon entropy of character distribution (bits per character)."""
    counts = Counter(text.lower())
    total = len(text)
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def _type_token_ratio(text: str) -> float:
    """Ratio of unique words to total words."""
    words = text.lower().split()
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def _sentence_length_cv(text: str) -> float:
    """Coefficient of variation of sentence lengths."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    if len(sentences) < 2:
        return 0.5
    lengths = [len(s.split()) for s in sentences]
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.0
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    return math.sqrt(variance) / mean


def _bigram_repetition_rate(text: str) -> float:
    """Fraction of bigrams that repeat."""
    words = text.lower().split()
    if len(words) < 2:
        return 0.0
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    counts = Counter(bigrams)
    repeats = sum(c - 1 for c in counts.values() if c > 1)
    return repeats / max(len(bigrams), 1)


def _trigram_repetition_rate(text: str) -> float:
    """Fraction of trigrams that repeat."""
    words = text.lower().split()
    if len(words) < 3:
        return 0.0
    trigrams = [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words) - 2)]
    counts = Counter(trigrams)
    repeats = sum(c - 1 for c in counts.values() if c > 1)
    return repeats / max(len(trigrams), 1)


def _vocab_concentration(text: str) -> float:
    """Fraction of text covered by the 100 most common words."""
    words = text.lower().split()
    if not words:
        return 0.0
    counts = Counter(words)
    top_100 = sum(c for _, c in counts.most_common(100))
    return top_100 / len(words)


def _avg_word_frequency(text: str) -> float:
    """Average log-frequency of words."""
    words = text.lower().split()
    if not words:
        return 0.0
    counts = Counter(words)
    freqs = [counts[w] for w in words]
    avg_freq = sum(freqs) / len(freqs)
    return math.log(avg_freq + 1)


def _punctuation_consistency(text: str) -> float:
    """Consistency of spacing around punctuation."""
    after_period = re.findall(r'\.\s', text)
    no_space_after_period = re.findall(r'\.[A-Z]', text)
    total_periods = len(after_period) + len(no_space_after_period)
    if total_periods == 0:
        return 0.5
    return len(after_period) / total_periods


def _passive_voice_ratio(text: str) -> float:
    """Approximate passive voice ratio."""
    passive_patterns = [
        r'\b(is|are|was|were|been|being)\s+(being\s+)?\w+ed\b',
        r'\b(has|have|had)\s+been\s+\w+ed\b',
        r'\b(is|are|was|were)\s+\w+ed\s+by\b',
    ]
    passive_count = 0
    for pattern in passive_patterns:
        passive_count += len(re.findall(pattern, text, re.IGNORECASE))
    sentences = len(re.split(r'[.!?]+', text)) - 1
    if sentences == 0:
        return 0.0
    return passive_count / sentences


def _exclamation_ratio(text: str) -> float:
    """Ratio of exclamation marks."""
    exclaims = text.count('!')
    sentences = len(re.split(r'[.!?]+', text)) - 1
    if sentences == 0:
        return 0.0
    return exclaims / sentences


# ---------------------------------------------------------------------------
# Analysis and scoring
# ---------------------------------------------------------------------------

def analyze_text(text: str) -> Dict[str, Any]:
    """
    Analyze text and return detailed scoring against AI detection signals.
    
    Returns:
        {
            "overall_score": float (0-100, higher = more human-like),
            "features": dict of individual feature scores,
            "ai_signals": list of detected AI patterns,
            "human_signals": list of detected human patterns,
            "recommendations": list of specific improvements
        }
    """
    features = {
        "char_entropy": _char_entropy(text),
        "ttr": _type_token_ratio(text),
        "sent_cv": _sentence_length_cv(text),
        "bigram_repeat": _bigram_repetition_rate(text),
        "trigram_repeat": _trigram_repetition_rate(text),
        "vocab_concentration": _vocab_concentration(text),
        "punct_consistency": _punctuation_consistency(text),
        "passive_ratio": _passive_voice_ratio(text),
        "exclamation_ratio": _exclamation_ratio(text),
    }
    
    # Compute human-like scores (1.0 = perfectly human-like)
    human_scores = {}
    
    # Character entropy: higher = more human-like
    entropy_diff = features["char_entropy"] - AI_REF_CHAR_ENTROPY
    human_range = HUMAN_REF_CHAR_ENTROPY - AI_REF_CHAR_ENTROPY
    human_scores["char_entropy"] = min(1.0, max(0.0, entropy_diff / human_range))
    
    # TTR: higher = more human-like
    ttr_diff = features["ttr"] - AI_REF_TTR
    human_range = HUMAN_REF_TTR - AI_REF_TTR
    human_scores["ttr"] = min(1.0, max(0.0, ttr_diff / human_range))
    
    # Sentence CV: higher = more human-like
    cv_diff = features["sent_cv"] - AI_REF_SENT_CV
    human_range = HUMAN_REF_SENT_CV - AI_REF_SENT_CV
    human_scores["sent_cv"] = min(1.0, max(0.0, cv_diff / human_range))
    
    # Bigram repetition: lower = more human-like
    repeat_diff = AI_REF_NGRAM_REPEAT - features["bigram_repeat"]
    human_range = AI_REF_NGRAM_REPEAT - HUMAN_REF_NGRAM_REPEAT
    human_scores["bigram_repeat"] = min(1.0, max(0.0, repeat_diff / human_range))
    
    # Vocab concentration: lower = more human-like
    vocab_diff = AI_REF_VOCAB_CONCENTRATION - features["vocab_concentration"]
    human_range = AI_REF_VOCAB_CONCENTRATION - HUMAN_REF_VOCAB_CONCENTRATION
    human_scores["vocab_concentration"] = min(1.0, max(0.0, vocab_diff / human_range))
    
    # Punctuation consistency: lower = more human-like (more varied)
    human_scores["punct_consistency"] = 1.0 - features["punct_consistency"]
    
    # Passive voice: lower = more human-like
    human_scores["passive_ratio"] = 1.0 - min(1.0, features["passive_ratio"] * 5.0)
    
    # Overall human-like score (weighted average)
    weights = {
        "char_entropy": 0.15,
        "ttr": 0.12,
        "sent_cv": 0.15,
        "bigram_repeat": 0.12,
        "vocab_concentration": 0.10,
        "punct_consistency": 0.10,
        "passive_ratio": 0.08,
    }
    
    total_weight = sum(weights.values())
    overall_score = sum(human_scores[k] * weights[k] for k in weights) / total_weight * 100
    
    # Detect AI signals
    ai_signals = []
    human_signals = []
    
    if features["char_entropy"] < 3.9:
        ai_signals.append(f"Low character entropy ({features['char_entropy']:.2f} bits/char)")
    elif features["char_entropy"] > 4.2:
        human_signals.append(f"High character entropy ({features['char_entropy']:.2f} bits/char)")
    
    if features["ttr"] < 0.50:
        ai_signals.append(f"Low vocabulary diversity (TTR: {features['ttr']:.2f})")
    elif features["ttr"] > 0.55:
        human_signals.append(f"High vocabulary diversity (TTR: {features['ttr']:.2f})")
    
    if features["sent_cv"] < 0.35:
        ai_signals.append(f"Uniform sentence lengths (CV: {features['sent_cv']:.2f})")
    elif features["sent_cv"] > 0.60:
        human_signals.append(f"Variable sentence lengths (CV: {features['sent_cv']:.2f})")
    
    if features["bigram_repeat"] > 0.15:
        ai_signals.append(f"High phrase repetition ({features['bigram_repeat']:.1%})")
    
    if features["vocab_concentration"] > 0.35:
        ai_signals.append(f"Overuse of common words ({features['vocab_concentration']:.1%})")
    
    if features["passive_ratio"] > 0.15:
        ai_signals.append(f"Excessive passive voice ({features['passive_ratio']:.1%})")
    
    # Generate recommendations
    recommendations = []
    
    if features["sent_cv"] < 0.40:
        recommendations.append("Vary sentence lengths: mix short punchy sentences with longer complex ones")
    
    if features["ttr"] < 0.55:
        recommendations.append("Use more diverse vocabulary: avoid repeating the same words")
    
    if features["bigram_repeat"] > 0.10:
        recommendations.append("Reduce phrase repetition: rephrase repeated word combinations")
    
    if features["vocab_concentration"] > 0.30:
        recommendations.append("Use more specific/less common words instead of generic terms")
    
    if features["passive_ratio"] > 0.10:
        recommendations.append("Convert passive constructions to active voice where possible")
    
    if features["char_entropy"] < 4.0:
        recommendations.append("Include more varied characters: numbers, symbols, contractions")
    
    if features["punct_consistency"] > 0.85:
        recommendations.append("Vary punctuation patterns: add some unconventional spacing")
    
    return {
        "overall_score": round(overall_score, 1),
        "features": {k: round(v, 4) for k, v in features.items()},
        "human_scores": {k: round(v, 4) for k, v in human_scores.items()},
        "ai_signals": ai_signals,
        "human_signals": human_signals,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Text transformation suggestions
# ---------------------------------------------------------------------------

# Common AI phrases to avoid
AI_PHRASES = [
    "in the end",
    "little did he know",
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
    "he couldn't help but",
    "she couldn't help but",
    "at that moment",
    "it was then that",
    "one last time",
    "time seemed to stand still",
    "it's worth noting",
    "it's important to note",
    "in today's world",
    "in conclusion",
    "to sum up",
    "in summary",
    "needless to say",
    "it goes without saying",
    "at the end of the day",
    "when all is said and done",
    "the fact of the matter is",
    "as a matter of fact",
    "in light of",
    "with regard to",
    "in terms of",
    "it is important to note",
    "it is worth mentioning",
    "it is interesting to note",
    "it should be noted",
    "it is important to emphasize",
]

# Human-like alternatives
HUMAN_ALTERNATIVES = {
    "in the end": ["finally", "afterwards", "once it was over", "looking back"],
    "little did he know": ["he had no idea", "unbeknownst to him", "he couldn't have known"],
    "heart racing": ["pulse quickening", "blood pounding", "chest tight"],
    "took a deep breath": ["inhaled sharply", "breathed in slowly", "filled his lungs"],
    "out of nowhere": ["suddenly", "without warning", "unexpectedly"],
    "all of a sudden": ["suddenly", "abruptly", "without preamble"],
    "in the blink of an eye": ["instantly", "in a flash", "before he could react"],
    "a sense of": ["a feeling of", "something like", "what might be called"],
    "in that moment": ["then", "right then", "in that instant"],
    "for the first time in years": ["for the first time in ages", "not since", "after years"],
    "the world seemed": ["reality felt", "everything appeared", "it was as though"],
    "as if": ["like", "as though", "almost like"],
    "deep down": ["beneath it all", "underneath", "at his core"],
    "in the back of his mind": ["somewhere inside", "in the recesses of", "buried in"],
    "he couldn't help but": ["he found himself", "involuntarily", "without thinking"],
    "she couldn't help but": ["she found herself", "involuntarily", "without thinking"],
    "at that moment": ["then", "right then", "at that very instant"],
    "it was then that": ["suddenly", "that's when", "only then"],
    "one last time": ["for the final time", "once more", "again"],
    "time seemed to stand still": ["everything paused", "the moment stretched", "seconds felt like hours"],
}


def suggest_replacements(text: str) -> List[Dict[str, str]]:
    """Find AI-like phrases and suggest human alternatives."""
    suggestions = []
    text_lower = text.lower()
    
    for phrase, alternatives in HUMAN_ALTERNATIVES.items():
        if phrase in text_lower:
            # Find the actual case in the text
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            match = pattern.search(text)
            if match:
                suggestions.append({
                    "original": match.group(),
                    "suggestion": random.choice(alternatives),
                    "position": match.start(),
                })
    
    return suggestions


def suggest_human_variations(text: str) -> List[str]:
    """Generate specific suggestions to make text more human-like."""
    suggestions = []
    
    # Check for sentence length uniformity
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    if len(sentences) > 3:
        lengths = [len(s.split()) for s in sentences]
        if max(lengths) / min(lengths) < 2.0:
            suggestions.append("Your sentences are too uniform in length. Mix short fragments with longer, complex sentences.")
    
    # Check for word repetition
    words = text.lower().split()
    word_counts = Counter(words)
    common_words = [(w, c) for w, c in word_counts.most_common(10) if c > 3 and len(w) > 3]
    if common_words:
        repeated = [f"'{w}' ({c} times)" for w, c in common_words[:3]]
        suggestions.append(f"Consider replacing some instances of {', '.join(repeated)} with synonyms.")
    
    # Check for passive voice
    passive_ratio = _passive_voice_ratio(text)
    if passive_ratio > 0.10:
        suggestions.append("Reduce passive voice. Instead of 'The ball was thrown by him', write 'He threw the ball'.")
    
    # Check for clichés
    cliches_found = [p for p in AI_PHRASES if p in text.lower()]
    if cliches_found:
        suggestions.append(f"Replace clichés like '{cliches_found[0]}' with more original phrasing.")
    
    # Check for exclamation marks
    if text.count('!') > 3:
        suggestions.append("Reduce exclamation marks. Human writing uses them sparingly.")
    
    # Check for ellipses
    if text.count('...') > 2 or text.count('…') > 2:
        suggestions.append("Reduce ellipses. Overuse is a common AI pattern.")
    
    return suggestions


# ---------------------------------------------------------------------------
# Example human-like text templates
# ---------------------------------------------------------------------------

HUMAN_TEMPLATES = [
    # Short, punchy sentences mixed with longer ones
    """
The coffee was cold. Maria noticed it the moment she lifted the mug to her lips—
a lukewarm betrayal that somehow matched her mood. She'd been sitting at this 
kitchen table for three hours now, the same spot where her mother used to 
spread flour across the countertop every Sunday morning, back when Sundays 
meant something other than dread.
""",
    # Fragmented, conversational style
    """
Look. I'm not going to pretend this makes sense. One minute I'm filing 
paperwork—boring, tedious, the kind of stuff that makes you question why 
you even bothered getting out of bed—and the next, my phone's buzzing with 
a number I don't recognize. Virginia area code. Who the hell calls from 
Virginia anymore?
""",
    # Personal, reflective tone with specific details
    """
The house on Elm Street still has the same blue shutters. My daughter 
pointed them out last Tuesday during our drive through the old neighborhood. 
Mom, she said, isn't that where you— Yeah. Yeah, it is. Twelve years 
since I last stood on that porch. The paint's peeling near the mailbox now, 
and someone planted marigolds where Dad's rose bushes used to be. Time does 
that. Rewrites the landscape while you're busy not paying attention.
""",
    # Fragmented dialogue with natural speech patterns
    """
"Wait, you're serious?" I asked.
"Dead serious."
"That's... no. No way."
"Way." She folded her arms. "Ask Marcus if you don't believe me."
"I already did. He said—"
"What?"
"He said the same thing you're saying."
"Then why do you look like you're about to bolt?"
Because I was. Because the hallway suddenly felt ten degrees colder and my 
shoes were glued to the linoleum and I couldn't remember a single reason 
why I should stay.
""",
]


def get_human_examples() -> List[str]:
    """Return example texts that score as human-written."""
    return HUMAN_TEMPLATES


# ---------------------------------------------------------------------------
# Main interface
# ---------------------------------------------------------------------------

def humanize_report(text: str) -> str:
    """
    Generate a comprehensive report on how human-like the text appears.
    
    Returns formatted report string.
    """
    analysis = analyze_text(text)
    suggestions = suggest_human_variations(text)
    replacements = suggest_replacements(text)
    
    report = []
    report.append("=" * 60)
    report.append("AI DETECTION EVASION REPORT")
    report.append("Based on DNA-DetectLLM & StoryScope analysis")
    report.append("=" * 60)
    report.append("")
    
    # Overall score
    score = analysis["overall_score"]
    if score >= 70:
        verdict = "LIKELY HUMAN-WRITTEN ✓"
    elif score >= 50:
        verdict = "BORDERLINE - Could pass as human"
    else:
        verdict = "LIKELY AI-DETECTED ✗"
    
    report.append(f"Overall Human-Likeness Score: {score:.1f}/100")
    report.append(f"Verdict: {verdict}")
    report.append("")
    
    # AI signals detected
    if analysis["ai_signals"]:
        report.append("AI SIGNALS DETECTED (problems to fix):")
        for signal in analysis["ai_signals"]:
            report.append(f"  ⚠ {signal}")
        report.append("")
    
    # Human signals detected
    if analysis["human_signals"]:
        report.append("HUMAN SIGNALS DETECTED (good signs):")
        for signal in analysis["human_signals"]:
            report.append(f"  ✓ {signal}")
        report.append("")
    
    # Recommendations
    if analysis["recommendations"]:
        report.append("RECOMMENDATIONS:")
        for i, rec in enumerate(analysis["recommendations"], 1):
            report.append(f"  {i}. {rec}")
        report.append("")
    
    # Specific phrase suggestions
    if replacements:
        report.append("PHRASE REPLACEMENTS:")
        for rep in replacements[:5]:
            report.append(f"  Replace '{rep['original']}' → '{rep['suggestion']}'")
        report.append("")
    
    # Additional suggestions
    if suggestions:
        report.append("ADDITIONAL TIPS:")
        for tip in suggestions:
            report.append(f"  • {tip}")
        report.append("")
    
    report.append("=" * 60)
    report.append("TEXT STATISTICS:")
    report.append(f"  Characters: {len(text)}")
    report.append(f"  Words: {len(text.split())}")
    report.append(f"  Sentences: {len([s for s in re.split(r'[.!?]+', text) if s.strip()])}")
    report.append(f"  Character Entropy: {analysis['features']['char_entropy']:.2f} bits/char")
    report.append(f"  Type-Token Ratio: {analysis['features']['ttr']:.2f}")
    report.append(f"  Sentence Length CV: {analysis['features']['sent_cv']:.2f}")
    report.append(f"  Bigram Repetition: {analysis['features']['bigram_repeat']:.1%}")
    report.append(f"  Passive Voice: {analysis['features']['passive_ratio']:.1%}")
    report.append("=" * 60)
    
    return "\n".join(report)


if __name__ == "__main__":
    # Demo
    sample_ai_text = """
    It is important to note that artificial intelligence has transformed 
    numerous aspects of modern life. In today's world, the integration of 
    machine learning algorithms has become increasingly prevalent. It goes 
    without saying that these technological advancements have profound 
    implications for society. The fact of the matter is that we must adapt 
    to these changes or risk being left behind. Needless to say, the 
    transformation is already underway. At the end of the day, it is 
    important to emphasize that human oversight remains crucial.
    """
    
    print(humanize_report(sample_ai_text))
    print("\n\n")
    print("=" * 60)
    print("EXAMPLE HUMAN-LIKE TEXT:")
    print("=" * 60)
    print(random.choice(HUMAN_TEMPLATES))
