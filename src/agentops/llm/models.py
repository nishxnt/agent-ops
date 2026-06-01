"""Shared LLM request and response models."""

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    """Provider-neutral chat completion request."""

    messages: list[dict[str, str]]
    model: str
    max_tokens: int = 1024
    temperature: float = 0.0
    agent_type: str = Field(
        default="unknown",
        description=(
            "The agent calling this request. Production callers must set this "
            'explicitly; "unknown" is a safety net.'
        ),
    )


class LLMResponse(BaseModel):
    """Provider-neutral chat completion response."""

    content: str
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class LLMError(Exception):
    """Provider-neutral LLM exception."""

    def __init__(self, message: str, provider: str) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
