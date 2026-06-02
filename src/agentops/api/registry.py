"""In-memory run registry for asynchronous API execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class RunRecord:
    run_id: str
    query: str
    status: str
    submitted_at: datetime
    completed_at: datetime | None = None
    final_state: Any = None
    error: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class RunRegistry:
    """In-memory tracking of pipeline runs. Single-process scope only."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()

    async def register(self, run_id: str, query: str) -> RunRecord:
        async with self._lock:
            record = RunRecord(
                run_id=run_id,
                query=query,
                status="PENDING",
                submitted_at=datetime.now(UTC),
            )
            self._runs[run_id] = record
            return record

    async def attach_task(self, run_id: str, task: asyncio.Task[None]) -> None:
        async with self._lock:
            self._runs[run_id].task = task
            self._runs[run_id].status = "RUNNING"

    async def mark_complete(self, run_id: str, final_state: Any) -> None:
        async with self._lock:
            record = self._runs[run_id]
            record.status = "COMPLETED"
            record.completed_at = datetime.now(UTC)
            record.final_state = final_state

    async def mark_failed(self, run_id: str, error: str) -> None:
        async with self._lock:
            record = self._runs[run_id]
            record.status = "FAILED"
            record.completed_at = datetime.now(UTC)
            record.error = error

    async def get(self, run_id: str) -> RunRecord | None:
        async with self._lock:
            return self._runs.get(run_id)

    async def wait_for_completion(
        self,
        run_id: str,
        timeout: float = 10.0,
    ) -> RunRecord:
        """Test helper: await the underlying task with a timeout."""

        record = self._runs.get(run_id)
        if record is None or record.task is None:
            raise KeyError(run_id)
        try:
            await asyncio.wait_for(asyncio.shield(record.task), timeout=timeout)
        except TimeoutError:
            pass
        return self._runs[run_id]
