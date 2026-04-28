import { Interaction, Response, Status } from "./models.js";

export interface Store {
  save(interaction: Interaction): void;
  get(interactionId: string): Interaction | null;
  listPending(toPid?: string): Interaction[];
  respond(interactionId: string, response: Response): boolean;
  cancel(interactionId: string, reason?: string): boolean;
  wait?(interactionId: string, timeout?: number): Promise<Interaction | null>;
}

interface WaitHandle {
  resolve: (interaction: Interaction | null) => void;
  promise: Promise<Interaction | null>;
}

export class InMemoryStore implements Store {
  private _data = new Map<string, Interaction>();
  private _waiters = new Map<string, WaitHandle>();

  save(interaction: Interaction): void {
    this._data.set(interaction.id, interaction);
    if (!this._waiters.has(interaction.id)) {
      let resolve!: (v: Interaction | null) => void;
      const promise = new Promise<Interaction | null>((r) => { resolve = r; });
      this._waiters.set(interaction.id, { resolve, promise });
    }
  }

  get(interactionId: string): Interaction | null {
    const ix = this._data.get(interactionId) ?? null;
    if (ix && ix.status === Status.PENDING && ix.is_expired) {
      ix.status = Status.EXPIRED;
      ix.updated_at = new Date().toISOString();
    }
    return ix;
  }

  listPending(toPid?: string): Interaction[] {
    const result: Interaction[] = [];
    for (const ix of this._data.values()) {
      if (ix.status === Status.PENDING && ix.is_expired) {
        ix.status = Status.EXPIRED;
        ix.updated_at = new Date().toISOString();
        continue;
      }
      if (ix.status !== Status.PENDING) continue;
      if (toPid) {
        const ixPid = `${ix.to_namespace}/${ix.to_name}`;
        if (ixPid !== toPid) continue;
      }
      result.push(ix);
    }
    return result;
  }

  respond(interactionId: string, response: Response): boolean {
    const ix = this._data.get(interactionId);
    if (!ix || ix.status !== Status.PENDING) return false;
    if (ix.is_expired) {
      ix.status = Status.EXPIRED;
      ix.updated_at = new Date().toISOString();
      return false;
    }
    ix.response = response;
    ix.status = Status.ANSWERED;
    ix.updated_at = new Date().toISOString();
    const waiter = this._waiters.get(interactionId);
    if (waiter) {
      waiter.resolve(ix);
      this._waiters.delete(interactionId);
    }
    return true;
  }

  cancel(interactionId: string, reason = ""): boolean {
    const ix = this._data.get(interactionId);
    if (!ix || ix.status !== Status.PENDING) return false;
    ix.status = Status.CANCELLED;
    ix.context["cancel_reason"] = reason;
    ix.updated_at = new Date().toISOString();
    const waiter = this._waiters.get(interactionId);
    if (waiter) {
      waiter.resolve(ix);
      this._waiters.delete(interactionId);
    }
    return true;
  }

  async wait(interactionId: string, timeout = 300): Promise<Interaction | null> {
    const ix = this._data.get(interactionId);
    if (!ix) return null;
    if (ix.status === Status.ANSWERED || ix.status === Status.CANCELLED) return ix;

    let effectiveTimeout = timeout * 1000;
    if (ix.deadline) {
      const deadlineMs = new Date(ix.deadline).getTime() - Date.now();
      if (deadlineMs > 0) effectiveTimeout = Math.min(effectiveTimeout, deadlineMs);
    }

    const waiter = this._waiters.get(interactionId);
    if (!waiter) return null;

    const timeoutPromise = new Promise<Interaction | null>((resolve) => {
      setTimeout(() => resolve(null), effectiveTimeout);
    });

    return Promise.race([waiter.promise, timeoutPromise]);
  }
}
