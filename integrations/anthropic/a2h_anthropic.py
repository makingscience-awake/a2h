"""
A2H integration for Anthropic SDK (Claude).

Provides tool definitions and an agentic loop that wraps A2H Gateway
methods as Anthropic tool_use/tool_result blocks.

    from a2h import Gateway, Participant
    from integrations.anthropic.a2h_anthropic import get_a2h_tools, run_with_a2h

    gw = Gateway()
    gw.register(Participant(name="sarah", namespace="sales"))

    client = Anthropic()
    result = await run_with_a2h(
        client, gw, model="claude-sonnet-4-20250514",
        system="You are a sales agent. Ask humans for deal approvals.",
        prompt="Approve the MegaInc deal at $2.5M",
        from_name="sales-agent",
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

A2H_TOOLS = [
    {
        "name": "human_ask",
        "description": (
            "Ask a human a structured question and wait for their response. "
            "Use for approvals, decisions, choices, and confirmations. "
            "The human responds via their preferred channel (Slack, dashboard, email)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human's name (e.g., 'sarah')"},
                "question": {"type": "string", "description": "The question to ask"},
                "response_type": {
                    "type": "string",
                    "enum": ["choice", "approval", "text", "number", "confirm"],
                    "description": "Type of response expected",
                },
                "options": {
                    "type": "string",
                    "description": "JSON array of options for choice type",
                },
                "context": {
                    "type": "string",
                    "description": "JSON object with context to help the human decide",
                },
                "namespace": {"type": "string", "description": "Human's namespace"},
                "priority": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                    "description": "Request priority",
                },
            },
            "required": ["name", "question"],
        },
    },
    {
        "name": "human_notify",
        "description": "Send a notification to a human. No response needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human's name"},
                "message": {"type": "string", "description": "The notification message"},
                "namespace": {"type": "string"},
                "severity": {"type": "string", "enum": ["info", "success", "warning", "error"]},
                "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            },
            "required": ["name", "message"],
        },
    },
    {
        "name": "human_check",
        "description": "Check the status of a pending human request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "The request ID from human_ask"},
            },
            "required": ["request_id"],
        },
    },
]


def get_a2h_tools() -> list[dict]:
    """Return A2H tool definitions in Anthropic format."""
    return A2H_TOOLS


# ---------------------------------------------------------------------------
# Tool executor (shared with OpenAI integration)
# ---------------------------------------------------------------------------

async def execute_a2h_tool(
    gateway,
    tool_name: str,
    tool_input: dict,
    from_name: str = "",
    from_namespace: str = "default",
) -> str:
    """Execute an A2H tool and return result as string."""
    if tool_name == "human_ask":
        namespace = tool_input.get("namespace", "default")
        name = tool_input["name"]
        options = json.loads(tool_input["options"]) if tool_input.get("options") else None
        context = json.loads(tool_input["context"]) if tool_input.get("context") else None

        req = await gateway.ask(
            f"{namespace}/{name}",
            question=tool_input["question"],
            response_type=tool_input.get("response_type", "text"),
            options=options,
            context=context,
            priority=tool_input.get("priority", "medium"),
            from_name=from_name,
            from_namespace=from_namespace,
        )

        if req.status.value == "auto_delegated":
            return json.dumps({
                "status": "auto_delegated",
                "response": req.response.to_dict() if req.response else None,
            })

        result = await gateway.wait(req.id, timeout=300)
        return json.dumps({
            "status": result.status.value if result else "timeout",
            "response": result.response.to_dict() if result and result.response else None,
        })

    elif tool_name == "human_notify":
        namespace = tool_input.get("namespace", "default")
        notif = await gateway.notify(
            f"{namespace}/{tool_input['name']}",
            message=tool_input["message"],
            severity=tool_input.get("severity", "info"),
            priority=tool_input.get("priority", "low"),
            from_name=from_name,
            from_namespace=from_namespace,
        )
        return json.dumps({"delivered": True, "notification_id": notif.id})

    elif tool_name == "human_check":
        interaction = gateway.get(tool_input["request_id"])
        if not interaction:
            return json.dumps({"error": "Request not found"})
        d = interaction.to_dict()
        return json.dumps({"status": d["status"], "response": d.get("response")})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ---------------------------------------------------------------------------
# Full agentic loop with A2H
# ---------------------------------------------------------------------------

async def run_with_a2h(
    client,
    gateway,
    *,
    model: str = "claude-sonnet-4-20250514",
    system: str = "",
    prompt: str,
    from_name: str = "",
    from_namespace: str = "default",
    extra_tools: list[dict] | None = None,
    max_steps: int = 10,
) -> dict:
    """Run an Anthropic agentic loop with A2H tools.

    Handles the tool_use → execute → tool_result loop automatically.
    Returns {"text": final_text, "steps": num_steps, "tool_calls": [...]}.
    """
    tools = get_a2h_tools() + (extra_tools or [])
    messages = [{"role": "user", "content": prompt}]
    all_tool_calls = []

    for step in range(max_steps):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "",
            )
            return {"text": text, "steps": step + 1, "tool_calls": all_tool_calls}

        # Extract tool_use blocks
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        # Add assistant message
        messages.append({"role": "assistant", "content": response.content})

        # Execute each tool and collect results
        tool_results = []
        for tu in tool_uses:
            all_tool_calls.append({"name": tu.name, "input": tu.input})

            if tu.name.startswith("human_"):
                result_str = await execute_a2h_tool(
                    gateway, tu.name, tu.input,
                    from_name=from_name, from_namespace=from_namespace,
                )
            else:
                result_str = json.dumps({"error": f"No handler for tool: {tu.name}"})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})

    return {"text": "[Max steps reached]", "steps": max_steps, "tool_calls": all_tool_calls}
