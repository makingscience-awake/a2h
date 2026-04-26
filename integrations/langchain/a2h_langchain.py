"""
A2H integration for LangChain.

Wraps A2H Gateway methods as LangChain StructuredTool instances with
Pydantic input schemas.

    from a2h import Gateway, Participant
    from a2h_langchain import build_a2h_tools

    gw = Gateway()
    gw.register(Participant(name="sarah", namespace="sales"))

    tools = build_a2h_tools(gw, from_name="my-agent")

    agent = create_tool_calling_agent(llm, tools, prompt=...)
    executor = AgentExecutor(agent=agent, tools=tools)
"""

from __future__ import annotations
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


def build_a2h_tools(
    gateway,
    from_participant: str | None = None,
    from_participant: str = "default/agent",
    ,
) -> list:
    """Build LangChain StructuredTool instances for A2H operations.

    Args:
        gateway: A2H Gateway instance.
        from_participant: Registered sender PID ("namespace/name"). Preferred.
        from_name: (Deprecated) Sender agent name.
        from_namespace: (Deprecated) Sender namespace.
    """
    if not LANGCHAIN_AVAILABLE:
        logger.warning("langchain-core not installed — A2H LangChain tools unavailable")
        return []

    _sender_kwargs: dict[str, Any] = {}
    if from_participant:
        _sender_kwargs["from_participant"] = from_participant
    elif from_name:
        _sender_kwargs["from_name"] = from_name
        _sender_kwargs["from_namespace"] = from_namespace

    class HumanAskInput(BaseModel):
        name: str = Field(description="Human's name (e.g., 'sarah')")
        question: str = Field(description="The question to ask the human")
        response_type: str = Field(
            default="approval",
            description="Type of response: choice, approval, text, number, confirm",
        )
        options: Optional[list[dict]] = Field(
            default=None,
            description="Options for choice type: [{'label': 'Yes', 'value': 'yes'}, ...]",
        )
        context: Optional[dict] = Field(
            default=None,
            description="Structured context to help the human decide",
        )
        namespace: str = Field(default="default", description="Human's namespace")
        priority: str = Field(default="medium", description="critical, high, medium, low")

    class HumanCheckInput(BaseModel):
        request_id: str = Field(description="The request ID from human_ask")

    class HumanNotifyInput(BaseModel):
        name: str = Field(description="Human's name")
        message: str = Field(description="The notification message")
        namespace: str = Field(default="default", description="Human's namespace")
        severity: str = Field(default="info", description="info, success, warning, error")
        priority: str = Field(default="low", description="critical, high, medium, low")

    async def _ask_human(
        name: str,
        question: str,
        response_type: str = "approval",
        options: list[dict] | None = None,
        context: dict | None = None,
        namespace: str = "default",
        priority: str = "medium",
    ) -> dict:
        """Ask a human a structured question and wait for their response."""
        req = await gateway.ask(
            f"{namespace}/{name}",
            question=question,
            response_type=response_type,
            options=options,
            context=context,
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

    async def _check_human(request_id: str) -> dict:
        """Check the status of a pending human request."""
        interaction = gateway.get(request_id)
        if not interaction:
            return {"error": "Request not found"}
        d = interaction.to_dict()
        return {"status": d["status"], "response": d.get("response")}

    async def _notify_human(
        name: str,
        message: str,
        namespace: str = "default",
        severity: str = "info",
        priority: str = "low",
    ) -> dict:
        """Send a notification to a human. No response needed."""
        notif = await gateway.notify(
            f"{namespace}/{name}",
            message=message,
            severity=severity,
            priority=priority,
            **_sender_kwargs,
        )
        return {"delivered": True, "notification_id": notif.id}

    return [
        StructuredTool.from_function(
            coroutine=_ask_human,
            name="human_ask",
            description=(
                "Ask a human a structured question. Use for approvals, decisions, "
                "and any action requiring human judgment. The human responds via "
                "their preferred channel (Slack, dashboard, email)."
            ),
            args_schema=HumanAskInput,
        ),
        StructuredTool.from_function(
            coroutine=_check_human,
            name="human_check",
            description="Check the status of a pending human request.",
            args_schema=HumanCheckInput,
        ),
        StructuredTool.from_function(
            coroutine=_notify_human,
            name="human_notify",
            description="Send a notification to a human. No response needed.",
            args_schema=HumanNotifyInput,
        ),
    ]
