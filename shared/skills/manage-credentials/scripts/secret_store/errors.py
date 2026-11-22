"""The one error type of the secrets store. Messages never carry key material or plaintext."""


class SecretStoreError(RuntimeError):
    """Raised when a secrets-store operation cannot complete safely."""


class IntegrityError(SecretStoreError):
    """A check of the store itself failed: the checkpoint or pin on disk, or the local copy against
    the checkpoint. Never swallowed, never taken for a refusal of one change (plan L4, rules 1 and 5)."""
