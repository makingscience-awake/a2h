import { randomUUID } from "node:crypto";

function randomHex(prefix: string): string {
  return prefix + randomUUID().replace(/-/g, "").slice(0, 10);
}

function nowISO(): string {
  return new Date().toISOString();
}

// --- Enums ---

export const Status = {
  CREATED: "created",
  PENDING: "pending",
  ANSWERED: "answered",
  EXPIRED: "expired",
  CANCELLED: "cancelled",
  ESCALATED: "escalated",
  AUTO_DELEGATED: "auto_delegated",
} as const;
export type Status = (typeof Status)[keyof typeof Status];

export const ResponseType = {
  CHOICE: "choice",
  APPROVAL: "approval",
  TEXT: "text",
  NUMBER: "number",
  CONFIRM: "confirm",
  FORM: "form",
} as const;
export type ResponseType = (typeof ResponseType)[keyof typeof ResponseType];

export const Priority = {
  CRITICAL: "critical",
  HIGH: "high",
  MEDIUM: "medium",
  LOW: "low",
} as const;
export type Priority = (typeof Priority)[keyof typeof Priority];

// --- Option ---

export class Option {
  readonly label: string;
  readonly value: string;
  readonly description: string;

  constructor(opts: { label: string; value: string; description?: string }) {
    this.label = opts.label;
    this.value = opts.value;
    this.description = opts.description ?? "";
  }

  toDict(): Record<string, unknown> {
    return { label: this.label, value: this.value, description: this.description };
  }
}

// --- AgentIdentity ---

export class AgentIdentity {
  readonly name: string;
  readonly namespace: string;
  readonly display_name: string;
  readonly description: string;
  readonly deployed_by: string;
  readonly platform_name: string;
  readonly platform_url: string;
  readonly verified: boolean;

  constructor(opts: {
    name: string;
    namespace?: string;
    display_name?: string;
    description?: string;
    deployed_by?: string;
    platform_name?: string;
    platform_url?: string;
    verified?: boolean;
  }) {
    this.name = opts.name;
    this.namespace = opts.namespace ?? "default";
    this.display_name = opts.display_name ?? "";
    this.description = opts.description ?? "";
    this.deployed_by = opts.deployed_by ?? "";
    this.platform_name = opts.platform_name ?? "";
    this.platform_url = opts.platform_url ?? "";
    this.verified = opts.verified ?? false;
  }

  toDict(): Record<string, unknown> {
    return {
      participant_type: "agent",
      name: this.name,
      namespace: this.namespace,
      display_name: this.display_name,
      description: this.description,
      deployed_by: this.deployed_by,
      platform_name: this.platform_name,
      platform_url: this.platform_url,
      verified: this.verified,
    };
  }
}

// --- StateRule ---

export class StateRule {
  readonly accepts_requests: boolean;
  readonly queue: boolean;
  readonly reroute_to: string | null;

  constructor(opts?: { accepts_requests?: boolean; queue?: boolean; reroute_to?: string | null }) {
    this.accepts_requests = opts?.accepts_requests ?? true;
    this.queue = opts?.queue ?? false;
    this.reroute_to = opts?.reroute_to ?? null;
  }
}

// --- DelegationRule ---

export class DelegationRule {
  readonly name: string;
  readonly from_namespace: string | null;
  readonly from_name_pattern: string | null;
  readonly response_type: string | null;
  readonly priority_max: string | null;
  readonly context_conditions: Record<string, Record<string, unknown>>;
  readonly auto_response: Record<string, unknown>;

  constructor(opts?: {
    name?: string;
    from_namespace?: string | null;
    from_name_pattern?: string | null;
    response_type?: string | null;
    priority_max?: string | null;
    context_conditions?: Record<string, Record<string, unknown>>;
    auto_response?: Record<string, unknown>;
  }) {
    this.name = opts?.name ?? "";
    this.from_namespace = opts?.from_namespace ?? null;
    this.from_name_pattern = opts?.from_name_pattern ?? null;
    this.response_type = opts?.response_type ?? null;
    this.priority_max = opts?.priority_max ?? null;
    this.context_conditions = opts?.context_conditions ?? {};
    this.auto_response = opts?.auto_response ?? {};
  }

