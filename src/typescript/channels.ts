import type { Interaction, Notification } from "./models.js";

export interface ChannelCapability {
  readonly channelId: string;
  readonly displayName: string;
  readonly responseTypes: string[];
  readonly maxOptions: number;
  readonly supportsContextCard: boolean;
  readonly supportsDeadlineDisplay: boolean;
  readonly supportsAgentIdentityBadge: boolean;
  readonly responseLatency: "seconds" | "minutes";
  readonly verificationMethod: string;
  readonly trustLevel: "high" | "medium" | "low";
  supports(responseType: string): boolean;
  toDict(): Record<string, unknown>;
}

export class ChannelCapabilityImpl implements ChannelCapability {
  readonly channelId: string;
  readonly displayName: string;
  readonly responseTypes: string[];
  readonly maxOptions: number;
  readonly supportsContextCard: boolean;
  readonly supportsDeadlineDisplay: boolean;
  readonly supportsAgentIdentityBadge: boolean;
  readonly responseLatency: "seconds" | "minutes";
  readonly verificationMethod: string;
  readonly trustLevel: "high" | "medium" | "low";

  constructor(opts: {
    channelId: string;
    displayName?: string;
    responseTypes?: string[];
    maxOptions?: number;
    supportsContextCard?: boolean;
    supportsDeadlineDisplay?: boolean;
    supportsAgentIdentityBadge?: boolean;
    responseLatency?: "seconds" | "minutes";
    verificationMethod?: string;
    trustLevel?: "high" | "medium" | "low";
  }) {
    this.channelId = opts.channelId;
    this.displayName = opts.displayName ?? "";
    this.responseTypes = opts.responseTypes ?? ["choice", "approval", "text", "number", "confirm"];
    this.maxOptions = opts.maxOptions ?? 10;
    this.supportsContextCard = opts.supportsContextCard ?? true;
    this.supportsDeadlineDisplay = opts.supportsDeadlineDisplay ?? true;
    this.supportsAgentIdentityBadge = opts.supportsAgentIdentityBadge ?? true;
    this.responseLatency = opts.responseLatency ?? "seconds";
    this.verificationMethod = opts.verificationMethod ?? "authenticated_session";
    this.trustLevel = opts.trustLevel ?? "high";
  }

  supports(responseType: string): boolean {
    return this.responseTypes.includes(responseType);
  }

  toDict(): Record<string, unknown> {
    return {
      channel_id: this.channelId,
      display_name: this.displayName,
      response_types: this.responseTypes,
      max_options: this.maxOptions,
      supports_context_card: this.supportsContextCard,
      supports_deadline_display: this.supportsDeadlineDisplay,
      supports_agent_identity_badge: this.supportsAgentIdentityBadge,
      response_latency: this.responseLatency,
      verification_method: this.verificationMethod,
      trust_level: this.trustLevel,
    };
  }
}

// --- Pre-defined capabilities ---

export const DASHBOARD_CAPABILITY = new ChannelCapabilityImpl({
  channelId: "dashboard",
  displayName: "Dashboard",
  responseTypes: ["choice", "approval", "text", "number", "confirm", "form"],
  trustLevel: "high",
  verificationMethod: "authenticated_session",
});

export const SLACK_CAPABILITY = new ChannelCapabilityImpl({
  channelId: "slack",
  displayName: "Slack",
  responseTypes: ["choice", "approval", "text", "confirm"],
  maxOptions: 5,
  trustLevel: "medium",
  verificationMethod: "slack_user_id",
});

export const EMAIL_CAPABILITY = new ChannelCapabilityImpl({
  channelId: "email",
  displayName: "Email",
  responseTypes: ["choice", "approval", "text", "number", "confirm"],
  supportsContextCard: false,
  supportsAgentIdentityBadge: false,
  responseLatency: "minutes",
  trustLevel: "low",
  verificationMethod: "email_address",
});

export const SMS_CAPABILITY = new ChannelCapabilityImpl({
  channelId: "sms",
  displayName: "SMS",
  responseTypes: ["approval", "confirm", "text"],
  maxOptions: 3,
  supportsContextCard: false,
  responseLatency: "minutes",
  trustLevel: "medium",
  verificationMethod: "phone_number",
});

// --- ResponseVerification ---

export interface ResponseVerification {
  method: string;
  externalId: string;
  mappedTo: string;
  trustLevel: string;
  toDict(): Record<string, unknown>;
}

export class ResponseVerificationImpl implements ResponseVerification {
  readonly method: string;
  readonly externalId: string;
  readonly mappedTo: string;
  readonly trustLevel: string;

  constructor(opts?: { method?: string; externalId?: string; mappedTo?: string; trustLevel?: string }) {
    this.method = opts?.method ?? "authenticated_session";
    this.externalId = opts?.externalId ?? "";
    this.mappedTo = opts?.mappedTo ?? "";
    this.trustLevel = opts?.trustLevel ?? "high";
  }

  toDict(): Record<string, unknown> {
    return { method: this.method, external_id: this.externalId, mapped_to: this.mappedTo, trust_level: this.trustLevel };
  }
}

// --- Channel interface ---

export interface Channel {
  readonly name: string;
  readonly capability: ChannelCapability;
  deliverRequest(interaction: Interaction): Promise<boolean>;
  deliverNotification(notification: Notification): Promise<boolean>;
}

// --- LogChannel ---

export class LogChannel implements Channel {
  readonly name = "log";
  readonly capability: ChannelCapability = DASHBOARD_CAPABILITY;

  async deliverRequest(interaction: Interaction): Promise<boolean> {
    console.log(`[a2h] Request ${interaction.id} -> ${interaction.to_namespace}/${interaction.to_name}: ${interaction.question}`);
    return true;
  }

  async deliverNotification(notification: Notification): Promise<boolean> {
    console.log(`[a2h] Notification ${notification.id} -> ${notification.to_namespace}/${notification.to_name}: ${notification.message}`);
    return true;
  }
}

// --- DashboardChannel ---

export class DashboardChannel implements Channel {
  readonly name = "dashboard";
  readonly capability: ChannelCapability = DASHBOARD_CAPABILITY;

  async deliverRequest(interaction: Interaction): Promise<boolean> {
    console.log(`[dashboard] Request ${interaction.id}: "${interaction.question}" -> ${interaction.to_namespace}/${interaction.to_name}`);
    return true;
  }

  async deliverNotification(notification: Notification): Promise<boolean> {
    console.log(`[dashboard] Notification ${notification.id}: "${notification.message}" -> ${notification.to_namespace}/${notification.to_name}`);
    return true;
  }
}
