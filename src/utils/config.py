"""Configuration management using Pydantic settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # LLM Configuration (provider-agnostic)
    llm_provider: str = "anthropic"          # anthropic | openai | azure_openai
    llm_api_key: str = "your-api-key-here"   # set LLM_API_KEY in .env
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.7

    # Legacy alias -- still accepted if someone has OPENAI_API_KEY in their .env
    openai_api_key: Optional[str] = None

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    redis_db: int = 0

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "dev-secret-key-change-in-production"
    debug: bool = False

    # Agent Configuration
    max_retry_attempts: int = 1   # reduced from 3 -- one retry is enough
    budget_limit_usd: float = 10.0
    context_window_limit: int = 200000  # Claude's context window

    # Session Management
    session_timeout_minutes: int = 60
    max_concurrent_sessions: int = 100

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Database -- placeholder SQLite by default, swap for real DWH in production
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "fintech_placeholder"
    db_user: str = ""
    db_password: str = ""

    # Document store
    docs_path: str = "data/docs"
    vector_store_path: str = "data/chroma"

    # Monitoring
    prometheus_enabled: bool = False
    prometheus_port: int = 9090


def _validate() -> "Settings":
    s = Settings()
    if s.llm_api_key == "your-api-key-here":
        import warnings
        warnings.warn(
            "LLM_API_KEY is still the placeholder value. "
            "Set a real key in .env before making LLM calls.",
            stacklevel=2,
        )
    return s


# Global settings instance
settings = _validate()
