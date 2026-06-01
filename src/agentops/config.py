"""Configuration primitives for AgentOps execution modes."""

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentOpsMode(StrEnum):
    """Supported execution modes."""

    MOCK = "mock"
    LOCAL = "local"
    CLOUD = "cloud"


class LLMRole(StrEnum):
    """LLM roles that intentionally use different model families."""

    GENERATION = "generation"
    EVALUATION = "evaluation"


class Settings(BaseSettings):
    """Environment-backed runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )

    mode: AgentOpsMode = Field(default=AgentOpsMode.MOCK, alias="AGENTOPS_MODE")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    llm_generation_model: str = Field(
        default="llama-3.3-70b-versatile", alias="LLM_GENERATION_MODEL"
    )
    llm_evaluation_model: str = Field(
        default="mixtral-8x7b-32768", alias="LLM_EVALUATION_MODEL"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    local_generation_model: str = Field(
        default="qwen2.5:7b", alias="LOCAL_GENERATION_MODEL"
    )
    local_evaluation_model: str = Field(
        default="llama3.1:8b", alias="LOCAL_EVALUATION_MODEL"
    )
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="agentops", alias="LANGSMITH_PROJECT")
    langsmith_tracing: bool = Field(default=True, alias="LANGSMITH_TRACING")
    default_token_budget: int = Field(default=50_000, alias="DEFAULT_TOKEN_BUDGET")
    budget_token_limit: int = Field(default=50_000, alias="BUDGET_TOKEN_LIMIT")
    researcher_timeout_secs: int = Field(default=30, alias="RESEARCHER_TIMEOUT_SECS")
    max_recovery_attempts: int = Field(default=2, alias="MAX_RECOVERY_ATTEMPTS")
    quality_gate_max_revisions: int = Field(
        default=2, alias="QUALITY_GATE_MAX_REVISIONS"
    )
    search_cache_dir: str = Field(
        default=".agentops-cache/search", alias="AGENTOPS_SEARCH_CACHE_DIR"
    )
    search_cache_ttl_seconds: int = Field(
        default=2_592_000, alias="AGENTOPS_SEARCH_CACHE_TTL_SECONDS"
    )
    audit_db_path: str = Field(default=".data/audit.db", alias="AUDIT_DB_PATH")

    def model_for(self, role: LLMRole) -> str:
        """Return the configured model for a role in the active execution mode."""

        if self.mode is AgentOpsMode.CLOUD:
            models = {
                LLMRole.GENERATION: self.llm_generation_model,
                LLMRole.EVALUATION: self.llm_evaluation_model,
            }
        else:
            models = {
                LLMRole.GENERATION: self.local_generation_model,
                LLMRole.EVALUATION: self.local_evaluation_model,
            }

        generation_model = models[LLMRole.GENERATION]
        evaluation_model = models[LLMRole.EVALUATION]
        if generation_model == evaluation_model:
            msg = "Generation and evaluation models must be different."
            raise ValueError(msg)

        return models[role]


def get_settings() -> Settings:
    """Load settings from the current environment."""

    return Settings()
