"""
A2H Participant Registry — file-backed participant management.

Loads participants from a YAML configuration file and serves as the
source of truth for who is authorized to operate in the system.

    from a2h.registry import ParticipantRegistry

    # Load from file
    registry = ParticipantRegistry("participants.yaml")

    # Or strict mode — blocks runtime registration
    registry = ParticipantRegistry("participants.yaml", mode="strict")

    # Use with Gateway
    gw = Gateway(registry=registry)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .errors import DuplicateParticipant, RegistryLoadError, UnauthorizedParticipant
from .models import (
    AgentIdentity,
    DelegationRule,
    Participant,
    StateRule,
)

logger = logging.getLogger(__name__)


class ParticipantRegistry:
    """Centralized participant registry with optional YAML file backing.

    Modes:
        permissive: File-loaded participants get trust_level="verified".
                    Runtime registration is allowed with trust_level="runtime".
        strict:     Only file-declared participants are allowed. Runtime
                    ``register()`` raises ``UnauthorizedParticipant``.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        mode: str = "permissive",
    ):
        if mode not in ("permissive", "strict"):
            raise ValueError(f"Invalid registry mode '{mode}': must be 'permissive' or 'strict'")
        self._mode = mode
        self._participants: dict[str, Participant] = {}
        self._file_pids: set[str] = set()
        self._path: Path | None = None

        if path is not None:
            self.load(path)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def file_path(self) -> Path | None:
        return self._path

    # ---- Loading -----------------------------------------------------------

    def load(self, path: str | Path) -> list[str]:
        """Load participants from a YAML file.

        Returns list of loaded PIDs. Raises ``RegistryLoadError``
        on parse or validation errors.
        """
        path = Path(path)
        if not path.exists():
            raise RegistryLoadError(f"Registry file not found: {path}", path=str(path))

        try:
            raw = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise RegistryLoadError(f"YAML parse error in {path}: {e}", path=str(path)) from e

        if not isinstance(data, dict):
            raise RegistryLoadError(
                f"Invalid registry file: expected a mapping, got {type(data).__name__}",
                path=str(path),
            )

        participants_data = data.get("participants")
        if not isinstance(participants_data, list):
            raise RegistryLoadError(
                "Registry file must contain a 'participants' list",
                path=str(path),
            )

        defaults = data.get("defaults", {}) or {}
        loaded_pids: list[str] = []

        for i, entry in enumerate(participants_data):
            if not isinstance(entry, dict):
                raise RegistryLoadError(
                    f"Participant entry #{i + 1} must be a mapping",
                    path=str(path),
                )
            try:
                participant = self._parse_participant(entry, defaults)
            except (ValueError, TypeError, KeyError) as e:
                name = entry.get("name", f"entry #{i + 1}")
                raise RegistryLoadError(
                    f"Invalid participant '{name}': {e}",
                    path=str(path),
                ) from e

            pid = participant.pid
            self._participants[pid] = participant
            self._file_pids.add(pid)
            loaded_pids.append(pid)

        self._path = path
        logger.info("A2H registry loaded %d participants from %s", len(loaded_pids), path)
        return loaded_pids

    def reload(self) -> list[str]:
        """Reload from the last-loaded file path.

        File-loaded participants are replaced. Runtime-registered
        participants are preserved.
        """
        if self._path is None:
            raise RegistryLoadError("No file path to reload from")

        for pid in list(self._file_pids):
            self._participants.pop(pid, None)
        self._file_pids.clear()

        return self.load(self._path)

    # ---- Registration ------------------------------------------------------

    def register(self, participant: Participant, *, allow_replace: bool = False) -> str:
        """Register a participant at runtime.

        In strict mode, raises ``UnauthorizedParticipant``.
        In permissive mode, sets ``trust_level="runtime"``.
        """
        pid = participant.pid

        if self._mode == "strict":
            raise UnauthorizedParticipant(
                f"Runtime registration of '{pid}' is not allowed in strict mode",
                pid=pid,
            )

        if pid in self._participants and not allow_replace:
            raise DuplicateParticipant(
                f"Participant '{pid}' is already registered",
                pid=pid,
            )

        participant.trust_level = "runtime"
        self._participants[pid] = participant
        logger.info("A2H registry: runtime-registered %s (%s)", pid, participant.participant_type)
        return pid

    def unregister(self, pid: str) -> bool:
        """Remove a participant from the registry.

        In strict mode, file-loaded participants cannot be unregistered.
        """
        if self._mode == "strict" and pid in self._file_pids:
            logger.warning("A2H registry: cannot unregister file-loaded participant %s in strict mode", pid)
            return False

        removed = self._participants.pop(pid, None)
        if removed is None:
            return False

        self._file_pids.discard(pid)
        return True

    # ---- Lookup ------------------------------------------------------------

    def get(self, pid: str) -> Participant | None:
        return self._participants.get(pid)

    def resolve(self, namespace: str, name: str) -> Participant | None:
        return self._participants.get(f"{namespace}/{name}")

    def list(
        self,
        *,
        participant_type: str | None = None,
        namespace: str | None = None,
        trust_level: str | None = None,
    ) -> list[Participant]:
        results = list(self._participants.values())
        if participant_type:
            results = [p for p in results if p.participant_type == participant_type]
        if namespace:
            results = [p for p in results if p.namespace == namespace]
        if trust_level:
            results = [p for p in results if p.trust_level == trust_level]
        return results

    def is_file_loaded(self, pid: str) -> bool:
        return pid in self._file_pids

    # ---- YAML parsing internals --------------------------------------------

    def _parse_participant(self, data: dict[str, Any], defaults: dict[str, Any]) -> Participant:
        name = data["name"]
        namespace = data.get("namespace", defaults.get("namespace", "default"))
        participant_type = data.get("type", data.get("participant_type", "human"))

        channels = data.get("channels", defaults.get("channels", ["dashboard"]))
        availability = data.get("availability", defaults.get("availability", "business_hours"))

        kwargs: dict[str, Any] = {
            "name": name,
            "namespace": namespace,
            "participant_type": participant_type,
            "channels": channels,
            "availability": availability,
            "trust_level": "verified",
        }

        if "description" in data:
            kwargs["description"] = data["description"]
        if "role" in data:
            kwargs["role"] = data["role"]
        if "delegate" in data:
            kwargs["delegate"] = data["delegate"]
        if "current_state" in data:
            kwargs["current_state"] = data["current_state"]
        if "metadata" in data:
            kwargs["metadata"] = data["metadata"]

        if "states" in data:
            kwargs["states"] = self._parse_states(data["states"])

        if "delegation_rules" in data:
            kwargs["delegation_rules"] = self._parse_delegation_rules(data["delegation_rules"])

        if "identity" in data and participant_type == "agent":
            kwargs["identity"] = self._parse_identity(data["identity"], name, namespace)

        return Participant(**kwargs)

    @staticmethod
    def _parse_delegation_rules(rules_data: list[dict]) -> list[DelegationRule]:
        result = []
        for rule_data in rules_data:
            match = rule_data.get("match", {})
            result.append(DelegationRule(
                name=rule_data.get("name", ""),
                from_namespace=match.get("from_namespace"),
                from_name_pattern=match.get("from_name_pattern"),
                response_type=match.get("response_type"),
                priority_max=match.get("priority_max"),
                context_conditions=match.get("context_conditions", {}),
                auto_response=rule_data.get("auto_response", {}),
            ))
        return result

    @staticmethod
    def _parse_states(states_data: dict[str, dict]) -> dict[str, StateRule]:
        result = {}
        for state_name, state_config in states_data.items():
            result[state_name] = StateRule(
                accepts_requests=state_config.get("accepts_requests", True),
                queue=state_config.get("queue", False),
                reroute_to=state_config.get("reroute_to"),
            )
        return result

    @staticmethod
    def _parse_identity(identity_data: dict[str, Any], name: str, namespace: str) -> AgentIdentity:
        return AgentIdentity(
            name=identity_data.get("name", name),
            namespace=identity_data.get("namespace", namespace),
            display_name=identity_data.get("display_name", ""),
            description=identity_data.get("description", ""),
            deployed_by=identity_data.get("deployed_by", ""),
            platform_name=identity_data.get("platform_name", ""),
            platform_url=identity_data.get("platform_url", ""),
            verified=identity_data.get("verified", False),
        )
