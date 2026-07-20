"""Tests for the typed, versioned Vault KV v2 gateway."""

from collections.abc import Mapping
from typing import cast
from unittest.mock import Mock, call

import hvac.exceptions
import pytest
import requests.exceptions

from vltconfig.config import VaultAccess
from vltconfig.errors import (
    VaultAuthenticationError,
    VaultAuthorizationError,
    VaultConflictError,
    VaultPathNotFoundError,
    VaultResponseError,
    VaultUnavailableError,
)
from vltconfig.retry import VaultRetry
from vltconfig.vault_gateway import HvacVaultGateway


def _access() -> VaultAccess:
    """Return non-environment Vault access configuration for unit tests."""
    return VaultAccess.model_validate(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_TOKEN": "unit-token",
            "VAULT_APP_NAME": "apps/example",
            "VAULT_MOUNT_POINT": "config",
        }
    )


def _gateway(client: Mock) -> HvacVaultGateway:
    """Build a no-sleep gateway around one fake authenticated client."""
    authenticator = Mock()
    authenticator.authenticate.return_value = client
    return HvacVaultGateway(
        _access(),
        authenticator=authenticator,
        retry_policy=VaultRetry(max_attempts=1),
    )


@pytest.mark.unit
def test_read_narrows_versioned_response_and_redacts_repr() -> None:
    """The adapter returns a safe wrapper around copied payload data."""
    canary = "gateway-read-payload-canary"
    client = Mock()
    client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"token": canary}, "metadata": {"version": 7}}
    }

    secret = _gateway(client).read()
    copied = secret.copy_data()
    copied["token"] = "changed"

    assert secret.version == 7
    assert secret.copy_data() == {"token": canary}
    assert canary not in repr(secret)
    client.secrets.kv.v2.read_secret_version.assert_called_once_with(
        path="apps/example",
        mount_point="config",
        raise_on_deleted_version=True,
    )


@pytest.mark.unit
def test_create_and_update_use_exact_cas_values() -> None:
    """Create is create-only and update is pinned to the approved version."""
    client = Mock()
    gateway = _gateway(client)

    gateway.create({"token": "new"})
    gateway.update({"token": "changed"}, version=11)

    assert client.secrets.kv.v2.create_or_update_secret.call_args_list == [
        call(
            path="apps/example",
            secret={"token": "new"},
            mount_point="config",
            cas=0,
        ),
        call(
            path="apps/example",
            secret={"token": "changed"},
            mount_point="config",
            cas=11,
        ),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        (hvac.exceptions.InvalidPath("secret-value"), VaultPathNotFoundError),
        (hvac.exceptions.Forbidden("secret-value"), VaultAuthorizationError),
        (requests.exceptions.ConnectionError("secret-value"), VaultUnavailableError),
    ],
)
def test_read_translates_upstream_failures_without_their_messages(
    upstream: Exception,
    expected: type[Exception],
) -> None:
    """Read failures expose stable categories rather than upstream detail."""
    client = Mock()
    client.secrets.kv.v2.read_secret_version.side_effect = upstream

    with pytest.raises(expected) as captured:
        _gateway(client).read()

    assert "secret-value" not in str(captured.value)
    assert "secret-value" not in repr(captured.value)


@pytest.mark.unit
def test_write_invalid_request_is_a_safe_cas_conflict() -> None:
    """Vault check-and-set rejection requires a fresh read and plan."""
    client = Mock()
    client.secrets.kv.v2.create_or_update_secret.side_effect = (
        hvac.exceptions.InvalidRequest("payload-and-version-canary")
    )

    with pytest.raises(VaultConflictError) as captured:
        _gateway(client).update({"token": "secret"}, version=3)

    assert "payload-and-version-canary" not in str(captured.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "response",
    [
        {},
        {"data": {}},
        {"data": {"data": [], "metadata": {"version": 1}}},
        {"data": {"data": {}, "metadata": {"version": "1"}}},
        {"data": {"data": {1: "value"}, "metadata": {"version": 1}}},
    ],
)
def test_read_rejects_malformed_third_party_responses(response: object) -> None:
    """Dynamic HVAC responses are narrowed once at the boundary."""
    client = Mock()
    client.secrets.kv.v2.read_secret_version.return_value = response

    with pytest.raises(VaultResponseError):
        _gateway(client).read()


@pytest.mark.unit
def test_authentication_failure_is_translated_without_credentials() -> None:
    """Gateway construction does not leak authenticator exception text."""
    authenticator = Mock()
    authenticator.authenticate.side_effect = ValueError("credential-canary")
    gateway = HvacVaultGateway(
        _access(),
        authenticator=authenticator,
        retry_policy=VaultRetry(max_attempts=1),
    )

    with pytest.raises(VaultAuthenticationError) as captured:
        gateway.read()

    assert "credential-canary" not in str(captured.value)


@pytest.mark.unit
def test_authentication_network_failure_is_availability() -> None:
    """Transient authentication transport errors retain their operational category."""
    authenticator = Mock()
    authenticator.authenticate.side_effect = requests.exceptions.Timeout("canary")
    gateway = HvacVaultGateway(
        _access(),
        authenticator=authenticator,
        retry_policy=VaultRetry(max_attempts=1),
    )

    with pytest.raises(VaultUnavailableError):
        gateway.read()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        (hvac.exceptions.InvalidRequest("canary"), VaultResponseError),
        (hvac.exceptions.InternalServerError("canary"), VaultUnavailableError),
        (ValueError("canary"), VaultResponseError),
    ],
)
def test_other_read_failures_are_translated_safely(
    upstream: Exception,
    expected: type[Exception],
) -> None:
    """Non-CAS request failures retain stable response/availability categories."""
    client = Mock()
    client.secrets.kv.v2.read_secret_version.side_effect = upstream

    with pytest.raises(expected) as captured:
        _gateway(client).read()

    assert "canary" not in str(captured.value)


@pytest.mark.unit
def test_write_rejects_non_string_keys_and_invalid_versions() -> None:
    """Runtime callers cannot bypass the typed gateway contract."""
    gateway = _gateway(Mock())

    with pytest.raises(VaultResponseError):
        gateway.create(cast("Mapping[str, object]", {1: "value"}))
    with pytest.raises(ValueError):
        gateway.update({}, version=0)
    with pytest.raises(ValueError):
        gateway.update({}, version=True)
