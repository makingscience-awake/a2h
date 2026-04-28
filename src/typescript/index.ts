// Models
export {
  Status,
  ResponseType,
  Priority,
  Option,
  AgentIdentity,
  StateRule,
  Participant,
  Interaction,
  Response,
  Notification,
  EscalationLevel,
  EscalationChain,
  DelegationRule,
  AuditEvent,
} from "./models.js";

// Gateway
export { Gateway } from "./gateway.js";

// Store
export type { Store } from "./store.js";
export { InMemoryStore } from "./store.js";

// Channels
export type { Channel, ChannelCapability, ResponseVerification } from "./channels.js";
export {
  ChannelCapabilityImpl,
  ResponseVerificationImpl,
  LogChannel,
  DashboardChannel,
  DASHBOARD_CAPABILITY,
  SLACK_CAPABILITY,
  EMAIL_CAPABILITY,
  SMS_CAPABILITY,
} from "./channels.js";

// Registry
export { ParticipantRegistry } from "./registry.js";

// Audit
export type { AuditLog } from "./audit.js";
export { InMemoryAuditLog, computeResponseTime } from "./audit.js";

// Callbacks
export { CallbackRegistry, WebhookTarget } from "./callbacks.js";

// Errors
export {
  A2HError,
  ParticipantNotFound,
  ParticipantUnavailable,
  DuplicateParticipant,
  InvalidParticipantID,
  SenderNotRegistered,
  RequestNotFound,
  RequestNotPending,
  RequestExpired,
  InvalidResponseType,
  ChannelDeliveryFailed,
  NoSupportedChannel,
  ChannelVerificationFailed,
  SignatureInvalid,
  TrustLevelInsufficient,
  RateLimitExceeded,
  ExecutionMismatch,
  RegistryError,
  RegistryLoadError,
  UnauthorizedParticipant,
  StoreSaveFailed,
  StoreReadFailed,
} from "./errors.js";

// Testing
export { MockChannel, AutoResponder, FailingChannel } from "./testing.js";

// Server
export { createA2HServer } from "./server.js";
