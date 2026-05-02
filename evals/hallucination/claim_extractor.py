"""
Layer 2 hallucination detection: claim extraction pipeline.

Extracts atomic factual claims from an LLM response using a lightweight
regex/heuristic extractor (no API call required) plus an optional
LLM-backed extractor for higher precision.
"""

import json
import re
from typing import Optional

CLAIM_EXTRACTION_PROMPT = """Extract all factual claims from the following response as a JSON list.
Each claim should be a single, atomic, verifiable statement.
Ignore hedging phrases, filler, and meta-commentary.

Response: {response}

Return ONLY valid JSON: ["claim1", "claim2", ...]"""


# ---------------------------------------------------------------------------
# Heuristic extractor (no LLM required)
# ---------------------------------------------------------------------------

def extract_claims_heuristic(response: str) -> list[str]:
    """
    Fast, zero-cost claim extractor.
    Splits on sentence boundaries and filters out low-information sentences.
    """
    sentences = re.split(r"(?<=[.!?])\s+", response.strip())
    claims = []
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 15:
            continue
        # Skip meta-commentary and hedges
        lowered = sent.lower()
        if any(lowered.startswith(p) for p in (
            "i think", "i believe", "in my opinion", "it seems",
            "note that", "please note", "as an ai",
        )):
            continue
        claims.append(sent)
    return claims


# ---------------------------------------------------------------------------
# LLM-backed extractor (Anthropic SDK)
# ---------------------------------------------------------------------------

def extract_claims_llm(
    response: str,
    call_fn: Optional[callable] = None,
) -> list[str]:
    """
    Use an LLM to extract claims.  `call_fn(prompt) -> str` must be provided
    by the caller (avoids hard dependency on a specific SDK in this module).
    Falls back to heuristic extractor if call_fn is None or raises.
    """
    if call_fn is None:
        return extract_claims_heuristic(response)
    try:
        prompt = CLAIM_EXTRACTION_PROMPT.format(response=response)
        raw = call_fn(prompt)
        claims = json.loads(raw.strip())
        if isinstance(claims, list):
            return [str(c) for c in claims]
    except Exception:
        pass
    return extract_claims_heuristic(response)
