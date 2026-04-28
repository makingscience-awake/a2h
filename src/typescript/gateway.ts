import { randomUUID } from "node:crypto";
import {
  Interaction,
  Notification,
  Response,
  Participant,
  Option,
  AuditEvent,
  Status,
  Priority,
  type ResponseType,
  type EscalationChain,
} from "./models.js";
import { Store, InMemoryStore } from "./store.js";
import type { Channel } from "./channels.js";
import type { AuditLog } from "./audit.js";
import { ParticipantRegistry } from "./registry.js";
import {
  ParticipantNotFound,
  ParticipantUnavailable,
  DuplicateParticipant,
  SenderNotRegistered,
  RequestNotFound,
  RequestNotPending,
} from "./errors.js";

function randomHex(prefix: string): string {
  return prefix + randomUUID().replace(/-/g, "").slice(0, 10);
}

export class Gateway {
  private _store: Store;
  private _channels: Channel[];
  private _registry: ParticipantRegistry;
  private _auditLog: AuditLog | null;

  constructor(opts?: {
    store?: Store;
    channels?: Channel[];
    registry?: ParticipantRegistry;
    auditLog?: AuditLog;
  }) {
    this._store = opts?.store ?? new InMemoryStore();
    this._channels = opts?.channels ?? [];
    this._registry = opts?.registry ?? new ParticipantRegistry();
    this._auditLog = opts?.auditLog ?? null;
  }

  get registry(): ParticipantRegistry {
    return this._registry;
  }

  // --- Participant Management ---

  register(participant: Participant, opts?: { allowReplace?: boolean }): string {
    return this._registry.register(participant, opts);
  }

  unregister(pid: string, opts?: { cascade?: boolean }): boolean {
    if (opts?.cascade) {
      const pending = this._store.listPending(pid);
      for (const ix of pending) {
        this._store.cancel(ix.id, "participant_unregistered");
      }
    }
    return this._registry.unregister(pid);
  }

  getParticipant(pid: string): Participant | null {
    return this._registry.get(pid);
  }

  resolve(namespace: string, name: string): Participant | null {
    return this._registry.resolve(namespace, name);
  }

  listParticipants(opts?: { participantType?: string; namespace?: string }): Participant[] {
    return this._registry.list(opts);
  }

  discover(): Record<string, unknown>[] {
    return this._registry.list().map((p) => p.toCard());
  }

  // --- A2H: Ask ---

  async ask(
    to: string,
    opts: {
      question: string;
      responseType?: ResponseType;
      options?: Array<{ label: string; value: string; description?: string }>;
      context?: Record<string, unknown>;
      priority?: Priority;
      deadline?: string;
      slaHours?: number;
      escalation?: EscalationChain;
      fromParticipant?: string;
      strict?: boolean;
    }
  ): Promise<Interaction> {
    const { namespace: toNs, name: toName } = Gateway.parsePid(to);
    const sender = this._resolveSender(opts.fromParticipant);
    const strict = opts.strict ?? true;

    const options = (opts.options ?? []).map(
      (o) => new Option({ label: o.label, value: o.value, description: o.description })
    );

    const interaction = new Interaction({
      from_name: sender.name,
      from_namespace: sender.namespace,
      to_name: toName,
      to_namespace: toNs,
      question: opts.question,
      response_type: opts.responseType,
      options,
      context: opts.context ?? {},
      priority: opts.priority,
      deadline: opts.deadline,
      sla_hours: opts.slaHours,
      escalation: opts.escalation,
    });

    const target = this._registry.resolve(toNs, toName);

    if (!target) {
      if (strict) {
        throw new ParticipantNotFound(`Participant "${to}" not found`);
      }
      interaction.status = Status.CANCELLED;
      interaction.context["cancel_reason"] = "participant_not_found";
      this._store.save(interaction);
      this._emit("request_created", interaction.id, sender.name, {
        to: to,
        question: opts.question,
        status: "cancelled",
      });
      return interaction;
    }

    // State-aware routing
    if (!target.accepts_requests) {
      const reroute = target.reroute_target;
      if (reroute) {
        interaction.rerouted_from = to;
        interaction.to_name = Gateway.parsePid(reroute).name;
        interaction.to_namespace = Gateway.parsePid(reroute).namespace;
        this._emit("request_rerouted", interaction.id, "gateway", {
          from_target: to,
          to_target: reroute,
          reason: `state:${target.current_state}`,
        });
      } else if (target.should_queue) {
        // Leave as pending, will be delivered when available
      } else {
        throw new ParticipantUnavailable(`Participant "${to}" is ${target.current_state}`);
      }
    }

    // Check delegation rules
    for (const rule of target.delegation_rules) {
      if (rule.matches(interaction)) {
        const autoResp = new Response({
          value: rule.auto_response.value,
          text: (rule.auto_response.text as string) ?? "",
          approved: (rule.auto_response.approved as boolean) ?? null,
          confirmed: (rule.auto_response.confirmed as boolean) ?? null,
        });
        interaction.response = autoResp;
        interaction.status = Status.AUTO_DELEGATED;
        interaction.matched_rule = rule.name;
        interaction.updated_at = new Date().toISOString();
        this._store.save(interaction);
        this._emit("delegation_matched", interaction.id, "gateway", {
          rule_name: rule.name,
          auto_response: rule.auto_response,
        });
        this._emit("request_created", interaction.id, sender.name, {
          to,
          question: opts.question,
          response_type: interaction.response_type,
          priority: interaction.priority,
          status: "auto_delegated",
        });
        return interaction;
      }
    }

    // Normal path: set pending, deliver, save
    interaction.status = Status.PENDING;
    interaction.updated_at = new Date().toISOString();
    this._store.save(interaction);

    this._emit("request_created", interaction.id, sender.name, {
      to,
      question: opts.question,
      response_type: interaction.response_type,
      priority: interaction.priority,
    });

    await this._deliver(interaction);

    return interaction;
  }

