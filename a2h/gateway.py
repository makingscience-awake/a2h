"""
A2H Gateway — the core protocol handler.

Manages participant registration, request creation, delivery, response
collection, delegation rule evaluation, and escalation chain progression.

This is the main entry point for A2H operations::

    gw = Gateway()
    gw.register(Participant(name="sarah", namespace="sales", type="human"))

    req = await gw.ask("sales/sarah", question="Approve?", response_type="approval")
    gw.respond(req.id, {"approved": True})
"""

from __future__ import annotations

import logging
import warnings
from datetime import datetime, timezone
from typing import Any

from .models import (
    DelegationRule,
    EscalationChain,
    Interaction,
    Notification,
    Option,
    Participant,
    Priority,
    Response,
    ResponseType,
    Status,
)
from .store import InMemoryStore, Store
from .channels import Channel, LogChannel
from .errors import DuplicateParticipant, ParticipantNotFound, SenderNotRegistered
from .registry import ParticipantRegistry

logger = logging.getLogger(__name__)


class Gateway:
    """A2H Protocol Gateway.

    Stateless protocol handler. Storage, delivery, and participant
    management are pluggable via ``Store``, ``Channel``, and
    ``ParticipantRegistry`` implementations.

    Args:
        store: Storage backend (default: InMemoryStore)
        channels: Delivery channels (default: [LogChannel()])
        registry: Pre-configured ParticipantRegistry instance.
        participants_file: Path to a participants.yaml file to load.
        registry_mode: Registry mode — "permissive" (default) or "strict".
    """

    def __init__(
        self,
        store: Store | None = None,
        channels: list[Channel] | None = None,
        *,
        registry: ParticipantRegistry | None = None,
        participants_file: str | None = None,
        registry_mode: str = "permissive",
    ):
        self._store: Store = store or InMemoryStore()
        self._channels: list[Channel] = channels or [LogChannel()]

        if registry is not None and participants_file is not None:
            raise ValueError("Cannot specify both 'registry' and 'participants_file'")

        if registry is not None:
            self._registry = registry
        elif participants_file is not None:
            self._registry = ParticipantRegistry(participants_file, mode=registry_mode)
        else:
            self._registry = ParticipantRegistry(mode=registry_mode)

    @property
    def registry(self) -> ParticipantRegistry:
        return self._registry

    # ---- Participant management --------------------------------------------

    def register(self, participant: Participant, *, allow_replace: bool = False) -> str:
        """Register a participant (human or agent). Returns PID."""
        return self._registry.register(participant, allow_replace=allow_replace)

    def unregister(self, pid: str, *, cascade: bool = False) -> bool:
        """Remove a participant from the registry.

        Args:
            pid: The participant ID ("namespace/name").
            cascade: If True, cancel pending interactions addressed to this
                participant and clear delegate references pointing to them.
        """
        if cascade:
            for interaction in self._store.list_pending(pid):
                self._store.cancel(interaction.id, f"Participant {pid} unregistered")
            for p in self._registry.list():
                if p.delegate_pid == pid:
                    p.delegate = None
        return self._registry.unregister(pid)

    def get_participant(self, pid: str) -> Participant | None:
        return self._registry.get(pid)

    def resolve(self, namespace: str, name: str) -> Participant | None:
        return self._registry.resolve(namespace, name)

    def list_participants(
        self,
        participant_type: str | None = None,
        namespace: str | None = None,
    ) -> list[Participant]:
        return self._registry.list(
            participant_type=participant_type, namespace=namespace
        )

    def discover(self, **filters) -> list[dict]:
        """Return Participant Cards for discovery (per A2H spec)."""
        return [p.to_card() for p in self.list_participants(**filters)]

    # ---- A2H: Agent asks human ---------------------------------------------

    async def ask(
        self,
        to: str,
        *,
        question: str,
        response_type: str = "text",
        options: list[dict] | None = None,
        context: dict | None = None,
        priority: str = "medium",
        deadline: str | None = None,
        sla_hours: float = 24.0,
        escalation: EscalationChain | None = None,
        from_participant: str | None = None,
        from_name: str = "",
        from_namespace: str = "default",
        strict: bool = True,
    ) -> Interaction:
        """Create an A2H request and deliver it.

        Args:
            to: Target PID ("namespace/name")
            question: The question to ask
            response_type: choice, approval, text, number, confirm, form
            options: For choice type — list of {"label", "value", "description"}
            context: Structured data to help the human decide
            priority: critical, high, medium, low
            deadline: ISO 8601 timestamp or duration ("4h", "1d")
            sla_hours: Fallback SLA if no deadline given
            escalation: Escalation chain definition
            from_participant: Registered sender PID ("namespace/name"). Preferred.
            from_name: (Deprecated) Sender agent name
            from_namespace: (Deprecated) Sender namespace
            strict: If True (default), raise ParticipantNotFound for unknown
                targets. If False, return a CANCELLED interaction instead.

        Returns:
            The created Interaction with its ID and status.

        Raises:
            SenderNotRegistered: if a sender identity is claimed but not
                registered.
            ParticipantNotFound: if strict=True and the target is not
                registered.
        """
        # Resolve sender identity
        from_name, from_namespace = self._resolve_sender(
            from_participant, from_name, from_namespace
        )

        # Resolve target
        to_ns, to_name = self._parse_pid(to)
        target = self.resolve(to_ns, to_name)

        if not target:
            if strict:
                raise ParticipantNotFound(
                    f"Participant '{to}' not found", pid=to
                )
            interaction = self._make_interaction(
                from_name, from_namespace, to_name, to_ns,
                question, response_type, options, context, priority, sla_hours, escalation,
            )
            interaction.status = Status.CANCELLED
            interaction.context["error"] = f"Participant {to} not found"
            self._store.save(interaction)
            return interaction

        # State-aware routing
        if not target.accepts_requests and not target.should_queue:
            reroute = target.reroute_target
            if reroute:
                reroute_ns, reroute_name = self._parse_pid(reroute)
                rerouted = self.resolve(reroute_ns, reroute_name)
                if rerouted and rerouted.accepts_requests:
                    logger.info("A2H rerouting: %s (%s) → %s",
                                target.name, target.current_state, rerouted.name)
                    target = rerouted
                    to_name = rerouted.name
                    to_ns = rerouted.namespace

        # Build interaction
        parsed_options = [Option(**o) for o in (options or [])]
        interaction = Interaction(
            from_name=from_name, from_namespace=from_namespace, from_type="agent",
            to_name=to_name, to_namespace=to_ns, to_type=target.participant_type,
            question=question, response_type=ResponseType(response_type),
            options=parsed_options, context=context or {},
            priority=Priority(priority), sla_hours=sla_hours,
            escalation=escalation,
        )
        if deadline:
            interaction.deadline = deadline
        interaction.status = Status.PENDING

        # Check delegation rules
        auto_delegate_rule = None
        for rule in target.delegation_rules:
            if rule.matches(interaction):
                auto_delegate_rule = rule
                break

        self._store.save(interaction)

        if auto_delegate_rule:
            logger.info("A2H auto-delegated: %s (rule: %s)", interaction.id, auto_delegate_rule.name)
            self.respond(interaction.id, auto_delegate_rule.auto_response, channel="auto_delegation")
            # Ensure status is set to AUTO_DELEGATED instead of just ANSWERED
            interaction.status = Status.AUTO_DELEGATED
        else:
            # Deliver (if not auto-delegated)
            await self._deliver(interaction)

        return interaction

    # ---- Notification (one-way) --------------------------------------------

    async def notify(
        self,
        to: str,
        *,
        message: str,
        severity: str = "info",
        priority: str = "low",
        context: dict | None = None,
        from_participant: str | None = None,
        from_name: str = "",
        from_namespace: str = "default",
    ) -> Notification:
        """Send a notification to a human. No response expected."""
        from_name, from_namespace = self._resolve_sender(
            from_participant, from_name, from_namespace
        )
        to_ns, to_name = self._parse_pid(to)

        notification = Notification(
            from_name=from_name, from_namespace=from_namespace,
            to_name=to_name, to_namespace=to_ns,
            message=message, severity=severity,
            priority=Priority(priority), context=context or {},
        )

        for channel in self._channels:
            try:
                await channel.deliver_notification(notification)
            except Exception as e:
                logger.warning("A2H notification delivery failed (%s): %s", channel.name, e)

        return notification

    # ---- Human responds ----------------------------------------------------

    def respond(
        self,
        interaction_id: str,
        response_data: dict[str, Any],
        channel: str = "dashboard",
    ) -> dict[str, Any]:
        """Submit a human response to a pending request.

        Args:
            interaction_id: The request ID
            response_data: The response (shape depends on response_type)
            channel: Which channel the human used

        Returns:
            {"success": True/False, "status": "answered", ...}
        """
        interaction = self._store.get(interaction_id)
        if not interaction:
            return {"success": False, "error": "Request not found"}
        if interaction.status != Status.PENDING:
            return {"success": False, "error": f"Request is {interaction.status.value}"}

        response = Response.from_dict({**response_data, "channel": channel})
        ok = self._store.respond(interaction_id, response)
        if not ok:
            return {"success": False, "error": "Failed to record response"}

        return {"success": True, "request_id": interaction_id, "status": "answered"}

    # ---- Cancel ------------------------------------------------------------

    def cancel(self, interaction_id: str, reason: str = "") -> dict[str, Any]:
        """Cancel a pending request."""
        ok = self._store.cancel(interaction_id, reason)
        if not ok:
            return {"success": False, "error": "Cannot cancel"}
        return {"success": True, "request_id": interaction_id, "status": "cancelled"}

    # ---- Query -------------------------------------------------------------

    def get(self, interaction_id: str) -> Interaction | None:
        return self._store.get(interaction_id)

    def list_pending(self, to: str | None = None) -> list[Interaction]:
        return self._store.list_pending(to)

    async def wait(self, interaction_id: str, timeout: float = 300) -> Interaction | None:
        """Block until the human responds or timeout."""
        if hasattr(self._store, "wait") and callable(getattr(self._store, "wait")):
            return await getattr(self._store, "wait")(interaction_id, timeout)
            
        # Fallback polling for stores without wait()
        import asyncio
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            interaction = self._store.get(interaction_id)
            if not interaction or interaction.status != Status.PENDING:
                return interaction
            await asyncio.sleep(1.0)
        return self._store.get(interaction_id)

    # ---- Internal ----------------------------------------------------------

    def _resolve_sender(
        self,
        from_participant: str | None,
        from_name: str,
        from_namespace: str,
    ) -> tuple[str, str]:
        """Resolve and verify the sender identity.

        Returns (from_name, from_namespace) after validation.
        """
        if from_participant:
            sender = self.get_participant(from_participant)
            if not sender:
                raise SenderNotRegistered(
                    f"Sender '{from_participant}' is not registered",
                    pid=from_participant,
                )
            return sender.name, sender.namespace

        if from_name:
            pid = f"{from_namespace}/{from_name}"
            warnings.warn(
                "from_name/from_namespace are deprecated, use "
                f"from_participant='{pid}'",
                DeprecationWarning,
                stacklevel=3,
            )
            sender = self.get_participant(pid)
            if not sender:
                raise SenderNotRegistered(
                    f"Sender '{pid}' is not registered",
                    pid=pid,
                )
            return from_name, from_namespace

        # Anonymous sender — allowed for backward compat
        return from_name, from_namespace

    def _make_interaction(self, from_name, from_ns, to_name, to_ns,
                          question, response_type, options, context,
                          priority, sla_hours, escalation) -> Interaction:
        parsed_options = [Option(**o) for o in (options or [])]
        return Interaction(
            from_name=from_name, from_namespace=from_ns,
            to_name=to_name, to_namespace=to_ns,
            question=question, response_type=ResponseType(response_type),
            options=parsed_options, context=context or {},
            priority=Priority(priority), sla_hours=sla_hours,
            escalation=escalation,
        )

    async def _deliver(self, interaction: Interaction) -> None:
        for channel in self._channels:
            try:
                await channel.deliver_request(interaction)
            except Exception as e:
                logger.warning("A2H delivery failed (%s): %s", channel.name, e)

    @staticmethod
    def _parse_pid(pid: str) -> tuple[str, str]:
        if "/" in pid:
            parts = pid.split("/", 1)
            return parts[0], parts[1]
        return "default", pid
