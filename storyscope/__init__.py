"""
StoryScope: narrative-feature AI fiction detection.

A production port of the research pipeline from:

  Russell, Rajendhran, Pham, Iyyer, Wieting (2026).
  "StoryScope: Investigating idiosyncrasies in AI fiction."
  arXiv:2604.03136  https://github.com/jenna-russell/storyscope (MIT)

StoryScope detects AI-written fiction by reading *narrative structure*
(plot, character agency, temporal structure, theme handling, ...) instead
of surface style. The published 304-feature taxonomy and the LLM extraction
prompts are used verbatim; the classifier is an XGBoost gradient-boosted
tree model trained on the paper's released per-story feature matrix
(61,575 stories, human + 5 LLMs).

Reported paper results: 93.2% macro-F1 (human vs AI) using narrative
features alone; a compact set of 30 core features retains >97% of that.

This package is self-contained: the classifier runs through a dependency-free
pure-Python XGBoost JSON scorer (validated against the native library), so the
server only needs `requests` (for the LLM feature extraction) plus pandas/pyarrow
for training.
"""