  matches(interaction: Interaction): boolean {
    if (this.from_namespace && interaction.from_namespace !== this.from_namespace) return false;
    if (this.from_name_pattern) {
      const pattern = this.from_name_pattern;
      if (pattern.includes("*")) {
        const regex = new RegExp("^" + pattern.replace(/\*/g, ".*") + "$");
        if (!regex.test(interaction.from_name)) return false;
      } else if (interaction.from_name !== pattern) {
        return false;
      }
    }
    if (this.response_type && interaction.response_type !== this.response_type) return false;
    if (this.priority_max) {
      const levels: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };
      if ((levels[interaction.priority] ?? 0) > (levels[this.priority_max] ?? 0)) return false;
    }
    for (const [key, conds] of Object.entries(this.context_conditions)) {
      const val = interaction.context[key];
      if (val === undefined) return false;
      if ("eq" in conds && val !== conds.eq) return false;
      if ("lt" in conds && typeof val === "number" && typeof conds.lt === "number" && val >= conds.lt) return false;
      if ("gt" in conds && typeof val === "number" && typeof conds.gt === "number" && val <= conds.gt) return false;
    }
    return true;
  }
}

// --- Escalation ---

export class EscalationLevel {
  readonly target: string;
  readonly timeout_minutes: number;
  readonly priority_override: string | null;

  constructor(opts: { target: string; timeout_minutes?: number; priority_override?: string | null }) {
    this.target = opts.target;
    this.timeout_minutes = opts.timeout_minutes ?? 10;
    this.priority_override = opts.priority_override ?? null;
  }
}

export class EscalationChain {
  levels: EscalationLevel[];
  current_level: number;

  constructor(opts?: { levels?: EscalationLevel[]; current_level?: number }) {
    this.levels = opts?.levels ?? [];
    this.current_level = opts?.current_level ?? 0;
  }

  nextTarget(): EscalationLevel | null {
    if (this.current_level < this.levels.length) return this.levels[this.current_level]!;
    return null;
  }

  promote(): EscalationLevel | null {
    this.current_level++;
    return this.nextTarget();
  }

  toDict(): Record<string, unknown> {
    return {
      levels: this.levels.map((l) => ({
        target: l.target,
        timeout_minutes: l.timeout_minutes,
        priority_override: l.priority_override,
      })),
      current_level: this.current_level,
    };
  }
}

// --- Response ---

export class Response {
  value: unknown;
  text: string;
  approved: boolean | null;
  confirmed: boolean | null;
  fields: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  responded_at: string;
  channel: string;

  constructor(opts?: {
    value?: unknown;
    text?: string;
    approved?: boolean | null;
    confirmed?: boolean | null;
    fields?: Record<string, unknown> | null;
    metadata?: Record<string, unknown>;
    responded_at?: string;
    channel?: string;
  }) {
    this.value = opts?.value ?? null;
    this.text = opts?.text ?? "";
    this.approved = opts?.approved ?? null;
    this.confirmed = opts?.confirmed ?? null;
    this.fields = opts?.fields ?? null;
    this.metadata = opts?.metadata ?? {};
    this.responded_at = opts?.responded_at ?? nowISO();
    this.channel = opts?.channel ?? "dashboard";
  }

  toDict(): Record<string, unknown> {
    return {
      value: this.value,
      text: this.text,
      approved: this.approved,
      confirmed: this.confirmed,
      fields: this.fields,
      metadata: this.metadata,
      responded_at: this.responded_at,
      channel: this.channel,
    };
  }

  static fromDict(data: Record<string, unknown>): Response {
    return new Response({
      value: data.value,
      text: (data.text as string) ?? "",
      approved: (data.approved as boolean | null) ?? null,
      confirmed: (data.confirmed as boolean | null) ?? null,
      fields: (data.fields as Record<string, unknown> | null) ?? null,
      metadata: (data.metadata as Record<string, unknown>) ?? {},
      responded_at: (data.responded_at as string) ?? nowISO(),
      channel: (data.channel as string) ?? "dashboard",
    });
  }
}

// --- Participant ---

const NAME_RE = /^[a-zA-Z][a-zA-Z0-9._-]{0,63}$/;

export class Participant {
  readonly name: string;
  readonly namespace: string;
  participant_type: string;
  description: string;
  role: string;
  channels: string[];
  availability: string;
  states: Map<string, StateRule>;
  current_state: string;
  delegate: string | null;
  delegation_rules: DelegationRule[];
  identity: AgentIdentity | null;
  metadata: Record<string, unknown>;
  trust_level: string;

