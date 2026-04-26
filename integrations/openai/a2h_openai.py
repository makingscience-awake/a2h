"""
A2H integration for OpenAI SDK.

Two integration paths:

  Path 1 — Agents SDK (highest level, recommended):
    from integrations.openai.a2h_openai import build_a2h_agent_tools
    tools = build_a2h_agent_tools(gw, from_participant="sales/my-agent")
    agent = Agent(tools=tools)  # agent runs the loop automatically

  Path 2 — Chat Completions (lower level, more control):
    from integrations.openai.a2h_openai import get_a2h_tools, run_with_a2h
    result = await run_with_a2h(client, gw, prompt="...", from_participant="sales/my-agent")

Also works with xAI/Grok, Together, Fireworks, Groq, Ollama — any
OpenAI-compatible API. Just change base_url.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _parse_participant(from_participant: str) -> tuple[str, str]:
    """Parse 'namespace/name' into (namespace, name)."""
    if "/" in from_participant:
        ns, name = from_participant.split("/", 1)
        return ns, name
    return "default", from_participant


# ---------------------------------------------------------------------------
# Shared tool executor
# ---------------------------------------------------------------------------

async def _execute(gateway, tool_name: str, args: dict, from_participant: str) -> str:
    ns, name = _parse_participant(from_participant)

    if tool_name == "human_ask":
        target_ns = args.get("namespace", "default")
        options = json.loads(args["options"]) if args.get("options") else None
        context = json.loads(args["context"]) if args.get("context") else None

        req = await gateway.ask(
            f"{target_ns}/{args['name']}",
            question=args["question"],
            response_type=args.get("response_type", "text"),
            options=options, context=context,
            priority=args.get("priority", "medium"),
            from_name=name, from_namespace=ns,
        )
        if req.status.value == "auto_delegated":
            return json.dumps({"status": "auto_delegated",
                               "response": req.response.to_dict() if req.response else None,
                               "request_id": req.id})

        result = await gateway.wait(req.id, timeout=300)
        return json.dumps({"status": result.status.value if result else "timeout",
                           "response": result.response.to_dict() if result and result.response else None,
                           "request_id": req.id})

    elif tool_name == "human_notify":
        target_ns = args.get("namespace", "default")
        notif = await gateway.notify(
            f"{target_ns}/{args['name']}",
            message=args["message"],
            severity=args.get("severity", "info"),
            priority=args.get("priority", "low"),
            from_name=name, from_namespace=ns,
        )
        return json.dumps({"delivered": True, "notification_id": notif.id})

    elif tool_name == "human_check":
        interaction = gateway.get(args["request_id"])
        if not interaction:
            return json.dumps({"error": "Request not found"})
        d = interaction.to_dict()
        return json.dumps({"status": d["status"], "response": d.get("response")})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ═══════════════════════════════════════════════════════════════════════════
# PATH 1: OpenAI Agents SDK (@function_tool)
# ═══════════════════════════════════════════════════════════════════════════

def build_a2h_agent_tools(gateway, from_participant: str = "default/agent") -> list:
    """Build A2H tools for the OpenAI Agents SDK.

    Returns @function_tool decorated functions that the Agent class
    runs automatically — no manual loop needed.

        from openai.agents import Agent
        tools = build_a2h_agent_tools(gw, from_participant="sales/deal-bot")
        agent = Agent(name="deal-closer", tools=tools,
            instructions="Ask humans for approvals over $10K")
        result = await agent.run("Approve the MegaInc deal")

    Requires: pip install openai[agents]
    """
    try:
        from openai.agents import function_tool
    except ImportError:
        logger.warning("openai.agents not available — install with: pip install openai[agents]")
        return []

    @function_tool
    async def human_ask(
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
        return await _execute(gateway, "human_ask", {
            "name": name, "question": question, "response_type": response_type,
            "options": options, "context": context, "namespace": namespace,
            "priority": priority,
        }, from_participant)

    @function_tool
    async def human_notify(
        name: str,
        message: str,
        namespace: str = "default",
        severity: str = "info",
        priority: str = "low",
    ) -> str:
        """Send a notification to a human. No response needed."""
        return await _execute(gateway, "human_notify", {
            "name": name, "message": message, "namespace": namespace,
            "severity": severity, "priority": priority,
        }, from_participant)

    @function_tool
    async def human_check(request_id: str) -> str:
        """Check the status of a pending human request."""
        return await _execute(gateway, "human_check",
                              {"request_id": request_id}, from_participant)

    return [human_ask, human_notify, human_check]


# ═══════════════════════════════════════════════════════════════════════════
# PATH 2: Chat Completions / Responses API (manual loop)
# ═══════════════════════════════════════════════════════════════════════════

A2H_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "human_ask",
            "description": "Ask a human a structured question and wait for their response.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Human's name"},
                    "question": {"type": "string", "description": "The question to ask"},
                    "response_type": {"type": "string", "enum": ["choice", "approval", "text", "number", "confirm"]},
                    "options": {"type": "string", "description": "JSON array of options for choice type"},
                    "context": {"type": "string", "description": "JSON object with decision context"},
                    "namespace": {"type": "string", "default": "default"},
                    "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                },
                "required": ["name", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "human_notify",
            "description": "Send a notification to a human. No response needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}, "message": {"type": "string"},
                    "namespace": {"type": "string"}, "severity": {"type": "string"},
                    "priority": {"type": "string"},
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
                "properties": {"request_id": {"type": "string"}},
                "required": ["request_id"],
            },
        },
    },
]


def get_a2h_tools() -> list[dict]:
    """Return A2H tools in OpenAI Chat Completions format."""
    return A2H_TOOLS


async def run_with_a2h(
    client, gateway, *, model: str = "gpt-4o", system: str = "", prompt: str,
    from_participant: str = "default/agent",
    extra_tools: list[dict] | None = None, max_steps: int = 10,
) -> dict:
    """Run a complete agentic loop with A2H tools (Chat Completions API)."""
    tools = get_a2h_tools() + (extra_tools or [])
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    all_tool_calls = []

    for step in range(max_steps):
        response = client.chat.completions.create(model=model, messages=messages, tools=tools)
        choice = response.choices[0]

        if not choice.message.tool_calls:
            return {"text": choice.message.content or "", "steps": step + 1, "tool_calls": all_tool_calls}

        messages.append({
            "role": "assistant", "content": choice.message.content,
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                           for tc in choice.message.tool_calls],
        })

        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            all_tool_calls.append({"name": tc.function.name, "input": args})
            result = await _execute(gateway, tc.function.name, args, from_participant)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return {"text": "[Max steps reached]", "steps": max_steps, "tool_calls": all_tool_calls}
