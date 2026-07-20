"""Integration coverage for supported Vault authentication methods."""

import os

import pytest

from tests.integration.conftest import VaultIntegration
from vltconfig.auth import VaultAuthenticator
from vltconfig.config import VaultAccess


def _base_environment(integration: VaultIntegration) -> dict[str, str]:
    """Return non-credential access settings for the disposable server."""
    return {
        "VAULT_ADDRESS": integration.address,
        "VAULT_APP_NAME": "integration/config",
        "VAULT_MOUNT_POINT": "secret",
    }


@pytest.mark.integration
def test_token_authentication(
    vault_integration: VaultIntegration, clean_env: None
) -> None:
    """A policy-scoped token authenticates through the production client."""
    os.environ.update(
        {
            **_base_environment(vault_integration),
            "VAULT_TOKEN": vault_integration.read_token,
        }
    )

    assert VaultAuthenticator().authenticate(VaultAccess()).is_authenticated()


@pytest.mark.integration
def test_approle_authentication(
    vault_integration: VaultIntegration, clean_env: None
) -> None:
    """The disposable AppRole identity authenticates successfully."""
    os.environ.update(
        {
            **_base_environment(vault_integration),
            "VAULT_ROLE_ID": vault_integration.role_id,
            "VAULT_SECRET_ID": vault_integration.secret_id,
        }
    )

    assert VaultAuthenticator().authenticate(VaultAccess()).is_authenticated()


@pytest.mark.integration
def test_userpass_authentication(
    vault_integration: VaultIntegration, clean_env: None
) -> None:
    """The disposable userpass identity authenticates successfully."""
    os.environ.update(
        {
            **_base_environment(vault_integration),
            "VAULT_USERNAME": vault_integration.username,
            "VAULT_PASSWORD": vault_integration.password,
        }
    )

    assert VaultAuthenticator().authenticate(VaultAccess()).is_authenticated()
