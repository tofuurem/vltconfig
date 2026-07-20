"""Tests for explicit Vault source failure policies."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import hvac.exceptions
import pytest
from pydantic_settings import BaseSettings

from vltconfig import VaultFailurePolicy, VaultJsonConfig
from vltconfig.errors import (
    VaultAuthenticationError,
    VaultAuthorizationError,
    VaultConfigurationError,
    VaultPathNotFoundError,
    VaultResponseError,
    VaultUnavailableError,
)
from vltconfig.vault_source import PydanticVaultSource


@pytest.fixture(autouse=True)
def _disable_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Policy translation tests should never use production backoff."""
    monkeypatch.setattr("vltconfig.retry.time.sleep", lambda _delay: None)


def _configure_vault() -> None:
    """Set a complete, fake token configuration."""
    os.environ.update(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_TOKEN": "policy-test-token",
            "VAULT_APP_NAME": "policy/config",
        }
    )


@pytest.mark.unit
def test_absent_vault_configuration_skips_optional_source(clean_env: None) -> None:
    """No Vault variables means the optional source is absent, not broken."""
    source = PydanticVaultSource(BaseSettings)

    with patch.object(source, "_get_secret_from_vault") as get_secret:
        assert source() == {}

    get_secret.assert_not_called()


@pytest.mark.unit
def test_partial_vault_configuration_is_an_error(clean_env: None) -> None:
    """A partial Vault setup must not look like an absent optional source."""
    os.environ["VAULT_TOKEN"] = "policy-test-token"
    source = PydanticVaultSource(BaseSettings)

    with pytest.raises(VaultConfigurationError):
        source()


@pytest.mark.unit
def test_strict_policy_prevents_json_from_hiding_vault_failure(
    tmp_path: Path, clean_env: None
) -> None:
    """Configured Vault failures are visible even when JSON has valid data."""
    _configure_vault()
    (tmp_path / "config.json").write_text(json.dumps({"api_key": "json-value"}))
    os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

    class Settings(VaultJsonConfig):
        api_key: str

    with (
        patch.object(
            PydanticVaultSource,
            "_get_secret_from_vault",
            side_effect=hvac.exceptions.Forbidden("unsafe upstream detail"),
        ),
        pytest.raises(VaultAuthorizationError),
    ):
        Settings()


@pytest.mark.unit
def test_explicit_fallback_policy_allows_lower_priority_sources(
    tmp_path: Path, clean_env: None
) -> None:
    """Callers can deliberately retain the 1.x fail-open behavior."""
    _configure_vault()
    (tmp_path / "config.json").write_text(json.dumps({"api_key": "json-value"}))
    os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

    class Settings(VaultJsonConfig):
        vault_failure_policy = VaultFailurePolicy.FALLBACK

        api_key: str

    with patch.object(
        PydanticVaultSource,
        "_get_secret_from_vault",
        side_effect=hvac.exceptions.Forbidden("unsafe upstream detail"),
    ):
        settings = Settings()

    assert settings.api_key == "json-value"
    assert "vault_failure_policy" not in Settings.model_fields


@pytest.mark.unit
@pytest.mark.parametrize(
    ("upstream_error", "expected_error"),
    [
        (ValueError("authentication detail"), VaultAuthenticationError),
        (hvac.exceptions.Forbidden("authorization detail"), VaultAuthorizationError),
        (hvac.exceptions.InvalidPath("path detail"), VaultPathNotFoundError),
        (hvac.exceptions.VaultDown("availability detail"), VaultUnavailableError),
        (ConnectionError("network detail"), VaultUnavailableError),
        (TimeoutError("timeout detail"), VaultUnavailableError),
        (KeyError("payload detail"), VaultResponseError),
    ],
)
def test_strict_policy_translates_known_failure_categories(
    upstream_error: Exception,
    expected_error: type[Exception],
    clean_env: None,
) -> None:
    """Known runtime failures map to stable public error categories."""
    _configure_vault()
    source = PydanticVaultSource(BaseSettings)

    with (
        patch.object(source, "_get_secret_from_vault", side_effect=upstream_error),
        pytest.raises(expected_error),
    ):
        source()
