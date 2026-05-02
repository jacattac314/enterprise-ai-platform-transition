"""
Layer 1 hallucination detection: self-consistency check.

Runs the same prompt N times and measures semantic similarity across
responses.  High variance → high hallucination risk.

Uses sentence-transformers when available; falls back to a lightweight
Jaccard-overlap baseline so the check works without GPU deps.
"""

import hashlib
import math
import re
from typing import Callable

_SENTENCE_TRANSFORMERS_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
    _model = SentenceTransformer("all-MiniLM-L6-v2")
except (ImportError, Exception):
    _model = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def self_consistency_score(responses: list[str]) -> float:
    """
    Returns 0.0 (max inconsistency) to 1.0 (fully consistent).
    Requires at least 2 responses.
    """
    if len(responses) < 2:
        raise ValueError("At least 2 responses required for self-consistency check")

    if _SENTENCE_TRANSFORMERS_AVAILABLE and _model is not None:
        return _cosine_consistency(responses)
    return _jaccard_consistency(responses)


def should_sample() -> bool:
    """Return True for 5% of calls (deterministic per-process sampling)."""
    import random
    return random.random() < 0.05


# ---------------------------------------------------------------------------
# Embedding-based consistency (sentence-transformers)
# ---------------------------------------------------------------------------

def _cosine_consistency(responses: list[str]) -> float:
    import numpy as np
    embeddings = _model.encode(responses, normalize_embeddings=True)
    # Cosine similarity = dot product on normalized vectors
    sim_matrix = embeddings @ embeddings.T
    n = len(responses)
    upper = [sim_matrix[i][j] for i in range(n) for j in range(i + 1, n)]
    return float(np.mean(upper))


# ---------------------------------------------------------------------------
# Jaccard-overlap fallback (no GPU deps)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b\w+\b", text.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _jaccard_consistency(responses: list[str]) -> float:
    tokens = [_tokenize(r) for r in responses]
    n = len(tokens)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    scores = [_jaccard(tokens[i], tokens[j]) for i, j in pairs]
    return sum(scores) / len(scores) if scores else 0.0
