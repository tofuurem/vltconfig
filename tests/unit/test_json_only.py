"""Tests for using vltconfig with JSON only (no Vault configuration)."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from vltconfig import VaultJsonConfig


@pytest.mark.unit
class TestJSONOnlyConfiguration:
    """Test that vltconfig works with only JSON config when Vault is not configured."""

    def test_json_only_no_vault_env_vars(self, clean_env: None) -> None:
        """Test loading config from JSON only when no Vault env vars are set.

        This is the main use case: user wants to use JSON config without Vault.

        :param clean_env: Fixture that cleans environment variables
        """
        # Create temporary config.json
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_data = {
                "database_url": "postgresql://localhost/testdb",
                "api_key": "test-key-from-json",
                "debug": True,
            }
            config_file.write_text(json.dumps(config_data))

            # Set only JSON path, NO Vault env vars
            os.environ["PYDANTIC_JSON_PATH"] = tmpdir

            # Define config class
            class TestConfig(VaultJsonConfig):
                database_url: str = "default"
                api_key: str = "default"
                debug: bool = False

            # Should load successfully from JSON without Vault
            config = TestConfig()

            assert config.database_url == "postgresql://localhost/testdb"
            assert config.api_key == "test-key-from-json"
            assert config.debug is True

    def test_json_and_env_vars_no_vault(self, clean_env: None) -> None:
        """Test that env vars take priority over JSON when Vault is not configured.

        :param clean_env: Fixture that cleans environment variables
        """
        # Create temporary config.json
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_data = {
                "database_url": "json-database-url",
                "api_key": "json-api-key",
            }
            config_file.write_text(json.dumps(config_data))

            # Set JSON path and override with env var
            os.environ["PYDANTIC_JSON_PATH"] = tmpdir
            os.environ["DATABASE_URL"] = "env-database-url"

            # Define config class
            class TestConfig(VaultJsonConfig):
                database_url: str
                api_key: str

            config = TestConfig()

            # Env var should take priority
            assert config.database_url == "env-database-url"
            # JSON value should be used for api_key
            assert config.api_key == "json-api-key"

    def test_defaults_when_no_vault_no_json(self, clean_env: None) -> None:
        """Test that default values work when neither Vault nor JSON are available.

        :param clean_env: Fixture that cleans environment variables
        """

        class TestConfig(VaultJsonConfig):
            database_url: str = "default-database"
            api_key: str = "default-key"
            debug: bool = False

        # No Vault env vars, no JSON path
        config = TestConfig()

        # Should use defaults
        assert config.database_url == "default-database"
        assert config.api_key == "default-key"
        assert config.debug is False

    def test_json_only_with_missing_required_field(self, clean_env: None) -> None:
        """Test that validation still works with JSON only config.

        :param clean_env: Fixture that cleans environment variables
        """
        # Create temporary config.json with missing required field
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_data = {
                "api_key": "test-key",
                # Missing database_url
            }
            config_file.write_text(json.dumps(config_data))

            os.environ["PYDANTIC_JSON_PATH"] = tmpdir

            # Define config class with required field
            class TestConfig(VaultJsonConfig):
                database_url: str  # No default = required
                api_key: str

            # Should raise ValidationError for missing required field
            with pytest.raises(ValidationError):
                TestConfig()
