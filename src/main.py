"""
LLM Security Gateway — full pipeline (Phase 1 + 2).

Request flow:
  JWT validation → PII redaction → role-scoped system prompt injection
  → LLM call → output detokenization → audit log → response
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
from security.audit_logger import AuditLogger, AuditRecord
from security.output_detokenizer import OutputDetokenizer
from security.llm_gateway import complete as llm_complete, CompletionResult

app = FastAPI(title="LLM Security Gateway", version="2.0.0")
app.add_middleware(JWTRoleMiddleware)

_pii_detector = PIIDetector()
_token_store = PIITokenStore()
_audit_logger = AuditLogger()
_detokenizer = OutputDetokenizer(_token_store)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PromptRequest(BaseModel):
    prompt: str
    approved_datasets: list[str] = []
    approved_tools: list[str] = []


class PromptResponse(BaseModel):
    audit_event_id: str
    response: str
    pii_detected: bool
    pii_token_count: int
    unresolved_pii_tokens: list[str] = []
    compliance_flags: list[str] = []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "redis": _token_store.ping(),
        "audit_records": _audit_logger.count(),
    }


@app.post(
    "/v1/prompt",
    response_model=PromptResponse,
    dependencies=[Depends(require_role("ANALYST", "DEVELOPER", "PLATFORM_ADMIN", "SUPER_ADMIN"))],
)
async def submit_prompt(body: PromptRequest, request: Request):
    user_id: str = request.state.user_id
    role: str = request.state.user_role
    session_id: str = request.state.session_id
    event_id = str(uuid.uuid4())

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

    # 6. LLM call with secured payload
    result: CompletionResult = llm_complete(system_prompt, redacted_prompt)

    # 7. Detokenize response (only for PII-access roles)
    response_text, unresolved_tokens = _detokenizer.detokenize(result.text, role)

    # 8. Derive compliance flags
    compliance_flags: list[str] = []
    if unresolved_tokens:
        compliance_flags.append("UNRESOLVED_PII_TOKENS")

    # 9. Audit log (append-only)
    _audit_logger.log(AuditRecord(
        event_id=event_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_id=user_id,
        user_role=role,
        session_id=session_id,
        request_hash=raw_hash,
        redacted_prompt_hash=redacted_hash,
        pii_tokens_present=[e.token for e in entities],
        model_id=result.model_id,
        tool_calls=[],
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
        response_hash=hashlib.sha256(response_text.encode()).hexdigest(),
        compliance_flags=compliance_flags,
    ))

    return PromptResponse(
        audit_event_id=event_id,
        response=response_text,
        pii_detected=len(entities) > 0,
        pii_token_count=len(entities),
        unresolved_pii_tokens=unresolved_tokens,
        compliance_flags=compliance_flags,
    )


@app.get(
    "/v1/audit",
    dependencies=[Depends(require_role("PLATFORM_ADMIN", "SUPER_ADMIN"))],
)
async def get_audit_log(request: Request, limit: int = 50, offset: int = 0):
    role: str = request.state.user_role
    records = _audit_logger.query(caller_role=role, limit=limit, offset=offset)
    return {"total": _audit_logger.count(), "records": records}
