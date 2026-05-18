"""Authentication and authorization utilities."""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from pydantic import BaseModel
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

ALGORITHM = "HS256"


class TokenData(BaseModel):
    """Token payload data."""
    user_id: str
    session_id: Optional[str] = None
    exp: Optional[datetime] = None


class AuthManager:
    """Handles JWT token creation and verification."""
    
    @staticmethod
    def create_access_token(
        data: dict,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token.
        
        Args:
            data: Data to encode in the token
            expires_delta: Token expiration time
            
        Returns:
            Encoded JWT token
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.api_secret_key,
            algorithm=ALGORITHM
        )
        
        logger.info(
            "access_token_created",
            user_id=data.get("user_id"),
            expires_at=expire.isoformat()
        )
        
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[TokenData]:
        """Verify and decode a JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            TokenData if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                settings.api_secret_key,
                algorithms=[ALGORITHM]
            )
            
            user_id: str = payload.get("user_id")
            if user_id is None:
                logger.warning("token_missing_user_id")
                return None
            
            return TokenData(
                user_id=user_id,
                session_id=payload.get("session_id"),
                exp=datetime.fromtimestamp(payload.get("exp"))
            )
            
        except JWTError as e:
            logger.warning("token_verification_failed", error=str(e))
            return None
    
    @staticmethod
    def create_session_token(user_id: str, session_id: str) -> str:
        """Create a session-specific token.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            
        Returns:
            JWT token
        """
        return AuthManager.create_access_token(
            data={"user_id": user_id, "session_id": session_id},
            expires_delta=timedelta(minutes=settings.session_timeout_minutes)
        )
