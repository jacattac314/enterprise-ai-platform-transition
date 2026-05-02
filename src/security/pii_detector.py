"""
PII detection pipeline — spaCy NER + regex patterns.
Tokenizes detected PII before prompt reaches the LLM.
"""

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

try:
    import spacy
    _nlp = spacy.load("en_core_web_sm")
except (ImportError, OSError):
    _nlp = None

# ---------------------------------------------------------------------------
# Entity types and confidence thresholds (per PRD §5.2)
# ---------------------------------------------------------------------------

class PIIEntityType(str, Enum):
    PERSON = "PERSON"
    EMAIL = "EMAIL"
    SSN = "SSN"
    PHONE = "PHONE"
    CREDIT_CARD = "CREDIT_CARD"
    IP_ADDRESS = "IP_ADDRESS"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"


CONFIDENCE_THRESHOLDS: dict[PIIEntityType, float] = {
    PIIEntityType.PERSON: 0.85,
    PIIEntityType.EMAIL: 1.0,
    PIIEntityType.SSN: 1.0,
    PIIEntityType.PHONE: 0.95,
    PIIEntityType.CREDIT_CARD: 1.0,
    PIIEntityType.IP_ADDRESS: 1.0,
    PIIEntityType.DATE_OF_BIRTH: 0.80,
}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_PATTERNS: dict[PIIEntityType, re.Pattern] = {
    PIIEntityType.EMAIL: re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    ),
    PIIEntityType.SSN: re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    PIIEntityType.PHONE: re.compile(
        r"(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"
    ),
    PIIEntityType.IP_ADDRESS: re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    ),
    # Simple 13–19 digit card pattern — Luhn check applied separately
    PIIEntityType.CREDIT_CARD: re.compile(
        r"\b(?:\d[ \-]?){13,19}\b"
    ),
}


# ---------------------------------------------------------------------------
# Luhn algorithm for credit card validation
# ---------------------------------------------------------------------------

def _luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------

@dataclass
class DetectedEntity:
    entity_type: PIIEntityType
    value: str
    start: int
    end: int
    confidence: float
    token: str = field(default_factory=lambda: f"<PII_TOKEN_{uuid.uuid4().hex[:8].upper()}>")


# ---------------------------------------------------------------------------
# Core detector
# ---------------------------------------------------------------------------

class PIIDetector:
    """Detects PII entities in text and replaces them with opaque tokens."""

    def detect(self, text: str) -> list[DetectedEntity]:
        entities: list[DetectedEntity] = []
        entities.extend(self._regex_detect(text))
        entities.extend(self._ner_detect(text))
        entities = self._deduplicate(entities)
        return entities

    def redact(self, text: str) -> tuple[str, list[DetectedEntity]]:
        """Returns redacted text and the list of replaced entities."""
        entities = self.detect(text)
        # Process in reverse order so offsets stay valid during replacement
        entities_sorted = sorted(entities, key=lambda e: e.start, reverse=True)
        result = text
        for ent in entities_sorted:
            result = result[: ent.start] + ent.token + result[ent.end :]
        return result, entities

    # ------------------------------------------------------------------

    def _regex_detect(self, text: str) -> list[DetectedEntity]:
        found: list[DetectedEntity] = []
        for entity_type, pattern in _PATTERNS.items():
            for m in pattern.finditer(text):
                value = m.group()
                if entity_type == PIIEntityType.CREDIT_CARD:
                    digits_only = re.sub(r"[ \-]", "", value)
                    if not (13 <= len(digits_only) <= 19) or not _luhn_valid(digits_only):
                        continue
                confidence = CONFIDENCE_THRESHOLDS[entity_type]
                found.append(
                    DetectedEntity(
                        entity_type=entity_type,
                        value=value,
                        start=m.start(),
                        end=m.end(),
                        confidence=confidence,
                    )
                )
        return found

    def _ner_detect(self, text: str) -> list[DetectedEntity]:
        if _nlp is None:
            return []
        doc = _nlp(text)
        found: list[DetectedEntity] = []
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                conf = CONFIDENCE_THRESHOLDS[PIIEntityType.PERSON]
                found.append(
                    DetectedEntity(
                        entity_type=PIIEntityType.PERSON,
                        value=ent.text,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=conf,
                    )
                )
            elif ent.label_ == "DATE" and _looks_like_dob(ent.text):
                conf = CONFIDENCE_THRESHOLDS[PIIEntityType.DATE_OF_BIRTH]
                found.append(
                    DetectedEntity(
                        entity_type=PIIEntityType.DATE_OF_BIRTH,
                        value=ent.text,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=conf,
                    )
                )
        return found

    @staticmethod
    def _deduplicate(entities: list[DetectedEntity]) -> list[DetectedEntity]:
        """Remove overlapping entities — keep higher-confidence match."""
        entities = sorted(entities, key=lambda e: (e.start, -e.confidence))
        result: list[DetectedEntity] = []
        last_end = -1
        for ent in entities:
            if ent.start >= last_end:
                result.append(ent)
                last_end = ent.end
        return result


def _looks_like_dob(text: str) -> bool:
    """Heuristic: a spaCy DATE entity that contains digits is likely a DOB."""
    return bool(re.search(r"\d", text))
