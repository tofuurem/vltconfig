"""Unit tests for vlt.vault_source module."""

import os
from typing import Any
from unittest.mock import Mock, patch

import hvac.exceptions
import pytest

from vltconfig.vault_source import PydanticVaultSource, _authenticate_vault


@pytest.mark.unit
class TestAuthenticateVault:
    """Tests for _authenticate_vault function."""

    @patch("vltconfig.vault_source.hvac.Client")
    def test_token_authentication_success(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test successful token authentication.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        mock_client.is_authenticated.return_value = True
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()
        client = _authenticate_vault(cfg)

        assert client == mock_client
        mock_client.is_authenticated.assert_called_once()

    @patch("vltconfig.vault_source.hvac.Client")
    def test_token_authentication_failure(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test token authentication failure.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        mock_client.is_authenticated.return_value = False
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()

        with pytest.raises(ValueError, match="All authentication methods failed"):
            _authenticate_vault(cfg)

    @patch("vltconfig.vault_source.hvac.Client")
    def test_userpass_authentication_success(
        self,
        mock_client_class: Mock,
        vault_userpass_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test successful userpass authentication.

        :param mock_client_class: Mock hvac.Client class
        :param vault_userpass_env_vars: Fixture with userpass env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_userpass_env_vars)

        mock_client = Mock()
        mock_client.auth.userpass.login.return_value = {
            "auth": {"client_token": "s.generated-token"}
        }
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()
        client = _authenticate_vault(cfg)

        assert client == mock_client
        assert client.token == "s.generated-token"
        mock_client.auth.userpass.login.assert_called_once_with(
            username="test-user", password="test-password"
        )

    @patch("vltconfig.vault_source.hvac.Client")
    def test_approle_authentication_success(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test successful AppRole authentication.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        # Setup AppRole env vars
        vault_env_vars["VAULT_ROLE_ID"] = "test-role-id"
        vault_env_vars["VAULT_SECRET_ID"] = "test-secret-id"
        # Remove token to force AppRole
        del vault_env_vars["VAULT_TOKEN"]
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        mock_client.auth.approle.login.return_value = {
            "auth": {"client_token": "s.approle-token"}
        }
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()
        client = _authenticate_vault(cfg)

        assert client == mock_client
        assert client.token == "s.approle-token"
        mock_client.auth.approle.login.assert_called_once_with(
            role_id="test-role-id", secret_id="test-secret-id"
        )

    @patch("vltconfig.vault_source.hvac.Client")
    def test_approle_authentication_failure(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test AppRole authentication failure when it's the only method.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        # Setup AppRole env vars only (no fallback)
        vault_env_vars["VAULT_ROLE_ID"] = "test-role-id"
        vault_env_vars["VAULT_SECRET_ID"] = "invalid-secret"
        del vault_env_vars["VAULT_TOKEN"]
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        mock_client.auth.approle.login.side_effect = hvac.exceptions.InvalidRequest(
            "Invalid role_id or secret_id"
        )
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()

        with pytest.raises(ValueError, match="All authentication methods failed"):
            _authenticate_vault(cfg)

    @patch("vltconfig.vault_source.hvac.Client")
    def test_token_takes_precedence_over_approle(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test that token authentication takes precedence over AppRole.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        # Provide both token and AppRole
        vault_env_vars["VAULT_TOKEN"] = "s.test-token"
        vault_env_vars["VAULT_ROLE_ID"] = "test-role-id"
        vault_env_vars["VAULT_SECRET_ID"] = "test-secret-id"
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        mock_client.is_authenticated.return_value = True
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()
        client = _authenticate_vault(cfg)

        # Should use token, not AppRole
        assert client.token == "s.test-token"
        mock_client.auth.approle.login.assert_not_called()

    @patch("vltconfig.vault_source.hvac.Client")
    def test_approle_takes_precedence_over_userpass(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test that AppRole authentication takes precedence over userpass.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        # Provide both AppRole and userpass, but no token
        vault_env_vars["VAULT_ROLE_ID"] = "test-role-id"
        vault_env_vars["VAULT_SECRET_ID"] = "test-secret-id"
        vault_env_vars["VAULT_USERNAME"] = "test-user"
        vault_env_vars["VAULT_PASSWORD"] = "test-password"
        del vault_env_vars["VAULT_TOKEN"]
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        mock_client.auth.approle.login.return_value = {
            "auth": {"client_token": "s.approle-token"}
        }
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()
        client = _authenticate_vault(cfg)

        # Should use AppRole, not userpass
        assert client.token == "s.approle-token"
        mock_client.auth.approle.login.assert_called_once()
        mock_client.auth.userpass.login.assert_not_called()

    @patch("vltconfig.vault_source.hvac.Client")
    def test_fallback_from_invalid_token_to_approle(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test fallback from invalid token to valid AppRole.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        # Provide both token and AppRole
        vault_env_vars["VAULT_TOKEN"] = "s.invalid-token"
        vault_env_vars["VAULT_ROLE_ID"] = "test-role-id"
        vault_env_vars["VAULT_SECRET_ID"] = "test-secret-id"
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        # Token auth fails
        mock_client.is_authenticated.return_value = False
        # AppRole succeeds
        mock_client.auth.approle.login.return_value = {
            "auth": {"client_token": "s.approle-fallback-token"}
        }
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()
        client = _authenticate_vault(cfg)

        # Should fallback to AppRole
        assert client.token == "s.approle-fallback-token"
        mock_client.is_authenticated.assert_called_once()
        mock_client.auth.approle.login.assert_called_once()

    @patch("vltconfig.vault_source.hvac.Client")
    def test_fallback_from_invalid_approle_to_userpass(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test fallback from invalid AppRole to valid userpass.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        # Provide AppRole and userpass, no token
        vault_env_vars["VAULT_ROLE_ID"] = "invalid-role-id"
        vault_env_vars["VAULT_SECRET_ID"] = "invalid-secret-id"
        vault_env_vars["VAULT_USERNAME"] = "test-user"
        vault_env_vars["VAULT_PASSWORD"] = "test-password"
        del vault_env_vars["VAULT_TOKEN"]
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        # AppRole fails
        mock_client.auth.approle.login.side_effect = hvac.exceptions.InvalidRequest(
            "Invalid credentials"
        )
        # Userpass succeeds
        mock_client.auth.userpass.login.return_value = {
            "auth": {"client_token": "s.userpass-fallback-token"}
        }
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()
        client = _authenticate_vault(cfg)

        # Should fallback to userpass
        assert client.token == "s.userpass-fallback-token"
        mock_client.auth.approle.login.assert_called_once()
        mock_client.auth.userpass.login.assert_called_once()

    @patch("vltconfig.vault_source.hvac.Client")
    def test_all_methods_fail_raises_combined_error(
        self, mock_client_class: Mock, vault_env_vars: dict[str, str], clean_env: None
    ) -> None:
        """Test that all methods failing raises error with all failure reasons.

        :param mock_client_class: Mock hvac.Client class
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        # Provide all three methods
        vault_env_vars["VAULT_TOKEN"] = "s.invalid-token"
        vault_env_vars["VAULT_ROLE_ID"] = "invalid-role-id"
        vault_env_vars["VAULT_SECRET_ID"] = "invalid-secret-id"
        vault_env_vars["VAULT_USERNAME"] = "invalid-user"
        vault_env_vars["VAULT_PASSWORD"] = "invalid-password"
        os.environ.update(vault_env_vars)

        mock_client = Mock()
        # All methods fail
        mock_client.is_authenticated.return_value = False
        mock_client.auth.approle.login.side_effect = hvac.exceptions.InvalidRequest(
            "AppRole failed"
        )
        mock_client.auth.userpass.login.side_effect = hvac.exceptions.InvalidRequest(
            "Userpass failed"
        )
        mock_client_class.return_value = mock_client

        from vltconfig.config import VaultAccess

        cfg = VaultAccess()

        with pytest.raises(ValueError, match="All authentication methods failed"):
            _authenticate_vault(cfg)


@pytest.mark.unit
class TestPydanticVaultSource:
    """Tests for PydanticVaultSource class."""

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_successful_secret_retrieval(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test successful secret retrieval from Vault.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        # Setup mocks
        mock_cfg = Mock()
        mock_cfg.app_name = "test-app/config"
        mock_cfg.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client

        # Test
        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        assert result == sample_vault_secrets
        mock_client.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="test-app/config", mount_point="secret"
        )

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_forbidden_exception_handling(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test handling of Forbidden exception.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = (
            hvac.exceptions.Forbidden("Access denied")
        )
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        # Should return empty dict on error
        assert result == {}

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_invalid_path_exception_handling(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test handling of InvalidPath exception.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = (
            hvac.exceptions.InvalidPath("Path not found")
        )
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        assert result == {}

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_vault_down_exception_handling(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test handling of VaultDown exception.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = (
            hvac.exceptions.VaultDown("Vault is down")
        )
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        assert result == {}

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_connection_error_handling(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test handling of ConnectionError.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = ConnectionError(
            "Network error"
        )
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        assert result == {}

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_timeout_error_handling(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test handling of TimeoutError.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = TimeoutError(
            "Request timeout"
        )
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        assert result == {}

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_authentication_failure_handling(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test handling of authentication failure.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_auth.side_effect = ValueError("Authentication failed")

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        assert result == {}

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_get_field_value_existing(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test get_field_value for existing field.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client

        from pydantic.fields import FieldInfo
        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        source()  # Load secrets

        field_info = FieldInfo(annotation=str, default=None)
        value, name, is_set = source.get_field_value(field_info, "api_key")

        assert value == "test-api-key-123"
        assert name == "api_key"
        assert is_set is True

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_get_field_value_missing(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test get_field_value for missing field.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client

        from pydantic.fields import FieldInfo
        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        source()  # Load secrets

        field_info = FieldInfo(annotation=str, default=None)
        value, name, is_set = source.get_field_value(field_info, "nonexistent")

        assert value is None
        assert name == "nonexistent"
        assert is_set is False


@pytest.mark.unit
class TestVaultSourceCaching:
    """Tests for PydanticVaultSource caching functionality."""

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_cache_hit_on_second_call(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test that second call hits cache and doesn't call Vault.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        # Clear cache before test
        from vltconfig.vault_source import PydanticVaultSource

        PydanticVaultSource._cache.clear()
        PydanticVaultSource._cache_enabled = True

        mock_cfg = Mock()
        mock_cfg.address = "https://vault.example.com/"
        mock_cfg.app_name = "test-app/config"
        mock_cfg.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        # First call - should hit Vault
        source1 = PydanticVaultSource(settings_cls=BaseSettings)
        result1 = source1()

        assert result1 == sample_vault_secrets
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 1

        # Second call - should hit cache
        source2 = PydanticVaultSource(settings_cls=BaseSettings)
        result2 = source2()

        assert result2 == sample_vault_secrets
        # Vault should still be called only once (from first call)
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 1

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    @patch("vltconfig.vault_source.datetime")
    def test_cache_miss_after_ttl_expiration(
        self,
        mock_datetime: Mock,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test that cache expires after TTL.

        :param mock_datetime: Mock datetime module
        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        # Clear cache before test
        from datetime import datetime, timedelta

        from vltconfig.vault_source import PydanticVaultSource

        PydanticVaultSource._cache.clear()
        PydanticVaultSource._cache_enabled = True
        PydanticVaultSource._cache_ttl_seconds = 300

        mock_cfg = Mock()
        mock_cfg.address = "https://vault.example.com/"
        mock_cfg.app_name = "test-app/config"
        mock_cfg.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        # Mock datetime for first call
        first_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = first_time

        # First call
        source1 = PydanticVaultSource(settings_cls=BaseSettings)
        result1 = source1()

        assert result1 == sample_vault_secrets
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 1

        # Mock datetime for second call (after TTL expiration)
        expired_time = first_time + timedelta(seconds=301)
        mock_datetime.now.return_value = expired_time

        # Second call - cache should be expired
        source2 = PydanticVaultSource(settings_cls=BaseSettings)
        result2 = source2()

        assert result2 == sample_vault_secrets
        # Vault should be called twice (cache expired)
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 2

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_cache_disabled_via_env_var(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test that cache can be disabled via environment variable.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        vault_env_vars["VAULT_CACHE_DISABLED"] = "true"
        os.environ.update(vault_env_vars)

        # Clear cache before test
        from vltconfig.vault_source import PydanticVaultSource

        PydanticVaultSource._cache.clear()

        mock_cfg = Mock()
        mock_cfg.address = "https://vault.example.com/"
        mock_cfg.app_name = "test-app/config"
        mock_cfg.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        # First call
        source1 = PydanticVaultSource(settings_cls=BaseSettings)
        result1 = source1()

        assert result1 == sample_vault_secrets
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 1

        # Second call - should not use cache
        source2 = PydanticVaultSource(settings_cls=BaseSettings)
        result2 = source2()

        assert result2 == sample_vault_secrets
        # Vault should be called twice (cache disabled)
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 2

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_custom_cache_ttl_via_env_var(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test custom cache TTL via environment variable.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        vault_env_vars["VAULT_CACHE_TTL"] = "600"
        os.environ.update(vault_env_vars)

        # Clear cache before test
        from vltconfig.vault_source import PydanticVaultSource

        PydanticVaultSource._cache.clear()
        PydanticVaultSource._cache_enabled = True

        mock_cfg = Mock()
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        _ = PydanticVaultSource(settings_cls=BaseSettings)

        # Verify TTL was set from environment
        assert PydanticVaultSource._cache_ttl_seconds == 600

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_different_cache_keys_for_different_configs(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test that different configurations use different cache keys.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        # Clear cache before test
        from vltconfig.vault_source import PydanticVaultSource

        PydanticVaultSource._cache.clear()
        PydanticVaultSource._cache_enabled = True

        # First call with first config
        vault_env_vars["VAULT_ADDRESS"] = "https://vault1.example.com"
        vault_env_vars["VAULT_APP_NAME"] = "app1/config"
        os.environ.update(vault_env_vars)

        mock_cfg1 = Mock()
        mock_cfg1.address = "https://vault1.example.com/"
        mock_cfg1.app_name = "app1/config"
        mock_cfg1.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg1

        mock_client1 = Mock()
        mock_client1.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client1

        from pydantic_settings import BaseSettings

        source1 = PydanticVaultSource(settings_cls=BaseSettings)
        result1 = source1()

        assert result1 == sample_vault_secrets
        assert mock_client1.secrets.kv.v2.read_secret_version.call_count == 1

        # Second call with different config
        vault_env_vars["VAULT_ADDRESS"] = "https://vault2.example.com"
        vault_env_vars["VAULT_APP_NAME"] = "app2/config"
        os.environ.update(vault_env_vars)

        mock_cfg2 = Mock()
        mock_cfg2.address = "https://vault2.example.com/"
        mock_cfg2.app_name = "app2/config"
        mock_cfg2.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg2

        mock_client2 = Mock()
        mock_client2.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_vault_secrets}
        }
        mock_auth.return_value = mock_client2

        source2 = PydanticVaultSource(settings_cls=BaseSettings)
        result2 = source2()

        assert result2 == sample_vault_secrets
        # Second config should also hit Vault (different cache key)
        assert mock_client2.secrets.kv.v2.read_secret_version.call_count == 1


@pytest.mark.unit
class TestVaultSourceRetry:
    """Tests for PydanticVaultSource retry functionality."""

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_successful_retry_after_vault_down(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test successful retry after VaultDown error.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        from vltconfig.vault_source import PydanticVaultSource

        # Clear cache to ensure fresh call
        PydanticVaultSource._cache.clear()
        PydanticVaultSource._cache_enabled = False

        mock_cfg = Mock()
        mock_cfg.address = "https://vault.example.com/"
        mock_cfg.app_name = "test-app/config"
        mock_cfg.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        # First call fails with VaultDown, second succeeds
        mock_client.secrets.kv.v2.read_secret_version.side_effect = [
            hvac.exceptions.VaultDown("Vault is down"),
            {"data": {"data": sample_vault_secrets}},
        ]
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        # Should succeed after retry
        assert result == sample_vault_secrets
        # Should be called twice (1 failure + 1 success)
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 2

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_all_retries_exhausted_vault_down(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        vault_env_vars: dict[str, Any],
        clean_env: None,
    ) -> None:
        """Test that all retries are exhausted and exception is caught.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        from vltconfig.vault_source import PydanticVaultSource

        # Clear cache
        PydanticVaultSource._cache.clear()
        PydanticVaultSource._cache_enabled = False

        mock_cfg = Mock()
        mock_cfg.address = "https://vault.example.com/"
        mock_cfg.app_name = "test-app/config"
        mock_cfg.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        # All attempts fail
        mock_client.secrets.kv.v2.read_secret_version.side_effect = (
            hvac.exceptions.VaultDown("Vault is down")
        )
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        # Should return empty dict after all retries fail
        assert result == {}
        # Should be called 3 times (all retry attempts)
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 3

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_no_retry_on_forbidden_error(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test that Forbidden error does not trigger retry.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        from vltconfig.vault_source import PydanticVaultSource

        # Clear cache
        PydanticVaultSource._cache.clear()
        PydanticVaultSource._cache_enabled = False

        mock_cfg = Mock()
        mock_cfg.address = "https://vault.example.com/"
        mock_cfg.app_name = "test-app/config"
        mock_cfg.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        # Forbidden error should not retry
        mock_client.secrets.kv.v2.read_secret_version.side_effect = (
            hvac.exceptions.Forbidden("Access denied")
        )
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        # Should return empty dict immediately (no retry)
        assert result == {}
        # Should be called only once (no retries for Forbidden)
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 1

    @patch("vltconfig.vault_source._authenticate_vault")
    @patch("vltconfig.vault_source.VaultAccess")
    def test_successful_retry_after_connection_error(
        self,
        mock_vault_access: Mock,
        mock_auth: Mock,
        sample_vault_secrets: dict[str, Any],
        vault_env_vars: dict[str, str],
        clean_env: None,
    ) -> None:
        """Test successful retry after ConnectionError.

        :param mock_vault_access: Mock VaultAccess
        :param mock_auth: Mock authentication function
        :param sample_vault_secrets: Fixture with sample secrets
        :param vault_env_vars: Fixture with vault env vars
        :param clean_env: Fixture that cleans environment
        """
        os.environ.update(vault_env_vars)

        from vltconfig.vault_source import PydanticVaultSource

        # Clear cache
        PydanticVaultSource._cache.clear()
        PydanticVaultSource._cache_enabled = False

        mock_cfg = Mock()
        mock_cfg.address = "https://vault.example.com/"
        mock_cfg.app_name = "test-app/config"
        mock_cfg.mount_point = "secret"
        mock_vault_access.return_value = mock_cfg

        mock_client = Mock()
        # First call fails with ConnectionError, second succeeds
        mock_client.secrets.kv.v2.read_secret_version.side_effect = [
            ConnectionError("Network error"),
            {"data": {"data": sample_vault_secrets}},
        ]
        mock_auth.return_value = mock_client

        from pydantic_settings import BaseSettings

        source = PydanticVaultSource(settings_cls=BaseSettings)
        result = source()

        # Should succeed after retry
        assert result == sample_vault_secrets
        # Should be called twice (1 failure + 1 success)
        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 2
