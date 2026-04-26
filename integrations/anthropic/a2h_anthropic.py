"""
A2H integration for Anthropic SDK (Claude).

Two integration paths:

  Path 1 — beta_tool + tool_runner (highest level):
    from integrations.anthropic.a2h_anthropic import build_a2h_beta_tools
    tools = build_a2h_beta_tools(gw, from_participant="sales/my-agent")
    # Use with anthropic tool_runner — it manages the loop automatically

  Path 2 — Messages API (lower level, more control):
    from integrations.anthropic.a2h_anthropic import get_a2h_tools, run_with_a2h
    result = await run_with_a2h(client, gw, prompt="...", from_participant="sales/my-agent")
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _parse_participant(from_participant: str) -> tuple[str, str]:
    if "/" in from_participant:
        ns, name = from_participant.split("/", 1)
        return ns, name
    return "default", from_participant


async def _execute(gateway, tool_name: str, tool_input: dict, from_participant: str) -> str:
    ns, name = _parse_participant(from_participant)

    if tool_name == "human_ask":
        target_ns = tool_input.get("namespace", "default")
        options = json.loads(tool_input["options"]) if tool_input.get("options") else None
        context = json.loads(tool_input["context"]) if tool_input.get("context") else None

        req = await gateway.ask(
            f"{target_ns}/{tool_input['name']}",
            question=tool_input["question"],
            response_type=tool_input.get("response_type", "text"),
            options=options, context=context,
            priority=tool_input.get("priority", "medium"),
            from_name=name, from_namespace=ns,
        )
        if req.status.value == "auto_delegated":
            return json.dumps({"status": "auto_delegated",
                               "response": req.response.to_dict() if req.response else None})
        result = await gateway.wait(req.id, timeout=300)
        return json.dumps({"status": result.status.value if result else "timeout",
                           "response": result.response.to_dict() if result and result.response else None})

    elif tool_name == "human_notify":
        target_ns = tool_input.get("namespace", "default")
        notif = await gateway.notify(
            f"{target_ns}/{tool_input['name']}",
            message=tool_input["message"],
            severity=tool_input.get("severity", "info"),
            priority=tool_input.get("priority", "low"),
            from_name=name, from_namespace=ns,
        )
        return json.dumps({"delivered": True, "notification_id": notif.id})

    elif tool_name == "human_check":
        interaction = gateway.get(tool_input["request_id"])
        if not interaction:
            return json.dumps({"error": "Request not found"})
        d = interaction.to_dict()
        return json.dumps({"status": d["status"], "response": d.get("response")})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ═══════════════════════════════════════════════════════════════════════════
# PATH 1: @beta_tool decorator (use with tool_runner)
# ═══════════════════════════════════════════════════════════════════════════

def build_a2h_beta_tools(gateway, from_participant: str = "default/agent") -> list:
    """Build A2H tools using Anthropic's @beta_tool decorator.

    Returns decorated functions for use with Anthropic's tool_runner,
    which auto-manages the tool_use/tool_result loop.

    Requires: pip install anthropic (with beta_tool support)
    """
    try:
        from anthropic import beta_tool
    except ImportError:
        logger.warning("anthropic beta_tool not available — use manual path instead")
        return []

    @beta_tool
    def human_ask(
        name: str,
        question: str,
        response_type: str = "approval",
        options: str = "",
        context: str = "",
        namespace: str = "default",
        priority: str = "medium",
    ) -> str:
        """Ask a human a structured question and wait for their response.
        Use for approvals, decisions, choices, and confirmations."""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_execute(gateway, "human_ask", {
                "name": name, "question": question, "response_type": response_type,
                "options": options, "context": context, "namespace": namespace,
                "priority": priority,
            }, from_participant))
        finally:
            loop.close()

    @beta_tool
    def human_notify(
        name: str,
        message: str,
        namespace: str = "default",
        severity: str = "info",
        priority: str = "low",
    ) -> str:
        """Send a notification to a human. No response needed."""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_execute(gateway, "human_notify", {
                "name": name, "message": message, "namespace": namespace,
                "severity": severity, "priority": priority,
            }, from_participant))
        finally:
            loop.close()

    @beta_tool
    def human_check(request_id: str) -> str:
        """Check the status of a pending human request."""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_execute(gateway, "human_check",
                                                    {"request_id": request_id}, from_participant))
        finally:
            loop.close()

    return [human_ask, human_notify, human_check]


# ═══════════════════════════════════════════════════════════════════════════
# PATH 2: Messages API (manual loop)
# ═══════════════════════════════════════════════════════════════════════════

A2H_TOOLS = [
    {
        "name": "human_ask",
        "description": "Ask a human a structured question and wait for their response.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human's name"},
                "question": {"type": "string", "description": "The question to ask"},
                "response_type": {"type": "string", "enum": ["choice", "approval", "text", "number", "confirm"]},
                "options": {"type": "string"}, "context": {"type": "string"},
                "namespace": {"type": "string"}, "priority": {"type": "string"},
            },
            "required": ["name", "question"],
        },
    },
    {
        "name": "human_notify",
        "description": "Send a notification to a human. No response needed.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "message": {"type": "string"},
                           "namespace": {"type": "string"}, "severity": {"type": "string"},
                           "priority": {"type": "string"}},
            "required": ["name", "message"],
        },
    },
    {
        "name": "human_check",
        "description": "Check the status of a pending human request.",
        "input_schema": {
            "type": "object",
            "properties": {"request_id": {"type": "string"}},
            "required": ["request_id"],
        },
    },
]


def get_a2h_tools() -> list[dict]:
    return A2H_TOOLS


async def run_with_a2h(
    client, gateway, *, model: str = "claude-sonnet-4-20250514",
    system: str = "", prompt: str,
    from_participant: str = "default/agent",
    extra_tools: list[dict] | None = None, max_steps: int = 10,
) -> dict:
    """Run a complete agentic loop with A2H tools (Messages API)."""
    tools = get_a2h_tools() + (extra_tools or [])
    messages = [{"role": "user", "content": prompt}]
    all_tool_calls = []

    for step in range(max_steps):
        response = client.messages.create(
            model=model, max_tokens=4096, system=system,
            tools=tools, messages=messages,
        )
        if response.stop_reason != "tool_use":
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            return {"text": text, "steps": step + 1, "tool_calls": all_tool_calls}

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tu in tool_uses:
            all_tool_calls.append({"name": tu.name, "input": tu.input})
            result_str = await _execute(gateway, tu.name, tu.input, from_participant)
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result_str})
        messages.append({"role": "user", "content": tool_results})

    return {"text": "[Max steps reached]", "steps": max_steps, "tool_calls": all_tool_calls}
