"""
A2H error taxonomy.

Every error an A2H adopter can encounter, with clear error codes
and guidance on how to handle each one.

    from a2h.errors import A2HError, ParticipantNotFound, RequestExpired

    try:
        req = await gw.ask("sales/nobody", question="Hello?")
    except ParticipantNotFound as e:
        print(e.code)       # "A2H_PARTICIPANT_NOT_FOUND"
        print(e.suggestion) # "Register the participant with gw.register()"
"""

from __future__ import annotations


class A2HError(Exception):
    """Base class for all A2H protocol errors."""
    code: str = "A2H_ERROR"
    suggestion: str = ""

    def __init__(self, message: str = "", **details):
        self.message = message
        self.details = details
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Participant errors
# ---------------------------------------------------------------------------

class ParticipantNotFound(A2HError):
    code = "A2H_PARTICIPANT_NOT_FOUND"
    suggestion = "Register the participant with gateway.register(Participant(...))"

class ParticipantUnavailable(A2HError):
    code = "A2H_PARTICIPANT_UNAVAILABLE"
    suggestion = "The participant is offline with no delegate configured. Set a delegate or wait."

class DuplicateParticipant(A2HError):
    code = "A2H_DUPLICATE_PARTICIPANT"
    suggestion = "A participant with this namespace/name is already registered. Use allow_replace=True to overwrite."

class InvalidParticipantID(A2HError):
    code = "A2H_INVALID_PARTICIPANT_ID"
    suggestion = "Name and namespace must be 1-64 alphanumeric characters (plus .-_), starting with a letter or digit."

class SenderNotRegistered(A2HError):
    code = "A2H_SENDER_NOT_REGISTERED"
    suggestion = "Register the sending agent with gateway.register() before sending requests."


# ---------------------------------------------------------------------------
# Request errors
# ---------------------------------------------------------------------------

class RequestNotFound(A2HError):
    code = "A2H_REQUEST_NOT_FOUND"
    suggestion = "The request_id may be wrong or the request was already cleaned up."

class RequestNotPending(A2HError):
    code = "A2H_REQUEST_NOT_PENDING"
    suggestion = "This request has already been answered, cancelled, or expired."

class RequestExpired(A2HError):
    code = "A2H_REQUEST_EXPIRED"
    suggestion = "The deadline passed before the human responded. Create a new request with a longer deadline."

class InvalidResponseType(A2HError):
    code = "A2H_INVALID_RESPONSE_TYPE"
    suggestion = "Response type must be one of: choice, approval, text, number, confirm, form."


# ---------------------------------------------------------------------------
# Channel errors
# ---------------------------------------------------------------------------

class ChannelDeliveryFailed(A2HError):
    code = "A2H_CHANNEL_DELIVERY_FAILED"
    suggestion = "The channel could not deliver the request. Check channel configuration and connectivity."

class NoSupportedChannel(A2HError):
    code = "A2H_NO_SUPPORTED_CHANNEL"
    suggestion = "No configured channel supports the requested response_type. Add a channel that supports it."

class ChannelVerificationFailed(A2HError):
    code = "A2H_CHANNEL_VERIFICATION_FAILED"
    suggestion = "The response could not be verified through this channel. Use a higher-trust channel."


# ---------------------------------------------------------------------------
# Security errors
# ---------------------------------------------------------------------------

class SignatureInvalid(A2HError):
    code = "A2H_SIGNATURE_INVALID"
    suggestion = "The request signature does not match. The request may have been tampered with."

class TrustLevelInsufficient(A2HError):
    code = "A2H_TRUST_LEVEL_INSUFFICIENT"
    suggestion = "This operation requires a higher-trust channel (e.g., dashboard instead of email)."

class RateLimitExceeded(A2HError):
    code = "A2H_RATE_LIMIT_EXCEEDED"
    suggestion = "Too many requests to this human. Wait before sending more."

class ExecutionMismatch(A2HError):
    code = "A2H_EXECUTION_MISMATCH"
    suggestion = "The agent's actual operation doesn't match what the human approved. Execution blocked."


# ---------------------------------------------------------------------------
# Registry errors
# ---------------------------------------------------------------------------

class RegistryError(A2HError):
    code = "A2H_REGISTRY_ERROR"
    suggestion = "Check the registry configuration and participant declarations."

class RegistryLoadError(RegistryError):
    code = "A2H_REGISTRY_LOAD_ERROR"
    suggestion = "Check the YAML file for syntax errors and required fields (name, namespace)."

class UnauthorizedParticipant(RegistryError):
    code = "A2H_UNAUTHORIZED_PARTICIPANT"
    suggestion = (
        "In strict mode, only participants declared in participants.yaml are allowed. "
        "Add the participant to the file or switch to permissive mode."
    )


# ---------------------------------------------------------------------------
# Store errors
# ---------------------------------------------------------------------------

class StoreSaveFailed(A2HError):
    code = "A2H_STORE_SAVE_FAILED"
    suggestion = "The storage backend could not save the request. Check database connectivity."

class StoreReadFailed(A2HError):
    code = "A2H_STORE_READ_FAILED"
    suggestion = "The storage backend could not read the request. Check database connectivity."
