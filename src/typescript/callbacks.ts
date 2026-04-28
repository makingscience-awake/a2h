import type { Interaction } from "./models.js";
import type { Gateway } from "./gateway.js";

type Callback = (interaction: Interaction) => Promise<void>;

export class CallbackRegistry {
  private _gateway: Gateway;
  private _originalRespond: Gateway["respond"];
  private _perRequest = new Map<string, Callback>();
  private _perParticipant = new Map<string, Callback>();
  private _global: Callback[] = [];

  constructor(gateway: Gateway) {
    this._gateway = gateway;
    this._originalRespond = gateway.respond.bind(gateway);
    gateway.respond = this._interceptedRespond.bind(this);
  }

  onResponse(requestId: string, callback: Callback): void {
    this._perRequest.set(requestId, callback);
  }

  onAnyResponse(participantPid: string, callback: Callback): void {
    this._perParticipant.set(participantPid, callback);
  }

  onAllResponses(callback: Callback): void {
    this._global.push(callback);
  }

  remove(participantPid?: string): void {
    if (participantPid) {
      this._perParticipant.delete(participantPid);
    } else {
      this._perRequest.clear();
      this._perParticipant.clear();
      this._global = [];
    }
  }

  reset(): void {
    this._gateway.respond = this._originalRespond;
    this.remove();
  }

  private _interceptedRespond(
    interactionId: string,
    responseData: Record<string, unknown>,
    channel = "dashboard"
  ): { success: boolean; status: string; error?: string } {
    const result = this._originalRespond(interactionId, responseData, channel);

    if (result.success) {
      const ix = this._gateway.get(interactionId);
      if (ix) {
        void this._fire(ix);
      }
    }

    return result;
  }

  private async _fire(interaction: Interaction): Promise<void> {
    // One-shot per request
    const reqCb = this._perRequest.get(interaction.id);
    if (reqCb) {
      this._perRequest.delete(interaction.id);
      try { await reqCb(interaction); } catch { /* ignore */ }
    }

    // Persistent per participant
    const pid = `${interaction.to_namespace}/${interaction.to_name}`;
    const partCb = this._perParticipant.get(pid);
    if (partCb) {
      try { await partCb(interaction); } catch { /* ignore */ }
    }

    // Global
    for (const cb of this._global) {
      try { await cb(interaction); } catch { /* ignore */ }
    }
  }
}

export class WebhookTarget {
  private _url: string;
  private _events: string[] | null;
  private _secret: string;

  constructor(url: string, opts?: { events?: string[]; secret?: string }) {
    this._url = url;
    this._events = opts?.events ?? null;
    this._secret = opts?.secret ?? "";
  }

  async fire(interaction: Interaction): Promise<void> {
    const eventType = interaction.response ? "response" : "expired";
    if (this._events && !this._events.includes(eventType)) return;

    const payload = JSON.stringify({
      event: eventType,
      interaction: interaction.toDict(),
    });

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (this._secret) {
      const encoder = new TextEncoder();
      const key = await crypto.subtle.importKey(
        "raw",
        encoder.encode(this._secret),
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["sign"]
      );
      const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(payload));
      const hex = Array.from(new Uint8Array(sig))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
      headers["X-A2H-Signature"] = `sha256=${hex}`;
    }

    await fetch(this._url, { method: "POST", headers, body: payload });
  }
}
