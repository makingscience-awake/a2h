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
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .models import Interaction, Notification

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


# ---------------------------------------------------------------------------
# Agent identity (A2H spec — enriched "from" field)
# ---------------------------------------------------------------------------

@dataclass
class AgentIdentity:
    """How an agent presents itself to humans through channels."""
    name: str
    namespace: str = "default"
    display_name: str = ""
    description: str = ""
    deployed_by: str = ""
    platform_name: str = ""
    platform_url: str = ""
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name, "namespace": self.namespace,
            "participant_type": "agent",
        }
        if self.display_name:
            d["display_name"] = self.display_name
        if self.description:
            d["description"] = self.description
        if self.deployed_by:
            d["deployed_by"] = self.deployed_by
        if self.platform_name:
            d["platform"] = {
                "name": self.platform_name,
                "url": self.platform_url,
                "verified": self.verified,
            }
        return d


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
