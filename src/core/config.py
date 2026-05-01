"""Typed settings loaded from .env via pydantic-settings.

Single ``load_dotenv`` happens implicitly through ``BaseSettings``. Import
``settings`` anywhere in the codebase; never read ``os.environ`` directly.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed environment-backed settings for the entire app."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # MongoDB Atlas
    mongodb_uri: str = Field(..., alias="MONGODB_URI")
    mongodb_db: str = Field("agent_coalitions", alias="MONGODB_DB")

    # OpenAI (chat may be routed through OpenRouter via OPENAI_BASE_URL +
    # OPENAI_API_KEY=sk-or-...; embeddings still require OpenAI proper).
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(None, alias="OPENAI_BASE_URL")
    openai_embedding_api_key: str | None = Field(None, alias="OPENAI_EMBEDDING_API_KEY")
    openai_embedding_model: str = Field(
        "text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )
    openai_chat_model: str = Field("gpt-4o-mini", alias="OPENAI_CHAT_MODEL")

    # Pipeline
    use_mock_llm: bool = Field(True, alias="USE_MOCK_LLM")
    seed: int = Field(42, alias="SEED")


@lru_cache(maxsize=1)
def _load() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings: Settings = _load()
