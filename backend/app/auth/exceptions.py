"""Authentication domain exceptions."""


class AuthError(Exception):
    """Base class for authentication failures."""


class InvalidTokenError(AuthError):
    """Raised when an access token cannot be decoded or is not an access token."""


class TokenExpiredError(InvalidTokenError):
    """Raised when an access token is expired."""
