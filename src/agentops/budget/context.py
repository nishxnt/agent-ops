"""Context-local active budget guard."""

from contextvars import ContextVar

from agentops.budget.guard import BudgetGuard

current_budget_guard: ContextVar[BudgetGuard | None] = ContextVar(
    "current_budget_guard",
    default=None,
)
