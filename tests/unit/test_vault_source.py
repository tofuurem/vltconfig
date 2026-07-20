"""Focused tests for Pydantic Vault settings-source orchestration."""

import os
from typing import Any, cast
from unittest.mock import Mock, patch

import hvac
import pytest
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings

from vltconfig.cache import VaultCache
from vltconfig.config import VaultAccess
from vltconfig.retry import VaultRetry
from vltconfig.vault_source import PydanticVaultSource


class FakeAuthenticator:
    """Record validated configurations and return one fake client."""

    def __init__(self, client: hvac.Client) -> None:
        self._client = client
        self.configs: list[VaultAccess] = []

    def authenticate(self, config: VaultAccess) -> hvac.Client:
        """Return the configured fake client."""
        self.configs.append(config)
        return self._client


def _configure_vault(*, token: str = "source-test-token") -> None:
    """Set a complete fake Vault environment."""
    os.environ.update(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_TOKEN": token,
            "VAULT_APP_NAME": "source/config",
            "VAULT_MOUNT_POINT": "secret",
        }
    )


def _client_with(payload: dict[str, Any]) -> tuple[hvac.Client, Mock]:
    """Return a typed fake client and its assertion-friendly mock."""
    client_mock = Mock()
    client_mock.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": payload}
    }
    return cast(hvac.Client, client_mock), client_mock


def _source(
    authenticator: FakeAuthenticator,
    *,
    cache: VaultCache | None = None,
) -> PydanticVaultSource:
    """Build a deterministic source with no retry sleep."""
    return PydanticVaultSource(
        BaseSettings,
        authenticator=authenticator,
        retry_policy=VaultRetry(sleeper=lambda _delay: None),
        cache=cache,
    )


@pytest.mark.unit
def test_source_reads_nested_vault_payload(clean_env: None) -> None:
    """The source returns the KV v2 data mapping without flattening values."""
    _configure_vault()
    payload = {
        "database_url": "postgresql://localhost/test",
        "nested": {"workers": 4},
        "optional": None,
    }
    client, client_mock = _client_with(payload)
    authenticator = FakeAuthenticator(client)

    result = _source(authenticator, cache=VaultCache(enabled=False))()

    assert result == payload
    assert len(authenticator.configs) == 1
    client_mock.secrets.kv.v2.read_secret_version.assert_called_once_with(
        path="source/config",
        mount_point="secret",
        raise_on_deleted_version=True,
    )


@pytest.mark.unit
def test_source_reuses_explicit_shared_cache(clean_env: None) -> None:
    """Consumers can deliberately share one isolated cache collaborator."""
    _configure_vault()
    payload = {"api_key": "cached-value"}
    client, client_mock = _client_with(payload)
    cache = VaultCache(fingerprint_key=b"source-test-key")

    first = _source(FakeAuthenticator(client), cache=cache)()
    second = _source(FakeAuthenticator(client), cache=cache)()

    assert first == second == payload
    assert client_mock.secrets.kv.v2.read_secret_version.call_count == 1


@pytest.mark.unit
def test_source_cache_invalidation_forces_a_fresh_read(clean_env: None) -> None:
    """The source exposes an explicit invalidation seam."""
    _configure_vault()
    client, client_mock = _client_with({"value": "fresh"})
    source = _source(
        FakeAuthenticator(client),
        cache=VaultCache(fingerprint_key=b"source-test-key"),
    )

    source()
    source.invalidate_cache()
    source()

    assert client_mock.secrets.kv.v2.read_secret_version.call_count == 2


@pytest.mark.unit
def test_source_parses_vault_access_once_per_load(clean_env: None) -> None:
    """Validation is reused for cache identity, auth, and the read request."""
    _configure_vault()
    client, _ = _client_with({"value": "loaded"})
    authenticator = FakeAuthenticator(client)

    with patch("vltconfig.vault_source.VaultAccess", wraps=VaultAccess) as factory:
        _source(authenticator, cache=VaultCache(enabled=False))()

    factory.assert_called_once_with()
    assert len(authenticator.configs) == 1


@pytest.mark.unit
def test_absent_vault_source_never_authenticates(clean_env: None) -> None:
    """JSON-only operation stays offline when all Vault variables are absent."""
    client, _ = _client_with({"value": "must-not-load"})
    authenticator = FakeAuthenticator(client)

    assert _source(authenticator)() == {}
    assert authenticator.configs == []


@pytest.mark.unit
def test_get_field_value_reports_existing_and_missing_fields(clean_env: None) -> None:
    """Pydantic's field lookup adapter keeps its established contract."""
    _configure_vault()
    client, _ = _client_with({"api_key": "loaded"})
    source = _source(FakeAuthenticator(client), cache=VaultCache(enabled=False))
    source()
    field = FieldInfo(annotation=str, default=None)

    assert source.get_field_value(field, "api_key") == (
        "loaded",
        "api_key",
        True,
    )
    assert source.get_field_value(field, "missing") == (None, "missing", False)
