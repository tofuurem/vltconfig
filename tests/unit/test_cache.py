"""Unit tests for isolated Vault cache state."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from vltconfig.cache import VaultCache
from vltconfig.config import VaultAccess


class Clock:
    """Controllable monotonic clock."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _access(*, token: str, path: str = "cache/config") -> VaultAccess:
    """Build a fake access model for cache identity tests."""
    os.environ.update(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_TOKEN": token,
            "VAULT_APP_NAME": path,
            "VAULT_MOUNT_POINT": "secret",
        }
    )
    return VaultAccess()


@pytest.mark.unit
def test_cache_uses_monotonic_ttl_and_expires_entries(clean_env: None) -> None:
    """Expiry depends only on the injected monotonic clock."""
    clock = Clock()
    cache = VaultCache(ttl_seconds=5, clock=clock, fingerprint_key=b"test-key")
    key = cache.key_for(_access(token="cache-test-token"))
    cache.put(key, {"value": "cached"})

    clock.now = 4.9
    assert cache.get(key) == {"value": "cached"}

    clock.now = 5.0
    assert cache.get(key) is None
    assert len(cache) == 0


@pytest.mark.unit
def test_cache_is_bounded_and_evicts_least_recently_used(clean_env: None) -> None:
    """Adding beyond capacity removes the least recently accessed entry."""
    cache = VaultCache(max_entries=2, fingerprint_key=b"test-key")
    first = cache.key_for(_access(token="cache-token-1", path="cache/one"))
    second = cache.key_for(_access(token="cache-token-2", path="cache/two"))
    third = cache.key_for(_access(token="cache-token-3", path="cache/three"))

    cache.put(first, {"value": 1})
    cache.put(second, {"value": 2})
    assert cache.get(first) == {"value": 1}
    cache.put(third, {"value": 3})

    assert cache.get(first) == {"value": 1}
    assert cache.get(second) is None
    assert cache.get(third) == {"value": 3}


@pytest.mark.unit
def test_cache_copies_values_on_write_and_read(clean_env: None) -> None:
    """Callers cannot mutate cached nested data through shared references."""
    cache = VaultCache(fingerprint_key=b"test-key")
    key = cache.key_for(_access(token="cache-copy-token"))
    original = {"nested": {"items": [1, 2]}}
    cache.put(key, original)

    original["nested"]["items"].append(3)
    first_read = cache.get(key)
    assert first_read == {"nested": {"items": [1, 2]}}

    assert first_read is not None
    first_read["nested"]["items"].append(4)
    assert cache.get(key) == {"nested": {"items": [1, 2]}}


@pytest.mark.unit
def test_cache_invalidation_supports_one_key_or_every_key(clean_env: None) -> None:
    """Consumers can invalidate an addressable entry or the entire cache."""
    cache = VaultCache(fingerprint_key=b"test-key")
    first = cache.key_for(_access(token="cache-token-1", path="cache/one"))
    second = cache.key_for(_access(token="cache-token-2", path="cache/two"))
    cache.put(first, {"value": 1})
    cache.put(second, {"value": 2})

    cache.invalidate(first)
    assert cache.get(first) is None
    assert cache.get(second) == {"value": 2}

    cache.invalidate()
    assert len(cache) == 0


@pytest.mark.unit
def test_credential_rotation_changes_opaque_cache_identity(clean_env: None) -> None:
    """Rotated credentials cannot read an earlier identity's cache entry."""
    first_canary = "cache-credential-canary-one"
    second_canary = "cache-credential-canary-two"
    cache = VaultCache(fingerprint_key=b"test-key")
    first = cache.key_for(_access(token=first_canary))
    second = cache.key_for(_access(token=second_canary))

    assert first != second
    assert first_canary not in repr(first)
    assert second_canary not in repr(second)


@pytest.mark.unit
def test_cache_instances_keep_configuration_independent(clean_env: None) -> None:
    """Disabling or expiring one cache cannot mutate another cache."""
    clock = Clock()
    disabled = VaultCache(enabled=False, ttl_seconds=1, clock=clock)
    enabled = VaultCache(enabled=True, ttl_seconds=10, clock=clock)
    access = _access(token="cache-independent-token")
    disabled_key = disabled.key_for(access)
    enabled_key = enabled.key_for(access)

    disabled.put(disabled_key, {"value": "disabled"})
    enabled.put(enabled_key, {"value": "enabled"})
    clock.now = 2

    assert disabled.get(disabled_key) is None
    assert enabled.get(enabled_key) == {"value": "enabled"}


@pytest.mark.unit
def test_cache_operations_are_thread_safe(clean_env: None) -> None:
    """Concurrent readers and writers preserve a valid bounded cache."""
    cache = VaultCache(max_entries=4, fingerprint_key=b"test-key")
    key = cache.key_for(_access(token="cache-thread-token"))

    def write_and_read(index: int) -> bool:
        cache.put(key, {"worker": index, "nested": [index]})
        value = cache.get(key)
        return value is not None and isinstance(value["worker"], int)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(write_and_read, range(100)))

    assert all(results)
    assert len(cache) == 1


@pytest.mark.unit
def test_environment_configuration_builds_one_cache(clean_env: None) -> None:
    """Legacy cache environment variables configure only the new instance."""
    os.environ["VAULT_CACHE_DISABLED"] = "yes"
    os.environ["VAULT_CACHE_TTL"] = "42"
    os.environ["VAULT_CACHE_MAX_ENTRIES"] = "7"

    cache = VaultCache.from_environment()

    assert cache.enabled is False
    assert cache.ttl_seconds == 42
    assert cache.max_entries == 7
