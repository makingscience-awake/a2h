"""
A2H integration for CrewAI.

Wraps A2H Gateway methods as CrewAI BaseTool subclasses so any
crew agent can ask humans structured questions.

    from a2h import Gateway, Participant
    from a2h_crewai import HumanAskTool, HumanNotifyTool

    gw = Gateway()
    gw.register(Participant(name="sarah", namespace="sales"))

    agent = Agent(
        role="Deal Closer",
        goal="Close deals with human approval",
        tools=[HumanAskTool(gateway=gw, from_name="deal-closer")],
    )
"""

from __future__ import annotations
import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False


def build_a2h_tools(gateway, from_name: str = "", from_namespace: str = "default") -> list:
    """Build CrewAI BaseTool instances for A2H operations."""
    if not CREWAI_AVAILABLE:
        logger.warning("crewai not installed — A2H CrewAI tools unavailable")
        return []

    class HumanAskTool(BaseTool):
        name: str = "human_ask"
        description: str = (
            "Ask a human a structured question and wait for their response. "
            "Use for approvals, decisions, and any action requiring human judgment. "
            "Parameters: name (human's name), question, response_type (approval/choice/text/confirm), "
            "options (JSON array for choice type), context (JSON object), namespace, priority."
        )

        def _run(
            self,
            name: str = "",
            question: str = "",
            response_type: str = "approval",
            options: str = "",
            context: str = "",
            namespace: str = "default",
            priority: str = "medium",
            **kwargs,
        ) -> str:
            parsed_options = json.loads(options) if options else None
            parsed_context = json.loads(context) if context else None

            loop = asyncio.new_event_loop()
            try:
                req = loop.run_until_complete(gateway.ask(
                    f"{namespace}/{name}",
                    question=question,
                    response_type=response_type,
                    options=parsed_options,
                    context=parsed_context,
                    priority=priority,
                    from_name=from_name,
                    from_namespace=from_namespace,
                ))

                if req.status.value == "auto_delegated":
                    resp = req.response.to_dict() if req.response else {}
                    return f"Auto-delegated: {json.dumps(resp)}"

                result = loop.run_until_complete(gateway.wait(req.id, timeout=300))
                if result and result.status.value == "answered":
                    return f"Human responded: {json.dumps(result.response.to_dict())}"
                return f"No response (status: {result.status.value if result else 'timeout'})"
            except Exception as e:
                return f"Error: {e}"
            finally:
                loop.close()

    class HumanNotifyTool(BaseTool):
        name: str = "human_notify"
        description: str = (
            "Send a notification to a human. No response needed. "
            "Use for status updates, reports, and alerts. "
            "Parameters: name, message, namespace, severity (info/warning/error), priority."
        )

        def _run(
            self,
            name: str = "",
            message: str = "",
            namespace: str = "default",
            severity: str = "info",
            priority: str = "low",
            **kwargs,
        ) -> str:
            loop = asyncio.new_event_loop()
            try:
                notif = loop.run_until_complete(gateway.notify(
                    f"{namespace}/{name}",
                    message=message,
                    severity=severity,
                    priority=priority,
                    from_name=from_name,
                    from_namespace=from_namespace,
                ))
                return f"Notification sent: {notif.id}"
            except Exception as e:
                return f"Error: {e}"
            finally:
                loop.close()

    class HumanCheckTool(BaseTool):
        name: str = "human_check"
        description: str = (
            "Check the status of a pending human request. "
            "Parameters: request_id (from human_ask)."
        )

        def _run(self, request_id: str = "", **kwargs) -> str:
            interaction = gateway.get(request_id)
            if not interaction:
                return "Request not found"
            d = interaction.to_dict()
            return json.dumps({"status": d["status"], "response": d.get("response")})

    return [HumanAskTool(), HumanNotifyTool(), HumanCheckTool()]
