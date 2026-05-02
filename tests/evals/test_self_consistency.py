import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "evals"))

import pytest
from self_consistency import self_consistency_score, _jaccard_consistency, _tokenize


def test_identical_responses_score_one():
    responses = ["The answer is 42.", "The answer is 42.", "The answer is 42."]
    score = self_consistency_score(responses)
    assert score == pytest.approx(1.0, abs=0.01)


def test_completely_different_responses_low_score():
    responses = [
        "The capital is Paris and it has a rich history.",
        "Quantum mechanics describes subatomic particle behaviour.",
        "The recipe requires flour, eggs, and butter.",
    ]
    score = self_consistency_score(responses)
    assert score < 0.5


def test_similar_responses_high_score():
    responses = [
        "Paris is the capital city of France.",
        "France's capital city is Paris.",
        "The capital of France is the city of Paris.",
    ]
    score = self_consistency_score(responses)
    assert score > 0.5


def test_requires_at_least_two_responses():
    with pytest.raises(ValueError):
        self_consistency_score(["only one response"])


def test_two_responses_works():
    score = self_consistency_score(["hello world", "hello world"])
    assert score == pytest.approx(1.0, abs=0.01)


def test_empty_strings_handled():
    score = self_consistency_score(["", ""])
    assert 0.0 <= score <= 1.0
