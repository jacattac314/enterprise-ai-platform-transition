"""
LLM Security Gateway — Phase 1 entry point.

Wires together:
  - JWT role-extraction middleware
  - PII redaction pipeline
  - Redis token mapping store
  - Role-scoped system prompt injection
"""

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from security import (
    JWTRoleMiddleware,
    PIIDetector,
    PIITokenStore,
    SessionContext,
    build_system_prompt,
    require_role,
    VALID_ROLES,
)

app = FastAPI(title="LLM Security Gateway", version="1.0.0")
app.add_middleware(JWTRoleMiddleware)

_pii_detector = PIIDetector()
_token_store = PIITokenStore()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PromptRequest(BaseModel):
    prompt: str
    approved_datasets: list[str] = []
    approved_tools: list[str] = []


class AuditRecord(BaseModel):
    event_id: str
    timestamp: str
    user_id: str
    user_role: str
    session_id: str
    request_hash: str
    redacted_prompt_hash: str
    pii_tokens_present: list[str]
    model_id: str = "pending"
    tool_calls: list[str] = []
    completion_tokens: int = 0
    latency_ms: int = 0
    response_hash: str = ""
    compliance_flags: list[str] = []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "redis": _token_store.ping()}


@app.post(
    "/v1/prompt",
    dependencies=[Depends(require_role("ANALYST", "DEVELOPER", "PLATFORM_ADMIN", "SUPER_ADMIN"))],
)
async def submit_prompt(body: PromptRequest, request: Request):
    user_id: str = request.state.user_id
    role: str = request.state.user_role
    session_id: str = request.state.session_id

    # 1. Hash raw prompt for audit (pre-redaction)
    raw_hash = hashlib.sha256(body.prompt.encode()).hexdigest()

    # 2. Redact PII
    redacted_prompt, entities = _pii_detector.redact(body.prompt)

    # 3. Store token mappings
    for ent in entities:
        _token_store.put(
            token=ent.token,
            value=ent.value,
            entity_type=ent.entity_type.value,
            session_id=session_id,
        )

    # 4. Hash redacted prompt for audit
    redacted_hash = hashlib.sha256(redacted_prompt.encode()).hexdigest()

    # 5. Build role-scoped system prompt
    ctx = SessionContext(
        user_id=user_id,
        role=role,
        session_id=session_id,
        approved_datasets=body.approved_datasets,
        approved_tools=body.approved_tools,
    )
    system_prompt = build_system_prompt(ctx)

    # 6. Emit audit record (in production this writes to append-only store)
    audit = AuditRecord(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_id=user_id,
        user_role=role,
        session_id=session_id,
        request_hash=raw_hash,
        redacted_prompt_hash=redacted_hash,
        pii_tokens_present=[e.token for e in entities],
    )

    # 7. Return the prepared payload for the downstream LLM call
    #    (actual model call wired in Phase 2)
    return {
        "audit_event_id": audit.event_id,
        "system_prompt": system_prompt,
        "redacted_prompt": redacted_prompt,
        "pii_detected": len(entities) > 0,
        "pii_token_count": len(entities),
    }
