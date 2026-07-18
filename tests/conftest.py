"""Pytest configuration and shared fixtures for vault-pydantic-simple tests."""

import json
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest


@pytest.fixture
def vault_env_vars() -> dict[str, str]:
    """Standard Vault environment variables for testing.

    :return: Dictionary of Vault configuration env vars
    """
    return {
        "VAULT_ADDRESS": "https://vault.example.com",
        "VAULT_TOKEN": "s.test-token-123",
        "VAULT_APP_NAME": "test-app/config",
        "VAULT_MOUNT_POINT": "secret",
    }


@pytest.fixture
def vault_userpass_env_vars() -> dict[str, str]:
    """Vault environment variables for userpass authentication.

    :return: Dictionary of Vault userpass env vars
    """
    return {
        "VAULT_ADDRESS": "https://vault.example.com",
        "VAULT_USERNAME": "test-user",
        "VAULT_PASSWORD": "test-password",
        "VAULT_APP_NAME": "test-app/config",
    }


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Clean environment fixture that removes all Vault env vars.

    Yields after removing Vault vars, restores them after test.

    :yield: None
    """
    # Store original env vars
    original_env = os.environ.copy()

    # Remove all Vault-related env vars
    vault_vars = [
        "VAULT_ADDRESS",
        "VAULT_TOKEN",
        "VAULT_USERNAME",
        "VAULT_PASSWORD",
        "VAULT_ROLE_ID",
        "VAULT_SECRET_ID",
        "VAULT_APP_NAME",
        "VAULT_MOUNT_POINT",
        "PYDANTIC_JSON_PATH",
    ]
    for var in vault_vars:
        os.environ.pop(var, None)

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_vault_client() -> Mock:
    """Create a mock hvac Client for testing.

    :return: Mock hvac.Client instance
    """
    mock_client = Mock()
    mock_client.is_authenticated.return_value = True
    mock_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {
            "data": {
                "database_url": "postgresql://localhost/testdb",
                "api_key": "test-api-key-123",
                "debug": True,
                "max_connections": 10,
            }
        }
    }
    return mock_client


@pytest.fixture
def sample_vault_secrets() -> dict[str, Any]:
    """Sample secrets returned from Vault.

    :return: Dictionary of test secrets
    """
    return {
        "database_url": "postgresql://localhost/testdb",
        "api_key": "test-api-key-123",
        "debug": True,
        "max_connections": 10,
    }


@pytest.fixture
def temp_json_config(tmp_path: Path) -> Path:
    """Create a temporary config.json file.

    :param tmp_path: Pytest temporary directory
    :return: Path to created config.json
    """
    config_data = {
        "database_url": "postgresql://localhost/jsondb",
        "api_key": "json-api-key",
        "debug": False,
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    return config_file


@pytest.fixture
def temp_json_config_dir(tmp_path: Path, temp_json_config: Path) -> Path:
    """Get directory containing config.json.

    :param tmp_path: Pytest temporary directory
    :param temp_json_config: Path to config.json file
    :return: Directory path
    """
    return tmp_path
