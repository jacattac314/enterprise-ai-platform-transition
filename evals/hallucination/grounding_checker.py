"""
Layer 2 hallucination detection: grounding check for RAG responses.

For each extracted claim, checks whether it is directly supported by
at least one of the provided context chunks.

Two modes:
  - Keyword overlap (fast, zero-cost)
  - LLM judge per claim (slower, higher precision)
"""

import re
from dataclasses import dataclass
from typing import Optional


GROUNDING_CHECK_PROMPT = """Given this source context:
{context}

Is the following claim directly supported by the context above? Answer YES or NO only.
Claim: {claim}"""


@dataclass
class ClaimGroundingResult:
    claim: str
    grounded: bool
    confidence: float   # 0.0–1.0
    method: str         # "keyword" | "llm"


def check_grounding(
    claims: list[str],
    context_chunks: list[str],
    call_fn: Optional[callable] = None,
    use_llm: bool = False,
) -> list[ClaimGroundingResult]:
    """
    Check each claim against context chunks.
    Returns a result per claim; grounding_score = grounded_count / total.
    """
    if use_llm and call_fn is not None:
        return _llm_grounding(claims, context_chunks, call_fn)
    return _keyword_grounding(claims, context_chunks)


def grounding_score(results: list[ClaimGroundingResult]) -> float:
    """Fraction of claims that are grounded (0.0–1.0)."""
    if not results:
        return 1.0
    return sum(1 for r in results if r.grounded) / len(results)


# ---------------------------------------------------------------------------
# Keyword overlap grounding
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b\w{3,}\b", text.lower()))


def _keyword_grounding(
    claims: list[str], context_chunks: list[str]
) -> list[ClaimGroundingResult]:
    context_tokens = set()
    for chunk in context_chunks:
        context_tokens |= _tokenize(chunk)

    results = []
    for claim in claims:
        claim_tokens = _tokenize(claim)
        if not claim_tokens:
            results.append(ClaimGroundingResult(claim, True, 1.0, "keyword"))
            continue
        overlap = len(claim_tokens & context_tokens) / len(claim_tokens)
        # Threshold: ≥40% of claim tokens must appear in context
        grounded = overlap >= 0.40
        results.append(ClaimGroundingResult(claim, grounded, overlap, "keyword"))
    return results


# ---------------------------------------------------------------------------
# LLM-per-claim grounding
# ---------------------------------------------------------------------------

def _llm_grounding(
    claims: list[str],
    context_chunks: list[str],
    call_fn: callable,
) -> list[ClaimGroundingResult]:
    combined_context = "\n\n".join(context_chunks)
    results = []
    for claim in claims:
        try:
            prompt = GROUNDING_CHECK_PROMPT.format(
                context=combined_context[:4000], claim=claim
            )
            answer = call_fn(prompt).strip().upper()
            grounded = answer.startswith("YES")
            confidence = 0.95 if grounded else 0.05
        except Exception:
            # Fallback to keyword on error
            keyword_result = _keyword_grounding([claim], context_chunks)[0]
            results.append(keyword_result)
            continue
        results.append(ClaimGroundingResult(claim, grounded, confidence, "llm"))
    return results
