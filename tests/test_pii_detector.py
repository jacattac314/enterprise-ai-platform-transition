import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from security.pii_detector import PIIDetector, PIIEntityType


@pytest.fixture
def detector():
    return PIIDetector()


def test_email_detection(detector):
    text = "Contact john.doe@example.com for details."
    _, entities = detector.redact(text)
    assert any(e.entity_type == PIIEntityType.EMAIL for e in entities)


def test_ssn_detection(detector):
    text = "SSN is 123-45-6789 per the form."
    _, entities = detector.redact(text)
    assert any(e.entity_type == PIIEntityType.SSN for e in entities)


def test_ip_address_detection(detector):
    text = "Server at 192.168.1.100 is down."
    _, entities = detector.redact(text)
    assert any(e.entity_type == PIIEntityType.IP_ADDRESS for e in entities)


def test_redaction_replaces_value(detector):
    text = "Email: test@example.org"
    redacted, entities = detector.redact(text)
    assert "test@example.org" not in redacted
    assert entities[0].token in redacted


def test_multiple_pii_in_one_text(detector):
    text = "Call 555-867-5309 or email foo@bar.com, SSN 987-65-4321."
    _, entities = detector.redact(text)
    types = {e.entity_type for e in entities}
    assert PIIEntityType.EMAIL in types
    assert PIIEntityType.SSN in types


def test_no_pii_passthrough(detector):
    text = "The weather today is sunny."
    redacted, entities = detector.redact(text)
    assert redacted == text
    assert entities == []


def test_invalid_luhn_not_flagged(detector):
    # 1234567890123456 fails Luhn
    text = "Card 1234567890123456 was declined."
    _, entities = detector.redact(text)
    assert not any(e.entity_type == PIIEntityType.CREDIT_CARD for e in entities)


def test_valid_luhn_flagged(detector):
    # Luhn-valid test card number
    text = "Card 4532015112830366 was processed."
    _, entities = detector.redact(text)
    assert any(e.entity_type == PIIEntityType.CREDIT_CARD for e in entities)
