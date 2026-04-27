"""
A2H Decision Audit Trail — immutable event log for compliance.

Records every state-changing operation in the A2H system: request
creation, delivery, rerouting, delegation, response, cancellation,
and expiry. Events are append-only and queryable.

    from a2h.audit import InMemoryAuditLog

    audit = InMemoryAuditLog()
    gw = Gateway(audit_log=audit)

    # After some interactions...
    history = audit.get_history(request_id)
    recent = audit.query(participant="sales/sarah", limit=50)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from .models import AuditEvent, Interaction

logger = logging.getLogger(__name__)


def compute_response_time(interaction: Interaction) -> float | None:
    """Seconds between request creation and human response."""
    if not interaction.response or not interaction.response.responded_at:
        return None
    try:
        created = datetime.fromisoformat(interaction.created_at)
        responded = datetime.fromisoformat(interaction.response.responded_at)
        return (responded - created).total_seconds()
    except (ValueError, TypeError):
        return None


@runtime_checkable
class AuditLog(Protocol):
    """Append-only audit log for A2H decision events."""

    def record(self, event: AuditEvent) -> None: ...

    def get_history(self, interaction_id: str) -> list[AuditEvent]: ...

    def query(
        self,
        *,
        participant: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]: ...


class InMemoryAuditLog:
    """Reference implementation — stores events in an append-only list."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)
        logger.debug("A2H audit: %s %s %s", event.event_type, event.interaction_id, event.actor)

    def get_history(self, interaction_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.interaction_id == interaction_id]

    def query(
        self,
        *,
        participant: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        results = list(self._events)

        if event_type:
            results = [e for e in results if e.event_type == event_type]

        if participant:
            results = [e for e in results if participant in (
                e.actor,
                e.details.get("to"),
                e.details.get("from_target"),
                e.details.get("to_target"),
            )]

        if since:
            results = [e for e in results if e.timestamp >= since]

        if until:
            results = [e for e in results if e.timestamp <= until]

        return results[-limit:]

    def __len__(self) -> int:
        return len(self._events)
