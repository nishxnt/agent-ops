import json
from pathlib import Path

import pytest

from agentops.audit.context import current_audit_logger, current_run_id
from agentops.audit.log import AuditLogger
from agentops.budget.context import current_budget_guard
from agentops.budget.guard import BudgetExceededError, BudgetGuard
from agentops.llm.client import LLMClient
from agentops.llm.models import LLMRequest, LLMResponse


class FakeLLMClient(LLMClient):
    def __init__(self, *, prompt_tokens: int = 10, completion_tokens: int = 20) -> None:
        super().__init__(model="test-model")
        self._p = prompt_tokens
        self._c = completion_tokens

    async def _do_complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=json.dumps(request.messages, sort_keys=True),
            model=self.model,
            prompt_tokens=self._p,
            completion_tokens=self._c,
        )


@pytest.fixture
def audit_logger(tmp_path: Path) -> AuditLogger:
    return AuditLogger(db_path=tmp_path / "audit.sqlite")


def _set_audit_context(
    logger: AuditLogger,
    run_id: str,
) -> tuple[object, object]:
    """Set both contextvars; return tokens for reset."""

    log_token = current_audit_logger.set(logger)
    rid_token = current_run_id.set(run_id)
    return log_token, rid_token


def _request(content: str, *, agent_type: str = "planner") -> LLMRequest:
    return LLMRequest(
        messages=[{"role": "user", "content": content}],
        model="m",
        agent_type=agent_type,
    )


@pytest.mark.asyncio
async def test_audit_entry_written_per_call(audit_logger: AuditLogger) -> None:
    log_token, rid_token = _set_audit_context(audit_logger, "test-run")
    try:
        await FakeLLMClient(prompt_tokens=10, completion_tokens=20).complete(
            _request("x")
        )
    finally:
        current_run_id.reset(rid_token)
        current_audit_logger.reset(log_token)

    entries = audit_logger.query_by_run_id("test-run")
    assert len(entries) == 1
    assert entries[0].agent_type == "planner"
    assert entries[0].prompt_tokens == 10
    assert entries[0].completion_tokens == 20
    assert entries[0].status == "SUCCESS"
    assert entries[0].latency_ms >= 0


@pytest.mark.asyncio
async def test_audit_input_output_hashes_differ_per_call(
    audit_logger: AuditLogger,
) -> None:
    log_token, rid_token = _set_audit_context(audit_logger, "test-run")
    try:
        await FakeLLMClient().complete(_request("first"))
        await FakeLLMClient().complete(_request("second"))
    finally:
        current_run_id.reset(rid_token)
        current_audit_logger.reset(log_token)

    first, second = audit_logger.query_by_run_id("test-run")
    assert first.input_hash != second.input_hash
    assert first.output_hash != second.output_hash


@pytest.mark.asyncio
async def test_no_audit_when_logger_unset(audit_logger: AuditLogger) -> None:
    assert current_audit_logger.get() is None
    rid_token = current_run_id.set("test-run")
    try:
        await FakeLLMClient().complete(_request("x"))
    finally:
        current_run_id.reset(rid_token)

    assert audit_logger.query_by_run_id("test-run") == []


@pytest.mark.asyncio
async def test_no_audit_when_run_id_unset(audit_logger: AuditLogger) -> None:
    assert current_run_id.get() is None
    log_token = current_audit_logger.set(audit_logger)
    try:
        await FakeLLMClient().complete(_request("x"))
    finally:
        current_audit_logger.reset(log_token)

    assert audit_logger.query_by_run_id("test-run") == []


@pytest.mark.asyncio
async def test_audit_fires_before_budget_check(audit_logger: AuditLogger) -> None:
    log_token, rid_token = _set_audit_context(audit_logger, "test-run")
    budget_token = current_budget_guard.set(BudgetGuard(10))
    try:
        with pytest.raises(BudgetExceededError):
            await FakeLLMClient(prompt_tokens=10, completion_tokens=20).complete(
                _request("x")
            )
    finally:
        current_budget_guard.reset(budget_token)
        current_run_id.reset(rid_token)
        current_audit_logger.reset(log_token)

    entries = audit_logger.query_by_run_id("test-run")
    assert len(entries) == 1
    assert entries[0].status == "SUCCESS"
