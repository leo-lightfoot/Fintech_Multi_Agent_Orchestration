"""Task coordinator — submits tasks to the graph and tracks active runs."""
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from src.orchestrator.state import create_initial_state, OrchestratorState, TaskStatus
from src.orchestrator.graph import OrchestrationGraph
from src.memory.redis_store import RedisStore
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TaskCoordinator:
    """Accepts task submissions and drives them through the orchestration graph."""

    def __init__(self, redis_store: RedisStore):
        self.redis_store = redis_store
        self.graph = OrchestrationGraph()
        self.active_tasks: Dict[str, asyncio.Task] = {}

    async def submit_task(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        logger.info("task_submitted", task_id=task_id, session_id=session_id, user_id=user_id)

        initial_state = create_initial_state(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            task=task,
            context=context,
            budget_limit_usd=settings.budget_limit_usd,
        )

        await self.redis_store.save_task_state(task_id, initial_state)

        coro = self._process_task(task_id, initial_state)
        self.active_tasks[task_id] = asyncio.create_task(coro)

    async def _process_task(self, task_id: str, initial_state: OrchestratorState) -> None:
        try:
            logger.info("processing_task", task_id=task_id)
            final_state = await self.graph.run(initial_state)
            await self.redis_store.save_task_state(task_id, final_state)

            await self.redis_store.add_to_session_history(
                final_state["session_id"],
                task_id,
                {
                    "task": final_state["task"],
                    "status": final_state["status"],
                    "intent": final_state.get("intent"),
                    "agents": final_state.get("agents_selected", []),
                    "result": final_state.get("final_response"),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            )

            logger.info("task_completed", task_id=task_id, status=final_state["status"])

        except Exception as exc:
            logger.error("task_processing_failed", task_id=task_id, error=str(exc), exc_info=True)
            initial_state["status"] = TaskStatus.FAILED
            initial_state["errors"].append(str(exc))
            await self.redis_store.save_task_state(task_id, initial_state)

        finally:
            self.active_tasks.pop(task_id, None)

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        state = await self.redis_store.get_task_state(task_id)
        if not state:
            return None

        return {
            "task_id": task_id,
            "status": state["status"],
            "phase": state["phase"],
            "progress": state["progress"],
            "intent": state.get("intent"),
            "agents_selected": state.get("agents_selected", []),
            "result": state.get("final_response"),
            "error": state["errors"][-1] if state.get("errors") else None,
            "created_at": state["created_at"],
            "updated_at": state["updated_at"],
        }

    async def cancel_task(self, task_id: str) -> bool:
        if task_id in self.active_tasks:
            self.active_tasks[task_id].cancel()
            self.active_tasks.pop(task_id, None)
            logger.info("task_cancelled", task_id=task_id)
            return True
        return False
