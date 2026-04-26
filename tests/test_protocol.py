"""A2H Protocol conformance tests."""

import pytest
from a2h import (
    AgentIdentity,
    DelegationRule,
    DuplicateParticipant,
    EscalationChain,
    EscalationLevel,
    Gateway,
    Interaction,
    Participant,
    Priority,
    Response,
    ResponseType,
    SenderNotRegistered,
    ParticipantNotFound,
    Status,
)


@pytest.fixture
def gw():
    g = Gateway()
    g.register(Participant(name="sarah", namespace="sales", role="VP Sales"))
    g.register(Participant(name="tom", namespace="sales", role="Manager"))
    g.register(Participant(name="bot", namespace="sales", participant_type="agent"))
    return g


# ---------------------------------------------------------------------------
# Registration & Discovery
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_human(self, gw):
        assert gw.get_participant("sales/sarah") is not None

    def test_register_agent(self, gw):
        p = gw.get_participant("sales/bot")
        assert p.participant_type == "agent"

    def test_discover_returns_cards(self, gw):
        cards = gw.discover()
        assert len(cards) == 3
        assert all("protocol" in c for c in cards)

    def test_discover_filter_by_type(self, gw):
        humans = gw.discover(participant_type="human")
        assert len(humans) == 2

    def test_unregister(self, gw):
        assert gw.unregister("sales/sarah") is True
        assert gw.get_participant("sales/sarah") is None


# ---------------------------------------------------------------------------
# Participant validation
# ---------------------------------------------------------------------------

class TestParticipantValidation:
    def test_valid_name(self):
        p = Participant(name="sarah-01", namespace="sales.us-west")
        assert p.pid == "sales.us-west/sarah-01"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="Invalid name"):
            Participant(name="", namespace="sales")

    def test_empty_namespace_raises(self):
        with pytest.raises(ValueError, match="Invalid namespace"):
            Participant(name="sarah", namespace="")

    def test_slash_in_name_raises(self):
        with pytest.raises(ValueError, match="Invalid name"):
            Participant(name="foo/bar", namespace="sales")

    def test_whitespace_in_name_raises(self):
        with pytest.raises(ValueError, match="Invalid name"):
            Participant(name="foo bar", namespace="sales")

    def test_special_chars_raise(self):
        with pytest.raises(ValueError):
            Participant(name="foo@bar", namespace="sales")

    def test_name_too_long_raises(self):
        with pytest.raises(ValueError):
            Participant(name="a" * 65, namespace="sales")


class TestParticipantFreezing:
    def test_cannot_mutate_name(self):
        p = Participant(name="sarah", namespace="sales")
        with pytest.raises(AttributeError, match="frozen"):
            p.name = "hacked"

    def test_cannot_mutate_namespace(self):
        p = Participant(name="sarah", namespace="sales")
        with pytest.raises(AttributeError, match="frozen"):
            p.namespace = "hacked"

    def test_can_mutate_state(self):
        p = Participant(name="sarah", namespace="sales")
        p.set_state("busy")
        assert p.current_state == "busy"

    def test_can_mutate_delegation_rules(self):
        p = Participant(name="sarah", namespace="sales")
        p.delegation_rules.append(DelegationRule(name="test"))
        assert len(p.delegation_rules) == 1


# ---------------------------------------------------------------------------
# Registry duplicates
# ---------------------------------------------------------------------------

class TestRegistryDuplicates:
    def test_duplicate_raises(self, gw):
        with pytest.raises(DuplicateParticipant):
            gw.register(Participant(name="sarah", namespace="sales"))

    def test_allow_replace(self, gw):
        pid = gw.register(
            Participant(name="sarah", namespace="sales", role="New Role"),
            allow_replace=True,
        )
        assert gw.get_participant(pid).role == "New Role"


# ---------------------------------------------------------------------------
# Agent identity
# ---------------------------------------------------------------------------

