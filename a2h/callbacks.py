"""
A2H webhook callbacks.

Instead of polling with human_check or blocking with gw.wait(),
register a callback that fires when a human responds.

    from a2h import Gateway, Participant
    from a2h.callbacks import CallbackRegistry

    gw = Gateway()
    callbacks = CallbackRegistry(gw)

    # Register a callback
    async def on_deal_approved(interaction):
        print(f"Deal approved: {interaction.response.value}")
        await execute_deal(interaction.context)

    callbacks.on_response("req_abc123", on_deal_approved)

    # Or register for ALL responses from a participant
    callbacks.on_any_response("sales/sarah", on_deal_approved)

For HTTP webhooks, use the server endpoint:

    POST /a2h/v1/webhooks
    {"url": "https://my-app.com/a2h-callback", "events": ["response", "expired"]}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from .models import Interaction, Status

logger = logging.getLogger(__name__)

Callback = Callable[[Interaction], Awaitable[None]]


class CallbackRegistry:
    """Register callbacks that fire when humans respond to A2H requests.

    Wraps the Gateway's respond method to trigger callbacks after
    a successful response is recorded.
    """

    def __init__(self, gateway):
        self._gw = gateway
        self._request_callbacks: dict[str, list[Callback]] = {}
        self._participant_callbacks: dict[str, list[Callback]] = {}
        self._global_callbacks: list[Callback] = []

        # Wrap the gateway's respond method
        self._original_respond = gateway.respond
        gateway.respond = self._intercepted_respond

    def _intercepted_respond(self, request_id: str, response_data: dict,
                              channel: str = "dashboard") -> dict:
        result = self._original_respond(request_id, response_data, channel)

        if result.get("success"):
            interaction = self._gw.get(request_id)
            if interaction:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._fire(interaction))
                except RuntimeError:
                    asyncio.run(self._fire(interaction))

        return result

    async def _fire(self, interaction: Interaction) -> None:
        """Fire all matching callbacks for this interaction."""
        callbacks: list[Callback] = []

        # Request-specific callbacks
        callbacks.extend(self._request_callbacks.pop(interaction.id, []))

        # Participant-specific callbacks
        pid = f"{interaction.to_namespace}/{interaction.to_name}"
        callbacks.extend(self._participant_callbacks.get(pid, []))

        # Global callbacks
        callbacks.extend(self._global_callbacks)

        for cb in callbacks:
            try:
                await cb(interaction)
            except Exception as e:
                logger.error("A2H callback failed: %s", e)

    # ---- Registration API --------------------------------------------------

    def on_response(self, request_id: str, callback: Callback) -> None:
        """Fire callback when a specific request gets a response.

        One-shot: the callback is removed after firing.
        """
        self._request_callbacks.setdefault(request_id, []).append(callback)

    def on_any_response(self, participant_pid: str, callback: Callback) -> None:
        """Fire callback when ANY request to this participant gets a response.

        Persistent: fires for every response, not just one.
        """
        self._participant_callbacks.setdefault(participant_pid, []).append(callback)

    def on_all_responses(self, callback: Callback) -> None:
        """Fire callback for every response in the system.

        Use for logging, metrics, or audit.
        """
        self._global_callbacks.append(callback)

    def remove(self, participant_pid: str | None = None) -> None:
        """Remove callbacks for a participant, or all if None."""
        if participant_pid:
            self._participant_callbacks.pop(participant_pid, None)
        else:
            self._request_callbacks.clear()
            self._participant_callbacks.clear()
            self._global_callbacks.clear()


class WebhookTarget:
    """Sends HTTP POST to a URL when events occur.

        target = WebhookTarget(
            url="https://my-app.com/a2h-callback",
            events=["response", "expired"],
            secret="shared-secret-for-hmac",
        )
        callbacks.on_all_responses(target.fire)
    """

    def __init__(self, url: str, events: list[str] | None = None, secret: str = ""):
        self.url = url
        self.events = events or ["response"]
        self.secret = secret

    async def fire(self, interaction: Interaction) -> None:
        event_type = "response" if interaction.status == Status.ANSWERED else interaction.status.value

        if event_type not in self.events:
            return

        payload = {
            "event": event_type,
            "interaction": interaction.to_dict(),
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                headers = {"Content-Type": "application/json"}
                if self.secret:
                    import hashlib, hmac, json
                    body = json.dumps(payload).encode()
                    sig = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
                    headers["X-A2H-Signature"] = f"sha256={sig}"
                await client.post(self.url, json=payload, headers=headers)
        except Exception as e:
            logger.error("Webhook delivery failed to %s: %s", self.url, e)
