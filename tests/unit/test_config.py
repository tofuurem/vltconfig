"""Unit tests for vlt.config module."""

import os

import pytest
from pydantic import SecretStr, ValidationError

from vltconfig.config import VaultAccess


def _secret_value(value: SecretStr | None) -> str | None:
    """Reveal a test credential only for an explicit boundary assertion."""
    return value.get_secret_value() if value is not None else None


@pytest.mark.unit
class TestVaultAccess:
    """Tests for VaultAccess configuration model."""

    def test_token_authentication(self, clean_env: None) -> None:
        """Test VaultAccess initialization with token authentication.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_APP_NAME"] = "test-app"

        config = VaultAccess()

        assert str(config.address) == "https://vault.example.com/"
        assert _secret_value(config.token) == "s.test-token"
        assert config.username is None
        assert config.password is None
        assert config.app_name == "test-app"
        assert config.mount_point == "secret"

    def test_userpass_authentication(self, clean_env: None) -> None:
        """Test VaultAccess initialization with username/password.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_USERNAME"] = "test-user"
        os.environ["VAULT_PASSWORD"] = "test-password"
        os.environ["VAULT_APP_NAME"] = "test-app"

        config = VaultAccess()

        assert str(config.address) == "https://vault.example.com/"
        assert config.token is None
        assert config.username == "test-user"
        assert _secret_value(config.password) == "test-password"
        assert config.app_name == "test-app"

    def test_missing_credentials_raises_error(self, clean_env: None) -> None:
        """Test that missing authentication credentials raises ValueError.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_APP_NAME"] = "test-app"

        with pytest.raises(ValueError, match="Must provide one of"):
            VaultAccess()

    def test_partial_userpass_raises_error(self, clean_env: None) -> None:
        """Test that incomplete userpass credentials raise ValueError.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_USERNAME"] = "test-user"
        # Missing password
        os.environ["VAULT_APP_NAME"] = "test-app"

        with pytest.raises(ValueError, match="Must provide one of"):
            VaultAccess()

    def test_invalid_url_scheme_raises_error(self, clean_env: None) -> None:
        """Test that invalid URL scheme raises ValidationError.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "ftp://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_APP_NAME"] = "test-app"

        with pytest.raises(ValidationError, match="URL scheme should be"):
            VaultAccess()

    def test_http_url_accepted(self, clean_env: None) -> None:
        """Test that http:// URLs are accepted (for local dev).

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "http://localhost:8200"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_APP_NAME"] = "test-app"

        config = VaultAccess()

        assert str(config.address) == "http://localhost:8200/"

    def test_https_url_accepted(self, clean_env: None) -> None:
        """Test that https:// URLs are accepted.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_APP_NAME"] = "test-app"

        config = VaultAccess()

        assert str(config.address) == "https://vault.example.com/"

    def test_custom_mount_point(self, clean_env: None) -> None:
        """Test custom mount point configuration.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_APP_NAME"] = "test-app"
        os.environ["VAULT_MOUNT_POINT"] = "custom-kv"

        config = VaultAccess()

        assert config.mount_point == "custom-kv"

    def test_field_aliases_work(self, clean_env: None) -> None:
        """Test that field aliases work correctly.

        :param clean_env: Fixture that cleans environment variables
        """
        # Using environment variables (aliases)
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_APP_NAME"] = "test-app"

        config = VaultAccess()

        # Should be accessible via field names
        assert config.address is not None
        assert _secret_value(config.token) == "s.test-token"
        assert config.app_name == "test-app"

    def test_both_token_and_userpass_prefers_token(self, clean_env: None) -> None:
        """Test that when both auth methods provided, validation passes.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_USERNAME"] = "test-user"
        os.environ["VAULT_PASSWORD"] = "test-password"
        os.environ["VAULT_APP_NAME"] = "test-app"

        config = VaultAccess()

        # Both should be present
        assert _secret_value(config.token) == "s.test-token"
        assert config.username == "test-user"
        assert _secret_value(config.password) == "test-password"

    def test_missing_app_name_raises_error(self, clean_env: None) -> None:
        """Test that missing VAULT_APP_NAME raises ValidationError.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        # Missing VAULT_APP_NAME

        with pytest.raises(ValidationError):
            VaultAccess()

    def test_missing_address_raises_error(self, clean_env: None) -> None:
        """Test that missing VAULT_ADDRESS raises ValidationError.

        :param clean_env: Fixture that cleans environment variables
        """
        # Missing VAULT_ADDRESS
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_APP_NAME"] = "test-app"

        with pytest.raises(ValidationError):
            VaultAccess()

    def test_approle_authentication(self, clean_env: None) -> None:
        """Test VaultAccess initialization with AppRole.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_ROLE_ID"] = "test-role-id"
        os.environ["VAULT_SECRET_ID"] = "test-secret-id"
        os.environ["VAULT_APP_NAME"] = "test-app"

        config = VaultAccess()

        assert str(config.address) == "https://vault.example.com/"
        assert _secret_value(config.role_id) == "test-role-id"
        assert _secret_value(config.secret_id) == "test-secret-id"
        assert config.token is None
        assert config.username is None
        assert config.password is None
        assert config.app_name == "test-app"

    def test_partial_approle_raises_error(self, clean_env: None) -> None:
        """Test that incomplete AppRole credentials raise ValueError.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_ROLE_ID"] = "test-role-id"
        # Missing VAULT_SECRET_ID
        os.environ["VAULT_APP_NAME"] = "test-app"

        with pytest.raises(ValueError, match="Must provide one of"):
            VaultAccess()

    def test_all_three_auth_methods_provided(self, clean_env: None) -> None:
        """Test that providing all three auth methods is valid.

        :param clean_env: Fixture that cleans environment variables
        """
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.test-token"
        os.environ["VAULT_USERNAME"] = "test-user"
        os.environ["VAULT_PASSWORD"] = "test-password"
        os.environ["VAULT_ROLE_ID"] = "test-role-id"
        os.environ["VAULT_SECRET_ID"] = "test-secret-id"
        os.environ["VAULT_APP_NAME"] = "test-app"

        config = VaultAccess()

        # All should be present
        assert _secret_value(config.token) == "s.test-token"
        assert config.username == "test-user"
        assert _secret_value(config.password) == "test-password"
        assert _secret_value(config.role_id) == "test-role-id"
        assert _secret_value(config.secret_id) == "test-secret-id"
