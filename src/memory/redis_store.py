"""Redis-backed state store for task state and session history."""
from typing import Any, Optional
import json
import redis.asyncio as redis
from datetime import datetime, timedelta

from src.orchestrator.state import OrchestratorState, CostTracking, ValidationResult
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RedisStore:
    """Redis-backed store for task state and session management."""

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self._connect()

    def _connect(self):
        try:
            self.redis = redis.from_url(
                settings.redis_url,
                password=settings.redis_password,
                db=settings.redis_db,
                decode_responses=True,
                encoding="utf-8",
            )
            logger.info("redis_connected", url=settings.redis_url)
        except Exception as exc:
            logger.error("redis_connection_failed", error=str(exc))
            raise

    async def health_check(self) -> bool:
        try:
            if not self.redis:
                return False
            await self.redis.ping()
            return True
        except Exception as exc:
            logger.error("redis_health_check_failed", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Task state
    # ------------------------------------------------------------------

    async def save_task_state(self, task_id: str, state: OrchestratorState) -> bool:
        try:
            state["updated_at"] = datetime.utcnow()
            state_json = self._serialize_state(state)

            await self.redis.setex(f"task:{task_id}", timedelta(hours=24), state_json)

            session_key = f"session:{state['session_id']}:tasks"
            await self.redis.sadd(session_key, task_id)
            await self.redis.expire(session_key, timedelta(hours=24))

            logger.debug("task_state_saved", task_id=task_id)
            return True
        except Exception as exc:
            logger.error("task_state_save_failed", task_id=task_id, error=str(exc), exc_info=True)
            return False

    async def get_task_state(self, task_id: str) -> Optional[OrchestratorState]:
        try:
            state_json = await self.redis.get(f"task:{task_id}")
            if not state_json:
                logger.debug("task_state_not_found", task_id=task_id)
                return None
            state = self._deserialize_state(state_json)
            logger.debug("task_state_retrieved", task_id=task_id)
            return state
        except Exception as exc:
            logger.error("task_state_retrieval_failed", task_id=task_id, error=str(exc))
            return None

    # ------------------------------------------------------------------
    # Session history
    # ------------------------------------------------------------------

    async def add_to_session_history(
        self, session_id: str, task_id: str, task_data: dict[str, Any]
    ) -> bool:
        try:
            key = f"session:{session_id}:history"
            timestamp = datetime.utcnow().timestamp()
            task_json = json.dumps(task_data, default=str)
            await self.redis.zadd(key, {f"{task_id}:{task_json}": timestamp})
            await self.redis.expire(key, timedelta(days=7))
            logger.debug("session_history_updated", session_id=session_id)
            return True
        except Exception as exc:
            logger.error("session_history_update_failed", session_id=session_id, error=str(exc))
            return False

    async def get_session_history(self, session_id: str, limit: int = 100) -> dict[str, Any]:
        try:
            task_ids = await self.redis.smembers(f"session:{session_id}:tasks")
            entries = await self.redis.zrevrange(
                f"session:{session_id}:history", 0, limit - 1, withscores=True
            )

            history_items = []
            for entry, timestamp in entries:
                if ":" in entry:
                    tid, task_json = entry.split(":", 1)
                    data = json.loads(task_json)
                    data["task_id"] = tid
                    data["timestamp"] = datetime.fromtimestamp(timestamp).isoformat()
                    history_items.append(data)

            return {
                "session_id": session_id,
                "task_count": len(task_ids),      # total tasks ever submitted
                "history": history_items,          # up to `limit` most recent
            }
        except Exception as exc:
            logger.error("session_history_retrieval_failed", session_id=session_id, error=str(exc))
            return {"session_id": session_id, "task_count": 0, "history": [], "error": str(exc)}

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    async def save_audit_entry(self, session_id: str, entry: dict) -> None:
        """Append one audit entry to the session log (sorted set, score = timestamp)."""
        try:
            from datetime import timezone
            key = f"audit:{session_id}"
            score = datetime.now(timezone.utc).timestamp()
            await self.redis.zadd(key, {json.dumps(entry, default=str): score})
            # Audit log kept for 90 days
            await self.redis.expire(key, timedelta(days=90))
        except Exception as exc:
            logger.error("audit_save_failed", session_id=session_id, error=str(exc))

    async def get_audit_log(self, session_id: str, limit: int = 200) -> list[dict]:
        """Return up to `limit` audit entries for a session, newest first."""
        try:
            raw = await self.redis.zrevrange(f"audit:{session_id}", 0, limit - 1)
            return [json.loads(r) for r in raw]
        except Exception as exc:
            logger.error("audit_read_failed", session_id=session_id, error=str(exc))
            return []

    async def close(self):
        if self.redis:
            await self.redis.close()
            logger.info("redis_connection_closed")

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _serialize_state(self, state: OrchestratorState) -> str:
        serializable: dict[str, Any] = {}
        for key, value in state.items():
            if hasattr(value, "model_dump"):
                serializable[key] = value.model_dump()
            elif hasattr(value, "value"):        # Enum
                serializable[key] = value.value
            elif isinstance(value, (list, dict, str, int, float, bool, type(None))):
                serializable[key] = value
            else:
                serializable[key] = str(value)
        return json.dumps(serializable, default=str)

    def _deserialize_state(self, state_json: str) -> OrchestratorState:
        """Reconstruct OrchestratorState from JSON, restoring Pydantic models."""
        data: dict = json.loads(state_json)

        # Reconstruct CostTracking -- coordinator calls .within_budget() on it
        if isinstance(data.get("cost_tracking"), dict):
            data["cost_tracking"] = CostTracking(**data["cost_tracking"])

        # Reconstruct ValidationResult if present
        if isinstance(data.get("validation_result"), dict):
            data["validation_result"] = ValidationResult(**data["validation_result"])

        return data  # type: ignore[return-value]
