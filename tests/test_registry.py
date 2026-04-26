"""A2H Participant Registry tests."""

import textwrap
from pathlib import Path

import pytest
from a2h import (
    DuplicateParticipant,
    Gateway,
    Participant,
    ParticipantRegistry,
    RegistryLoadError,
    Status,
    UnauthorizedParticipant,
)


@pytest.fixture
def yaml_file(tmp_path):
    """Write a sample participants.yaml and return its path."""
    content = textwrap.dedent("""\
        version: "1"

        defaults:
          availability: business_hours
          channels: [dashboard]

        participants:
          - name: sarah
            namespace: sales
            type: human
            role: VP Sales
            channels: [dashboard, slack]
            delegate: tom

          - name: tom
            namespace: sales
            type: human
            role: Manager

          - name: oncall
            namespace: ops
            type: human
            channels: [dashboard, slack, sms]
            metadata:
              rotation: weekly

          - name: pipeline-agent
            namespace: sales
            type: agent
            description: Qualifies leads
            identity:
              display_name: Sales Pipeline Agent
              deployed_by: sales-ops
              platform_name: ForgeOS
              verified: true
    """)
    p = tmp_path / "participants.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def delegation_yaml(tmp_path):
    """YAML with delegation rules."""
    content = textwrap.dedent("""\
        participants:
          - name: lead
            namespace: sales
            type: human
            delegation_rules:
              - name: auto_approve_small
                match:
                  from_namespace: sales
                  from_name_pattern: "sales-*"
                  response_type: approval
                  context_conditions:
                    deal_value: { lt: 10000 }
                auto_response:
                  approved: true
                  reason: "Auto: under $10K"
    """)
    p = tmp_path / "delegation.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def states_yaml(tmp_path):
    """YAML with custom states."""
    content = textwrap.dedent("""\
        participants:
          - name: alice
            namespace: eng
            type: human
            delegate: ops/oncall
            states:
              available:
                accepts_requests: true
              busy:
                accepts_requests: false
                queue: true
              away:
                accepts_requests: false
                reroute_to: delegate
              offline:
                accepts_requests: false
                reroute_to: ops/oncall
    """)
    p = tmp_path / "states.yaml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestRegistryLoad:
    def test_loads_participants(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        assert len(reg.list()) == 4

    def test_humans_loaded(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        sarah = reg.get("sales/sarah")
        assert sarah is not None
        assert sarah.participant_type == "human"
        assert sarah.role == "VP Sales"
        assert sarah.channels == ["dashboard", "slack"]
        assert sarah.delegate == "tom"

    def test_agents_loaded(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        agent = reg.get("sales/pipeline-agent")
        assert agent is not None
        assert agent.participant_type == "agent"
        assert agent.description == "Qualifies leads"

    def test_trust_level_verified(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        for p in reg.list():
            assert p.trust_level == "verified"

    def test_is_file_loaded(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        assert reg.is_file_loaded("sales/sarah") is True
        assert reg.is_file_loaded("unknown/pid") is False

    def test_file_path_stored(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        assert reg.file_path == yaml_file

    def test_load_returns_pids(self, yaml_file):
        reg = ParticipantRegistry()
        pids = reg.load(yaml_file)
        assert "sales/sarah" in pids
        assert "sales/pipeline-agent" in pids
        assert len(pids) == 4


class TestRegistryDefaults:
    def test_defaults_applied(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        tom = reg.get("sales/tom")
        assert tom.availability == "business_hours"
        assert tom.channels == ["dashboard"]

    def test_defaults_overridden(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        sarah = reg.get("sales/sarah")
        assert sarah.channels == ["dashboard", "slack"]

    def test_metadata_loaded(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        oncall = reg.get("ops/oncall")
        assert oncall.metadata == {"rotation": "weekly"}


class TestRegistryIdentity:
    def test_agent_identity_parsed(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        agent = reg.get("sales/pipeline-agent")
        assert agent.identity is not None
        assert agent.identity.display_name == "Sales Pipeline Agent"
        assert agent.identity.deployed_by == "sales-ops"
        assert agent.identity.platform_name == "ForgeOS"
        assert agent.identity.verified is True

    def test_agent_identity_inherits_name(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        agent = reg.get("sales/pipeline-agent")
        assert agent.identity.name == "pipeline-agent"
        assert agent.identity.namespace == "sales"

    def test_identity_in_card(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        agent = reg.get("sales/pipeline-agent")
        card = agent.to_card()
        assert "identity" in card
        assert card["trust_level"] == "verified"


class TestRegistryDelegationRules:
    def test_delegation_rules_parsed(self, delegation_yaml):
        reg = ParticipantRegistry(delegation_yaml)
        lead = reg.get("sales/lead")
        assert len(lead.delegation_rules) == 1
        rule = lead.delegation_rules[0]
        assert rule.name == "auto_approve_small"
        assert rule.from_namespace == "sales"
        assert rule.from_name_pattern == "sales-*"
        assert rule.response_type == "approval"
        assert rule.context_conditions == {"deal_value": {"lt": 10000}}
        assert rule.auto_response == {"approved": True, "reason": "Auto: under $10K"}


class TestRegistryStates:
    def test_custom_states_parsed(self, states_yaml):
        reg = ParticipantRegistry(states_yaml)
        alice = reg.get("eng/alice")
        assert "available" in alice.states
        assert alice.states["available"].accepts_requests is True
        assert alice.states["busy"].queue is True
        assert alice.states["away"].reroute_to == "delegate"
        assert alice.states["offline"].reroute_to == "ops/oncall"

    def test_delegate_with_namespace(self, states_yaml):
        reg = ParticipantRegistry(states_yaml)
        alice = reg.get("eng/alice")
        assert alice.delegate == "ops/oncall"
        assert alice.delegate_pid == "ops/oncall"


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

class TestRegistryStrictMode:
    def test_runtime_register_raises(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="strict")
        with pytest.raises(UnauthorizedParticipant):
            reg.register(Participant(name="new-agent", namespace="sales", participant_type="agent"))

    def test_cannot_unregister_file_loaded(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="strict")
        assert reg.unregister("sales/sarah") is False

    def test_file_loaded_participants_work(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="strict")
        assert reg.get("sales/sarah") is not None
        assert len(reg.list()) == 4


class TestRegistryPermissiveMode:
    def test_runtime_register_allowed(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="permissive")
        pid = reg.register(Participant(name="new-bot", namespace="sales", participant_type="agent"))
        assert pid == "sales/new-bot"
        assert reg.get("sales/new-bot").trust_level == "runtime"

    def test_file_loaded_are_verified(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="permissive")
        assert reg.get("sales/sarah").trust_level == "verified"

    def test_can_unregister_runtime(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="permissive")
        reg.register(Participant(name="temp", namespace="sales", participant_type="agent"))
        assert reg.unregister("sales/temp") is True
        assert reg.get("sales/temp") is None

    def test_can_unregister_file_loaded(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="permissive")
        assert reg.unregister("sales/sarah") is True

    def test_duplicate_raises(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="permissive")
        with pytest.raises(DuplicateParticipant):
            reg.register(Participant(name="sarah", namespace="sales"))

    def test_duplicate_allow_replace(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="permissive")
        reg.register(
            Participant(name="sarah", namespace="sales", role="New Role"),
            allow_replace=True,
        )
        assert reg.get("sales/sarah").role == "New Role"
        assert reg.get("sales/sarah").trust_level == "runtime"


class TestRegistryListFilters:
    def test_filter_by_type(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        humans = reg.list(participant_type="human")
        assert len(humans) == 3
        agents = reg.list(participant_type="agent")
        assert len(agents) == 1

    def test_filter_by_namespace(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        sales = reg.list(namespace="sales")
        assert len(sales) == 3

    def test_filter_by_trust_level(self, yaml_file):
        reg = ParticipantRegistry(yaml_file, mode="permissive")
        reg.register(Participant(name="temp", namespace="sales", participant_type="agent"))
        verified = reg.list(trust_level="verified")
        assert len(verified) == 4
        runtime = reg.list(trust_level="runtime")
        assert len(runtime) == 1


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------

class TestRegistryReload:
    def test_reload_picks_up_changes(self, tmp_path):
        p = tmp_path / "reg.yaml"
        p.write_text(textwrap.dedent("""\
            participants:
              - name: alice
                namespace: eng
                type: human
        """))
        reg = ParticipantRegistry(p)
        assert len(reg.list()) == 1

        p.write_text(textwrap.dedent("""\
            participants:
              - name: alice
                namespace: eng
                type: human
              - name: bob
                namespace: eng
                type: human
        """))
        reg.reload()
        assert len(reg.list()) == 2

    def test_reload_removes_deleted(self, tmp_path):
        p = tmp_path / "reg.yaml"
        p.write_text(textwrap.dedent("""\
            participants:
              - name: alice
                namespace: eng
                type: human
              - name: bob
                namespace: eng
                type: human
        """))
        reg = ParticipantRegistry(p)
        assert reg.get("eng/bob") is not None

        p.write_text(textwrap.dedent("""\
            participants:
              - name: alice
                namespace: eng
                type: human
        """))
        reg.reload()
        assert reg.get("eng/bob") is None

    def test_reload_preserves_runtime(self, tmp_path):
        p = tmp_path / "reg.yaml"
        p.write_text(textwrap.dedent("""\
            participants:
              - name: alice
                namespace: eng
                type: human
        """))
        reg = ParticipantRegistry(p, mode="permissive")
        reg.register(Participant(name="runtime-bot", namespace="eng", participant_type="agent"))
        reg.reload()
        assert reg.get("eng/runtime-bot") is not None
        assert reg.get("eng/runtime-bot").trust_level == "runtime"

    def test_reload_no_path_raises(self):
        reg = ParticipantRegistry()
        with pytest.raises(RegistryLoadError):
            reg.reload()


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestRegistryValidation:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(RegistryLoadError, match="not found"):
            ParticipantRegistry(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("{{invalid yaml")
        with pytest.raises(RegistryLoadError, match="YAML parse error"):
            ParticipantRegistry(p)

    def test_missing_participants_key(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("version: '1'\n")
        with pytest.raises(RegistryLoadError, match="participants"):
            ParticipantRegistry(p)

    def test_invalid_participant_name(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(textwrap.dedent("""\
            participants:
              - name: "invalid/name"
                namespace: test
        """))
        with pytest.raises(RegistryLoadError, match="Invalid"):
            ParticipantRegistry(p)

    def test_missing_name(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(textwrap.dedent("""\
            participants:
              - namespace: test
                type: human
        """))
        with pytest.raises(RegistryLoadError):
            ParticipantRegistry(p)

    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Invalid registry mode"):
            ParticipantRegistry(mode="invalid")


# ---------------------------------------------------------------------------
# Gateway integration
# ---------------------------------------------------------------------------

class TestGatewayWithRegistry:
    def test_gateway_with_file(self, yaml_file):
        gw = Gateway(participants_file=str(yaml_file))
        assert gw.get_participant("sales/sarah") is not None
        assert gw.get_participant("sales/sarah").trust_level == "verified"

    def test_gateway_with_registry(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        gw = Gateway(registry=reg)
        assert gw.get_participant("sales/sarah") is not None

    def test_gateway_both_raises(self, yaml_file):
        reg = ParticipantRegistry(yaml_file)
        with pytest.raises(ValueError, match="Cannot specify both"):
            Gateway(registry=reg, participants_file=str(yaml_file))

    def test_gateway_default_permissive(self):
        gw = Gateway()
        gw.register(Participant(name="test", namespace="ns", participant_type="human"))
        assert gw.get_participant("ns/test") is not None

    async def test_ask_respond_with_file(self, yaml_file):
        gw = Gateway(participants_file=str(yaml_file))
        req = await gw.ask(
            "sales/sarah",
            question="Approve deal?",
            response_type="approval",
            from_participant="sales/pipeline-agent",
        )
        assert req.status == Status.PENDING
        result = gw.respond(req.id, {"approved": True})
        assert result["success"] is True

    async def test_strict_mode_blocks_register(self, yaml_file):
        gw = Gateway(participants_file=str(yaml_file), registry_mode="strict")
        with pytest.raises(UnauthorizedParticipant):
            gw.register(Participant(name="rogue", namespace="sales", participant_type="agent"))

    def test_discover_shows_trust(self, yaml_file):
        gw = Gateway(participants_file=str(yaml_file))
        cards = gw.discover()
        assert all(c["trust_level"] == "verified" for c in cards)

    def test_registry_property(self, yaml_file):
        gw = Gateway(participants_file=str(yaml_file))
        assert isinstance(gw.registry, ParticipantRegistry)
        assert gw.registry.file_path is not None
