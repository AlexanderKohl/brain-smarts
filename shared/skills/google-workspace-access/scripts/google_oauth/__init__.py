"""Reusable Google Workspace OAuth 2.0 connection manager."""

from .client import GoogleConnection, GoogleOAuthError

__all__ = ["GoogleConnection", "GoogleOAuthError"]
