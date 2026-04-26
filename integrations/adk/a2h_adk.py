"""
A2H integration for Google ADK.

Wraps A2H Gateway methods as ADK FunctionTool instances so any
LlmAgent can ask humans structured questions.

    from a2h import Gateway, Participant
    from a2h_adk import build_a2h_tools

    gw = Gateway()
    gw.register(Participant(name="sarah", namespace="sales"))

    tools = build_a2h_tools(gw, from_name="my-agent", from_namespace="sales")

    agent = Agent(name="deal-closer", model="gemini-2.5-flash",
        instruction="Use human_ask for approvals over $10K",
        tools=tools)
"""

from __future__ import annotations
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from google.adk.tools import FunctionTool
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False


def build_a2h_tools(
    gateway,
    from_participant: str | None = None,
    from_participant: str = "default/agent",
    ,
) -> list:
    """Build ADK FunctionTool instances for A2H operations.

    Args:
        gateway: A2H Gateway instance.
        from_participant: Registered sender PID ("namespace/name"). Preferred.
        from_name: (Deprecated) Sender agent name.
        from_namespace: (Deprecated) Sender namespace.

    Returns tools for: human_ask, human_check, human_notify.
    """
    if not ADK_AVAILABLE:
        logger.warning("google-adk not installed — A2H ADK tools unavailable")
        return []

    _sender_kwargs: dict[str, Any] = {}
    if from_participant:
        _sender_kwargs["from_participant"] = from_participant
    elif from_name:
        _sender_kwargs["from_name"] = from_name
        _sender_kwargs["from_namespace"] = from_namespace

    async def human_ask(
        name: str,
        question: str,
        response_type: str = "approval",
        options: str = "",
        context: str = "",
        namespace: str = "default",
        priority: str = "medium",
    ) -> dict:
        """Ask a human a structured question and wait for their response.

        Args:
            name: Human's name (e.g., "sarah")
            question: The question to ask
            response_type: choice, approval, text, number, confirm
            options: JSON array of options for choice type (e.g., '[{"label":"Yes","value":"yes"}]')
            context: JSON object with context to help the human decide
            namespace: Human's namespace (default: "default")
            priority: critical, high, medium, low
        """
        parsed_options = json.loads(options) if options else None
        parsed_context = json.loads(context) if context else None

        req = await gateway.ask(
            f"{namespace}/{name}",
            question=question,
            response_type=response_type,
            options=parsed_options,
            context=parsed_context,
            priority=priority,
            **_sender_kwargs,
        )

        if req.status.value == "auto_delegated":
            return {
                "status": "auto_delegated",
                "response": req.response.to_dict() if req.response else None,
                "request_id": req.id,
            }

        result = await gateway.wait(req.id, timeout=300)
        return {
            "status": result.status.value if result else "timeout",
            "response": result.response.to_dict() if result and result.response else None,
            "request_id": req.id,
        }

    async def human_check(request_id: str) -> dict:
        """Check the status of a pending human request.

        Args:
            request_id: The request ID returned by human_ask
        """
        interaction = gateway.get(request_id)
        if not interaction:
            return {"error": "Request not found"}
        d = interaction.to_dict()
        return {"status": d["status"], "response": d.get("response")}

    async def human_notify(
        name: str,
        message: str,
        namespace: str = "default",
        severity: str = "info",
        priority: str = "low",
    ) -> dict:
        """Send a notification to a human. No response needed.

        Args:
            name: Human's name
            message: The notification message
            namespace: Human's namespace
            severity: info, success, warning, error
            priority: critical, high, medium, low
        """
        notif = await gateway.notify(
            f"{namespace}/{name}",
            message=message,
            severity=severity,
            priority=priority,
            **_sender_kwargs,
        )
        return {"delivered": True, "notification_id": notif.id}

    human_ask.__name__ = "human_ask"
    human_check.__name__ = "human_check"
    human_notify.__name__ = "human_notify"

    return [
        FunctionTool(human_ask),
        FunctionTool(human_check),
        FunctionTool(human_notify),
    ]
