"""Custom exceptions for RAG Config Manager."""


class RAGConfigManagerError(Exception):
    """Base exception for RAG Config Manager."""

    pass


class VaultConnectionError(RAGConfigManagerError):
    """Vault connection related errors."""

    pass


class VaultSecretError(RAGConfigManagerError):
    """Vault secret operations errors."""

    pass


class ConnectionNotFoundError(RAGConfigManagerError):
    """Connection not found error."""

    pass


class InvalidConnectionDataError(RAGConfigManagerError):
    """Invalid connection data error."""

    pass


class UserNotFoundError(RAGConfigManagerError):
    """User not found error."""

    pass
