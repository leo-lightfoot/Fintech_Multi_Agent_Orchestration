"""Recovery utilities for handling interruptions and failures."""
from typing import Optional, Dict, Any
from datetime import datetime

from src.memory.redis_store import RedisStore
from src.orchestrator.state import OrchestratorState, TaskStatus, Phase
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RecoveryManager:
    """Manages task recovery from interruptions."""
    
    def __init__(self, redis_store: RedisStore):
        """Initialize recovery manager.
        
        Args:
            redis_store: Redis store instance
        """
        self.redis_store = redis_store
    
    async def can_recover(self, task_id: str) -> bool:
        """Check if a task can be recovered.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if recoverable
        """
        state = await self.redis_store.get_task_state(task_id)
        
        if not state:
            return False
        
        # Can recover if not completed or failed
        status = state.get("status")
        return status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]
    
    async def recover_task(self, task_id: str) -> Optional[OrchestratorState]:
        """Recover a task from saved state.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Recovered state or None
        """
        logger.info("attempting_task_recovery", task_id=task_id)
        
        # Get saved state
        state = await self.redis_store.get_task_state(task_id)
        
        if not state:
            logger.warning("no_saved_state_found", task_id=task_id)
            return None
        
        # Check if already completed
        if state.get("status") in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            logger.info("task_already_complete", task_id=task_id)
            return state
        
        # Update recovery metadata
        if "metadata" not in state:
            state["metadata"] = {}
        
        state["metadata"]["recovered"] = True
        state["metadata"]["recovered_at"] = datetime.utcnow().isoformat()
        state["metadata"]["previous_status"] = state.get("status")
        
        logger.info(
            "task_recovered",
            task_id=task_id,
            phase=state.get("phase"),
            status=state.get("status")
        )
        
        return state
    
    async def create_recovery_checkpoint(
        self,
        task_id: str,
        state: OrchestratorState,
        checkpoint_name: str
    ) -> bool:
        """Create a recovery checkpoint.
        
        Args:
            task_id: Task identifier
            state: Current state
            checkpoint_name: Name for this checkpoint
            
        Returns:
            True if successful
        """
        checkpoint_data = {
            "task_id": task_id,
            "phase": state["phase"],
            "status": state["status"],
            "progress": state["progress"],
            "checkpoint_name": checkpoint_name,
            "created_at": datetime.utcnow().isoformat()
        }
        
        return await self.redis_store.save_checkpoint(
            task_id,
            checkpoint_name,
            checkpoint_data
        )
    
    async def list_checkpoints(self, task_id: str) -> list[str]:
        """List available checkpoints for a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            List of checkpoint names
        """
        # Common checkpoint names
        checkpoint_names = [
            "planning_complete",
            "execution_start",
            "validation_start",
            "summarization_complete"
        ]
        
        available = []
        for name in checkpoint_names:
            checkpoint = await self.redis_store.load_checkpoint(task_id, name)
            if checkpoint:
                available.append(name)
        
        return available
