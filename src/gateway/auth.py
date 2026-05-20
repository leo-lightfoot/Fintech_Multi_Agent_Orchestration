"""Authentication, authorization, and role-based access control."""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Role hierarchy -- higher index = more access
ROLES = ["ops_read", "ops_write", "risk_read", "admin"]

# Tables each role may query. admin and ops_write get everything.
ROLE_TABLE_ALLOWLIST: dict[str, set[str]] = {
    "ops_read":  {"funds", "positions", "nav_history", "trades"},
    "ops_write": {"funds", "positions", "nav_history", "trades", "limit_rules"},
    "risk_read": {"funds", "positions", "limit_rules", "nav_history"},
    "admin":     {"funds", "positions", "nav_history", "trades", "limit_rules"},
}


class TokenData(BaseModel):
    """JWT token payload."""
    user_id: str
    session_id: Optional[str] = None
    role: str = "ops_read"
    exp: Optional[datetime] = None


class AuthManager:
    """JWT token creation and verification."""

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode["exp"] = expire
        token = jwt.encode(to_encode, settings.api_secret_key, algorithm=ALGORITHM)
        logger.info("access_token_created", user_id=data.get("user_id"), role=data.get("role"))
        return token

    @staticmethod
    def verify_token(token: str) -> Optional[TokenData]:
        try:
            payload = jwt.decode(token, settings.api_secret_key, algorithms=[ALGORITHM])
            user_id = payload.get("user_id")
            if not user_id:
                return None
            return TokenData(
                user_id=user_id,
                session_id=payload.get("session_id"),
                role=payload.get("role", "ops_read"),
                exp=datetime.fromtimestamp(payload["exp"]) if payload.get("exp") else None,
            )
        except JWTError as exc:
            logger.warning("token_verification_failed", error=str(exc))
            return None

    @staticmethod
    def create_session_token(user_id: str, session_id: str, role: str = "ops_read") -> str:
        return AuthManager.create_access_token(
            data={"user_id": user_id, "session_id": session_id, "role": role},
            expires_delta=timedelta(minutes=settings.session_timeout_minutes),
        )


# ------------------------------------------------------------------
# FastAPI dependencies
# ------------------------------------------------------------------

async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> Optional[TokenData]:
    """Extract and verify the Bearer token. Returns None if absent or invalid."""
    if not authorization:
        return None
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
        return AuthManager.verify_token(token)
    except Exception as exc:
        logger.warning("auth_header_parse_failed", error=str(exc))
        return None


def require_role(*roles: str):
    """FastAPI dependency factory that enforces a minimum role.

    Usage:
        @app.get("/api/sensitive")
        async def endpoint(user = Depends(require_role("risk_read", "admin"))):
            ...
    """
    async def _check(current_user: Optional[TokenData] = Depends(get_current_user)):
        if current_user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if current_user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user.role}' is not permitted. Required: {list(roles)}",
            )
        return current_user
    return _check


def allowed_tables(role: str) -> set[str]:
    """Return the set of DB tables this role may query."""
    return ROLE_TABLE_ALLOWLIST.get(role, set())