  // --- Notify ---

  async notify(
    to: string,
    opts: {
      message: string;
      severity?: string;
      priority?: Priority;
      context?: Record<string, unknown>;
      fromParticipant?: string;
    }
  ): Promise<Notification> {
    const { namespace: toNs, name: toName } = Gateway.parsePid(to);
    const sender = this._resolveSender(opts.fromParticipant);

    const notification = new Notification({
      from_name: sender.name,
      from_namespace: sender.namespace,
      to_name: toName,
      to_namespace: toNs,
      message: opts.message,
      severity: opts.severity,
      priority: opts.priority,
      context: opts.context,
    });

    for (const ch of this._channels) {
      try {
        await ch.deliverNotification(notification);
      } catch {
        // best-effort delivery
      }
    }

    this._emit("notification_sent", notification.id, sender.name, {
      to,
      message: opts.message.slice(0, 200),
      severity: opts.severity ?? "info",
    });

    return notification;
  }

  // --- Respond ---

  respond(
    interactionId: string,
    responseData: Record<string, unknown>,
    channel = "dashboard"
  ): { success: boolean; status: string; error?: string } {
    const ix = this._store.get(interactionId);
    if (!ix) {
      return { success: false, status: "not_found", error: `Request ${interactionId} not found` };
    }
    if (ix.status !== Status.PENDING) {
      return { success: false, status: ix.status, error: `Request is ${ix.status}, not pending` };
    }

    const response = Response.fromDict({ ...responseData, channel, responded_at: new Date().toISOString() });
    const ok = this._store.respond(interactionId, response);

    if (ok) {
      this._emit("response_recorded", interactionId, channel, {
        channel,
        response_type: ix.response_type,
        response_data: responseData,
      });
    }

    return { success: ok, status: ok ? "answered" : ix.status };
  }

  // --- Cancel ---

  cancel(
    interactionId: string,
    reason = ""
  ): { success: boolean; status: string; error?: string } {
    const ix = this._store.get(interactionId);
    if (!ix) {
      return { success: false, status: "not_found", error: `Request ${interactionId} not found` };
    }

    const ok = this._store.cancel(interactionId, reason);
    if (ok) {
      this._emit("request_cancelled", interactionId, "gateway", { reason });
    }

    return { success: ok, status: ok ? "cancelled" : ix.status };
  }

  // --- Query ---

  get(interactionId: string): Interaction | null {
    return this._store.get(interactionId);
  }

  listPending(to?: string): Interaction[] {
    return this._store.listPending(to);
  }

  async wait(interactionId: string, timeout?: number): Promise<Interaction | null> {
    if (this._store.wait) {
      return this._store.wait(interactionId, timeout);
    }
    return null;
  }

  // --- Private Helpers ---

  private _resolveSender(fromParticipant?: string): { name: string; namespace: string } {
    if (!fromParticipant) return { name: "agent", namespace: "default" };
    const { namespace, name } = Gateway.parsePid(fromParticipant);
    return { name, namespace };
  }

  private _emit(
    eventType: string,
    interactionId: string,
    actor: string,
    details: Record<string, unknown>
  ): void {
    if (!this._auditLog) return;
    const event = new AuditEvent({
      event_type: eventType,
      interaction_id: interactionId,
      actor,
      details,
    });
    this._auditLog.record(event);
  }

  private async _deliver(interaction: Interaction): Promise<void> {
    for (const ch of this._channels) {
      try {
        const ok = await ch.deliverRequest(interaction);
        this._emit("request_delivered", interaction.id, "gateway", {
          channel: ch.name,
          success: ok,
        });
      } catch (err) {
        this._emit("request_delivered", interaction.id, "gateway", {
          channel: ch.name,
          success: false,
          error: String(err),
        });
      }
    }
  }

  static parsePid(pid: string): { namespace: string; name: string } {
    const slash = pid.indexOf("/");
    if (slash === -1) return { namespace: "default", name: pid };
    return { namespace: pid.slice(0, slash), name: pid.slice(slash + 1) };
  }
}
