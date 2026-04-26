"""
A2H integration for xAI/Grok.

Grok uses an OpenAI-compatible API, so this is a thin wrapper around
the OpenAI integration with the xAI base URL pre-configured.

    from a2h import Gateway, Participant
    from integrations.xai.a2h_xai import create_grok_client, run_with_a2h

    gw = Gateway()
    gw.register(Participant(name="sarah", namespace="sales"))

    client = create_grok_client()  # uses XAI_API_KEY env var
    result = await run_with_a2h(
        client, gw, model="grok-3",
        system="You are a sales agent.",
        prompt="Approve the MegaInc deal",
        from_name="sales-agent",
    )
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

# xAI/Grok uses OpenAI-compatible API — reuse the OpenAI integration
from integrations.openai.a2h_openai import (
    get_a2h_tools,
    execute_a2h_tool,
    run_with_a2h as _run_with_a2h,
    A2H_TOOLS,
)

XAI_BASE_URL = "https://api.x.ai/v1"
XAI_DEFAULT_MODEL = "grok-3"


def create_grok_client(api_key: str | None = None):
    """Create an OpenAI client pointed at xAI's API.

    Uses XAI_API_KEY environment variable if api_key not provided.
    """
    from openai import OpenAI

    key = api_key or os.environ.get("XAI_API_KEY", "")
    if not key:
        raise ValueError("XAI_API_KEY not set. Get one at https://console.x.ai/")

    return OpenAI(base_url=XAI_BASE_URL, api_key=key)


async def run_with_a2h(
    client,
    gateway,
    *,
    model: str = XAI_DEFAULT_MODEL,
    system: str = "",
    prompt: str,
    from_name: str = "",
    from_namespace: str = "default",
    extra_tools: list[dict] | None = None,
    max_steps: int = 10,
) -> dict:
    """Run a Grok agentic loop with A2H tools.

    Same interface as the OpenAI integration — Grok uses OpenAI-compatible API.
    """
    return await _run_with_a2h(
        client, gateway,
        model=model,
        system=system,
        prompt=prompt,
        from_name=from_name,
        from_namespace=from_namespace,
        extra_tools=extra_tools,
        max_steps=max_steps,
    )
