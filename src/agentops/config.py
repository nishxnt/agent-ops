"""Configuration primitives for AgentOps development modes."""

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentOpsMode(StrEnum):
    """Supported execution modes."""

    MOCK = "mock"
    LOCAL = "local"
    CLOUD = "cloud"


class Settings(BaseSettings):
    """Environment-backed runtime settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mode: AgentOpsMode = Field(default=AgentOpsMode.MOCK, alias="AGENTOPS_MODE")
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    llm_generation_model: str = Field(
        default="qwen2.5:7b", alias="LLM_GENERATION_MODEL"
    )
    llm_evaluation_model: str = Field(
        default="llama3.1:8b", alias="LLM_EVALUATION_MODEL"
    )
    search_cache_dir: str = Field(
        default=".agentops-cache/search", alias="AGENTOPS_SEARCH_CACHE_DIR"
    )
    search_cache_ttl_seconds: int = Field(
        default=2_592_000, alias="AGENTOPS_SEARCH_CACHE_TTL_SECONDS"
    )


def get_settings() -> Settings:
    """Load settings from the current environment."""

    return Settings()
