import re
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentops.audit.log import GENESIS_PREV_HASH, AuditLogger
from agentops.audit.schema import AuditEntry


@pytest.fixture
def logger(tmp_path: Path) -> AuditLogger:
    return AuditLogger(db_path=tmp_path / "audit.sqlite")


def _make_entry(
    run_id: str = "run-A",
    status: str = "SUCCESS",
    **overrides: object,
) -> AuditEntry:
    defaults = dict(
        run_id=run_id,
        agent_type="planner",
        timestamp_utc="2026-06-01T00:00:00Z",
        input_hash="a" * 64,
        output_hash="b" * 64,
        model_id="qwen2.5:7b",
        model_version="qwen2.5:7b",
        latency_ms=42,
        prompt_tokens=10,
        completion_tokens=20,
        status=status,
    )
    defaults.update(overrides)
    return AuditEntry(**defaults)


def test_audit_entry_is_frozen() -> None:
    entry = _make_entry()

    with pytest.raises(ValidationError):
        entry.run_id = "other"  # type: ignore[misc]


def test_init_creates_schema(logger: AuditLogger) -> None:
    with sqlite3.connect(logger.db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("audit_log",),
        ).fetchone()

    assert row is not None


def test_append_returns_64_char_hex_hash(logger: AuditLogger) -> None:
    entry_hash = logger.append(_make_entry())

    assert re.fullmatch(r"[0-9a-f]{64}", entry_hash) is not None


def test_first_entry_has_empty_prev_hash(logger: AuditLogger) -> None:
    logger.append(_make_entry())

    with sqlite3.connect(logger.db_path) as conn:
        row = conn.execute("SELECT prev_hash FROM audit_log").fetchone()

    assert row[0] == GENESIS_PREV_HASH


def test_second_entry_chains_to_first(logger: AuditLogger) -> None:
    logger.append(_make_entry())
    logger.append(_make_entry(output_hash="c" * 64))

    with sqlite3.connect(logger.db_path) as conn:
        rows = conn.execute(
            "SELECT prev_hash, entry_hash FROM audit_log ORDER BY id ASC"
        ).fetchall()

    assert rows[1][0] == rows[0][1]


def test_chains_independent_per_run_id(logger: AuditLogger) -> None:
    logger.append(_make_entry(run_id="run-a"))
    logger.append(_make_entry(run_id="run-b", output_hash="c" * 64))
    logger.append(_make_entry(run_id="run-a", output_hash="d" * 64))

    with sqlite3.connect(logger.db_path) as conn:
        run_b_first = conn.execute(
            """SELECT prev_hash FROM audit_log
               WHERE run_id = ? ORDER BY id ASC LIMIT 1""",
            ("run-b",),
        ).fetchone()

    assert run_b_first[0] == GENESIS_PREV_HASH
    assert logger.verify_chain("run-a") is True
    assert logger.verify_chain("run-b") is True


def test_verify_chain_detects_tampering(logger: AuditLogger) -> None:
    logger.append(_make_entry())
    logger.append(_make_entry(output_hash="c" * 64))
    logger.append(_make_entry(output_hash="d" * 64))

    with sqlite3.connect(logger.db_path) as conn:
        conn.execute(
            "UPDATE audit_log SET input_hash = ? WHERE id = ?",
            ("e" * 64, 2),
        )
        conn.commit()

    assert logger.verify_chain("run-A") is False
