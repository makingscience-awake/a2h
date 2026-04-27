"""
Delivery channels for A2H requests.

Each channel declares its capabilities (which response types it supports,
trust level for identity verification, etc.) and implements delivery for
requests and notifications.

The protocol specifies:
- Channel capability descriptors (what the channel supports)
- Priority-to-channel mapping (critical = all, low = dashboard)
- Response verification (trust levels per channel)
- Agent identity badges (how agents present themselves)

Implementations add: Slack API calls, email sending, SMS gateways, etc.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .models import AgentIdentity, Interaction, Notification

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Channel capability descriptor (A2H spec)
# ---------------------------------------------------------------------------

@dataclass
class ChannelCapability:
    """Declares what a channel supports per the A2H spec."""
    channel_id: str
    display_name: str = ""
    response_types: list[str] = field(default_factory=lambda: [
        "choice", "approval", "text", "number", "confirm",
    ])
    max_options: int = 10
    supports_context_card: bool = True
    supports_deadline_display: bool = True
    supports_agent_identity_badge: bool = True
    response_latency: str = "seconds"
    verification_method: str = "authenticated_session"
    trust_level: str = "high"

    def supports(self, response_type: str) -> bool:
        return response_type in self.response_types

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "display_name": self.display_name,
            "capabilities": {
                "response_types": self.response_types,
                "max_options": self.max_options,
                "supports_context_card": self.supports_context_card,
                "supports_deadline_display": self.supports_deadline_display,
                "supports_agent_identity_badge": self.supports_agent_identity_badge,
                "response_latency": self.response_latency,
            },
            "identity": {
                "verification_method": self.verification_method,
                "trust_level": self.trust_level,
            },
        }


# Pre-defined capability descriptors for common channels

DASHBOARD_CAPABILITY = ChannelCapability(
    channel_id="dashboard", display_name="Dashboard",
    response_types=["choice", "approval", "text", "number", "confirm", "form"],
    supports_context_card=True, supports_agent_identity_badge=True,
    verification_method="authenticated_session", trust_level="high",
)

SLACK_CAPABILITY = ChannelCapability(
    channel_id="slack", display_name="Slack",
    response_types=["choice", "approval", "text", "confirm"],
    max_options=5, supports_context_card=True,
    verification_method="slack_user_id", trust_level="medium",
)

EMAIL_CAPABILITY = ChannelCapability(
    channel_id="email", display_name="Email",
    response_types=["choice", "approval", "text", "number", "confirm"],
    supports_context_card=False, supports_agent_identity_badge=False,
    response_latency="minutes",
    verification_method="email_address", trust_level="low",
)

SMS_CAPABILITY = ChannelCapability(
    channel_id="sms", display_name="SMS",
    response_types=["approval", "confirm", "text"],
    max_options=3, supports_context_card=False,
    supports_agent_identity_badge=False, response_latency="minutes",
    verification_method="phone_number", trust_level="medium",
)

MACOS_DIALOG_CAPABILITY = ChannelCapability(
    channel_id="macos_dialog", display_name="macOS Dialog",
    response_types=["choice", "approval", "text", "number", "confirm", "form"],
    max_options=10, supports_context_card=True,
    supports_agent_identity_badge=False, response_latency="seconds",
    verification_method="local_session", trust_level="high",
)


# ---------------------------------------------------------------------------
# Response verification (A2H spec)
# ---------------------------------------------------------------------------

@dataclass
class ResponseVerification:
    """Metadata about how a human's response was verified."""
    method: str = "authenticated_session"
    external_id: str = ""
    mapped_to: str = ""
    trust_level: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "external_id": self.external_id,
            "mapped_to": self.mapped_to,
            "trust_level": self.trust_level,
        }


# AgentIdentity is now defined in models.py; re-exported here for backward compat.
# from .models import AgentIdentity  (imported above)


# ---------------------------------------------------------------------------
# Channel protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Channel(Protocol):
    """Delivery channel protocol."""

    @property
    def name(self) -> str: ...

    @property
    def capability(self) -> ChannelCapability: ...

    async def deliver_request(self, interaction: Interaction) -> bool: ...
    async def deliver_notification(self, notification: Notification) -> bool: ...


# ---------------------------------------------------------------------------
# Reference implementations
# ---------------------------------------------------------------------------

class LogChannel:
    """Logs deliveries to Python logging. For development and testing."""

    @property
    def name(self) -> str:
        return "log"

    @property
    def capability(self) -> ChannelCapability:
        return DASHBOARD_CAPABILITY

    async def deliver_request(self, interaction: Interaction) -> bool:
        logger.info(
            "A2H REQUEST | %s | %s/%s → %s/%s | %s | %s | deadline=%s",
            interaction.id,
            interaction.from_namespace, interaction.from_name,
            interaction.to_namespace, interaction.to_name,
            interaction.response_type.value,
            interaction.question[:80],
            interaction.deadline,
        )
        return True

    async def deliver_notification(self, notification: Notification) -> bool:
        logger.info(
            "A2H NOTIFY | %s | %s/%s → %s/%s | %s | %s",
            notification.id,
            notification.from_namespace, notification.from_name,
            notification.to_namespace, notification.to_name,
            notification.severity,
            notification.message[:80],
        )
        return True


