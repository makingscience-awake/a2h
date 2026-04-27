"""A2H Decision Audit Trail tests."""

import pytest
from a2h import (
    AuditEvent,
    DelegationRule,
    Gateway,
    InMemoryAuditLog,
    Participant,
    Status,
)
from a2h.audit import compute_response_time
from a2h.testing import MockChannel


@pytest.fixture
def audit():
    return InMemoryAuditLog()


@pytest.fixture
def gw(audit):
    channel = MockChannel()
    g = Gateway(channels=[channel], audit_log=audit)
    g.register(Participant(name="sarah", namespace="sales", role="VP Sales"))
    g.register(Participant(name="tom", namespace="sales", role="Manager"))
    g.register(Participant(name="bot", namespace="sales", participant_type="agent"))
    return g


# ---------------------------------------------------------------------------
# AuditEvent model
# ---------------------------------------------------------------------------

class TestAuditEvent:
    def test_auto_id(self):
        e = AuditEvent(event_type="test", interaction_id="req_123", actor="system")
        assert e.id.startswith("evt_")

    def test_auto_timestamp(self):
        e = AuditEvent(event_type="test", interaction_id="req_123", actor="system")
        assert e.timestamp != ""

    def test_to_dict(self):
        e = AuditEvent(event_type="test", interaction_id="req_123",
                       actor="sales/bot", details={"key": "val"})
        d = e.to_dict()
        assert d["event_type"] == "test"
        assert d["interaction_id"] == "req_123"
        assert d["actor"] == "sales/bot"
        assert d["details"] == {"key": "val"}


# ---------------------------------------------------------------------------
# InMemoryAuditLog
# ---------------------------------------------------------------------------

class TestAuditLogRecord:
    def test_record_and_len(self, audit):
        audit.record(AuditEvent(event_type="test", interaction_id="r1", actor="a"))
        audit.record(AuditEvent(event_type="test", interaction_id="r2", actor="b"))
        assert len(audit) == 2

    def test_get_history(self, audit):
        audit.record(AuditEvent(event_type="a", interaction_id="r1", actor="x"))
        audit.record(AuditEvent(event_type="b", interaction_id="r2", actor="x"))
        audit.record(AuditEvent(event_type="c", interaction_id="r1", actor="x"))
        history = audit.get_history("r1")
        assert len(history) == 2
        assert history[0].event_type == "a"
        assert history[1].event_type == "c"


class TestAuditLogQuery:
    def test_filter_by_event_type(self, audit):
        audit.record(AuditEvent(event_type="request_created", interaction_id="r1", actor="a"))
        audit.record(AuditEvent(event_type="response_recorded", interaction_id="r1", actor="b"))
        audit.record(AuditEvent(event_type="request_created", interaction_id="r2", actor="a"))
        results = audit.query(event_type="request_created")
        assert len(results) == 2

    def test_filter_by_participant_actor(self, audit):
        audit.record(AuditEvent(event_type="test", interaction_id="r1", actor="sales/bot"))
        audit.record(AuditEvent(event_type="test", interaction_id="r2", actor="ops/other"))
        results = audit.query(participant="sales/bot")
        assert len(results) == 1

    def test_filter_by_participant_in_details(self, audit):
        audit.record(AuditEvent(event_type="test", interaction_id="r1",
                                actor="system", details={"to": "sales/sarah"}))
        results = audit.query(participant="sales/sarah")
        assert len(results) == 1

    def test_limit(self, audit):
        for i in range(20):
            audit.record(AuditEvent(event_type="test", interaction_id=f"r{i}", actor="a"))
        results = audit.query(limit=5)
        assert len(results) == 5

    def test_combined_filters(self, audit):
        audit.record(AuditEvent(event_type="request_created", interaction_id="r1",
                                actor="sales/bot", details={"to": "sales/sarah"}))
        audit.record(AuditEvent(event_type="response_recorded", interaction_id="r1",
                                actor="sales/sarah"))
        audit.record(AuditEvent(event_type="request_created", interaction_id="r2",
                                actor="ops/bot"))
        results = audit.query(event_type="request_created", participant="sales/bot")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Gateway audit integration
# ---------------------------------------------------------------------------

class TestGatewayAuditIntegration:
    async def test_ask_emits_request_created(self, gw, audit):
        await gw.ask("sales/sarah", question="Approve?", response_type="approval")
        events = audit.query(event_type="request_created")
        assert len(events) == 1
        assert events[0].details["to"] == "sales/sarah"
        assert events[0].details["response_type"] == "approval"

    async def test_ask_emits_delivery(self, gw, audit):
        await gw.ask("sales/sarah", question="Test?")
        events = audit.query(event_type="request_delivered")
        assert len(events) >= 1
        assert events[0].details["success"] is True

    async def test_respond_emits_response_recorded(self, gw, audit):
        req = await gw.ask("sales/sarah", question="Yes?", response_type="confirm")
        gw.respond(req.id, {"confirmed": True})
        events = audit.query(event_type="response_recorded")
        assert len(events) == 1
        assert events[0].details["channel"] == "dashboard"
        assert events[0].details["response_data"] == {"confirmed": True}
        assert events[0].details["response_time_seconds"] is not None

    async def test_cancel_emits_request_cancelled(self, gw, audit):
        req = await gw.ask("sales/sarah", question="Cancel me")
        gw.cancel(req.id, reason="No longer needed")
        events = audit.query(event_type="request_cancelled")
        assert len(events) == 1
        assert events[0].details["reason"] == "No longer needed"

    async def test_notify_emits_notification_sent(self, gw, audit):
        await gw.notify("sales/sarah", message="Update")
        events = audit.query(event_type="notification_sent")
        assert len(events) == 1
        assert events[0].details["to"] == "sales/sarah"
        assert events[0].details["message"] == "Update"

    async def test_full_lifecycle_history(self, gw, audit):
        req = await gw.ask("sales/sarah", question="Approve?",
                           response_type="approval",
                           from_participant="sales/bot")
        gw.respond(req.id, {"approved": True})
        history = audit.get_history(req.id)
        types = [e.event_type for e in history]
        assert "request_created" in types
        assert "request_delivered" in types
        assert "response_recorded" in types

    async def test_ask_with_sender(self, gw, audit):
        await gw.ask("sales/sarah", question="Test?",
                     from_participant="sales/bot")
        events = audit.query(event_type="request_created")
        assert events[0].actor == "sales/bot"


