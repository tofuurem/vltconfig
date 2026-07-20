"""Bounded, isolated cache for Vault settings payloads."""

import hashlib
import hmac
import os
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

from vltconfig.config import VaultAccess


@dataclass(frozen=True, slots=True)
class VaultCacheKey:
    """Non-secret dimensions that isolate one cached Vault payload."""

    address: str
    mount_point: str
    path: str
    auth_fingerprint: str


@dataclass(slots=True)
class _CacheEntry:
    value: dict[str, Any]
    expires_at: float


class VaultCache:
    """Thread-safe per-consumer LRU cache with monotonic expiration."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        ttl_seconds: float = 300,
        max_entries: int = 128,
        clock: Callable[[], float] = time.monotonic,
        fingerprint_key: bytes | None = None,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must not be negative")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._fingerprint_key = fingerprint_key or secrets.token_bytes(32)
        self._entries: OrderedDict[VaultCacheKey, _CacheEntry] = OrderedDict()
        self._lock = RLock()

    @classmethod
    def from_environment(cls) -> "VaultCache":
        """Create an independent cache from the legacy cache environment knobs."""
        disabled = os.getenv("VAULT_CACHE_DISABLED", "").casefold() in {
            "true",
            "1",
            "yes",
        }
        ttl_text = os.getenv("VAULT_CACHE_TTL", "")
        maximum_text = os.getenv("VAULT_CACHE_MAX_ENTRIES", "")
        ttl = float(ttl_text) if ttl_text.isdigit() else 300.0
        maximum = int(maximum_text) if maximum_text.isdigit() else 128
        return cls(enabled=not disabled, ttl_seconds=ttl, max_entries=maximum)

    def key_for(self, config: VaultAccess) -> VaultCacheKey:
        """Build an opaque identity that changes whenever credentials rotate."""
        secret_parts = (
            config.token.get_secret_value() if config.token else "",
            config.username or "",
            config.password.get_secret_value() if config.password else "",
            config.role_id.get_secret_value() if config.role_id else "",
            config.secret_id.get_secret_value() if config.secret_id else "",
        )
        fingerprint = hmac.new(
            self._fingerprint_key,
            "\0".join(secret_parts).encode(),
            hashlib.sha256,
        ).hexdigest()
        return VaultCacheKey(
            address=str(config.address),
            mount_point=config.mount_point,
            path=config.app_name,
            auth_fingerprint=fingerprint,
        )

    def get(self, key: VaultCacheKey) -> dict[str, Any] | None:
        """Return an isolated cached copy, or ``None`` for miss/expiry/disabled."""
        if not self.enabled:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry.value)

    def put(self, key: VaultCacheKey, value: Mapping[str, Any]) -> None:
        """Store an isolated value and evict old entries beyond the bound."""
        if not self.enabled or self.ttl_seconds == 0:
            return
        with self._lock:
            self._entries[key] = _CacheEntry(
                value=deepcopy(dict(value)),
                expires_at=self._clock() + self.ttl_seconds,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def invalidate(self, key: VaultCacheKey | None = None) -> None:
        """Invalidate one addressable entry or every entry in this cache."""
        with self._lock:
            if key is None:
                self._entries.clear()
            else:
                self._entries.pop(key, None)

    def __len__(self) -> int:
        """Return the current entry count for diagnostics and tests."""
        with self._lock:
            return len(self._entries)