class DashboardChannel:
    """Dashboard delivery. Highest trust level — authenticated sessions."""

    @property
    def name(self) -> str:
        return "dashboard"

    @property
    def capability(self) -> ChannelCapability:
        return DASHBOARD_CAPABILITY

    async def deliver_request(self, interaction: Interaction) -> bool:
        logger.info("A2H DASHBOARD | %s | %s → %s/%s",
                     interaction.id, interaction.from_name,
                     interaction.to_namespace, interaction.to_name)
        return True

    async def deliver_notification(self, notification: Notification) -> bool:
        logger.info("A2H DASHBOARD NOTIFY | %s | %s",
                     notification.id, notification.message[:60])
        return True


class MacDialogChannel:
    """macOS native dialog boxes for interactive A2H responses.

    Uses ``osascript`` to show alerts, list pickers, and text input
    dialogs. Collects the human's response and calls
    ``gateway.respond()`` immediately.

        gw = Gateway()
        dialog = MacDialogChannel(gw)
        gw._channels.append(dialog)
    """

    def __init__(self, gateway):
        self._gw = gateway

    @property
    def name(self) -> str:
        return "macos_dialog"

    @property
    def capability(self) -> ChannelCapability:
        return MACOS_DIALOG_CAPABILITY

    async def deliver_request(self, interaction: Interaction) -> bool:
        rt = interaction.response_type.value
        question = interaction.question[:500]
        context_lines = self._format_context(interaction.context)
        full_text = f"{question}\n\n{context_lines}" if context_lines else question
        is_critical = interaction.priority.value == "critical"

        if rt == "approval":
            result = self._alert(full_text, buttons=["Reject", "Approve"], critical=is_critical)
            if result is not None:
                approved = result == "Approve"
                self._gw.respond(interaction.id, {"approved": approved}, channel="macos_dialog")

        elif rt == "confirm":
            result = self._alert(full_text, buttons=["No", "Yes"], critical=is_critical)
            if result is not None:
                confirmed = result == "Yes"
                self._gw.respond(interaction.id, {"confirmed": confirmed}, channel="macos_dialog")

        elif rt == "choice":
            labels = [o.label for o in interaction.options]
            result = self._choose_from_list(full_text, labels)
            if result is not None:
                matched = next((o for o in interaction.options if o.label == result), None)
                value = matched.value if matched else result
                self._gw.respond(interaction.id, {"value": value}, channel="macos_dialog")

        elif rt == "text":
            result = self._text_input(full_text)
            if result is not None:
                self._gw.respond(interaction.id, {"text": result}, channel="macos_dialog")

        elif rt == "number":
            result = self._text_input(full_text)
            if result is not None:
                try:
                    value = float(result)
                    self._gw.respond(interaction.id, {"value": value}, channel="macos_dialog")
                except ValueError:
                    logger.warning("MacDialogChannel: invalid number input '%s'", result)

        elif rt == "form":
            fields = {}
            form_fields = interaction.context.get("form_fields", interaction.context.get("fields", []))
            if isinstance(form_fields, list):
                for field_def in form_fields:
                    field_name = field_def if isinstance(field_def, str) else field_def.get("name", "")
                    label = field_def if isinstance(field_def, str) else field_def.get("label", field_name)
                    result = self._text_input(f"{question}\n\nField: {label}")
                    if result is None:
                        return True
                    fields[field_name] = result
            else:
                result = self._text_input(full_text)
                if result is not None:
                    fields["response"] = result
            if fields:
                self._gw.respond(interaction.id, {"fields": fields}, channel="macos_dialog")

        return True

    async def deliver_notification(self, notification: Notification) -> bool:
        message = notification.message[:150].replace('"', '\\"')
        severity = notification.severity.upper()
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "A2H [{severity}]"'
        ], check=False)
        return True

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace('\\', '\\\\').replace('"', '\\"')

    def _alert(self, message: str, buttons: list[str], critical: bool = False) -> str | None:
        msg = self._escape(message)
        btn_list = ", ".join(f'"{b}"' for b in buttons)
        default = f'default button "{buttons[-1]}"'
        crit = " as critical" if critical else ""
        script = f'display alert "A2H Request" message "{msg}" buttons {{{btn_list}}} {default}{crit}'
        return self._run_osascript(script, parse="button returned:")

    def _choose_from_list(self, message: str, items: list[str]) -> str | None:
        msg = self._escape(message)
        item_list = ", ".join(f'"{self._escape(i)}"' for i in items)
        script = f'choose from list {{{item_list}}} with prompt "{msg}" with title "A2H Choice"'
        result = self._run_osascript(script)
        if result and result != "false":
            return result
        return None

    def _text_input(self, message: str) -> str | None:
        msg = self._escape(message)
        script = f'display dialog "{msg}" default answer "" with title "A2H Input"'
        return self._run_osascript(script, parse="text returned:")

    @staticmethod
    def _run_osascript(script: str, parse: str | None = None) -> str | None:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                return None
            output = result.stdout.strip()
            if parse and parse in output:
                return output.split(parse, 1)[1].strip()
            return output
        except subprocess.TimeoutExpired:
            return None

    @staticmethod
    def _format_context(context: dict) -> str:
        if not context:
            return ""
        lines = []
        for k, v in list(context.items())[:6]:
            if not isinstance(v, (dict, list)):
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