class TestAgentIdentity:
    def test_agent_with_identity(self):
        identity = AgentIdentity(
            name="research-bot",
            namespace="eng",
            display_name="Research Bot",
            deployed_by="ACME Corp",
            platform_name="ACME Platform",
            verified=True,
        )
        p = Participant(
            name="research-bot",
            namespace="eng",
            participant_type="agent",
            identity=identity,
        )
        card = p.to_card()
        assert card["identity"]["display_name"] == "Research Bot"
        assert card["identity"]["platform"]["verified"] is True

    def test_human_card_has_no_identity(self):
        p = Participant(name="sarah", namespace="sales")
        card = p.to_card()
        assert "identity" not in card


# ---------------------------------------------------------------------------
# Delegate PID
# ---------------------------------------------------------------------------

class TestDelegatePID:
    def test_same_namespace_delegate(self):
        p = Participant(name="alice", namespace="eng", delegate="bob")
        assert p.delegate_pid == "eng/bob"

    def test_cross_namespace_delegate(self):
        p = Participant(name="alice", namespace="eng", delegate="ops/oncall")
        assert p.delegate_pid == "ops/oncall"

    def test_no_delegate(self):
        p = Participant(name="alice", namespace="eng")
        assert p.delegate_pid is None


# ---------------------------------------------------------------------------
# Ask & Respond lifecycle
# ---------------------------------------------------------------------------

