"""Local Gmail / Google Tasks synchronisation layer.

Google remains the external system of record. Normal reads use the local
SQLite index; background workers keep it fresh.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
