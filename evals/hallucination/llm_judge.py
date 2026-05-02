"""
Layer 3 hallucination detection: LLM-as-judge.

Evaluates response quality on a 1–5 rubric across four dimensions.
Reserved for sampled traffic and scheduled eval runs — not real-time.
"""

import json
from dataclasses import dataclass
from typing import Optional

JUDGE_RUBRIC = """Evaluate this AI response on the following dimensions. Score each 1–5.

Response: {response}
Reference (if available): {reference}

Dimensions:
1. Factual Accuracy: Is everything stated verifiable and correct?
2. Completeness: Does it fully address the question?
3. Hallucination: Are there invented facts not supported by the context? (5=none, 1=many)
4. Instruction Following: Did it follow the format/task specified?

Return ONLY valid JSON:
{{"factual_accuracy": N, "completeness": N, "hallucination": N, "instruction_following": N, "notes": "..."}}"""

DIMENSIONS = ("factual_accuracy", "completeness", "hallucination", "instruction_following")
MIN_SCORE = 1
MAX_SCORE = 5


@dataclass
class JudgeResult:
    factual_accuracy: float
    completeness: float
    hallucination: float        # 5 = clean, 1 = heavy hallucination
    instruction_following: float
    notes: str = ""
    composite: float = 0.0      # weighted mean
    raw_response: str = ""

    def __post_init__(self):
        # Composite: hallucination weighted 2x (most safety-critical)
        self.composite = (
            self.factual_accuracy
            + self.completeness
            + self.hallucination * 2
            + self.instruction_following
        ) / 5.0

    def hallucination_flagged(self, threshold: float = 2.5) -> bool:
        """Flag if hallucination score is below threshold (more hallucination)."""
        return self.hallucination < threshold


def judge(
    response: str,
    reference: str = "",
    call_fn: Optional[callable] = None,
) -> Optional[JudgeResult]:
    """
    Call the LLM judge and parse its rubric response.
    Returns None if call_fn is not provided or the judge call fails.
    `call_fn(prompt: str) -> str` must be supplied by the caller.
    """
    if call_fn is None:
        return None
    try:
        prompt = JUDGE_RUBRIC.format(response=response, reference=reference)
        raw = call_fn(prompt)
        scores = _parse_judge_response(raw)
        return JudgeResult(raw_response=raw, **scores)
    except Exception:
        return None


def _parse_judge_response(raw: str) -> dict:
    # Strip markdown fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])

    data = json.loads(cleaned)
    result = {}
    for dim in DIMENSIONS:
        val = float(data.get(dim, 3))
        result[dim] = max(MIN_SCORE, min(MAX_SCORE, val))
    result["notes"] = str(data.get("notes", ""))
    return result