class TestAskRespond:
    async def test_ask_creates_pending(self, gw):
        req = await gw.ask("sales/sarah", question="Approve?", response_type="approval")
        assert req.status == Status.PENDING
        assert req.id.startswith("req_")
        assert req.question == "Approve?"
        assert req.response_type == ResponseType.APPROVAL

    async def test_respond_answers(self, gw):
        req = await gw.ask("sales/sarah", question="Yes?", response_type="confirm")
        result = gw.respond(req.id, {"confirmed": True})
        assert result["success"] is True
        assert result["status"] == "answered"

        updated = gw.get(req.id)
        assert updated.status == Status.ANSWERED
        assert updated.response.confirmed is True

    async def test_respond_nonexistent_fails(self, gw):
        result = gw.respond("req_nonexistent", {"text": "hi"})
        assert result["success"] is False

    async def test_double_respond_fails(self, gw):
        req = await gw.ask("sales/sarah", question="Once?")
        gw.respond(req.id, {"text": "first"})
        result = gw.respond(req.id, {"text": "second"})
        assert result["success"] is False

    async def test_ask_unknown_participant_strict(self, gw):
        with pytest.raises(ParticipantNotFound):
            await gw.ask("sales/nobody", question="Hello?")

    async def test_ask_unknown_participant_lenient(self, gw):
        req = await gw.ask("sales/nobody", question="Hello?", strict=False)
        assert req.status == Status.CANCELLED

    async def test_choice_with_options(self, gw):
        req = await gw.ask("sales/sarah",
            question="Pick one",
            response_type="choice",
            options=[{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
        )
        assert len(req.options) == 2
        gw.respond(req.id, {"value": "a"})
        updated = gw.get(req.id)
        assert updated.response.value == "a"

    async def test_context_passed_through(self, gw):
        req = await gw.ask("sales/sarah", question="Approve deal?",
            context={"deal_value": 2500000, "score": 87})
        assert req.context["deal_value"] == 2500000

    async def test_priority_set(self, gw):
        req = await gw.ask("sales/sarah", question="Urgent!", priority="critical")
        assert req.priority == Priority.CRITICAL


# ---------------------------------------------------------------------------
# Sender verification
# ---------------------------------------------------------------------------

class TestSenderVerification:
    async def test_ask_with_registered_sender(self, gw):
        req = await gw.ask(
            "sales/sarah",
            question="Approve?",
            from_participant="sales/bot",
        )
        assert req.from_name == "bot"
        assert req.from_namespace == "sales"
        assert req.status == Status.PENDING

    async def test_ask_with_unregistered_sender_raises(self, gw):
        with pytest.raises(SenderNotRegistered):
            await gw.ask(
                "sales/sarah",
                question="Approve?",
                from_participant="unknown/agent",
            )

    async def test_anonymous_sender_allowed(self, gw):
        req = await gw.ask("sales/sarah", question="Approve?")
        assert req.status == Status.PENDING
        assert req.from_name == ""

    async def test_notify_with_registered_sender(self, gw):
        notif = await gw.notify(
            "sales/sarah",
            message="Update",
            from_participant="sales/bot",
        )
        assert notif.from_name == "bot"

    async def test_notify_with_unregistered_sender_raises(self, gw):
        with pytest.raises(SenderNotRegistered):
            await gw.notify(
                "sales/sarah",
                message="Update",
                from_participant="unknown/agent",
            )


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

class TestCancel:
    async def test_cancel_pending(self, gw):
        req = await gw.ask("sales/sarah", question="Cancel me")
        result = gw.cancel(req.id, reason="No longer needed")
        assert result["success"] is True
        assert gw.get(req.id).status == Status.CANCELLED

    async def test_cancel_answered_fails(self, gw):
        req = await gw.ask("sales/sarah", question="Answer then cancel")
        gw.respond(req.id, {"text": "done"})
        result = gw.cancel(req.id)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class TestNotifications:
    async def test_notify(self, gw):
        notif = await gw.notify("sales/sarah", message="Daily report ready")
        assert notif.id.startswith("notif_")
        assert notif.message == "Daily report ready"

    async def test_notify_with_severity(self, gw):
        notif = await gw.notify("sales/sarah", message="Alert!", severity="warning", priority="high")
        assert notif.severity == "warning"
        assert notif.priority == Priority.HIGH


# ---------------------------------------------------------------------------
# Pending list
# ---------------------------------------------------------------------------

class TestPendingList:
    async def test_list_pending(self, gw):
        await gw.ask("sales/sarah", question="Q1")
        await gw.ask("sales/sarah", question="Q2")
        await gw.ask("sales/tom", question="Q3")

        sarah_pending = gw.list_pending("sales/sarah")
        assert len(sarah_pending) == 2

        all_pending = gw.list_pending()
        assert len(all_pending) == 3


# ---------------------------------------------------------------------------
# Delegation rules
# ---------------------------------------------------------------------------

class TestDelegation:
    async def test_auto_approve(self):
        gw = Gateway()
        gw.register(Participant(
            name="bot", namespace="ops", participant_type="agent",
        ))
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

        req = await gw.ask("ops/priya", question="Approve $200?",
            response_type="approval",
            context={"amount": 200},
            from_participant="ops/bot")
        assert req.status == Status.AUTO_DELEGATED
        assert req.response.approved is True

    async def test_delegation_no_match_stays_pending(self):
        gw = Gateway()
        gw.register(Participant(
            name="priya", namespace="ops",
            delegation_rules=[
                DelegationRule(
                    name="auto_small",
                    context_conditions={"amount": {"lt": 500}},
                    auto_response={"approved": True},
                ),
            ],
        ))

        req = await gw.ask("ops/priya", question="Approve $1000?",
            response_type="approval", context={"amount": 1000})
        assert req.status == Status.PENDING

    async def test_delegation_pattern_match(self):
        gw = Gateway()
        gw.register(Participant(
            name="sales-pipeline-agent", namespace="sales", participant_type="agent",
        ))
        gw.register(Participant(
            name="lead", namespace="sales",
            delegation_rules=[
                DelegationRule(
                    name="from_sales_agents",
                    from_name_pattern="sales-*",
                    auto_response={"approved": True},
                ),
            ],
        ))

        req = await gw.ask("sales/lead", question="Approve?",
            response_type="approval", from_participant="sales/sales-pipeline-agent")
        assert req.status == Status.AUTO_DELEGATED

        req2 = await gw.ask("sales/lead", question="Approve?",
            response_type="approval")
        assert req2.status == Status.PENDING


# ---------------------------------------------------------------------------
# State-aware routing
# ---------------------------------------------------------------------------

class TestStateRouting:
    async def test_reroutes_when_away(self):
        gw = Gateway()
        alice = Participant(name="alice", namespace="eng", delegate="bob")
        bob = Participant(name="bob", namespace="eng")
        gw.register(alice)
        gw.register(bob)

        alice.set_state("away")

        req = await gw.ask("eng/alice", question="You there?")
        assert req.to_name == "bob"

    async def test_cross_namespace_delegate(self):
        gw = Gateway()
        alice = Participant(name="alice", namespace="eng", delegate="ops/oncall")
        oncall = Participant(name="oncall", namespace="ops")
        gw.register(alice)
        gw.register(oncall)

        alice.set_state("away")

        req = await gw.ask("eng/alice", question="Help?")
        assert req.to_name == "oncall"
        assert req.to_namespace == "ops"

    async def test_queues_when_busy(self):
        gw = Gateway()
        alice = Participant(name="alice", namespace="eng")
        gw.register(alice)
        alice.set_state("busy")

        req = await gw.ask("eng/alice", question="When free?")
        assert req.status == Status.PENDING
        assert req.to_name == "alice"


# ---------------------------------------------------------------------------
# Cascade unregister
# ---------------------------------------------------------------------------

class TestCascadeUnregister:
    async def test_cascade_cancels_pending(self):
        gw = Gateway()
        gw.register(Participant(name="sarah", namespace="sales"))
        await gw.ask("sales/sarah", question="Q1")
        await gw.ask("sales/sarah", question="Q2")
        assert len(gw.list_pending("sales/sarah")) == 2

        gw.unregister("sales/sarah", cascade=True)
        assert gw.get_participant("sales/sarah") is None

    async def test_cascade_clears_delegate(self):
        gw = Gateway()
        gw.register(Participant(name="alice", namespace="eng", delegate="bob"))
        gw.register(Participant(name="bob", namespace="eng"))

        gw.unregister("eng/bob", cascade=True)
        alice = gw.get_participant("eng/alice")
        assert alice.delegate is None


# ---------------------------------------------------------------------------
# Escalation chains
# ---------------------------------------------------------------------------

class TestEscalation:
    def test_chain_progression(self):
        chain = EscalationChain(levels=[
            EscalationLevel(target="lead", timeout_minutes=5),
            EscalationLevel(target="manager", timeout_minutes=10),
        ])
        assert chain.next_target().target == "lead"
        chain.promote()
        assert chain.next_target().target == "manager"
        chain.promote()
        assert chain.next_target() is None


# ---------------------------------------------------------------------------
# Async wait
# ---------------------------------------------------------------------------

class TestAsyncWait:
    async def test_wait_returns_on_respond(self, gw):
        import asyncio

        req = await gw.ask("sales/sarah", question="Waiting...")

        async def _respond_later():
            await asyncio.sleep(0.05)
            gw.respond(req.id, {"text": "Here!"})

        asyncio.create_task(_respond_later())
        result = await gw.wait(req.id, timeout=5.0)
        assert result.status == Status.ANSWERED
        assert result.response.text == "Here!"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    async def test_interaction_to_dict(self, gw):
        req = await gw.ask("sales/sarah", question="Test?", priority="high")
        d = req.to_dict()
        assert d["protocol"] == "a2h/v1"
        assert d["from"]["participant_type"] == "agent"
        assert d["to"]["participant_type"] == "human"
        assert d["content"]["question"] == "Test?"
        assert d["priority"] == "high"
        assert d["status"] == "pending"

    def test_participant_card(self):
        p = Participant(name="sarah", namespace="sales", role="VP",
                        channels=["dashboard", "slack"])
        card = p.to_card()
        assert card["protocol"] == "a2h/v1"
        assert card["participant_type"] == "human"
        assert card["a2h"]["channels"] == ["dashboard", "slack"]
