import { AuditEvent, Interaction } from "./models.js";

export interface AuditLog {
  record(event: AuditEvent): void;
  getHistory(interactionId: string): AuditEvent[];
  query(opts?: {
    participant?: string;
    eventType?: string;
    since?: string;
    until?: string;
    limit?: number;
  }): AuditEvent[];
}

export class InMemoryAuditLog implements AuditLog {
  private _events: AuditEvent[] = [];

  record(event: AuditEvent): void {
    this._events.push(event);
  }

  getHistory(interactionId: string): AuditEvent[] {
    return this._events.filter((e) => e.interaction_id === interactionId);
  }

  query(opts?: {
    participant?: string;
    eventType?: string;
    since?: string;
    until?: string;
    limit?: number;
  }): AuditEvent[] {
    let results = this._events;

    if (opts?.eventType) {
      results = results.filter((e) => e.event_type === opts.eventType);
    }

    if (opts?.participant) {
      const p = opts.participant;
      results = results.filter(
        (e) =>
          e.actor === p ||
          (e.details as Record<string, unknown>).to === p ||
          (e.details as Record<string, unknown>).from_target === p ||
          (e.details as Record<string, unknown>).to_target === p
      );
    }

    if (opts?.since) {
      results = results.filter((e) => e.timestamp >= opts.since!);
    }

    if (opts?.until) {
      results = results.filter((e) => e.timestamp <= opts.until!);
    }

    const limit = opts?.limit ?? 100;
    if (results.length > limit) {
      results = results.slice(-limit);
    }

    return results;
  }

  get length(): number {
    return this._events.length;
  }
}

export function computeResponseTime(interaction: Interaction): number | null {
  if (!interaction.response?.responded_at) return null;
  const created = new Date(interaction.created_at).getTime();
  const responded = new Date(interaction.response.responded_at).getTime();
  return (responded - created) / 1000;
}
