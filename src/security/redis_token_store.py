"""
Redis-backed PII token mapping store.

Tokens are stored with TTL = session lifetime so they are automatically
evicted when the session ends.  The store is write-once per token — there
is no update path, matching the immutability requirement.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_DEFAULT_SESSION_TTL_SECONDS = int(
    os.environ.get("PII_TOKEN_TTL_SECONDS", str(60 * 60))  # 1 hour default
)

_KEY_PREFIX = "pii_token:"


class PIITokenStore:
    """
    Stores PII token → original value mappings in Redis.

    Usage::

        store = PIITokenStore()
        store.put(token="<PII_TOKEN_7F3A>", value="john@example.com",
                  entity_type="EMAIL", session_id="sess_abc123")
        record = store.get("<PII_TOKEN_7F3A>")
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_SESSION_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._client: Optional["redis.Redis"] = None
        if _REDIS_AVAILABLE:
            self._client = redis.from_url(_REDIS_URL, decode_responses=True)

    # ------------------------------------------------------------------
    # Write (once)
    # ------------------------------------------------------------------

    def put(
        self,
        *,
        token: str,
        value: str,
        entity_type: str,
        session_id: str,
    ) -> None:
        """Store a PII token mapping. Silently skips if token already exists."""
        key = _KEY_PREFIX + token
        record = {
            "value": value,
            "type": entity_type,
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if self._client:
            # SET NX ensures write-once semantics
            self._client.set(key, json.dumps(record), ex=self._ttl, nx=True)
        else:
            # In-process fallback for unit tests / environments without Redis
            if not hasattr(self, "_mem"):
                self._mem: dict = {}
            if key not in self._mem:
                self._mem[key] = record

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, token: str) -> Optional[dict]:
        """Return the record for a token, or None if not found / expired."""
        key = _KEY_PREFIX + token
        if self._client:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        # In-process fallback
        if hasattr(self, "_mem"):
            return self._mem.get(key)
        return None

    # ------------------------------------------------------------------
    # Session cleanup (explicit, in addition to TTL auto-eviction)
    # ------------------------------------------------------------------

    def delete_session(self, session_id: str) -> int:
        """
        Remove all tokens belonging to a session.
        Returns the number of keys deleted.
        Only available when Redis is present (scan is not supported by the
        in-process fallback).
        """
        if not self._client:
            return 0
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = self._client.scan(
                cursor, match=f"{_KEY_PREFIX}*", count=100
            )
            for key in keys:
                raw = self._client.get(key)
                if raw:
                    record = json.loads(raw)
                    if record.get("session_id") == session_id:
                        self._client.delete(key)
                        deleted += 1
            if cursor == 0:
                break
        return deleted

    # ------------------------------------------------------------------
    # Health probe
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        if self._client:
            try:
                return self._client.ping()
            except Exception:
                return False
        return True  # in-process store is always "healthy"
