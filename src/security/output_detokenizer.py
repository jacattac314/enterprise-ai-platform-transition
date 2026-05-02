"""
Output detokenizer — re-injects PII values into LLM responses.

Only roles with PII access (PLATFORM_ADMIN, SUPER_ADMIN) receive
detokenized output.  All other roles see the token placeholders.
"""

import re
from typing import Optional

from .redis_token_store import PIITokenStore

# Roles that may see original PII in responses (PRD §4.2)
PII_ACCESS_ROLES = frozenset({"PLATFORM_ADMIN", "SUPER_ADMIN"})

_TOKEN_PATTERN = re.compile(r"<PII_TOKEN_[0-9A-F]{8}>")


class OutputDetokenizer:
    """
    Replaces PII_TOKEN placeholders in LLM output with their original
    values, but only for callers whose role has PII access.
    """

    def __init__(self, store: PIITokenStore):
        self._store = store

    def detokenize(self, text: str, role: str) -> tuple[str, list[str]]:
        """
        Returns (detokenized_text, list_of_unresolved_tokens).

        Unresolved tokens (expired or unknown) are left in place and
        reported so the caller can set compliance_flags accordingly.
        """
        if role not in PII_ACCESS_ROLES:
            # Non-PII roles: return as-is, no token replacement
            return text, []

        unresolved: list[str] = []
        result = text

        for match in _TOKEN_PATTERN.finditer(text):
            token = match.group()
            record = self._store.get(token)
            if record is not None:
                result = result.replace(token, record["value"], 1)
            else:
                unresolved.append(token)

        return result, unresolved
