"""One error shape everywhere: {"error": {"code", "message", "retryable", "details"}}."""
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    # Shared codes from the IncuBrix connector contract (Appendix A)
    DEST_SPEC_VIOLATION = "DEST_SPEC_VIOLATION"
    DEST_RULE_FREQUENCY_CAP = "DEST_RULE_FREQUENCY_CAP"
    CONNECTION_AUTH_EXPIRED = "CONNECTION_AUTH_EXPIRED"
    PLATFORM_RATE_LIMIT = "PLATFORM_RATE_LIMIT"
    PLATFORM_QUOTA_EXHAUSTED = "PLATFORM_QUOTA_EXHAUSTED"
    PLATFORM_CONTENT_REJECTED = "PLATFORM_CONTENT_REJECTED"
    PLATFORM_UNAVAILABLE = "PLATFORM_UNAVAILABLE"
    CONNECTOR_DISABLED = "CONNECTOR_DISABLED"
    # Posting-rules codes (service level)
    DEST_RULE_SELF_PROMOTION = "DEST_RULE_SELF_PROMOTION"
    DEST_RULE_LINK_POLICY = "DEST_RULE_LINK_POLICY"
    # Service-level codes
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN_CONNECTOR = "UNKNOWN_CONNECTOR"
    METHOD_NOT_SUPPORTED = "METHOD_NOT_SUPPORTED"
    CONNECTION_INVALID = "CONNECTION_INVALID"
    MISSING_IDEMPOTENCY_KEY = "MISSING_IDEMPOTENCY_KEY"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


RETRYABLE = {
    ErrorCode.PLATFORM_RATE_LIMIT: True,
    ErrorCode.PLATFORM_UNAVAILABLE: True,
    ErrorCode.DEST_RULE_FREQUENCY_CAP: True,   # retry later, after the cap window
    ErrorCode.PLATFORM_QUOTA_EXHAUSTED: True,  # retry in the next window
}

HTTP_STATUS = {
    ErrorCode.DEST_SPEC_VIOLATION: 422,
    ErrorCode.DEST_RULE_FREQUENCY_CAP: 429,
    ErrorCode.CONNECTION_AUTH_EXPIRED: 401,
    ErrorCode.PLATFORM_RATE_LIMIT: 429,
    ErrorCode.PLATFORM_QUOTA_EXHAUSTED: 429,
    ErrorCode.PLATFORM_CONTENT_REJECTED: 422,
    ErrorCode.PLATFORM_UNAVAILABLE: 502,
    ErrorCode.CONNECTOR_DISABLED: 503,
    ErrorCode.DEST_RULE_SELF_PROMOTION: 422,
    ErrorCode.DEST_RULE_LINK_POLICY: 422,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.UNKNOWN_CONNECTOR: 404,
    ErrorCode.METHOD_NOT_SUPPORTED: 501,
    ErrorCode.CONNECTION_INVALID: 422,
    ErrorCode.MISSING_IDEMPOTENCY_KEY: 400,
    ErrorCode.IDEMPOTENCY_KEY_REUSED: 409,
    ErrorCode.INTERNAL_ERROR: 500,
}


class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None,
                 retryable: bool | None = None, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = RETRYABLE.get(code, False) if retryable is None else retryable
        self.status_code = status_code or HTTP_STATUS.get(code, 400)

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code.value, "message": self.message,
                          "retryable": self.retryable, "details": self.details}}


class ConnectorError(AppError):
    """Raised by connectors when a platform call fails. Same shape, same codes."""
