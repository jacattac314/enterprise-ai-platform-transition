"""
JWT role-extraction middleware for FastAPI.

Reads the validated JWT from the Authorization header, extracts x-user-role,
and attaches it to request.state.  Role is NEVER read from the request body.
"""

import os
from typing import Optional

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

try:
    import jwt as pyjwt
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False

VALID_ROLES = frozenset(
    {"VIEWER", "ANALYST", "DEVELOPER", "PLATFORM_ADMIN", "SUPER_ADMIN"}
)

# Public key / secret sourced from environment — never hard-coded.
_JWT_SECRET = os.environ.get("JWT_SECRET", "")
_JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

# Paths that do not require a JWT (e.g. health probe)
_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class JWTRoleMiddleware(BaseHTTPMiddleware):
    """
    Validates the Bearer JWT and writes `user_id`, `user_role`, and
    `session_id` into request.state.  Rejects requests whose token is
    missing, expired, or carries an unrecognised role.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        token = _extract_bearer_token(request)
        if token is None:
            return _unauthorized("Missing Authorization header")

        claims = _decode_token(token)
        if claims is None:
            return _unauthorized("Invalid or expired JWT")

        role = claims.get("x-user-role") or claims.get("role")
        if role not in VALID_ROLES:
            return _forbidden(f"Unknown role: {role!r}")

        request.state.user_id = claims.get("sub", "")
        request.state.user_role = role
        request.state.session_id = claims.get("sid", "")

        return await call_next(request)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):]
    return None


def _decode_token(token: str) -> Optional[dict]:
    if not _JWT_AVAILABLE:
        # Graceful degradation in environments without PyJWT (e.g. unit tests
        # that inject state directly).  Real deployments must have PyJWT.
        return None
    if not _JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET environment variable is not set. "
            "Cannot validate tokens."
        )
    try:
        return pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": detail},
    )


# ---------------------------------------------------------------------------
# Convenience dependency (for routes that need the role explicitly)
# ---------------------------------------------------------------------------

def require_role(*allowed_roles: str):
    """FastAPI dependency that raises 403 if the caller's role is not allowed."""
    allowed = frozenset(allowed_roles)

    def _check(request: Request):
        role = getattr(request.state, "user_role", None)
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {role!r} is not permitted for this endpoint.",
            )
        return role

    return _check
