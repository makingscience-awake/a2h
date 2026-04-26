# A2H — Agent-to-Human Interaction Protocol

**The missing piece for human-agent collaboration.**

[A2A](https://github.com/google/A2A) defined how agents talk to agents. [MCP](https://modelcontextprotocol.io) defined how agents use tools. **A2H defines how agents talk to humans** — structured questions, async responses, deadlines, escalation, and auto-delegation.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│               THE COLLABORATION STACK                       │
│                                                             │
│    ┌─────────┐    A2A     ┌─────────┐    MCP    ┌───────┐  │
│    │  Agent  │◄──────────►│  Agent  │──────────►│ Tool  │  │
│    └────┬────┘            └─────────┘           └───────┘  │
│         │                                                   │
│         │  A2H (this protocol)                              │
│         │  structured questions                             │
│         │  async responses                                  │
│         │  deadlines + escalation                           │
│         │  auto-delegation                                  │
│         ▼                                                   │
│    ┌─────────┐                                              │
│    │  Human  │  responds via dashboard / Slack / email      │
│    └────┬────┘                                              │
│         │                                                   │
│         │  H2A (A2A from a UI — not a separate protocol)    │
│         │  human delegates work to agents                   │
│         ▼                                                   │
│    ┌─────────┐                                              │
│    │  Agent  │  executes the task using MCP tools            │
│    └─────────┘                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Why A2H?

Every real AI agent deployment reaches a point where an agent needs a human — an approval, a decision, clarification, a review. Today this is handled with ad-hoc Slack bots, custom UIs, and email triggers. There is no standard.

A2H is that standard. It defines:

| What | How |
|------|-----|
| **Structured questions** | Choice, approval, text, number, confirm, form — not free text |
| **Async responses** | Deadlines measured in hours, not milliseconds |
| **Delivery channels** | Dashboard, Slack, email, SMS — protocol doesn't care which |
| **Auto-delegation** | Rules that auto-respond to routine requests |
| **Escalation chains** | Timeout-based promotion to next human |
| **Availability states** | Busy → queue. Offline → reroute. Away → delegate. |

### What about H2A?

**H2A is not a separate protocol.** When a human delegates work to an agent, the protocol is A2A — the human just needs a UI (dashboard, Slack command, API call) that speaks A2A on their behalf. A2H is the genuinely novel part: agents reaching out to humans with structured requests.

## How It Works

```
┌──────────────────┐                        ┌──────────────────┐
│   Sales Agent    │                        │     Sarah        │
│   (AI)           │                        │     (Human)      │
│                  │                        │                  │
│  "Should we      │   POST /a2h/v1/       │   Sees in Slack: │
│   proceed with   │──────────────────────► │                  │
│   MegaInc at     │   requests            │   ┌────────────┐ │
│   $2.5M?"        │                        │   │ Approve    │ │
│                  │                        │   │ Counter    │ │
│  response_type:  │                        │   │ Reject     │ │
│    choice        │                        │   └────────────┘ │
│                  │                        │                  │
│  context:        │   POST /a2h/v1/       │   Clicks         │
│   deal: $2.5M    │◄──────────────────────│   "Approve"      │
│   bant: 87       │   requests/{id}/      │                  │
│   risk: medium   │   respond             │   "Good fit.     │
│                  │                        │    Proceed."     │
│  ✓ Approved      │                        │                  │
└──────────────────┘                        └──────────────────┘
```

## Quick Start

```python
from a2h import Gateway, Participant

# 1. Create gateway (strict mode ensures all participants are registered)
gw = Gateway(registry_mode="strict")

# 2. Register participants (humans and agents)
gw.register(Participant(
    name="sarah", namespace="sales", participant_type="human",
    role="VP Sales", channels=["dashboard", "slack"]
))
gw.register(Participant(
    name="sales-agent", namespace="ai", participant_type="agent"
))

# 3. Agent asks human
req = await gw.ask("sales/sarah",
    question="Approve the MegaInc deal at $2.5M?",
    response_type="choice",
    options=[
        {"label": "Approve", "value": "approve"},
        {"label": "Reject", "value": "reject"},
    ],
    context={"deal_value": 2500000, "bant_score": 87},
    priority="high",
    deadline="4h",
    from_participant="ai/sales-agent", # Sender identity is strictly validated
)
# req.id = "req_7f3a2b..."
# req.status = Status.PENDING

# 4. Human responds (from dashboard, Slack, email, API...)
gw.respond(req.id, {"value": "approve", "text": "Good fit."}, channel="slack")

# 5. Agent checks result
result = gw.get(req.id)
# result.status = Status.ANSWERED
# result.response.value = "approve"
```

## 6 Response Types

```python
# Choice — buttons
await gw.ask("sales/sarah", question="Pick one", response_type="choice",
    options=[{"label": "A", "value": "a"}, {"label": "B", "value": "b"}])

# Approval — approve/reject
await gw.ask("sales/sarah", question="Approve $500 spend?", response_type="approval")

# Free text — text field
await gw.ask("sales/sarah", question="What should we prioritize?", response_type="text")

# Number — numeric input
await gw.ask("sales/sarah", question="How many units to order?", response_type="number")

# Confirm — yes/no
await gw.ask("sales/sarah", question="Deploy to production?", response_type="confirm")

# Form — multi-field
await gw.ask("sales/sarah", question="New hire details", response_type="form",
    options=[{"label": "Name", "value": "name"}, {"label": "Role", "value": "role"}])
```

## Auto-Delegation

Humans can configure rules that auto-respond to routine requests:

```python
from a2h import DelegationRule

gw.register(Participant(
    name="priya", namespace="ops",
    delegation_rules=[
        DelegationRule(
            name="auto_approve_small",
            from_namespace="ops",
            response_type="approval",
            context_conditions={"amount": {"lt": 500}},
            auto_response={"approved": True, "reason": "Auto: under $500"},
        ),
    ],
))

# Agent asks — auto-approved immediately (no human action needed)
req = await gw.ask("ops/priya", question="Approve $200?",
    response_type="approval", context={"amount": 200}, from_namespace="ops")
# req.status = Status.AUTO_DELEGATED
# req.response.approved = True
```

## State-Aware Routing

When a human is unavailable, requests auto-reroute:

```python
alice = Participant(name="alice", namespace="eng", delegate="bob")
bob = Participant(name="bob", namespace="eng")
gw.register(alice)
gw.register(bob)

alice.set_state("away")  # away → reroute to delegate

req = await gw.ask("eng/alice", question="Need your review")
# req.to_name = "bob" (auto-rerouted to delegate)
```

| State | Behavior |
|-------|----------|
| `available` | Deliver immediately |
| `busy` | Queue until state changes |
| `away` | Reroute to delegate |
| `offline` | Reroute to on-call |

States are configurable — a call center adds `in_call` and `on_break`, a law firm adds `in_court`.

## Escalation Chains

If a human doesn't respond in time, auto-escalate:

```python
from a2h import EscalationChain, EscalationLevel

req = await gw.ask("sales/sarah",
    question="Urgent: approve deal?",
    escalation=EscalationChain(levels=[
        EscalationLevel(target="sales/sarah", timeout_minutes=10),
        EscalationLevel(target="sales/tom", timeout_minutes=30, priority_override="critical"),
    ]),
)
# If Sarah doesn't respond in 10 min → auto-escalates to Tom
```

## Participant Registry & Strict Validation

A2H includes a robust `ParticipantRegistry` to manage the identities of both humans and agents. In **strict mode**, the Gateway ensures that no unknown agent can ask a human a question, and no request is sent into the void.

```python
from a2h import Gateway

# Load participants from a YAML file and enforce strict validation
gw = Gateway(participants_file="participants.yaml", registry_mode="strict")

# If an unregistered agent tries to send a request:
await gw.ask(
    to="sales/sarah",
    question="Approve?",
    from_participant="unknown/hacker-bot"
) # Raises: SenderNotRegistered

# If an agent tries to contact an unregistered human:
await gw.ask(
    to="sales/nobody",
    question="Approve?",
    from_participant="ai/sales-agent"
) # Raises: ParticipantNotFound
```

Participant IDs (`namespace/name`) are strictly validated via regex and frozen upon creation to prevent identity drift.

## HTTP Transport

Run the A2H server with FastAPI:

```python
from a2h import Gateway, Participant
from a2h.server import create_app

gw = Gateway()
gw.register(Participant(name="sarah", namespace="sales"))

app = create_app(gw)
# uvicorn app:app --port 8000
```

### Endpoints

```
POST  /a2h/v1/requests                 → create request
GET   /a2h/v1/requests/{id}            → get status + response
POST  /a2h/v1/requests/{id}/respond    → submit response
POST  /a2h/v1/requests/{id}/cancel     → cancel request
GET   /a2h/v1/requests                 → list pending
POST  /a2h/v1/notifications            → send notification
GET   /.well-known/participants.json   → discovery
```

## Pluggable Architecture

### Custom Channels

```python
from a2h import Channel, Interaction, Notification

class SlackChannel:
    @property
    def name(self): return "slack"

    async def deliver_request(self, interaction: Interaction) -> bool:
        # Send Slack DM with interactive buttons
        await slack.send_dm(interaction.to_name, render_card(interaction))
        return True

    async def deliver_notification(self, notification: Notification) -> bool:
        await slack.send_dm(notification.to_name, notification.message)
        return True

gw = Gateway(channels=[SlackChannel()])
```

### Custom Storage

```python
from a2h import Store

class PostgresStore:
    def save(self, interaction): ...
    def get(self, interaction_id): ...
    def list_pending(self, to_pid=None): ...
    def respond(self, interaction_id, response): ...
    def cancel(self, interaction_id, reason=""): ...

gw = Gateway(store=PostgresStore(dsn="postgresql://..."))
```

## Real-World Example: Customer Support Complaint

A customer (Jane Smith, Premium tier) was charged twice for her $499 annual subscription. She's angry — this is her 3rd contact. The support agent investigates and routes decisions to the right humans.

```
┌──────────────┐                                             
│  Support     │  Step 2: confirm duplicate charge            
│  Agent       │──────A2H (confirm)──────► Maria (Support Agent)
│  (AI)        │                            ✓ "Confirmed"     
│              │                                              
│              │  Step 3: approve $499 refund                 
│              │──────A2H (approval)─────► Rachel (Team Lead) 
│              │  escalation:               ✓ "Approved"      
│              │  rachel(30m)→david(60m)                       
│              │                                              
│              │  Step 4: choose compensation                 
│              │──────A2H (choice)───────► Rachel             
│              │  options:                  ✓ "2 months free" 
│              │  [1mo│2mo│none│custom]                       
│              │                                              
│              │  Step 5: waive $15 late fee                  
│              │──────A2H (approval)─────► Rachel             
│              │  $15 < $100 rule           ✓ AUTO-DELEGATED  
│              │                            (no human action) 
│              │                                              
│              │  Step 6: resolution notification             
│              │──────A2H (notify)───────► Maria              
│              │  "Refund+credit processed.  (no response)    
│              │   Call Jane to confirm."                      
│              │                                              
│              │  Step 7: finance notification                
│              │──────A2H (notify)───────► David (Finance)    
│              │  "$597.17 total adjustment" (no response)    
└──────────────┘                                              
```

**Result:** 3 humans involved, but only **3 actual human actions** needed. The $15 late fee was auto-approved by Rachel's delegation rule. The agent handled all investigation, routing, and follow-up.

```python
# Step 3: Agent asks Rachel to approve the refund
req = await gw.ask("support/rachel",
    question="Approve refund of $499 for ticket #4521?",
    response_type="approval",
    priority="high",
    deadline="2h",
    escalation=EscalationChain(levels=[
        EscalationLevel(target="support/rachel", timeout_minutes=30),
        EscalationLevel(target="finance/david", timeout_minutes=60,
                        priority_override="critical"),
    ]),
    context={
        "ticket_id": "4521",
        "refund_amount": 499,
        "customer": "Jane Smith",
        "tier": "Premium",
        "lifetime_value": 14000,
        "reason": "duplicate_charge",
    },
    from_name="support-bot",
)

# Step 5: $15 waiver auto-delegated (Rachel's rule: < $100 = auto-approve)
req = await gw.ask("support/rachel",
    question="Waive $15 late fee?",
    response_type="approval",
    context={"refund_amount": 15},
    from_name="support-bot",
)
# req.status = Status.AUTO_DELEGATED (no human action needed)
```

Run the full example: `python examples/customer_support.py`

## Protocol Specification

The full specification is in [`docs/a2h-spec.md`](docs/a2h-spec.md), including:

- Data model with JSON Schemas
- HTTP transport endpoints
- Lifecycle state machine
- Delegation rule matching
- Escalation chain behavior
- Security considerations
- Conformance requirements

JSON Schemas: [`docs/schemas/`](docs/schemas/)

## Project Structure

```
a2h/
  __init__.py      # Public API: Gateway, Participant, Interaction, ...
  models.py        # Protocol types (zero dependencies)
  gateway.py       # Core protocol handler
  registry.py      # Participant identity management
  store.py         # Storage protocol + InMemoryStore
  channels.py      # Delivery channel protocol + LogChannel
  server.py        # FastAPI HTTP transport (optional dependency)
  callbacks.py     # Async callbacks and webhooks
  errors.py        # Typed protocol errors
  testing.py       # Mock channels and auto-responders
integrations/
  adk/             # Google ADK tools
  anthropic/       # Anthropic Claude tools
  crewai/          # CrewAI tools
  langchain/       # LangChain tools
  openai/          # OpenAI function calling
  openclaw/        # OpenClaw skills
  xai/             # xAI Grok tools
  slack_example.py # Example Slack channel implementation
examples/
  customer_support.py         # 7-step realistic workflow
  advanced_routing_example.py # Escalation & auto-delegation
  server_webhook_example.py   # FastAPI server + webhooks
  adk_a2h_example.py          # ADK integration example
  crewai_a2h_example.py       # CrewAI integration example
  langchain_a2h_example.py    # LangChain integration example
docs/
  a2h-spec.md      # Full protocol specification
  schemas/         # JSON Schemas for all protocol objects
tests/
  test_protocol.py # Core protocol conformance tests
  test_registry.py # Registry and validation tests (100 total tests)
```

## Install

```bash
pip install a2h              # core (zero dependencies)
pip install a2h[server]      # with FastAPI HTTP transport
```

## License

Apache 2.0
