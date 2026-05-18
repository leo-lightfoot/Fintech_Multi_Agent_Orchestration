"""Redis-backed state store for persistence and recovery."""
from typing import Dict, Any, Optional, List
import json
import redis.asyncio as redis
from datetime import datetime, timedelta

from src.orchestrator.state import OrchestratorState
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RedisStore:
    """Redis-backed store for task state and session management."""
    
    def __init__(self):
        """Initialize Redis connection."""
        self.redis: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self):
        """Establish Redis connection."""
        try:
            self.redis = redis.from_url(
                settings.redis_url,
                password=settings.redis_password,
                db=settings.redis_db,
                decode_responses=True,
                encoding="utf-8"
            )
            logger.info("redis_connected", url=settings.redis_url)
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise
    
    async def health_check(self) -> bool:
        """Check if Redis is connected and responding.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self.redis:
                return False
            await self.redis.ping()
            return True
        except Exception as e:
            logger.error("redis_health_check_failed", error=str(e))
            return False
    
    async def save_task_state(
        self,
        task_id: str,
        state: OrchestratorState
    ) -> bool:
        """Save task state to Redis.
        
        Args:
            task_id: Task identifier
            state: Current task state
            
        Returns:
            True if successful
        """
        try:
            # Update timestamp
            state["updated_at"] = datetime.utcnow()
            
            # Serialize state
            state_json = self._serialize_state(state)
            
            # Save to Redis with TTL
            key = f"task:{task_id}"
            await self.redis.setex(
                key,
                timedelta(hours=24),  # 24 hour TTL
                state_json
            )
            
            # Add to session index
            session_key = f"session:{state['session_id']}:tasks"
            await self.redis.sadd(session_key, task_id)
            await self.redis.expire(session_key, timedelta(hours=24))
            
            logger.debug("task_state_saved", task_id=task_id)
            return True
        
        except Exception as e:
            logger.error(
                "task_state_save_failed",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def get_task_state(self, task_id: str) -> Optional[OrchestratorState]:
        """Retrieve task state from Redis.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task state or None if not found
        """
        try:
            key = f"task:{task_id}"
            state_json = await self.redis.get(key)
            
            if not state_json:
                logger.debug("task_state_not_found", task_id=task_id)
                return None
            
            state = self._deserialize_state(state_json)
            logger.debug("task_state_retrieved", task_id=task_id)
            
            return state
        
        except Exception as e:
            logger.error(
                "task_state_retrieval_failed",
                task_id=task_id,
                error=str(e)
            )
            return None
    
    async def add_to_session_history(
        self,
        session_id: str,
        task_id: str,
        task_data: Dict[str, Any]
    ) -> bool:
        """Add task to session history.
        
        Args:
            session_id: Session identifier
            task_id: Task identifier
            task_data: Task summary data
            
        Returns:
            True if successful
        """
        try:
            key = f"session:{session_id}:history"
            
            # Store as sorted set with timestamp score
            timestamp = datetime.utcnow().timestamp()
            task_json = json.dumps(task_data, default=str)
            
            await self.redis.zadd(
                key,
                {f"{task_id}:{task_json}": timestamp}
            )
            
            # Set TTL
            await self.redis.expire(key, timedelta(days=7))
            
            logger.debug("session_history_updated", session_id=session_id)
            return True
        
        except Exception as e:
            logger.error(
                "session_history_update_failed",
                session_id=session_id,
                error=str(e)
            )
            return False
    
    async def get_session_history(
        self,
        session_id: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Retrieve session history.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of tasks to return
            
        Returns:
            Session history data
        """
        try:
            # Get task list
            tasks_key = f"session:{session_id}:tasks"
            task_ids = await self.redis.smembers(tasks_key)
            
            # Get history
            history_key = f"session:{session_id}:history"
            history_entries = await self.redis.zrevrange(
                history_key,
                0,
                limit - 1,
                withscores=True
            )
            
            history_items = []
            for entry, timestamp in history_entries:
                # Parse task_id and data
                if ':' in entry:
                    task_id, task_json = entry.split(':', 1)
                    task_data = json.loads(task_json)
                    task_data['task_id'] = task_id
                    task_data['timestamp'] = datetime.fromtimestamp(timestamp).isoformat()
                    history_items.append(task_data)
            
            return {
                "session_id": session_id,
                "task_count": len(task_ids),
                "history": history_items
            }
        
        except Exception as e:
            logger.error(
                "session_history_retrieval_failed",
                session_id=session_id,
                error=str(e)
            )
            return {
                "session_id": session_id,
                "task_count": 0,
                "history": [],
                "error": str(e)
            }
    
    async def save_checkpoint(
        self,
        task_id: str,
        checkpoint_name: str,
        checkpoint_data: Dict[str, Any]
    ) -> bool:
        """Save a checkpoint for recovery.
        
        Args:
            task_id: Task identifier
            checkpoint_name: Name of the checkpoint
            checkpoint_data: Data to save
            
        Returns:
            True if successful
        """
        try:
            key = f"checkpoint:{task_id}:{checkpoint_name}"
            data_json = json.dumps(checkpoint_data, default=str)
            
            await self.redis.setex(
                key,
                timedelta(hours=24),
                data_json
            )
            
            logger.info(
                "checkpoint_saved",
                task_id=task_id,
                checkpoint=checkpoint_name
            )
            return True
        
        except Exception as e:
            logger.error(
                "checkpoint_save_failed",
                task_id=task_id,
                checkpoint=checkpoint_name,
                error=str(e)
            )
            return False
    
    async def load_checkpoint(
        self,
        task_id: str,
        checkpoint_name: str
    ) -> Optional[Dict[str, Any]]:
        """Load a checkpoint for recovery.
        
        Args:
            task_id: Task identifier
            checkpoint_name: Name of the checkpoint
            
        Returns:
            Checkpoint data or None
        """
        try:
            key = f"checkpoint:{task_id}:{checkpoint_name}"
            data_json = await self.redis.get(key)
            
            if not data_json:
                return None
            
            return json.loads(data_json)
        
        except Exception as e:
            logger.error(
                "checkpoint_load_failed",
                task_id=task_id,
                checkpoint=checkpoint_name,
                error=str(e)
            )
            return None
    
    def _serialize_state(self, state: OrchestratorState) -> str:
        """Serialize state to JSON.
        
        Args:
            state: Orchestrator state
            
        Returns:
            JSON string
        """
        # Convert Pydantic models and enums to dicts/strings
        serializable = {}
        
        for key, value in state.items():
            if hasattr(value, 'model_dump'):
                # Pydantic model
                serializable[key] = value.model_dump()
            elif hasattr(value, 'value'):
                # Enum
                serializable[key] = value.value
            elif isinstance(value, (list, dict, str, int, float, bool, type(None))):
                serializable[key] = value
            else:
                serializable[key] = str(value)
        
        return json.dumps(serializable, default=str)
    
    def _deserialize_state(self, state_json: str) -> OrchestratorState:
        """Deserialize state from JSON.
        
        Args:
            state_json: JSON string
            
        Returns:
            Orchestrator state
        """
        # Parse JSON
        data = json.loads(state_json)
        
        # Reconstruct state
        # Note: This is simplified. In production, properly reconstruct
        # Pydantic models and enums
        
        return data
    
    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("redis_connection_closed")
