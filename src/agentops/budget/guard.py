"""Per-run token budget guard."""


class BudgetExceededError(Exception):
    """Raised when a charge would push spend past the configured budget.

    The offending LLM call already happened; check_and_charge raises before
    incrementing self.spent, so self.spent <= self.budget is always preserved.
    The "lost" call is sunk cost.
    """

    def __init__(
        self,
        *,
        spent: int,
        budget: int,
        agent_type: str,
        attempted: int,
    ) -> None:
        super().__init__(
            f"Budget exceeded: agent={agent_type} attempted={attempted} "
            f"spent={spent} budget={budget}"
        )
        self.spent = spent
        self.budget = budget
        self.agent_type = agent_type
        self.attempted = attempted


class BudgetGuard:
    """Track token spend and reject charges beyond the configured budget."""

    def __init__(self, budget_tokens: int) -> None:
        self.budget = budget_tokens
        self.spent = 0
        self.per_agent_spend: dict[str, int] = {}

    def check_and_charge(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
        agent_type: str,
    ) -> None:
        cost = prompt_tokens + completion_tokens
        if self.spent + cost > self.budget:
            raise BudgetExceededError(
                spent=self.spent,
                budget=self.budget,
                agent_type=agent_type,
                attempted=cost,
            )
        self.spent += cost
        self.per_agent_spend[agent_type] = (
            self.per_agent_spend.get(agent_type, 0) + cost
        )
