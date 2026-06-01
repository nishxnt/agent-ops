from pathlib import Path

from agentops.config import AgentOpsMode, LLMRole, Settings


def test_settings_load_defaults() -> None:
    settings = Settings()

    assert settings.mode is AgentOpsMode.MOCK
    assert settings.default_token_budget == 50_000
    assert settings.budget_token_limit == 50_000
    assert settings.max_recovery_attempts == 2
    assert settings.audit_db_path == Path("./audit.sqlite")


def test_model_for_cloud_mode_uses_cloud_models() -> None:
    settings = Settings(mode=AgentOpsMode.CLOUD)

    generation_model = settings.model_for(LLMRole.GENERATION)
    evaluation_model = settings.model_for(LLMRole.EVALUATION)

    assert generation_model == "llama-3.3-70b-versatile"
    assert evaluation_model == "mixtral-8x7b-32768"
    assert generation_model != evaluation_model


def test_model_for_local_mode_uses_local_models() -> None:
    settings = Settings(mode=AgentOpsMode.LOCAL)

    generation_model = settings.model_for(LLMRole.GENERATION)
    evaluation_model = settings.model_for(LLMRole.EVALUATION)

    assert generation_model == "qwen2.5:7b"
    assert evaluation_model == "llama3.1:8b"
    assert generation_model != evaluation_model


def test_model_for_mock_mode_uses_local_model_labels() -> None:
    settings = Settings(mode=AgentOpsMode.MOCK)

    assert settings.model_for(LLMRole.GENERATION) == "qwen2.5:7b"
    assert settings.model_for(LLMRole.EVALUATION) == "llama3.1:8b"