  constructor(opts: {
    name: string;
    namespace?: string;
    participant_type?: string;
    description?: string;
    role?: string;
    channels?: string[];
    availability?: string;
    states?: Map<string, StateRule>;
    current_state?: string;
    delegate?: string | null;
    delegation_rules?: DelegationRule[];
    identity?: AgentIdentity | null;
    metadata?: Record<string, unknown>;
    trust_level?: string;
  }) {
    if (!NAME_RE.test(opts.name)) {
      throw new Error(`Invalid participant name: "${opts.name}". Must match ${NAME_RE}`);
    }
    this.name = opts.name;
    this.namespace = opts.namespace ?? "default";
    this.participant_type = opts.participant_type ?? "human";
    this.description = opts.description ?? "";
    this.role = opts.role ?? "";
    this.channels = opts.channels ?? ["dashboard"];
    this.availability = opts.availability ?? "business_hours";
    this.states = opts.states ?? new Map([
      ["available", new StateRule({ accepts_requests: true })],
      ["busy", new StateRule({ accepts_requests: false, queue: true })],
      ["away", new StateRule({ accepts_requests: false, reroute_to: "delegate" })],
      ["offline", new StateRule({ accepts_requests: false, reroute_to: "on_call" })],
    ]);
    this.current_state = opts.current_state ?? "available";
    this.delegate = opts.delegate ?? null;
    this.delegation_rules = opts.delegation_rules ?? [];
    this.identity = opts.identity ?? null;
    this.metadata = opts.metadata ?? {};
    this.trust_level = opts.trust_level ?? "runtime";
    Object.defineProperty(this, "name", { writable: false });
    Object.defineProperty(this, "namespace", { writable: false });
  }

  get pid(): string {
    return `${this.namespace}/${this.name}`;
  }

  get delegate_pid(): string | null {
    if (!this.delegate) return null;
    if (this.delegate.includes("/")) return this.delegate;
    return `${this.namespace}/${this.delegate}`;
  }

  get accepts_requests(): boolean {
    const rule = this.states.get(this.current_state);
    return rule ? rule.accepts_requests : true;
  }

  get should_queue(): boolean {
    const rule = this.states.get(this.current_state);
    return rule ? rule.queue : false;
  }

  get reroute_target(): string | null {
    const rule = this.states.get(this.current_state);
    if (!rule || !rule.reroute_to) return null;
    if (rule.reroute_to === "delegate") return this.delegate_pid;
    return rule.reroute_to;
  }

  setState(state: string): void {
    if (!this.states.has(state)) throw new Error(`Unknown state: ${state}`);
    (this as { current_state: string }).current_state = state;
  }

  toCard(): Record<string, unknown> {
    return {
      name: this.name,
      namespace: this.namespace,
      pid: this.pid,
      participant_type: this.participant_type,
      description: this.description,
      role: this.role,
      channels: this.channels,
      availability: this.availability,
      current_state: this.current_state,
      accepts_requests: this.accepts_requests,
      identity: this.identity?.toDict() ?? null,
    };
  }
}

// --- Interaction ---

export class Interaction {
  readonly id: string;
  readonly protocol: string;
  from_name: string;
  from_namespace: string;
  from_type: string;
  to_name: string;
  to_namespace: string;
  to_type: string;
  question: string;
  response_type: ResponseType;
  options: Option[];
  context: Record<string, unknown>;
  priority: Priority;
  deadline: string | null;
  sla_hours: number;
  escalation: EscalationChain | null;
  status: Status;
  response: Response | null;
  created_at: string;
  updated_at: string;
  matched_rule: string | null;
  rerouted_from: string | null;

