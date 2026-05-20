"""FastAPI gateway for user requests."""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Any
import uuid
from datetime import datetime

from src.utils.config import settings
from src.utils.logging import configure_logging, get_logger
from src.gateway.sanitizer import InputSanitizer
from src.gateway.auth import AuthManager, TokenData, get_current_user, ROLES
from src.gateway.middleware import limiter, rate_limit_exceeded_handler, RateLimitExceededError
from src.orchestrator.coordinator import TaskCoordinator
from src.memory.redis_store import RedisStore

# Configure logging
configure_logging()
logger = get_logger(__name__)

# Module-level singletons initialised in lifespan
redis_store: RedisStore
coordinator: TaskCoordinator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and graceful shutdown."""
    global redis_store, coordinator

    # -- Startup --
    logger.info("api_starting")
    redis_store = RedisStore()
    coordinator = TaskCoordinator(redis_store)
    logger.info("api_ready", host=settings.api_host, port=settings.api_port)

    yield

    # -- Shutdown --
    logger.info("api_shutting_down")
    active = list(coordinator.active_tasks.values())
    if active:
        logger.info("shutdown_waiting_for_tasks", count=len(active))
        try:
            await asyncio.wait_for(
                asyncio.gather(*active, return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.warning("shutdown_timeout_cancelling_remaining_tasks")
            for t in coordinator.active_tasks.values():
                t.cancel()
    await redis_store.close()
    logger.info("api_stopped")


# Initialize FastAPI app
app = FastAPI(
    title="Fintech Multi-Agent Orchestrator",
    description="Supervisor-pattern multi-agent system for fintech solutions teams",
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
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


# Request/Response Models
class TaskRequest(BaseModel):
    """Request to submit a task."""
    task: str = Field(..., description="Task description")
    session_id: Optional[str] = Field(None, description="Session ID for continuity")
    context: Optional[dict[str, Any]] = Field(None, description="Additional context")
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
        role = current_user.role if current_user else "ops_read"

        logger.info(
            "task_submitted",
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            role=role,
            task_length=len(sanitized_task),
        )

        # Inject role into context so agents can enforce table-level restrictions
        if sanitized_context is None:
            sanitized_context = {}
        sanitized_context["_role"] = role

        # Submit to coordinator (async processing)
        await coordinator.submit_task(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            task=sanitized_task,
            context=sanitized_context,
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
        return await redis_store.get_session_history(session_id)
    except Exception as e:
        logger.error("session_retrieval_failed", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.delete("/api/task/{task_id}")
@limiter.limit("20/minute")
async def cancel_task(
    request: Request,
    task_id: str,
    current_user: Optional[TokenData] = Depends(get_current_user),
):
    """Cancel a running task. Returns 404 if not found or already complete."""
    cancelled = await coordinator.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Task not found or already completed")
    return {"task_id": task_id, "status": "cancelled"}


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
async def create_token(
    request: Request,
    user_id: str,
    role: str = "ops_read",
    session_id: Optional[str] = None,
):
    """Create an authentication token (dev endpoint -- no password required).

    Valid roles: ops_read, ops_write, risk_read, admin
    """
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Unknown role '{role}'. Valid: {ROLES}")
    session_id = session_id or str(uuid.uuid4())
    token = AuthManager.create_session_token(user_id, session_id, role=role)
    return {"access_token": token, "token_type": "bearer", "session_id": session_id, "role": role}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.gateway.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )
