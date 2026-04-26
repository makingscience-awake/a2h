"""
A2H — Agent-to-Human Interaction Protocol.

Reference implementation of the A2H protocol specification.
Companion to Google A2A (agent-to-agent) and Anthropic MCP (agent-to-tool).

    from a2h import Gateway, Participant, Request

    # Register a human
    gw = Gateway()
    gw.register(Participant(name="sarah", namespace="sales", type="human",
        channels=["dashboard", "slack"]))

    # Agent asks human
    req = await gw.ask("sales/sarah",
        question="Approve the deal?",
        response_type="approval",
        context={"deal_value": 2500000},
        deadline="4h")

    # Human responds
    gw.respond(req.id, {"approved": True, "reason": "Good fit"})

    # Agent checks
    result = gw.get(req.id)
    assert result.status == "answered"
"""

from .models import (
    AgentIdentity,
    DelegationRule,
    EscalationChain,
    EscalationLevel,
    Interaction,
    Notification,
    Participant,
    Priority,
    Response,
    ResponseType,
    Status,
)
from .gateway import Gateway
from .registry import ParticipantRegistry
from .store import InMemoryStore, Store
from .channels import (
    Channel,
    ChannelCapability,
    DashboardChannel,
    DASHBOARD_CAPABILITY,
    EMAIL_CAPABILITY,
    LogChannel,
    ResponseVerification,
    SLACK_CAPABILITY,
    SMS_CAPABILITY,
)

from .errors import (
    A2HError,
    ChannelDeliveryFailed,
    DuplicateParticipant,
    ExecutionMismatch,
    InvalidParticipantID,
    InvalidResponseType,
    NoSupportedChannel,
    ParticipantNotFound,
    ParticipantUnavailable,
    RateLimitExceeded,
    RegistryError,
    RegistryLoadError,
    RequestExpired,
    RequestNotFound,
    RequestNotPending,
    SenderNotRegistered,
    SignatureInvalid,
    TrustLevelInsufficient,
    UnauthorizedParticipant,
)

__version__ = "0.1.0"
__all__ = [
    # Errors
    "A2HError",
    "ChannelDeliveryFailed",
    "DuplicateParticipant",
    "ExecutionMismatch",
    "InvalidParticipantID",
    "InvalidResponseType",
    "NoSupportedChannel",
    "ParticipantNotFound",
    "ParticipantUnavailable",
    "RateLimitExceeded",
    "RegistryError",
    "RegistryLoadError",
    "RequestExpired",
    "RequestNotFound",
    "RequestNotPending",
    "SenderNotRegistered",
    "SignatureInvalid",
    "TrustLevelInsufficient",
    "UnauthorizedParticipant",
    #
    "AgentIdentity",
    "Channel",
    "ChannelCapability",
    "DashboardChannel",
    "DASHBOARD_CAPABILITY",
    "DelegationRule",
    "EMAIL_CAPABILITY",
    "EscalationChain",
    "EscalationLevel",
    "Gateway",
    "InMemoryStore",
    "Interaction",
    "LogChannel",
    "Notification",
    "Participant",
    "ParticipantRegistry",
    "Priority",
    "Response",
    "ResponseType",
    "ResponseVerification",
    "SLACK_CAPABILITY",
    "SMS_CAPABILITY",
    "Status",
    "Store",
]
