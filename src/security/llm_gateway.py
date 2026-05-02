"""
LLM gateway — executes the model call with the secured payload.

Accepts a system prompt, redacted user prompt, and session metadata;
returns the raw completion text and token usage.

Uses the Anthropic SDK. Model and max_tokens are configurable via
environment variables so the gateway is not hard-coupled to a single model.
"""

import os
import time
from dataclasses import dataclass

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1024"))
_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


@dataclass
class CompletionResult:
    text: str
    model_id: str
    completion_tokens: int
    latency_ms: int


def complete(system_prompt: str, user_prompt: str) -> CompletionResult:
    """
    Call the LLM with the secured (redacted + role-scoped) payload.
    Raises RuntimeError if the Anthropic SDK is unavailable or unconfigured.
    """
    if not _ANTHROPIC_AVAILABLE:
        raise RuntimeError(
            "anthropic SDK is not installed. "
            "Run: pip install anthropic"
        )
    if not _API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set."
        )

    client = anthropic.Anthropic(api_key=_API_KEY)

    t0 = time.monotonic()
    message = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    text = message.content[0].text if message.content else ""
    return CompletionResult(
        text=text,
        model_id=message.model,
        completion_tokens=message.usage.output_tokens,
        latency_ms=latency_ms,
    )
