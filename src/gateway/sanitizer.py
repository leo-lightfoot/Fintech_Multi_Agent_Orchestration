"""Input sanitization utilities."""
import re
from typing import Any, Dict
import html
import bleach
from src.utils.logging import get_logger

logger = get_logger(__name__)


class InputSanitizer:
    """Sanitizes user input to prevent injection attacks."""
    
    # Patterns to detect potential threats
    SQL_INJECTION_PATTERN = re.compile(
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)",
        re.IGNORECASE
    )
    
    COMMAND_INJECTION_PATTERN = re.compile(
        r"[;&|`$(){}[\]<>]"
    )
    
    MAX_INPUT_LENGTH = 50000
    
    @classmethod
    def sanitize_text(cls, text: str, allow_html: bool = False) -> str:
        """Sanitize text input.
        
        Args:
            text: Raw input text
            allow_html: Whether to allow safe HTML tags
            
        Returns:
            Sanitized text
        """
        if not isinstance(text, str):
            text = str(text)
        
        # Check length
        if len(text) > cls.MAX_INPUT_LENGTH:
            logger.warning(
                "input_too_long",
                length=len(text),
                max_length=cls.MAX_INPUT_LENGTH
            )
            text = text[:cls.MAX_INPUT_LENGTH]
        
        # Remove null bytes
        text = text.replace('\x00', '')
        
        if allow_html:
            # Allow only safe HTML tags
            text = bleach.clean(
                text,
                tags=['p', 'br', 'strong', 'em', 'u', 'code', 'pre'],
                strip=True
            )
        else:
            # Escape HTML
            text = html.escape(text)
        
        return text.strip()
    
    @classmethod
    def check_for_injections(cls, text: str) -> tuple[bool, list[str]]:
        """Check for potential injection attacks.
        
        Returns:
            (is_safe, list of detected threats)
        """
        threats = []
        
        if cls.SQL_INJECTION_PATTERN.search(text):
            threats.append("potential_sql_injection")
        
        if cls.COMMAND_INJECTION_PATTERN.search(text):
            threats.append("potential_command_injection")
        
        is_safe = len(threats) == 0
        
        if not is_safe:
            logger.warning(
                "injection_attempt_detected",
                threats=threats,
                input_preview=text[:100]
            )
        
        return is_safe, threats
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary values.
        
        Args:
            data: Dictionary with potentially unsafe values
            
        Returns:
            Sanitized dictionary
        """
        sanitized = {}
        
        for key, value in data.items():
            # Sanitize keys
            safe_key = cls.sanitize_text(str(key), allow_html=False)
            
            # Sanitize values
            if isinstance(value, str):
                sanitized[safe_key] = cls.sanitize_text(value, allow_html=False)
            elif isinstance(value, dict):
                sanitized[safe_key] = cls.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[safe_key] = [
                    cls.sanitize_text(str(item), allow_html=False)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                sanitized[safe_key] = value
        
        return sanitized
