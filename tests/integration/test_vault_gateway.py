"""Integration coverage for versioned Vault KV v2 gateway behavior."""

import itertools

import pytest

from tests.integration.conftest import VaultIntegration
from vltconfig.config import VaultAccess
from vltconfig.errors import VaultAuthorizationError, VaultPathNotFoundError
from vltconfig.retry import VaultRetry
from vltconfig.vault_gateway import HvacVaultGateway

_PATH_COUNTER = itertools.count()


def _gateway(
    integration: VaultIntegration,
    *,
    token: str,
    path: str,
) -> HvacVaultGateway:
    """Build a production gateway against the disposable server."""
    access = VaultAccess.model_validate(
        {
            "VAULT_ADDRESS": integration.address,
            "VAULT_TOKEN": token,
            "VAULT_APP_NAME": path,
            "VAULT_MOUNT_POINT": "secret",
        }
    )
    return HvacVaultGateway(access, retry_policy=VaultRetry(max_attempts=1))


@pytest.mark.integration
def test_reads_payload_and_kv_version(vault_integration: VaultIntegration) -> None:
    """The production gateway extracts both data and KV v2 metadata."""
    gateway = _gateway(
        vault_integration,
        token=vault_integration.read_token,
        path="integration/config",
    )

    secret = gateway.read()

    assert secret.version >= 1
    assert secret.copy_data() == {
        "service_name": "integration-service",
        "workers": 3,
    }


@pytest.mark.integration
def test_real_missing_path_and_permission_are_translated(
    vault_integration: VaultIntegration,
) -> None:
    """Stable gateway failures survive the real HVAC/Vault boundary."""
    missing_path = f"integration/gateway-missing-{next(_PATH_COUNTER)}"
    missing = _gateway(
        vault_integration,
        token=vault_integration.read_token,
        path=missing_path,
    )
    denied = _gateway(
        vault_integration,
        token=vault_integration.denied_token,
        path="integration/config",
    )

    with pytest.raises(VaultPathNotFoundError):
        missing.read()
    with pytest.raises(VaultAuthorizationError):
        denied.read()
