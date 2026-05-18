"""Audit trail -- append-only log of every agent action.

Every time an agent runs, the orchestrator writes one AuditEntry to Redis.
The log is intentionally append-only: entries are never deleted or edited,
only added. This gives a full compliance trace of who asked what, which agents
ran, what data was accessed, and what it cost.

Stored in Redis as a sorted set keyed by session:
    audit:{session_id}   score=unix_timestamp   member=json(AuditEntry)
"""
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


class AuditEntry(BaseModel):
    """A single audit record for one agent action within a task."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    task_id: str
    session_id: str
    user_id: str
    role: str = "ops"

    # What happened
    action: str          # e.g. "agent_executed", "validation_passed", "task_failed"
    agent: str           # e.g. "data", "risk", "validator"

    # What data was touched (best-effort -- populated from agent result metadata)
    data_accessed: list[str] = Field(default_factory=list)

    # Outcome
    status: str = "success"   # success | error | stub
    result_summary: str = ""  # first 200 chars of the agent output
    cost_usd: float = 0.0


class AuditTrail:
    """Writes and retrieves AuditEntry records via RedisStore."""

    def __init__(self, redis_store):
        # redis_store is passed in from the coordinator -- avoids a circular import
        self._store = redis_store

    async def log(self, entry: AuditEntry) -> None:
        """Append one entry to the session audit log (fire-and-forget)."""
        if self._store is None:
            return
        try:
            await self._store.save_audit_entry(entry.session_id, entry.model_dump())
            logger.debug(
                "audit_entry_written",
                task_id=entry.task_id,
                agent=entry.agent,
                action=entry.action,
            )
        except Exception as exc:
            # Audit failures must never crash the main flow
            logger.error("audit_write_failed", error=str(exc))

    async def get_log(
        self, session_id: str, limit: int = 200
    ) -> list[dict]:
        """Return up to `limit` entries for a session, newest first."""
        if self._store is None:
            return []
        try:
            return await self._store.get_audit_log(session_id, limit)
        except Exception as exc:
            logger.error("audit_read_failed", error=str(exc))
            return []
