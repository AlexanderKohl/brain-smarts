"""The one error type of the secrets store. Messages never carry key material or plaintext."""


class SecretStoreError(RuntimeError):
    """Raised when a secrets-store operation cannot complete safely."""
