class PaySwiftError(Exception):
    """Base exception for all PaySwift errors."""


class PaySwiftConfigurationError(PaySwiftError):
    """Raised when PaySwift configuration is missing or invalid."""


class PaySwiftValidationError(PaySwiftError):
    """Raised when the provider rejects the request as invalid (HTTP 400)."""


class PaySwiftAuthenticationError(PaySwiftError):
    """Raised on HTTP 401/403."""


class PaySwiftNotFoundError(PaySwiftError):
    """Raised on HTTP 404."""


class PaySwiftTransientError(PaySwiftError):
    """Raised on transient provider errors (HTTP 502, 503, connection drops) that might be safely retried."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PaySwiftTimeoutError(PaySwiftTransientError):
    """Raised specifically on read/connect timeouts."""


class PaySwiftRateLimitError(PaySwiftTransientError):
    """Raised on HTTP 429."""


class PaySwiftUnavailableError(PaySwiftTransientError):
    """Raised on specific gateway timeouts or full outages (HTTP 504)."""


class PaySwiftConflictError(PaySwiftError):
    """Raised on HTTP 409 when idempotency keys conflict or resource already exists."""


class PaySwiftProtocolError(PaySwiftError):
    """Raised when the provider responds with unexpected/malformed data."""


class PaySwiftUnknownError(PaySwiftError):
    """Raised on unhandled/unknown provider errors."""
