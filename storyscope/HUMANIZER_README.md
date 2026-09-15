# AI Text Humanizer

A tool that uses StoryScope and DNA-DetectLLM detection logic to help write text that appears human-written rather than AI-generated.

## How It Works

Based on research from:
- **DNA-DetectLLM** (Zhu et al., NeurIPS 2025 Spotlight) - Mutation-repair paradigm for AI detection
- **StoryScope** (arXiv:2604.03136) - 304-feature narrative analysis

The tool analyzes text against key AI detection signals:

| Feature | AI Typical | Human Typical | Weight |
|---------|-----------|---------------|--------|
| Character Entropy | 3.7 bits/char | 4.3 bits/char | 15% |
| Type-Token Ratio | 0.45 | 0.60 | 12% |
| Sentence Length CV | 0.30 | 0.70 | 15% |
| Bigram Repetition | 20% | 8% | 12% |
| Vocab Concentration | 35% | 25% | 10% |
| Punctuation Consistency | High | Varied | 10% |
| Passive Voice | >15% | <10% | 8% |

## Usage

### Analyze Your Text

```python
from humanizer import analyze_text, humanize_report

# Get detailed analysis
analysis = analyze_text("Your text here...")
print(f"Human-Likeness Score: {analysis['overall_score']}/100")

# Get full report with recommendations
report = humanize_report("Your text here...")
print(report)
```

### Find Clichés and Get Replacements

```python
from humanizer import suggest_replacements

suggestions = suggest_replacements("In the end, little did she know...")
for s in suggestions:
    print(f"Replace '{s['original']}' → '{s['suggestion']}'")
```

### Run the Demo

```bash
cd storyscope
python3 demo_humanizer.py
```

## Key Principles to Evade Detection

### 1. Vary Sentence Lengths
AI text tends to have uniform sentence lengths. Mix:
- Short fragments: "She froze."
- Medium sentences: "The room smelled like old coffee and regret."
- Long complex sentences with multiple clauses

### 2. Use Specific Details
Replace generic terms with concrete examples:
- ❌ "Various industries"
- ✅ "Healthcare diagnostics, manufacturing floors, and hedge fund algorithms"

### 3. Add Personal Voice
Include opinions and natural speech patterns:
- ❌ "It is important to note that..."
- ✅ "Here's what most people miss..."

### 4. Avoid Clichés
Replace stock phrases:
- ❌ "Little did she know"
- ✅ "She had no idea"

### 5. Use Contractions
- ❌ "Do not", "cannot", "it is"
- ✅ "Don't", "can't", "it's"

### 6. Include Sentence Fragments
Human writing naturally uses fragments:
- "Virginia area code. Who the hell calls from Virginia anymore?"

### 7. Mix Active and Passive Voice
Mostly active, occasional passive:
- Active: "She threw the ball"
- Passive (sparingly): "The ball was thrown by someone else"

### 8. Add Imperfections
Minor awkwardness reads as human:
- Self-corrections: "The third—no, fourth—attempt"
- Tangents: "But that's a story for another time"

### 9. Use Casual Language
Where appropriate:
- "gonna", "wanna", "kinda"
- "stuff", "thing", "whatever"

### 10. Include Natural Dialogue
With interruptions and fillers:
```
"Wait—you're serious?"
"Dead serious."
"That's... no. No way."
```

## Example: AI vs Human

**AI-Generated (Score: 50.7/100):**
> The implementation of artificial intelligence has significantly impacted various industries. It is important to note that organizations must adapt to these changes. Furthermore, the integration of machine learning algorithms has become increasingly prevalent.

**Humanized (Score: 70.8/100):**
> AI's reshaped nearly every industry—some more than others. Take healthcare: diagnostic tools now flag cancers radiologists miss. Manufacturing? Whole factory floors run themselves. But here's what most consultants won't tell you: the tech itself isn't the hard part.

## Running Tests

```bash
# Test against StoryScope detection
cd storyscope
python3 -c "from detect import detect; print(detect('your text'))"

# Test against DNA-DetectLLM
python3 -c "from dna_detect import detect; print(detect('your text'))"
```

## Tips for Best Results

1. **Write naturally first**, then analyze and refine
2. **Aim for 70+ score** on the human-likeness metric
3. **Check multiple paragraphs** - detectors look at patterns
4. **Read aloud** - if it sounds robotic, rewrite it
5. **Add personal anecdotes** - specific details are hard to fake

## Limitations

- This tool optimizes for statistical patterns, not semantic content
- Advanced detectors may use additional signals (e.g., perplexity, burstiness)
- No method guarantees evasion of all detectors
- Best used as a guide for improving writing quality
