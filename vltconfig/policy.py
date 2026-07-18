"""Failure policies for optional configuration sources."""

from enum import StrEnum


class VaultFailurePolicy(StrEnum):
    """Control what happens when a configured Vault source fails."""

    STRICT = "strict"
    """Raise a typed error instead of consulting lower-priority sources."""

    FALLBACK = "fallback"
    """Explicitly retain the legacy fail-open behavior from vltconfig 1.x."""
