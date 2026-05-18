"""Input sanitization utilities.

Two separate concerns:
  - check_for_injections()  : safe for natural-language task descriptions.
                              Only checks for shell/XSS threats, NOT SQL keywords,
                              because ops users legitimately say things like
                              "select the top 10 funds" or "create a report".
  - validate_sql_param()    : strict check for raw strings that will be used
                              inside a database query.
"""
import re
from typing import Any, Dict
import html
import bleach
from src.utils.logging import get_logger

logger = get_logger(__name__)


class InputSanitizer:
    """Sanitizes user input to prevent injection attacks."""

    # Shell / OS command injection -- still dangerous in natural language context
    COMMAND_INJECTION_PATTERN = re.compile(r"[;&|`$(){}[\]<>]")

    # SQL keywords -- only used when validating raw query parameters, NOT task text
    SQL_INJECTION_PATTERN = re.compile(
        r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|TRUNCATE)\b",
        re.IGNORECASE,
    )

    MAX_INPUT_LENGTH = 50_000

    @classmethod
    def sanitize_text(cls, text: str, allow_html: bool = False) -> str:
        """Sanitize a text string: trim length, strip null bytes, escape HTML.

        Safe for natural language -- does not reject SQL vocabulary.
        """
        if not isinstance(text, str):
            text = str(text)

        if len(text) > cls.MAX_INPUT_LENGTH:
            logger.warning("input_too_long", length=len(text), max_length=cls.MAX_INPUT_LENGTH)
            text = text[: cls.MAX_INPUT_LENGTH]

        text = text.replace("\x00", "")

        if allow_html:
            text = bleach.clean(
                text,
                tags=["p", "br", "strong", "em", "u", "code", "pre"],
                strip=True,
            )
        else:
            text = html.escape(text)

        return text.strip()

    @classmethod
    def check_for_injections(cls, text: str) -> tuple[bool, list[str]]:
        """Check a natural-language task description for threats.

        Detects shell/command injection and XSS only.
        SQL keywords are intentionally NOT flagged here -- ops users write
        phrases like "select funds", "create a report", "drop the date filter".

        Returns:
            (is_safe, list of detected threat labels)
        """
        threats: list[str] = []

        if cls.COMMAND_INJECTION_PATTERN.search(text):
            threats.append("potential_command_injection")

        is_safe = len(threats) == 0

        if not is_safe:
            logger.warning(
                "injection_attempt_detected",
                threats=threats,
                input_preview=text[:100],
            )

        return is_safe, threats

    # Patterns dangerous inside an otherwise-valid SELECT query
    DANGEROUS_QUERY_PATTERN = re.compile(
        r"(;|UNION\s+SELECT|--|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b"
        r"|\bEXEC\b|\bEXECUTE\b|\bTRUNCATE\b|\bALTER\b|/\*)",
        re.IGNORECASE,
    )

    @classmethod
    def validate_sql_query(cls, query: str) -> tuple[bool, list[str]]:
        """Validate a SQL query string for dangerous constructs.

        Allows normal SELECT syntax (WHERE, JOIN, ORDER BY, GROUP BY, etc.)
        but blocks multi-statement injection, UNION attacks, and DDL/DML keywords
        that have no place inside a SELECT.

        Returns:
            (is_safe, list of detected threat labels)
        """
        threats: list[str] = []

        if cls.DANGEROUS_QUERY_PATTERN.search(query):
            threats.append("potential_sql_injection")

        if cls.COMMAND_INJECTION_PATTERN.search(query):
            threats.append("potential_command_injection")

        is_safe = len(threats) == 0
        if not is_safe:
            logger.warning("sql_query_injection_detected", threats=threats, query_preview=query[:100])

        return is_safe, threats

    @classmethod
    def validate_sql_param(cls, value: str) -> tuple[bool, list[str]]:
        """Strict check for a string that will be interpolated into a SQL query.

        Use this inside sql_tool before passing any user-supplied value to the DB.
        Checks both SQL keywords AND command injection characters.

        Returns:
            (is_safe, list of detected threat labels)
        """
        threats: list[str] = []

        if cls.SQL_INJECTION_PATTERN.search(value):
            threats.append("potential_sql_injection")

        if cls.COMMAND_INJECTION_PATTERN.search(value):
            threats.append("potential_command_injection")

        is_safe = len(threats) == 0

        if not is_safe:
            logger.warning(
                "sql_param_injection_detected",
                threats=threats,
                value_preview=value[:100],
            )

        return is_safe, threats

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary values (used for the context payload)."""
        sanitized: Dict[str, Any] = {}

        for key, value in data.items():
            safe_key = cls.sanitize_text(str(key), allow_html=False)

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