# ---------------------------------------------------------------------------
# Delegation audit
# ---------------------------------------------------------------------------

class TestAuditDelegation:
    async def test_delegation_emits_event(self):
        audit = InMemoryAuditLog()
        gw = Gateway(channels=[MockChannel()], audit_log=audit)
        gw.register(Participant(
            name="bot", namespace="ops", participant_type="agent",
        ))
        gw.register(Participant(
            name="lead", namespace="ops",
            delegation_rules=[
                DelegationRule(
                    name="auto_small",
                    context_conditions={"amount": {"lt": 100}},
                    auto_response={"approved": True, "reason": "Auto: under $100"},
                ),
            ],
        ))

        req = await gw.ask("ops/lead", question="Approve $50?",
                           response_type="approval",
                           context={"amount": 50},
                           from_participant="ops/bot")
        assert req.status == Status.AUTO_DELEGATED
        assert req.matched_rule == "auto_small"

        events = audit.query(event_type="delegation_matched")
        assert len(events) == 1
        assert events[0].details["rule_name"] == "auto_small"
        assert events[0].details["auto_response"]["approved"] is True


# ---------------------------------------------------------------------------
# Rerouting audit
# ---------------------------------------------------------------------------

class TestAuditRerouting:
    async def test_reroute_emits_event(self):
        audit = InMemoryAuditLog()
        gw = Gateway(channels=[MockChannel()], audit_log=audit)
        alice = Participant(name="alice", namespace="eng", delegate="bob")
        bob = Participant(name="bob", namespace="eng")
        gw.register(alice)
        gw.register(bob)
        alice.set_state("away")

        req = await gw.ask("eng/alice", question="Help?")
        assert req.to_name == "bob"
        assert req.rerouted_from == "eng/alice"

        events = audit.query(event_type="request_rerouted")
        assert len(events) == 1
        assert events[0].details["from_target"] == "eng/alice"
        assert events[0].details["to_target"] == "eng/bob"


# ---------------------------------------------------------------------------
# Response time
# ---------------------------------------------------------------------------

class TestAuditResponseTime:
    async def test_response_time_computed(self, gw, audit):
        req = await gw.ask("sales/sarah", question="Quick?")
        gw.respond(req.id, {"text": "Done"})
        events = audit.query(event_type="response_recorded")
        rt = events[0].details["response_time_seconds"]
        assert rt is not None
        assert rt >= 0

    def test_compute_response_time_no_response(self):
        from a2h import Interaction
        i = Interaction(question="test")
        assert compute_response_time(i) is None


# ---------------------------------------------------------------------------
# No audit log (backward compat)
# ---------------------------------------------------------------------------

class TestAuditNoLog:
    async def test_gateway_without_audit_works(self):
        gw = Gateway(channels=[MockChannel()])
        gw.register(Participant(name="sarah", namespace="sales"))
        req = await gw.ask("sales/sarah", question="Test?")
        assert req.status == Status.PENDING
        result = gw.respond(req.id, {"text": "OK"})
        assert result["success"] is True
        gw.cancel(req.id)


# ---------------------------------------------------------------------------
# Interaction audit metadata
# ---------------------------------------------------------------------------

class TestInteractionAuditMetadata:
    async def test_matched_rule_set(self):
        gw = Gateway(channels=[MockChannel()])
        gw.register(Participant(
            name="lead", namespace="ops",
            delegation_rules=[
                DelegationRule(name="auto_all", auto_response={"approved": True}),
            ],
        ))
        req = await gw.ask("ops/lead", question="?", response_type="approval")
        assert req.matched_rule == "auto_all"

    async def test_no_matched_rule(self):
        gw = Gateway(channels=[MockChannel()])
        gw.register(Participant(name="sarah", namespace="sales"))
        req = await gw.ask("sales/sarah", question="?")
        assert req.matched_rule is None

    async def test_rerouted_from_set(self):
        gw = Gateway(channels=[MockChannel()])
        alice = Participant(name="alice", namespace="eng", delegate="bob")
        gw.register(alice)
        gw.register(Participant(name="bob", namespace="eng"))
        alice.set_state("away")
        req = await gw.ask("eng/alice", question="?")
        assert req.rerouted_from == "eng/alice"

    async def test_no_reroute(self):
        gw = Gateway(channels=[MockChannel()])
        gw.register(Participant(name="sarah", namespace="sales"))
        req = await gw.ask("sales/sarah", question="?")
        assert req.rerouted_from is None
