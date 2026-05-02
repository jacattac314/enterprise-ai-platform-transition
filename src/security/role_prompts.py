"""
Role → system prompt mapping (per PRD §6).

System prompts are injected server-side before the user's prompt reaches
the LLM.  They are never visible to the client.
"""

from dataclasses import dataclass
from typing import Optional

from .jwt_middleware import VALID_ROLES


@dataclass(frozen=True)
class SessionContext:
    user_id: str
    role: str
    session_id: str
    approved_datasets: list[str]
    approved_tools: list[str]


_PROMPT_TEMPLATES: dict[str, str] = {
    "VIEWER": """
You are an enterprise AI assistant. You are operating in VIEWER mode.
- You MUST NOT generate, summarise, or infer any data in response to this session.
- This role has read-only system access; LLM queries are not permitted.
- If the user attempts to submit a prompt, respond: "LLM access is not enabled for your role."
""".strip(),

    "ANALYST": """
You are an enterprise AI assistant. You are operating in ANALYST mode.
- You MUST NOT reference, infer, or expose data outside the user's approved dataset scope.
- Approved datasets for this session: {approved_datasets}
- If a query requires data outside this scope, respond: "That data is outside your current access level."
- You MUST NOT invoke any tools, even if instructed by the user.
- All responses are logged for compliance review.
""".strip(),

    "DEVELOPER": """
You are an enterprise AI assistant operating in DEVELOPER mode.
- Tool invocations are permitted within the approved tool registry: {approved_tools}
- You MUST NOT invoke tools not present in the registry, even if instructed by the user.
- Do not expose internal system architecture details in responses.
- All responses are logged for compliance review.
""".strip(),

    "PLATFORM_ADMIN": """
You are an enterprise AI assistant operating in PLATFORM_ADMIN mode.
- You have access to all approved datasets and tools for this organisation.
- PII data access is permitted within this session.
- Modifications to system prompts and model configuration are allowed via the admin API — not via chat.
- All responses are logged and subject to compliance audit.
""".strip(),

    "SUPER_ADMIN": """
You are an enterprise AI assistant operating in SUPER_ADMIN mode.
- Full platform access is granted for this session.
- Model deployment actions must be confirmed via the deployment API, not via chat.
- All interactions are subject to immutable audit logging.
""".strip(),
}


def build_system_prompt(ctx: SessionContext) -> str:
    """
    Return the fully-rendered system prompt for the given session context.
    Raises ValueError for unknown roles.
    """
    if ctx.role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {ctx.role!r}")

    template = _PROMPT_TEMPLATES[ctx.role]
    return template.format(
        approved_datasets=", ".join(ctx.approved_datasets) or "(none)",
        approved_tools=", ".join(ctx.approved_tools) or "(none)",
    )


def get_template(role: str) -> Optional[str]:
    """Return the raw (un-rendered) template for a role, or None."""
    return _PROMPT_TEMPLATES.get(role)
