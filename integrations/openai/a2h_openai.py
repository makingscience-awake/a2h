"""
A2H integration for OpenAI SDK (and OpenAI-compatible APIs: Grok/xAI, Together, etc.)

Provides tool definitions and an agentic loop that wraps A2H Gateway
methods as OpenAI function-calling tools.

    from a2h import Gateway, Participant
    from integrations.openai.a2h_openai import get_a2h_tools, run_with_a2h

    gw = Gateway()
    gw.register(Participant(name="sarah", namespace="sales"))

    # Option 1: Get tools and handle loop yourself
    tools = get_a2h_tools()

    # Option 2: Run a complete agentic loop with A2H
    result = await run_with_a2h(
        client, gw, model="gpt-4o",
        system="You are a sales agent. Ask humans for deal approvals.",
        prompt="Approve the MegaInc deal at $2.5M",
        from_name="sales-agent",
    )

Also works with xAI/Grok:
    client = OpenAI(base_url="https://api.x.ai/v1", api_key=XAI_API_KEY)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

A2H_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "human_ask",
            "description": (
                "Ask a human a structured question and wait for their response. "
                "Use for approvals, decisions, choices, and confirmations. "
                "The human responds via their preferred channel (Slack, dashboard, email)."
            ),
            "parameters": {
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
                        "description": "JSON array of options for choice type: [{\"label\":\"Yes\",\"value\":\"yes\"}]",
                    },
                    "context": {
                        "type": "string",
                        "description": "JSON object with context to help the human decide",
                    },
                    "namespace": {"type": "string", "description": "Human's namespace", "default": "default"},
                    "priority": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Request priority",
                        "default": "medium",
                    },
                },
                "required": ["name", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "human_notify",
            "description": "Send a notification to a human. No response needed. Use for status updates and alerts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Human's name"},
                    "message": {"type": "string", "description": "The notification message"},
                    "namespace": {"type": "string", "default": "default"},
                    "severity": {"type": "string", "enum": ["info", "success", "warning", "error"], "default": "info"},
                    "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"], "default": "low"},
                },
                "required": ["name", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "human_check",
            "description": "Check the status of a pending human request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "The request ID from human_ask"},
                },
                "required": ["request_id"],
            },
        },
    },
]


def get_a2h_tools() -> list[dict]:
    """Return A2H tool definitions in OpenAI function-calling format."""
    return A2H_TOOLS


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

async def execute_a2h_tool(
    gateway,
    tool_name: str,
    arguments: dict,
    from_name: str = "",
    from_namespace: str = "default",
) -> str:
    """Execute an A2H tool call and return the result as a string."""
    if tool_name == "human_ask":
        namespace = arguments.get("namespace", "default")
        name = arguments["name"]
        options = json.loads(arguments["options"]) if arguments.get("options") else None
        context = json.loads(arguments["context"]) if arguments.get("context") else None

        req = await gateway.ask(
            f"{namespace}/{name}",
            question=arguments["question"],
            response_type=arguments.get("response_type", "text"),
            options=options,
            context=context,
            priority=arguments.get("priority", "medium"),
            from_name=from_name,
            from_namespace=from_namespace,
        )

        if req.status.value == "auto_delegated":
            return json.dumps({
                "status": "auto_delegated",
                "response": req.response.to_dict() if req.response else None,
                "request_id": req.id,
            })

        result = await gateway.wait(req.id, timeout=300)
        return json.dumps({
            "status": result.status.value if result else "timeout",
            "response": result.response.to_dict() if result and result.response else None,
            "request_id": req.id,
        })

    elif tool_name == "human_notify":
        namespace = arguments.get("namespace", "default")
        notif = await gateway.notify(
            f"{namespace}/{arguments['name']}",
            message=arguments["message"],
            severity=arguments.get("severity", "info"),
            priority=arguments.get("priority", "low"),
            from_name=from_name,
            from_namespace=from_namespace,
        )
        return json.dumps({"delivered": True, "notification_id": notif.id})

    elif tool_name == "human_check":
        interaction = gateway.get(arguments["request_id"])
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
    model: str = "gpt-4o",
    system: str = "",
    prompt: str,
    from_name: str = "",
    from_namespace: str = "default",
    extra_tools: list[dict] | None = None,
    max_steps: int = 10,
) -> dict:
    """Run an OpenAI agentic loop with A2H tools.

    Handles the tool_call → execute → tool_result loop automatically.
    Returns {"text": final_text, "steps": num_steps, "tool_calls": [...]}.

    Works with any OpenAI-compatible API (OpenAI, xAI/Grok, Together, etc.)
    """
    tools = get_a2h_tools() + (extra_tools or [])
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    all_tool_calls = []

    for step in range(max_steps):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools if tools else None,
        )

        choice = response.choices[0]
        message = choice.message

        if not message.tool_calls:
            return {
                "text": message.content or "",
                "steps": step + 1,
                "tool_calls": all_tool_calls,
            }

        # Process tool calls
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in message.tool_calls
            ],
        })

        for tc in message.tool_calls:
            args = json.loads(tc.function.arguments)
            all_tool_calls.append({"name": tc.function.name, "input": args})

            if tc.function.name.startswith("human_"):
                result = await execute_a2h_tool(
                    gateway, tc.function.name, args,
                    from_name=from_name, from_namespace=from_namespace,
                )
            else:
                result = json.dumps({"error": f"No handler for tool: {tc.function.name}"})

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return {"text": "[Max steps reached]", "steps": max_steps, "tool_calls": all_tool_calls}
