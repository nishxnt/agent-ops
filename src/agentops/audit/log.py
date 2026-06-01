"""Append-only hash-chained audit log backed by SQLite."""

import hashlib
import json
import sqlite3
from pathlib import Path

from agentops.audit.schema import AuditEntry

GENESIS_PREV_HASH = ""


class AuditLogger:
    """Append-only hash-chained audit log backed by SQLite.

    The public API intentionally exposes only append(), query_by_run_id(), and
    verify_chain(). There are no update or delete methods.

    The chain is per-run: entry N's prev_hash references entry N-1's entry_hash
    within the same run_id. Different runs have independent chains.

    Tamper-evidence: modifying any historical row breaks the chain because
    entry_hash is derived from the full row contents plus prev_hash.
    verify_chain() recomputes and detects mismatches.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        schema_sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(schema_sql)
            conn.commit()

    def append(self, entry: AuditEntry) -> str:
        """Append one entry. Returns its entry_hash. Transactional."""

        with sqlite3.connect(self.db_path) as conn:
            prev_hash = self._last_hash_for_run(conn, entry.run_id)
            entry_hash = _compute_entry_hash(entry, prev_hash)
            conn.execute(
                """INSERT INTO audit_log (
                    run_id, agent_type, timestamp_utc, input_hash,
                    output_hash, model_id, model_version, latency_ms,
                    prompt_tokens, completion_tokens, confidence_score,
                    reasoning_trace, parent_run_id, status,
                    prev_hash, entry_hash
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry.run_id,
                    entry.agent_type,
                    entry.timestamp_utc,
                    entry.input_hash,
                    entry.output_hash,
                    entry.model_id,
                    entry.model_version,
                    entry.latency_ms,
                    entry.prompt_tokens,
                    entry.completion_tokens,
                    entry.confidence_score,
                    entry.reasoning_trace,
                    entry.parent_run_id,
                    entry.status,
                    prev_hash,
                    entry_hash,
                ),
            )
            conn.commit()
            return entry_hash

    def query_by_run_id(self, run_id: str) -> list[AuditEntry]:
        """Return entries for a run in insertion order."""

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return [
            AuditEntry(**{key: row[key] for key in AuditEntry.model_fields})
            for row in rows
        ]

    def verify_chain(self, run_id: str) -> bool:
        """Re-derive entry hashes and check they match stored values.

        Returns False on any mismatch (tamper detected).
        """

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM audit_log WHERE run_id = ?
                   ORDER BY id ASC""",
                (run_id,),
            ).fetchall()

        prev = GENESIS_PREV_HASH
        for row in rows:
            entry = AuditEntry(**{key: row[key] for key in AuditEntry.model_fields})
            expected = _compute_entry_hash(entry, prev)
            if expected != row["entry_hash"] or row["prev_hash"] != prev:
                return False
            prev = row["entry_hash"]
        return True

    def _last_hash_for_run(self, conn: sqlite3.Connection, run_id: str) -> str:
        row = conn.execute(
            """SELECT entry_hash FROM audit_log WHERE run_id = ?
               ORDER BY id DESC LIMIT 1""",
            (run_id,),
        ).fetchone()
        return str(row[0]) if row else GENESIS_PREV_HASH


def _compute_entry_hash(entry: AuditEntry, prev_hash: str) -> str:
    """Compute SHA-256 over canonical(entry) + '|' + prev_hash."""

    canonical = json.dumps(entry.model_dump(), sort_keys=True, default=str)
    payload = f"{prev_hash}|{canonical}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
