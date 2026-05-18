"""Provider-agnostic LLM factory.

Usage:
    from src.utils.llm import get_llm

    llm = get_llm()                          # uses settings defaults
    llm = get_llm(model="claude-opus-4-7")   # override model only
"""
from langchain_core.language_models import BaseChatModel
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    """Return a LangChain chat model for the configured provider.

    Args:
        provider: Override the LLM_PROVIDER setting.
        model: Override the LLM_MODEL setting.
        temperature: Override the LLM_TEMPERATURE setting.

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: If the provider is not recognised.
        ImportError: If the provider's LangChain package is not installed.
    """
    provider = provider or settings.llm_provider
    model = model or settings.llm_model
    temperature = temperature if temperature is not None else settings.llm_temperature

    logger.debug("creating_llm", provider=provider, model=model)

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise ImportError(
                "langchain-anthropic is required for the anthropic provider. "
                "Run: pip install langchain-anthropic"
            ) from e
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=settings.llm_api_key,
        )

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise ImportError(
                "langchain-openai is required for the openai provider. "
                "Run: pip install langchain-openai"
            ) from e
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=settings.llm_api_key,
        )

    if provider == "azure_openai":
        try:
            from langchain_openai import AzureChatOpenAI
        except ImportError as e:
            raise ImportError(
                "langchain-openai is required for the azure_openai provider. "
                "Run: pip install langchain-openai"
            ) from e
        return AzureChatOpenAI(
            azure_deployment=model,
            temperature=temperature,
            api_key=settings.llm_api_key,
        )

    raise ValueError(
        f"Unknown LLM provider: '{provider}'. "
        "Valid options: anthropic, openai, azure_openai"
    )
