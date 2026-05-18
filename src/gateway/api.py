"""FastAPI gateway for user requests."""
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uuid
from datetime import datetime

from src.utils.config import settings
from src.utils.logging import configure_logging, get_logger
from src.gateway.sanitizer import InputSanitizer
from src.gateway.auth import AuthManager, TokenData
from src.gateway.middleware import limiter, rate_limit_exceeded_handler, RateLimitExceededError
from src.orchestrator.coordinator import TaskCoordinator
from src.memory.redis_store import RedisStore

# Configure logging
configure_logging()
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Fintech Multi-Agent Orchestrator",
    description="Supervisor-pattern multi-agent system for fintech solutions teams",
    version="1.0.0",
    debug=settings.debug,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)

# CORS -- localhost only for this learning project
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
redis_store = RedisStore()
coordinator = TaskCoordinator(redis_store)


# Request/Response Models
class TaskRequest(BaseModel):
    """Request to submit a task."""
    task: str = Field(..., description="Task description")
    session_id: Optional[str] = Field(None, description="Session ID for continuity")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    user_id: Optional[str] = Field(None, description="User identifier")


class TaskResponse(BaseModel):
    """Response after task submission."""
    task_id: str
    session_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response."""
    task_id: str
    status: str
    phase: str
    progress: float
    intent: Optional[str] = None
    agents_selected: list = []
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    redis_connected: bool
    timestamp: datetime


# Dependency for authentication
async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> Optional[TokenData]:
    """Verify authentication token.
    
    For demo purposes, this is optional. In production, make it required.
    """
    if not authorization:
        return None
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
        
        token_data = AuthManager.verify_token(token)
        return token_data
    
    except Exception as e:
        logger.warning("auth_failed", error=str(e))
        return None


# API Routes
@app.get("/", response_model=HealthResponse)
@limiter.limit("100/minute")
async def root(request: Request):
    """Root endpoint with health check."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        redis_connected=await redis_store.health_check(),
        timestamp=datetime.utcnow()
    )


@app.get("/health", response_model=HealthResponse)
@limiter.limit("100/minute")
async def health_check(request: Request):
    """Health check endpoint."""
    redis_ok = await redis_store.health_check()
    return HealthResponse(
        status="healthy" if redis_ok else "degraded",
        version="1.0.0",
        redis_connected=redis_ok,
        timestamp=datetime.utcnow()
    )


@app.post("/api/task", response_model=TaskResponse)
@limiter.limit("20/minute")
async def submit_task(
    request: Request,
    body: TaskRequest,
    current_user: Optional[TokenData] = Depends(get_current_user)
):
    """Submit a new task for processing.
    
    Args:
        request: Task request with description and optional context
        current_user: Authenticated user (optional for demo)
        
    Returns:
        Task submission response with task_id and session_id
    """
    try:
        # Sanitize input
        sanitized_task = InputSanitizer.sanitize_text(body.task)

        # Check for injections
        is_safe, threats = InputSanitizer.check_for_injections(sanitized_task)
        if not is_safe:
            logger.warning(
                "unsafe_input_rejected",
                threats=threats,
                user_id=current_user.user_id if current_user else None
            )
            raise HTTPException(
                status_code=400,
                detail=f"Input rejected due to security concerns: {', '.join(threats)}"
            )

        # Sanitize context if provided
        sanitized_context = None
        if body.context:
            sanitized_context = InputSanitizer.sanitize_dict(body.context)

        # Generate IDs
        task_id = str(uuid.uuid4())
        session_id = body.session_id or str(uuid.uuid4())
        user_id = (current_user.user_id if current_user
                   else body.user_id or "anonymous")
        
        logger.info(
            "task_submitted",
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            task_length=len(sanitized_task)
        )
        
        # Submit to coordinator (async processing)
        await coordinator.submit_task(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            task=sanitized_task,
            context=sanitized_context
        )
        
        return TaskResponse(
            task_id=task_id,
            session_id=session_id,
            status="submitted",
            message="Task submitted successfully and is being processed"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("task_submission_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/task/{task_id}", response_model=TaskStatusResponse)
@limiter.limit("100/minute")
async def get_task_status(
    request: Request,
    task_id: str,
    current_user: Optional[TokenData] = Depends(get_current_user)
):
    """Get the status of a task.
    
    Args:
        task_id: Task identifier
        current_user: Authenticated user (optional)
        
    Returns:
        Current task status and progress
    """
    try:
        status = await coordinator.get_task_status(task_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return TaskStatusResponse(**status)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("status_check_failed", task_id=task_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/session/{session_id}")
@limiter.limit("100/minute")
async def get_session_history(
    request: Request,
    session_id: str,
    current_user: Optional[TokenData] = Depends(get_current_user)
):
    """Get the history and state of a session.
    
    Args:
        session_id: Session identifier
        current_user: Authenticated user (optional)
        
    Returns:
        Session data including all tasks and state
    """
    try:
        history = await redis_store.get_session_history(session_id)
        
        if not history:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return history
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("session_retrieval_failed", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/audit/{session_id}")
@limiter.limit("100/minute")
async def get_audit_log(
    request: Request,
    session_id: str,
    limit: int = 100,
    current_user: Optional[TokenData] = Depends(get_current_user),
):
    """Return the audit log for a session -- every agent action recorded."""
    try:
        entries = await redis_store.get_audit_log(session_id, limit=limit)
        return {"session_id": session_id, "count": len(entries), "entries": entries}
    except Exception as e:
        logger.error("audit_retrieval_failed", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/auth/token")
@limiter.limit("10/minute")
async def create_token(request: Request, user_id: str, session_id: Optional[str] = None):
    """Create an authentication token (demo endpoint).
    
    In production, this would require actual authentication.
    """
    session_id = session_id or str(uuid.uuid4())
    token = AuthManager.create_session_token(user_id, session_id)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "session_id": session_id
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.gateway.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )
