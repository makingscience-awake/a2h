# A2H Framework Integrations

Use A2H with any agent framework or LLM SDK. Same protocol, native tool bindings.

## OpenAI SDK (GPT-4o, o3, etc.)

```python
from openai import OpenAI
from a2h import Gateway, Participant
from integrations.openai.a2h_openai import run_with_a2h

gw = Gateway()
gw.register(Participant(name="sarah", namespace="sales"))
client = OpenAI()

result = await run_with_a2h(client, gw, model="gpt-4o",
    system="Ask humans for approvals over $10K",
    prompt="Approve the MegaInc deal at $2.5M",
    from_name="sales-agent")
```

## Anthropic SDK (Claude)

```python
from anthropic import Anthropic
from a2h import Gateway, Participant
from integrations.anthropic.a2h_anthropic import run_with_a2h

gw = Gateway()
gw.register(Participant(name="sarah", namespace="sales"))
client = Anthropic()

result = await run_with_a2h(client, gw, model="claude-sonnet-4-20250514",
    system="Ask humans for approvals over $10K",
    prompt="Approve the MegaInc deal at $2.5M",
    from_name="sales-agent")
```

## xAI/Grok

```python
from a2h import Gateway, Participant
from integrations.xai.a2h_xai import create_grok_client, run_with_a2h

gw = Gateway()
gw.register(Participant(name="sarah", namespace="sales"))
client = create_grok_client()  # uses XAI_API_KEY env var

result = await run_with_a2h(client, gw, model="grok-3",
    system="Ask humans for approvals",
    prompt="Approve the deal",
    from_name="sales-agent")
```

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

| Tool | OpenAI | Anthropic | xAI/Grok | ADK | CrewAI | LangChain | OpenClaw |
|------|--------|-----------|----------|-----|--------|-----------|----------|
| `human_ask` | function call | tool_use block | function call | FunctionTool | BaseTool | StructuredTool | HTTP POST |
| `human_check` | function call | tool_use block | function call | FunctionTool | BaseTool | StructuredTool | HTTP GET |
| `human_notify` | function call | tool_use block | function call | FunctionTool | BaseTool | StructuredTool | HTTP POST |
| Agentic loop | `run_with_a2h()` | `run_with_a2h()` | `run_with_a2h()` | via Runner | via Crew | via AgentExecutor | manual |

All integrations use the same `Gateway` instance and `Participant` registrations. The protocol is identical — only the tool wrapper differs.

**OpenAI-compatible APIs** (Together, Fireworks, Groq, Ollama, etc.) work with the OpenAI integration — just set `base_url`:

```python
from openai import OpenAI
client = OpenAI(base_url="https://api.together.xyz/v1", api_key=TOGETHER_KEY)
# Then use run_with_a2h(client, gw, model="meta-llama/...", ...)
```
