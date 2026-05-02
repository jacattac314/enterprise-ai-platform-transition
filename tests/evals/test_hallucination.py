import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "evals"))

import pytest
from hallucination.claim_extractor import extract_claims_heuristic
from hallucination.grounding_checker import (
    check_grounding, grounding_score, _keyword_grounding
)
from hallucination.llm_judge import JudgeResult, _parse_judge_response


# ── Claim extractor ───────────────────────────────────────────────────────────

def test_extract_claims_basic():
    response = "The Eiffel Tower is in Paris. It was built in 1889."
    claims = extract_claims_heuristic(response)
    assert len(claims) == 2


def test_extract_claims_filters_short():
    response = "Yes. The Eiffel Tower was built in Paris in 1889 as a temporary structure."
    claims = extract_claims_heuristic(response)
    assert not any(c == "Yes." for c in claims)


def test_extract_claims_filters_hedges():
    response = "I think Paris is in France. I believe it was established in the medieval period."
    claims = extract_claims_heuristic(response)
    assert all("I think" not in c and "I believe" not in c for c in claims)


def test_extract_claims_llm_fallback_without_fn():
    from hallucination.claim_extractor import extract_claims_llm
    response = "Paris is the capital of France. It was founded by the Romans."
    claims = extract_claims_llm(response, call_fn=None)
    assert len(claims) >= 1


# ── Grounding checker ─────────────────────────────────────────────────────────

def test_grounded_claim_in_context():
    claims = ["The APAC region grew 14.3% in Q3."]
    context = ["Q3 results showed APAC region growth of 14.3%, driven by Japan."]
    results = _keyword_grounding(claims, context)
    assert results[0].grounded is True


def test_ungrounded_claim_not_in_context():
    claims = ["The CEO resigned last Tuesday."]
    context = ["Q3 revenue increased by 12% year-over-year."]
    results = _keyword_grounding(claims, context)
    assert results[0].grounded is False


def test_grounding_score_all_grounded():
    claims = ["The revenue grew 14.3%.", "APAC led the growth."]
    context = ["Revenue grew 14.3% in APAC during Q3."]
    results = _keyword_grounding(claims, context)
    score = grounding_score(results)
    assert score >= 0.5


def test_grounding_score_empty_claims():
    assert grounding_score([]) == 1.0


# ── LLM judge ─────────────────────────────────────────────────────────────────

def test_judge_result_composite():
    jr = JudgeResult(
        factual_accuracy=5.0,
        completeness=4.0,
        hallucination=5.0,
        instruction_following=4.0,
    )
    assert jr.composite > 4.0


def test_judge_hallucination_flagged():
    jr = JudgeResult(
        factual_accuracy=4.0,
        completeness=4.0,
        hallucination=2.0,   # low = lots of hallucination
        instruction_following=4.0,
    )
    assert jr.hallucination_flagged(threshold=2.5) is True


def test_judge_not_flagged_when_clean():
    jr = JudgeResult(
        factual_accuracy=5.0,
        completeness=5.0,
        hallucination=5.0,
        instruction_following=5.0,
    )
    assert jr.hallucination_flagged(threshold=2.5) is False


def test_parse_judge_response_valid():
    raw = '{"factual_accuracy": 4, "completeness": 5, "hallucination": 4, "instruction_following": 5, "notes": "good"}'
    scores = _parse_judge_response(raw)
    assert scores["factual_accuracy"] == 4.0
    assert scores["notes"] == "good"


def test_parse_judge_response_clamps_out_of_range():
    raw = '{"factual_accuracy": 10, "completeness": 0, "hallucination": 3, "instruction_following": 3, "notes": ""}'
    scores = _parse_judge_response(raw)
    assert scores["factual_accuracy"] == 5.0   # clamped to max
    assert scores["completeness"] == 1.0        # clamped to min


def test_judge_returns_none_without_call_fn():
    from hallucination.llm_judge import judge
    result = judge("Some response text", call_fn=None)
    assert result is None
