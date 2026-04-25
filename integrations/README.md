# A2H Framework Integrations

Use A2H with any agent framework. Same protocol, native tool bindings.

## Google ADK

```python
from a2h import Gateway, Participant
from integrations.adk.a2h_adk import build_a2h_tools

gw = Gateway()
gw.register(Participant(name="sarah", namespace="sales"))
tools = build_a2h_tools(gw, from_name="my-agent")

# tools = [FunctionTool(human_ask), FunctionTool(human_check), FunctionTool(human_notify)]
# Use with: Agent(name="...", tools=tools)
```

## CrewAI

```python
from a2h import Gateway, Participant
from integrations.crewai.a2h_crewai import build_a2h_tools

gw = Gateway()
gw.register(Participant(name="sarah", namespace="sales"))
tools = build_a2h_tools(gw, from_name="my-agent")

# tools = [HumanAskTool(), HumanNotifyTool(), HumanCheckTool()]
# Use with: Agent(role="...", tools=tools)
```

## LangChain

```python
from a2h import Gateway, Participant
from integrations.langchain.a2h_langchain import build_a2h_tools

gw = Gateway()
gw.register(Participant(name="sarah", namespace="sales"))
tools = build_a2h_tools(gw, from_name="my-agent")

# tools = [StructuredTool(human_ask), StructuredTool(human_check), StructuredTool(human_notify)]
# Use with: create_tool_calling_agent(llm, tools, prompt=...)
```

## OpenClaw

No code needed — copy `openclaw/skills.yaml` into your workspace's `SKILLS/` directory and set environment variables:

```bash
export A2H_SERVER_URL=http://localhost:8000
export A2H_PLATFORM_TOKEN=your-token
```

## What Each Integration Provides

| Tool | What it does | ADK | CrewAI | LangChain | OpenClaw |
|------|-------------|-----|--------|-----------|----------|
| `human_ask` | Ask a human a structured question | `FunctionTool` (async) | `BaseTool._run()` (sync) | `StructuredTool` (async) | HTTP POST |
| `human_check` | Check status of pending request | `FunctionTool` | `BaseTool` | `StructuredTool` | HTTP GET |
| `human_notify` | Send notification (no response) | `FunctionTool` | `BaseTool` | `StructuredTool` | HTTP POST |
| `human_list` | Discover available humans | — | — | — | HTTP GET |

All integrations use the same `Gateway` instance and `Participant` registrations. The protocol is identical — only the tool wrapper differs.
