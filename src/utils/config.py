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
    
    # LLM Configuration
    openai_api_key: str
    openai_model: str = "gpt-4-turbo-preview"
    openai_temperature: float = 0.7
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    redis_db: int = 0
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str
    debug: bool = False
    
    # Agent Configuration
    max_iterations: int = 3
    max_retry_attempts: int = 3
    budget_limit_usd: float = 10.0
    context_window_limit: int = 128000
    
    # Code Execution
    code_execution_timeout: int = 60
    enable_code_execution: bool = True
    docker_enabled: bool = True
    
    # Session Management
    session_timeout_minutes: int = 60
    max_concurrent_sessions: int = 100
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Monitoring
    prometheus_enabled: bool = False
    prometheus_port: int = 9090


# Global settings instance
settings = Settings()
