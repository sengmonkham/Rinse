#!/usr/bin/env python3
"""
Demo script showing how to use the AI Text Humanizer.

This script demonstrates:
1. Analyzing text for AI detection signals
2. Getting specific recommendations to appear more human
3. Finding clichés and suggesting replacements
4. Generating human-like text examples
"""

from humanizer import (
    analyze_text,
    suggest_human_variations,
    suggest_replacements,
    humanize_report,
    get_human_examples,
)
import random


def demo_analysis():
    """Demo 1: Analyze a piece of text."""
    print("=" * 70)
    print("DEMO 1: Analyzing text for AI detection signals")
    print("=" * 70)
    
    ai_text = """
    It is important to note that artificial intelligence has transformed 
    numerous aspects of modern life. In today's world, the integration of 
    machine learning algorithms has become increasingly prevalent. It goes 
    without saying that these technological advancements have profound 
    implications for society. The fact of the matter is that we must adapt 
    to these changes or risk being left behind. Needless to say, the 
    transformation is already underway. At the end of the day, it is 
    important to emphasize that human oversight remains crucial.
    """
    
    print("\nAI-style text to analyze:")
    print("-" * 40)
    print(ai_text.strip())
    print("-" * 40)
    
    analysis = analyze_text(ai_text)
    
    print(f"\nOverall Human-Likeness Score: {analysis['overall_score']}/100")
    
    if analysis['ai_signals']:
        print("\nAI SIGNALS DETECTED:")
        for signal in analysis['ai_signals']:
            print(f"  ⚠ {signal}")
    
    if analysis['recommendations']:
        print("\nRECOMMENDATIONS:")
        for i, rec in enumerate(analysis['recommendations'], 1):
            print(f"  {i}. {rec}")


def demo_replacements():
    """Demo 2: Find clichés and suggest replacements."""
    print("\n\n" + "=" * 70)
    print("DEMO 2: Finding clichés and suggesting replacements")
    print("=" * 70)
    
    text_with_cliches = """
    In the end, she realized that little did she know, her heart was racing.
    She took a deep breath and thought about all of a sudden, how life had 
    changed. It was then that she understood the world seemed different now.
    """
    
    print("\nText with clichés:")
    print("-" * 40)
    print(text_with_cliches.strip())
    print("-" * 40)
    
    replacements = suggest_replacements(text_with_cliches)
    
    print("\nSUGGESTED REPLACEMENTS:")
    for rep in replacements:
        print(f"  '{rep['original']}' → '{rep['suggestion']}'")


def demo_human_examples():
    """Demo 3: Show examples of human-like text."""
    print("\n\n" + "=" * 70)
    print("DEMO 3: Examples of human-like text that evades detection")
    print("=" * 70)
    
    examples = get_human_examples()
    
    for i, example in enumerate(examples, 1):
        print(f"\n--- Example {i} ---")
        print(example.strip())
        
        # Analyze the example
        analysis = analyze_text(example)
        print(f"\nHuman-Likeness Score: {analysis['overall_score']}/100")
        if analysis['human_signals']:
            print("Good signs:", ", ".join(analysis['human_signals'][:2]))
        print()


def demo_full_report():
    """Demo 4: Generate a full report."""
    print("\n\n" + "=" * 70)
    print("DEMO 4: Full humanization report")
    print("=" * 70)
    
    mixed_text = """
    The data clearly shows that organizations must prioritize digital 
    transformation. However, the implementation challenges are significant. 
    Companies need to invest in training programs to ensure their workforce 
    can adapt to new technologies. Furthermore, leadership must champion 
    these initiatives to drive adoption. It is crucial to note that success 
    depends on a clear strategy and adequate resources.
    """
    
    report = humanize_report(mixed_text)
    print(report)


def demo_humanized_version():
    """Demo 5: Show a humanized version of AI text."""
    print("\n\n" + "=" * 70)
    print("DEMO 5: AI text → Humanized version")
    print("=" * 70)
    
    ai_text = """
    The implementation of artificial intelligence has significantly impacted 
    various industries. It is important to note that organizations must 
    adapt to these changes. Furthermore, the integration of machine learning 
    algorithms has become increasingly prevalent. In today's world, companies 
    that fail to embrace technological advancements risk becoming obsolete. 
    The fact of the matter is that digital transformation is no longer optional.
    """
    
    humanized = """
    AI's reshaped nearly every industry—some more than others. Take healthcare:
    diagnostic tools now flag cancers radiologists miss. Manufacturing? Whole 
    factory floors run themselves. But here's what most consultants won't tell 
    you: the tech itself isn't the hard part. Training people to actually use 
    it, convincing old-guard managers it's not a fad, recovering from the 
    third failed pilot program—THAT'S the real work. Companies still clinging 
    to "we've always done it this way" are watching competitors eat their lunch.
    """
    
    print("\nORIGINAL (AI-style):")
    print("-" * 40)
    print(ai_text.strip())
    
    analysis_original = analyze_text(ai_text)
    print(f"\nHuman-Likeness Score: {analysis_original['overall_score']}/100")
    
    print("\n\nHUMANIZED VERSION:")
    print("-" * 40)
    print(humanized.strip())
    
    analysis_humanized = analyze_text(humanized)
    print(f"\nHuman-Likeness Score: {analysis_humanized['overall_score']}/100")
    
    print("\n" + "=" * 40)
    print(f"IMPROVEMENT: +{analysis_humanized['overall_score'] - analysis_original['overall_score']:.1f} points")
    print("=" * 40)


if __name__ == "__main__":
    print("AI TEXT HUMANIZER - DEMO")
    print("Using StoryScope & DNA-DetectLLM logic to evade AI detection")
    print()
    
    demo_analysis()
    demo_replacements()
    demo_human_examples()
    demo_full_report()
    demo_humanized_version()
    
    print("\n\n" + "=" * 70)
    print("SUMMARY: Tips to evade AI detection")
    print("=" * 70)
    print("""
1. VARY SENTENCE LENGTHS: Mix short fragments with long complex sentences
2. USE SPECIFIC DETAILS: Replace generic terms with concrete examples
3. ADD PERSONAL VOICE: Include opinions, asides, and natural speech patterns
4. AVOID CLICHÉS: Replace stock phrases with original expressions
5. USE CONTRACTIONS: "don't" instead of "do not", "can't" instead of "cannot"
6. INCLUDE FRAGMENTS: Sentence fragments are natural in human writing
7. MIX ACTIVE/PASSIVE: Use mostly active voice, occasional passive for variety
8. ADD IMPERFECTIONS: Minor awkwardness, tangents, and self-corrections
9. USE SLANG/CASUAL LANGUAGE: Where appropriate, informal tone reads human
10. INCLUDE DIALOGUE: Natural speech patterns with interruptions and fillers
""")
