"""Fixtures for the opt-in disposable Vault integration suite."""

import os
from dataclasses import dataclass

import hvac
import pytest


@dataclass(frozen=True, slots=True)
class VaultIntegration:
    """Fake credentials created inside one disposable Vault dev server."""

    address: str
    read_token: str
    write_token: str
    denied_token: str
    role_id: str
    secret_id: str
    username: str
    password: str


@pytest.fixture(scope="session")
def vault_integration() -> VaultIntegration:
    """Configure isolated KV, token, AppRole, and userpass test identities."""
    address = os.getenv("VLTCONFIG_INTEGRATION_VAULT_ADDRESS")
    root_token = os.getenv("VLTCONFIG_INTEGRATION_VAULT_ROOT_TOKEN")
    if not address or not root_token:
        pytest.skip("run through scripts/test-vault-integration.sh")

    client = hvac.Client(url=address, token=root_token)
    assert client.is_authenticated()
    client.secrets.kv.v2.create_or_update_secret(
        path="integration/config",
        secret={"service_name": "integration-service", "workers": 3},
        mount_point="secret",
    )

    read_policy = """
path "secret/data/integration/*" {
  capabilities = ["read"]
}
"""
    client.sys.create_or_update_policy("vltconfig-integration-read", read_policy)
    read_token = client.auth.token.create(
        policies=["vltconfig-integration-read"],
    )["auth"]["client_token"]
    write_policy = """
path "secret/data/integration/*" {
  capabilities = ["create", "read", "update"]
}
"""
    client.sys.create_or_update_policy("vltconfig-integration-write", write_policy)
    write_token = client.auth.token.create(
        policies=["vltconfig-integration-write"],
    )["auth"]["client_token"]
    denied_token = client.auth.token.create(
        policies=["default"],
    )["auth"]["client_token"]

    client.sys.enable_auth_method("approle")
    client.auth.approle.create_or_update_approle(
        "vltconfig-integration",
        token_policies=["vltconfig-integration-read"],
    )
    role_id = client.auth.approle.read_role_id("vltconfig-integration")["data"][
        "role_id"
    ]
    secret_id = client.auth.approle.generate_secret_id("vltconfig-integration")["data"][
        "secret_id"
    ]

    username = "vltconfig-integration-user"
    password = "vltconfig-integration-password"
    client.sys.enable_auth_method("userpass")
    client.auth.userpass.create_or_update_user(
        username,
        password=password,
        policies=["vltconfig-integration-read"],
    )

    return VaultIntegration(
        address=address,
        read_token=read_token,
        write_token=write_token,
        denied_token=denied_token,
        role_id=role_id,
        secret_id=secret_id,
        username=username,
        password=password,
    )
