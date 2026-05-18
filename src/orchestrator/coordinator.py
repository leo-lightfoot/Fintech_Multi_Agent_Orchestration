"""Task coordinator that manages the orchestration graph."""
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from src.orchestrator.state import create_initial_state, OrchestratorState
from src.orchestrator.graph import OrchestrationGraph
from src.memory.redis_store import RedisStore
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TaskCoordinator:
    """Coordinates task submission and execution."""
    
    def __init__(self, redis_store: RedisStore):
        """Initialize the coordinator.
        
        Args:
            redis_store: Redis store for state persistence
        """
        self.redis_store = redis_store
        self.graph = OrchestrationGraph()
        self.active_tasks: Dict[str, asyncio.Task] = {}
    
    async def submit_task(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Submit a task for processing.
        
        Args:
            task_id: Unique task identifier
            session_id: Session identifier
            user_id: User identifier
            task: Task description
            context: Additional context
        """
        logger.info(
            "task_submitted_to_coordinator",
            task_id=task_id,
            session_id=session_id,
            user_id=user_id
        )
        
        # Create initial state
        initial_state = create_initial_state(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            task=task,
            context=context,
            budget_limit_usd=settings.budget_limit_usd
        )
        
        # Save initial state
        await self.redis_store.save_task_state(task_id, initial_state)
        
        # Start processing in background
        task_coro = self._process_task(task_id, initial_state)
        self.active_tasks[task_id] = asyncio.create_task(task_coro)
    
    async def _process_task(
        self,
        task_id: str,
        initial_state: OrchestratorState
    ) -> None:
        """Process a task through the orchestration graph.
        
        Args:
            task_id: Task identifier
            initial_state: Initial state
        """
        try:
            logger.info("processing_task", task_id=task_id)
            
            # Run through the graph
            final_state = await self.graph.run(initial_state)
            
            # Save final state
            await self.redis_store.save_task_state(task_id, final_state)
            
            # Update session history
            await self.redis_store.add_to_session_history(
                final_state["session_id"],
                task_id,
                {
                    "task": final_state["task"],
                    "status": final_state["status"],
                    "result": final_state.get("final_response"),
                    "completed_at": datetime.utcnow().isoformat()
                }
            )
            
            logger.info(
                "task_completed",
                task_id=task_id,
                status=final_state["status"],
                cost=final_state["cost_tracking"].total_cost_usd
            )
        
        except Exception as e:
            logger.error(
                "task_processing_failed",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )
            
            # Save error state
            initial_state["status"] = "failed"
            initial_state["errors"].append(str(e))
            await self.redis_store.save_task_state(task_id, initial_state)
        
        finally:
            # Clean up
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task status dictionary or None if not found
        """
        state = await self.redis_store.get_task_state(task_id)
        
        if not state:
            return None
        
        return {
            "task_id": task_id,
            "status": state["status"],
            "phase": state["phase"],
            "progress": state["progress"],
            "result": state.get("final_response"),
            "error": state["errors"][-1] if state["errors"] else None,
            "created_at": state["created_at"],
            "updated_at": state["updated_at"]
        }
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if cancelled, False if not found or already completed
        """
        if task_id in self.active_tasks:
            self.active_tasks[task_id].cancel()
            del self.active_tasks[task_id]
            
            logger.info("task_cancelled", task_id=task_id)
            return True
        
        return False
