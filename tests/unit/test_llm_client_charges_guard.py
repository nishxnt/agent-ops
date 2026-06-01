import pytest

from agentops.budget.context import current_budget_guard
from agentops.budget.guard import BudgetGuard
from agentops.llm.client import LLMClient
from agentops.llm.models import LLMRequest, LLMResponse


class FakeLLMClient(LLMClient):
    def __init__(self, *, prompt_tokens: int = 10, completion_tokens: int = 20) -> None:
        super().__init__(model="test-model")
        self._p = prompt_tokens
        self._c = completion_tokens

    async def _do_complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="ok",
            model=self.model,
            prompt_tokens=self._p,
            completion_tokens=self._c,
        )


@pytest.mark.asyncio
async def test_complete_charges_guard_when_set() -> None:
    guard = BudgetGuard(1000)
    token = current_budget_guard.set(guard)
    try:
        await FakeLLMClient().complete(
            LLMRequest(
                messages=[{"role": "user", "content": "x"}],
                model="test-model",
                agent_type="test",
            )
        )
    finally:
        current_budget_guard.reset(token)

    assert guard.spent == 30
    assert guard.per_agent_spend == {"test": 30}


@pytest.mark.asyncio
async def test_complete_does_not_charge_when_guard_unset() -> None:
    assert current_budget_guard.get() is None

    response = await FakeLLMClient().complete(
        LLMRequest(
            messages=[{"role": "user", "content": "x"}],
            model="test-model",
            agent_type="test",
        )
    )

    assert response.content == "ok"
