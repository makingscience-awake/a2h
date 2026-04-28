import type { Interaction, Notification } from "./models.js";
import type { Channel, ChannelCapability } from "./channels.js";
import { DASHBOARD_CAPABILITY } from "./channels.js";
import type { Gateway } from "./gateway.js";

export class MockChannel implements Channel {
  readonly name = "mock";
  readonly capability: ChannelCapability = DASHBOARD_CAPABILITY;
  requests: Interaction[] = [];
  notifications: Notification[] = [];

  async deliverRequest(interaction: Interaction): Promise<boolean> {
    this.requests.push(interaction);
    return true;
  }

  async deliverNotification(notification: Notification): Promise<boolean> {
    this.notifications.push(notification);
    return true;
  }

  reset(): void {
    this.requests = [];
    this.notifications = [];
  }
}

export class AutoResponder {
  private _gateway: Gateway;
  private _originalAsk: Gateway["ask"];
  private _autoResponse: Record<string, unknown> | null = null;

  constructor(gateway: Gateway) {
    this._gateway = gateway;
    this._originalAsk = gateway.ask.bind(gateway);
  }

  approveAll(reason = "Auto-approved in test"): void {
    this._respondAll({ approved: true, text: reason });
  }

  rejectAll(reason = "Auto-rejected in test"): void {
    this._respondAll({ approved: false, text: reason });
  }

  respondChoice(value: string): void {
    this._respondAll({ value });
  }

  respondText(text: string): void {
    this._respondAll({ text });
  }

  respondConfirm(confirmed = true): void {
    this._respondAll({ confirmed });
  }

  respondAll(response: Record<string, unknown>): void {
    this._respondAll(response);
  }

  reset(): void {
    this._autoResponse = null;
    this._gateway.ask = this._originalAsk;
  }

  private _respondAll(response: Record<string, unknown>): void {
    this._autoResponse = response;
    this._gateway.ask = async (to, opts) => {
      const ix = await this._originalAsk(to, opts);
      if (this._autoResponse && ix.status === "pending") {
        this._gateway.respond(ix.id, this._autoResponse);
      }
      return ix;
    };
  }
}

export class FailingChannel implements Channel {
  readonly name = "failing";
  readonly capability: ChannelCapability = DASHBOARD_CAPABILITY;

  async deliverRequest(_interaction: Interaction): Promise<boolean> {
    throw new Error("Channel failure: simulated delivery error");
  }

  async deliverNotification(_notification: Notification): Promise<boolean> {
    throw new Error("Channel failure: simulated delivery error");
  }
}
