"""Unit tests for isolated Vault authentication."""

import os
from unittest.mock import Mock

import hvac.exceptions
import pytest

from vltconfig.auth import VaultAuthenticator
from vltconfig.config import VaultAccess


@pytest.mark.unit
def test_token_authentication_uses_injected_client_factory(clean_env: None) -> None:
    """Token auth should not construct or patch a module-global client."""
    os.environ.update(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_TOKEN": "auth-test-token",
            "VAULT_APP_NAME": "auth/config",
        }
    )
    client = Mock()
    client.is_authenticated.return_value = True
    client_factory = Mock(return_value=client)

    result = VaultAuthenticator(client_factory=client_factory).authenticate(
        VaultAccess()
    )

    assert result is client
    assert client.token == "auth-test-token"
    client_factory.assert_called_once_with(url="https://vault.example.com/")


@pytest.mark.unit
def test_authentication_falls_back_in_documented_order(clean_env: None) -> None:
    """Token, AppRole, and userpass remain the ordered fallback chain."""
    os.environ.update(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_TOKEN": "invalid-auth-test-token",
            "VAULT_ROLE_ID": "invalid-auth-test-role",
            "VAULT_SECRET_ID": "invalid-auth-test-secret-id",
            "VAULT_USERNAME": "auth-test-user",
            "VAULT_PASSWORD": "auth-test-password",
            "VAULT_APP_NAME": "auth/config",
        }
    )
    client = Mock()
    client.is_authenticated.return_value = False
    client.auth.approle.login.side_effect = hvac.exceptions.InvalidRequest(
        "unsafe AppRole detail"
    )
    client.auth.userpass.login.return_value = {
        "auth": {"client_token": "generated-userpass-token"}
    }

    result = VaultAuthenticator(client_factory=Mock(return_value=client)).authenticate(
        VaultAccess()
    )

    assert result is client
    assert client.token == "generated-userpass-token"
    client.is_authenticated.assert_called_once_with()
    client.auth.approle.login.assert_called_once_with(
        role_id="invalid-auth-test-role",
        secret_id="invalid-auth-test-secret-id",
    )
    client.auth.userpass.login.assert_called_once_with(
        username="auth-test-user",
        password="auth-test-password",
    )


@pytest.mark.unit
def test_approle_success_stops_before_userpass(clean_env: None) -> None:
    """A successful higher-priority method stops the fallback chain."""
    os.environ.update(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_ROLE_ID": "auth-test-role",
            "VAULT_SECRET_ID": "auth-test-secret-id",
            "VAULT_USERNAME": "auth-test-user",
            "VAULT_PASSWORD": "auth-test-password",
            "VAULT_APP_NAME": "auth/config",
        }
    )
    client = Mock()
    client.auth.approle.login.return_value = {
        "auth": {"client_token": "generated-approle-token"}
    }

    result = VaultAuthenticator(client_factory=Mock(return_value=client)).authenticate(
        VaultAccess()
    )

    assert result is client
    assert client.token == "generated-approle-token"
    client.auth.userpass.login.assert_not_called()


@pytest.mark.unit
def test_all_authentication_failures_produce_value_free_error(clean_env: None) -> None:
    """Failure diagnostics expose method names without upstream details."""
    canary = "auth-upstream-redaction-canary"
    os.environ.update(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_TOKEN": "invalid-auth-test-token",
            "VAULT_ROLE_ID": "invalid-auth-test-role",
            "VAULT_SECRET_ID": "invalid-auth-test-secret-id",
            "VAULT_USERNAME": "auth-test-user",
            "VAULT_PASSWORD": "auth-test-password",
            "VAULT_APP_NAME": "auth/config",
        }
    )
    client = Mock()
    client.is_authenticated.return_value = False
    client.auth.approle.login.side_effect = hvac.exceptions.InvalidRequest(canary)
    client.auth.userpass.login.side_effect = hvac.exceptions.InvalidRequest(canary)

    with pytest.raises(ValueError) as captured:
        VaultAuthenticator(client_factory=Mock(return_value=client)).authenticate(
            VaultAccess()
        )

    assert canary not in str(captured.value)
    assert "token, AppRole, userpass" in str(captured.value)
