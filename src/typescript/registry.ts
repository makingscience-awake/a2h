import {
  Participant,
  DelegationRule,
  StateRule,
  AgentIdentity,
} from "./models.js";
import {
  DuplicateParticipant,
  UnauthorizedParticipant,
  RegistryError,
} from "./errors.js";

export class ParticipantRegistry {
  private _participants = new Map<string, Participant>();
  private _fileLoaded = new Set<string>();
  private _mode: "permissive" | "strict";

  constructor(opts?: { mode?: "permissive" | "strict" }) {
    this._mode = opts?.mode ?? "permissive";
  }

  get mode(): string {
    return this._mode;
  }

  register(participant: Participant, opts?: { allowReplace?: boolean }): string {
    const pid = participant.pid;

    if (this._mode === "strict" && !this._fileLoaded.has(pid)) {
      participant.trust_level = "runtime";
    }

    if (this._participants.has(pid) && !opts?.allowReplace) {
      throw new DuplicateParticipant(`Participant "${pid}" already exists`);
    }

    this._participants.set(pid, participant);
    return pid;
  }

  unregister(pid: string): boolean {
    if (this._mode === "strict" && this._fileLoaded.has(pid)) {
      throw new RegistryError(`Cannot unregister file-loaded participant "${pid}" in strict mode`);
    }
    this._fileLoaded.delete(pid);
    return this._participants.delete(pid);
  }

  get(pid: string): Participant | null {
    return this._participants.get(pid) ?? null;
  }

  resolve(namespace: string, name: string): Participant | null {
    return this._participants.get(`${namespace}/${name}`) ?? null;
  }

  list(opts?: {
    participantType?: string;
    namespace?: string;
    trustLevel?: string;
  }): Participant[] {
    let results = Array.from(this._participants.values());
    if (opts?.participantType) {
      results = results.filter((p) => p.participant_type === opts.participantType);
    }
    if (opts?.namespace) {
      results = results.filter((p) => p.namespace === opts.namespace);
    }
    if (opts?.trustLevel) {
      results = results.filter((p) => p.trust_level === opts.trustLevel);
    }
    return results;
  }

  isFileLoaded(pid: string): boolean {
    return this._fileLoaded.has(pid);
  }

  loadFromData(data: {
    defaults?: Record<string, unknown>;
    participants: Array<Record<string, unknown>>;
  }): string[] {
    const defaults = data.defaults ?? {};
    const loaded: string[] = [];

    for (const entry of data.participants) {
      const p = this._parseParticipant(entry, defaults);
      const pid = p.pid;
      this._participants.set(pid, p);
      this._fileLoaded.add(pid);
      p.trust_level = "verified";
      loaded.push(pid);
    }

    return loaded;
  }

  private _parseParticipant(
    data: Record<string, unknown>,
    defaults: Record<string, unknown>
  ): Participant {
    const namespace = (data.namespace as string) ?? (defaults.namespace as string) ?? "default";
    const channels = (data.channels as string[]) ?? (defaults.channels as string[]) ?? ["dashboard"];
    const availability = (data.availability as string) ?? (defaults.availability as string) ?? "business_hours";

    let states: Map<string, StateRule> | undefined;
    if (data.states) {
      states = ParticipantRegistry._parseStates(data.states as Record<string, Record<string, unknown>>);
    }

    let delegationRules: DelegationRule[] = [];
    if (data.delegation_rules) {
      delegationRules = ParticipantRegistry._parseDelegationRules(
        data.delegation_rules as Array<Record<string, unknown>>
      );
    }

    let identity: AgentIdentity | null = null;
    if (data.identity) {
      identity = ParticipantRegistry._parseIdentity(
        data.identity as Record<string, unknown>,
        data.name as string,
        namespace
      );
    }

    return new Participant({
      name: data.name as string,
      namespace,
      participant_type: (data.type as string) ?? (data.participant_type as string) ?? "human",
      description: (data.description as string) ?? "",
      role: (data.role as string) ?? "",
      channels,
      availability,
      states,
      current_state: (data.current_state as string) ?? "available",
      delegate: (data.delegate as string) ?? null,
      delegation_rules: delegationRules,
      identity,
      metadata: (data.metadata as Record<string, unknown>) ?? {},
    });
  }

  private static _parseDelegationRules(
    rulesData: Array<Record<string, unknown>>
  ): DelegationRule[] {
    return rulesData.map((r) => {
      const match = (r.match as Record<string, unknown>) ?? r;
      return new DelegationRule({
        name: (r.name as string) ?? "",
        from_namespace: (match.from_namespace as string) ?? null,
        from_name_pattern: (match.from_name_pattern as string) ?? null,
        response_type: (match.response_type as string) ?? null,
        priority_max: (match.priority_max as string) ?? null,
        context_conditions: (match.context_conditions as Record<string, Record<string, unknown>>) ?? {},
        auto_response: (r.auto_response as Record<string, unknown>) ?? {},
      });
    });
  }

  private static _parseStates(
    statesData: Record<string, Record<string, unknown>>
  ): Map<string, StateRule> {
    const states = new Map<string, StateRule>();
    for (const [name, cfg] of Object.entries(statesData)) {
      states.set(
        name,
        new StateRule({
          accepts_requests: (cfg.accepts_requests as boolean) ?? true,
          queue: (cfg.queue as boolean) ?? false,
          reroute_to: (cfg.reroute_to as string) ?? null,
        })
      );
    }
    return states;
  }

  private static _parseIdentity(
    data: Record<string, unknown>,
    name: string,
    namespace: string
  ): AgentIdentity {
    return new AgentIdentity({
      name: (data.name as string) ?? name,
      namespace: (data.namespace as string) ?? namespace,
      display_name: (data.display_name as string) ?? "",
      description: (data.description as string) ?? "",
      deployed_by: (data.deployed_by as string) ?? "",
      platform_name: (data.platform_name as string) ?? "",
      platform_url: (data.platform_url as string) ?? "",
      verified: (data.verified as boolean) ?? false,
    });
  }
}
