"""
A2H testing utilities.

Provides mock channels and auto-responders for development and CI
where no real humans are available.

    from a2h import Gateway, Participant
    from a2h.testing import AutoResponder, MockChannel

    gw = Gateway(channels=[MockChannel()])
    gw.register(Participant(name="sarah", namespace="sales"))

    # Auto-respond to all requests
    responder = AutoResponder(gw)
    responder.approve_all()          # auto-approve every approval request
    responder.respond_choice("yes")  # auto-pick "yes" for choice requests
    responder.respond_text("OK")     # auto-respond "OK" for text requests

    # Now agents can call gw.ask() and get immediate responses
    req = await gw.ask("sales/sarah", question="Approve?", response_type="approval")
    assert req.status.value == "auto_delegated" or req.status.value == "answered"
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .models import Interaction, Notification, Response, Status
from .gateway import Gateway

logger = logging.getLogger(__name__)


class MockChannel:
    """Channel that records deliveries for assertions in tests.

        channel = MockChannel()
        gw = Gateway(channels=[channel])
        ...
        assert len(channel.requests) == 1
        assert channel.requests[0].question == "Approve?"
    """

    def __init__(self):
        self.requests: list[Interaction] = []
        self.notifications: list[Notification] = []

    @property
    def name(self) -> str:
        return "mock"

    @property
    def capability(self):
        from .channels import DASHBOARD_CAPABILITY
        return DASHBOARD_CAPABILITY

    async def deliver_request(self, interaction: Interaction) -> bool:
        self.requests.append(interaction)
        return True

    async def deliver_notification(self, notification: Notification) -> bool:
        self.notifications.append(notification)
        return True

    def reset(self):
        self.requests.clear()
        self.notifications.clear()


class AutoResponder:
    """Automatically responds to A2H requests for testing.

    Wraps a Gateway and intercepts ask() calls, responding immediately
    so tests don't need to simulate human interaction.

        responder = AutoResponder(gw)
        responder.approve_all()
        responder.respond_choice("yes")

        # All subsequent gw.ask() calls get auto-responded
    """

    def __init__(self, gateway: Gateway):
        self._gw = gateway
        self._rules: list[dict] = []
        self._original_ask = gateway.ask
        gateway.ask = self._intercepted_ask

    async def _intercepted_ask(self, *args, **kwargs) -> Interaction:
        req = await self._original_ask(*args, **kwargs)

        if req.status in (Status.AUTO_DELEGATED, Status.CANCELLED):
            return req

        for rule in self._rules:
            if self._matches(req, rule):
                response_data = rule["response"]
                self._gw.respond(req.id, response_data, channel="auto_test")
                req = self._gw.get(req.id)
                break

        return req

    def _matches(self, req: Interaction, rule: dict) -> bool:
        rt = rule.get("response_type")
        if rt and req.response_type.value != rt:
            return False
        return True

    def approve_all(self, reason: str = "Auto-approved in test"):
        """Auto-approve all approval requests."""
        self._rules.append({
            "response_type": "approval",
            "response": {"approved": True, "text": reason},
        })

    def reject_all(self, reason: str = "Auto-rejected in test"):
        """Auto-reject all approval requests."""
        self._rules.append({
            "response_type": "approval",
            "response": {"approved": False, "text": reason},
        })

    def respond_choice(self, value: str):
        """Auto-select a value for all choice requests."""
        self._rules.append({
            "response_type": "choice",
            "response": {"value": value},
        })

    def respond_text(self, text: str):
        """Auto-respond with text for all text requests."""
        self._rules.append({
            "response_type": "text",
            "response": {"text": text},
        })

    def respond_confirm(self, confirmed: bool = True):
        """Auto-confirm all confirmation requests."""
        self._rules.append({
            "response_type": "confirm",
            "response": {"confirmed": confirmed},
        })

    def respond_all(self, response: dict):
        """Auto-respond to ANY request with the given response."""
        self._rules.append({"response": response})

    def reset(self):
        """Clear all auto-response rules."""
        self._rules.clear()
        self._gw.ask = self._original_ask


class FailingChannel:
    """Channel that always fails delivery. For testing error handling."""

    @property
    def name(self) -> str:
        return "failing"

    @property
    def capability(self):
        from .channels import DASHBOARD_CAPABILITY
        return DASHBOARD_CAPABILITY

    async def deliver_request(self, interaction: Interaction) -> bool:
        raise ConnectionError("Channel delivery failed (test)")

    async def deliver_notification(self, notification: Notification) -> bool:
        raise ConnectionError("Channel delivery failed (test)")
