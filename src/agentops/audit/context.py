"""Context-local audit logging state."""

from contextvars import ContextVar

from agentops.audit.log import AuditLogger

current_audit_logger: ContextVar[AuditLogger | None] = ContextVar(
    "current_audit_logger",
    default=None,
)

current_run_id: ContextVar[str | None] = ContextVar(
    "current_run_id",
    default=None,
)
