class SandboxError(Exception):
    """Base exception for eci-as-sandbox."""


class AuthenticationError(SandboxError):
    """Raised when credentials are missing or invalid."""


class ApiError(SandboxError):
    """Raised for API-level errors."""