  constructor(opts?: {
    id?: string;
    from_name?: string;
    from_namespace?: string;
    from_type?: string;
    to_name?: string;
    to_namespace?: string;
    to_type?: string;
    question?: string;
    response_type?: ResponseType;
    options?: Option[];
    context?: Record<string, unknown>;
    priority?: Priority;
    deadline?: string | null;
    sla_hours?: number;
    escalation?: EscalationChain | null;
    status?: Status;
    response?: Response | null;
    matched_rule?: string | null;
    rerouted_from?: string | null;
  }) {
    const now = nowISO();
    this.id = opts?.id ?? randomHex("req_");
    this.protocol = "a2h/v1";
    this.from_name = opts?.from_name ?? "";
    this.from_namespace = opts?.from_namespace ?? "default";
    this.from_type = opts?.from_type ?? "agent";
    this.to_name = opts?.to_name ?? "";
    this.to_namespace = opts?.to_namespace ?? "default";
    this.to_type = opts?.to_type ?? "human";
    this.question = opts?.question ?? "";
    this.response_type = opts?.response_type ?? ResponseType.TEXT;
    this.options = opts?.options ?? [];
    this.context = opts?.context ?? {};
    this.priority = opts?.priority ?? Priority.MEDIUM;
    this.sla_hours = opts?.sla_hours ?? 24;
    this.escalation = opts?.escalation ?? null;
    this.status = opts?.status ?? Status.CREATED;
    this.response = opts?.response ?? null;
    this.created_at = now;
    this.updated_at = now;
    this.matched_rule = opts?.matched_rule ?? null;
    this.rerouted_from = opts?.rerouted_from ?? null;
    if (opts?.deadline) {
      this.deadline = opts.deadline;
    } else {
      const d = new Date(Date.now() + this.sla_hours * 3600_000);
      this.deadline = d.toISOString();
    }
  }

  get is_expired(): boolean {
    if (!this.deadline) return false;
    return new Date(this.deadline) < new Date();
  }

  toDict(): Record<string, unknown> {
    return {
      id: this.id,
      protocol: this.protocol,
      from: { name: this.from_name, namespace: this.from_namespace, type: this.from_type },
      to: { name: this.to_name, namespace: this.to_namespace, type: this.to_type },
      content: {
        question: this.question,
        response_type: this.response_type,
        options: this.options.map((o) => o.toDict()),
        context: this.context,
      },
      priority: this.priority,
      deadline: this.deadline,
      sla_hours: this.sla_hours,
      escalation: this.escalation?.toDict() ?? null,
      status: this.status,
      response: this.response?.toDict() ?? null,
      created_at: this.created_at,
      updated_at: this.updated_at,
      matched_rule: this.matched_rule,
      rerouted_from: this.rerouted_from,
    };
  }
}

// --- Notification ---

export class Notification {
  readonly id: string;
  readonly protocol: string;
  from_name: string;
  from_namespace: string;
  to_name: string;
  to_namespace: string;
  message: string;
  severity: string;
  priority: Priority;
  context: Record<string, unknown>;
  created_at: string;

  constructor(opts?: {
    id?: string;
    from_name?: string;
    from_namespace?: string;
    to_name?: string;
    to_namespace?: string;
    message?: string;
    severity?: string;
    priority?: Priority;
    context?: Record<string, unknown>;
  }) {
    this.id = opts?.id ?? randomHex("notif_");
    this.protocol = "a2h/v1";
    this.from_name = opts?.from_name ?? "";
    this.from_namespace = opts?.from_namespace ?? "default";
    this.to_name = opts?.to_name ?? "";
    this.to_namespace = opts?.to_namespace ?? "default";
    this.message = opts?.message ?? "";
    this.severity = opts?.severity ?? "info";
    this.priority = opts?.priority ?? Priority.LOW;
    this.context = opts?.context ?? {};
    this.created_at = nowISO();
  }

  toDict(): Record<string, unknown> {
    return {
      id: this.id,
      protocol: this.protocol,
      from: { name: this.from_name, namespace: this.from_namespace },
      to: { name: this.to_name, namespace: this.to_namespace },
      message: this.message,
      severity: this.severity,
      priority: this.priority,
      context: this.context,
      created_at: this.created_at,
    };
  }
}

// --- AuditEvent ---

export class AuditEvent {
  readonly id: string;
  readonly timestamp: string;
  event_type: string;
  interaction_id: string;
  actor: string;
  details: Record<string, unknown>;

  constructor(opts?: {
    id?: string;
    timestamp?: string;
    event_type?: string;
    interaction_id?: string;
    actor?: string;
    details?: Record<string, unknown>;
  }) {
    this.id = opts?.id ?? randomHex("evt_");
    this.timestamp = opts?.timestamp ?? nowISO();
    this.event_type = opts?.event_type ?? "";
    this.interaction_id = opts?.interaction_id ?? "";
    this.actor = opts?.actor ?? "";
    this.details = opts?.details ?? {};
  }

  toDict(): Record<string, unknown> {
    return {
      id: this.id,
      timestamp: this.timestamp,
      event_type: this.event_type,
      interaction_id: this.interaction_id,
      actor: this.actor,
      details: this.details,
    };
  }
}
