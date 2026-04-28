export class A2HError extends Error {
  code: string;
  suggestion: string;
  readonly details: Record<string, unknown>;

  constructor(message = "", details: Record<string, unknown> = {}) {
    super(message);
    this.name = this.constructor.name;
    this.code = "A2H_ERROR";
    this.suggestion = "";
    this.details = details;
  }

  toDict(): Record<string, unknown> {
    return { error: this.code, message: this.message, suggestion: this.suggestion, details: this.details };
  }
}

// --- Participant errors ---

export class ParticipantNotFound extends A2HError {
  code = "A2H_PARTICIPANT_NOT_FOUND";
  suggestion = "Check the participant ID or register the participant first.";
}

export class ParticipantUnavailable extends A2HError {
  code = "A2H_PARTICIPANT_UNAVAILABLE";
  suggestion = "Check participant state or try again later.";
}

export class DuplicateParticipant extends A2HError {
  code = "A2H_DUPLICATE_PARTICIPANT";
  suggestion = "Use allowReplace: true to overwrite, or choose a different name.";
}

export class InvalidParticipantID extends A2HError {
  code = "A2H_INVALID_PARTICIPANT_ID";
  suggestion = "Participant names must match /^[a-zA-Z][a-zA-Z0-9._-]{0,63}$/.";
}

export class SenderNotRegistered extends A2HError {
  code = "A2H_SENDER_NOT_REGISTERED";
  suggestion = "Register the sender participant before sending requests.";
}

// --- Request errors ---

export class RequestNotFound extends A2HError {
  code = "A2H_REQUEST_NOT_FOUND";
  suggestion = "Check the interaction ID.";
}

export class RequestNotPending extends A2HError {
  code = "A2H_REQUEST_NOT_PENDING";
  suggestion = "Only pending requests can be responded to or cancelled.";
}

export class RequestExpired extends A2HError {
  code = "A2H_REQUEST_EXPIRED";
  suggestion = "The deadline has passed. Create a new request.";
}

export class InvalidResponseType extends A2HError {
  code = "A2H_INVALID_RESPONSE_TYPE";
  suggestion = "Use one of: choice, approval, text, number, confirm, form.";
}

// --- Channel errors ---

export class ChannelDeliveryFailed extends A2HError {
  code = "A2H_CHANNEL_DELIVERY_FAILED";
  suggestion = "Check channel configuration and connectivity.";
}

export class NoSupportedChannel extends A2HError {
  code = "A2H_NO_SUPPORTED_CHANNEL";
  suggestion = "Ensure at least one channel supports the requested response type.";
}

export class ChannelVerificationFailed extends A2HError {
  code = "A2H_CHANNEL_VERIFICATION_FAILED";
  suggestion = "Verify the response came from an authenticated channel.";
}

// --- Security errors ---

export class SignatureInvalid extends A2HError {
  code = "A2H_SIGNATURE_INVALID";
  suggestion = "Check the webhook secret and signature computation.";
}

export class TrustLevelInsufficient extends A2HError {
  code = "A2H_TRUST_LEVEL_INSUFFICIENT";
  suggestion = "Use a higher-trust channel for this operation.";
}

export class RateLimitExceeded extends A2HError {
  code = "A2H_RATE_LIMIT_EXCEEDED";
  suggestion = "Wait before sending more requests.";
}

export class ExecutionMismatch extends A2HError {
  code = "A2H_EXECUTION_MISMATCH";
  suggestion = "The response does not match the expected format.";
}

// --- Registry errors ---

export class RegistryError extends A2HError {
  override code = "A2H_REGISTRY_ERROR";
  override suggestion = "Check registry configuration.";
}

export class RegistryLoadError extends RegistryError {
  override code = "A2H_REGISTRY_LOAD_ERROR";
  override suggestion = "Check the participants file format and path.";
}

export class UnauthorizedParticipant extends RegistryError {
  override code = "A2H_UNAUTHORIZED_PARTICIPANT";
  override suggestion = "In strict mode, only file-loaded participants are allowed.";
}

// --- Store errors ---

export class StoreSaveFailed extends A2HError {
  code = "A2H_STORE_SAVE_FAILED";
  suggestion = "Check store configuration and available storage.";
}

export class StoreReadFailed extends A2HError {
  code = "A2H_STORE_READ_FAILED";
  suggestion = "Check store connectivity and the interaction ID.";
}
