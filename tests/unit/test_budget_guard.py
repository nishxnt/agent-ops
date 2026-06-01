import pytest

from agentops.budget.guard import BudgetExceededError, BudgetGuard


def test_allows_within_budget() -> None:
    guard = BudgetGuard(100)

    guard.check_and_charge(
        prompt_tokens=10,
        completion_tokens=20,
        model="test-model",
        agent_type="planner",
    )

    assert guard.spent == 30


def test_raises_when_exceeded() -> None:
    guard = BudgetGuard(100)
    guard.check_and_charge(
        prompt_tokens=30,
        completion_tokens=30,
        model="test-model",
        agent_type="planner",
    )

    with pytest.raises(BudgetExceededError):
        guard.check_and_charge(
            prompt_tokens=25,
            completion_tokens=25,
            model="test-model",
            agent_type="researcher",
        )

    assert guard.spent == 60


def test_per_agent_spend_attribution() -> None:
    guard = BudgetGuard(100)

    guard.check_and_charge(
        prompt_tokens=10,
        completion_tokens=10,
        model="test-model",
        agent_type="planner",
    )
    guard.check_and_charge(
        prompt_tokens=15,
        completion_tokens=15,
        model="test-model",
        agent_type="researcher",
    )
    guard.check_and_charge(
        prompt_tokens=5,
        completion_tokens=5,
        model="test-model",
        agent_type="planner",
    )

    assert guard.per_agent_spend == {"planner": 30, "researcher": 30}
    assert guard.spent == 60


def test_error_attributes() -> None:
    guard = BudgetGuard(40)

    with pytest.raises(BudgetExceededError) as exc_info:
        guard.check_and_charge(
            prompt_tokens=20,
            completion_tokens=30,
            model="test-model",
            agent_type="critic",
        )

    exc = exc_info.value
    assert exc.spent == 0
    assert exc.budget == 40
    assert exc.agent_type == "critic"
    assert exc.attempted == 50
