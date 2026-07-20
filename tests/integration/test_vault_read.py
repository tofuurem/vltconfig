"""Integration coverage for Vault KV v2 reads and failure translation."""

import os

import pytest
from pydantic_settings import BaseSettings

from tests.integration.conftest import VaultIntegration
from vltconfig.cache import VaultCache
from vltconfig.errors import (
    VaultAuthorizationError,
    VaultPathNotFoundError,
    VaultUnavailableError,
)
from vltconfig.retry import VaultRetry
from vltconfig.vault_source import PydanticVaultSource


def _configure_token(integration: VaultIntegration, token: str, *, path: str) -> None:
    """Configure a source against the disposable server."""
    os.environ.update(
        {
            "VAULT_ADDRESS": integration.address,
            "VAULT_TOKEN": token,
            "VAULT_APP_NAME": path,
            "VAULT_MOUNT_POINT": "secret",
        }
    )


def _source() -> PydanticVaultSource:
    """Use no cache and a one-attempt policy in integration assertions."""
    return PydanticVaultSource(
        BaseSettings,
        cache=VaultCache(enabled=False),
        retry_policy=VaultRetry(max_attempts=1),
    )


@pytest.mark.integration
def test_reads_real_kv_v2_payload(
    vault_integration: VaultIntegration, clean_env: None
) -> None:
    """The production hvac boundary reads a disposable KV v2 secret."""
    _configure_token(
        vault_integration,
        vault_integration.read_token,
        path="integration/config",
    )

    assert _source()() == {
        "service_name": "integration-service",
        "workers": 3,
    }


@pytest.mark.integration
def test_missing_path_is_translated(
    vault_integration: VaultIntegration, clean_env: None
) -> None:
    """A real missing KV path maps to the stable public category."""
    _configure_token(
        vault_integration,
        vault_integration.read_token,
        path="integration/missing",
    )

    with pytest.raises(VaultPathNotFoundError):
        _source()()


@pytest.mark.integration
def test_permission_failure_is_translated(
    vault_integration: VaultIntegration, clean_env: None
) -> None:
    """A real policy denial maps to authorization rather than fallback."""
    _configure_token(
        vault_integration,
        vault_integration.denied_token,
        path="integration/config",
    )

    with pytest.raises(VaultAuthorizationError):
        _source()()


@pytest.mark.integration
def test_network_failure_is_translated(
    vault_integration: VaultIntegration, clean_env: None
) -> None:
    """The production Requests adapter failure maps to availability."""
    _configure_token(
        vault_integration,
        vault_integration.read_token,
        path="integration/config",
    )
    os.environ["VAULT_ADDRESS"] = "http://127.0.0.1:0"

    with pytest.raises(VaultUnavailableError):
        _source()()
