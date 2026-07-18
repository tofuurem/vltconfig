"""Unit tests for vlt.json_source module."""

import json
import os
from pathlib import Path

import pytest

from vltconfig.errors import (
    JSONDecodeError,
    JSONFileNotFoundError,
    JSONPermissionError,
    JSONStructureError,
)
from vltconfig.json_source import PydanticJSONSource


@pytest.mark.unit
class TestPydanticJSONSource:
    """Tests for PydanticJSONSource class."""

    def test_successful_json_loading(
        self, temp_json_config_dir: Path, clean_env: None
    ) -> None:
        """Test successful JSON config loading.

        :param temp_json_config_dir: Fixture with temp config directory
        :param clean_env: Fixture that cleans environment
        """
        os.environ["PYDANTIC_JSON_PATH"] = str(temp_json_config_dir)

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        result = source()

        assert result["database_url"] == "postgresql://localhost/jsondb"
        assert result["api_key"] == "json-api-key"
        assert result["debug"] is False

    def test_explicit_missing_file_is_an_error(
        self, tmp_path: Path, clean_env: None
    ) -> None:
        """Test that an explicitly configured missing file is visible.

        :param tmp_path: Pytest temporary directory
        :param clean_env: Fixture that cleans environment
        """
        # Point to directory without config.json
        os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        with pytest.raises(JSONFileNotFoundError):
            source()

    def test_invalid_json_error(self, tmp_path: Path, clean_env: None) -> None:
        """Test that invalid JSON logs error.

        :param tmp_path: Pytest temporary directory
        :param clean_env: Fixture that cleans environment
        """
        # Create invalid JSON file
        invalid_json = tmp_path / "config.json"
        invalid_json.write_text("{invalid json content")

        os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        with pytest.raises(JSONDecodeError):
            source()

    def test_default_path_package_directory(self, clean_env: None) -> None:
        """Test default path uses package directory.

        :param clean_env: Fixture that cleans environment
        """
        # Don't set PYDANTIC_JSON_PATH

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        result = source()

        # Should try package directory, return empty dict if not found
        assert result == {}

    def test_env_variable_overrides_default(
        self, temp_json_config_dir: Path, clean_env: None
    ) -> None:
        """Test PYDANTIC_JSON_PATH overrides default location.

        :param temp_json_config_dir: Fixture with temp config directory
        :param clean_env: Fixture that cleans environment
        """
        os.environ["PYDANTIC_JSON_PATH"] = str(temp_json_config_dir)

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        result = source()

        # Should load from specified path
        assert "database_url" in result
        assert result["database_url"] == "postgresql://localhost/jsondb"

    def test_get_field_value_existing(
        self, temp_json_config_dir: Path, clean_env: None
    ) -> None:
        """Test get_field_value for existing field.

        :param temp_json_config_dir: Fixture with temp config directory
        :param clean_env: Fixture that cleans environment
        """
        os.environ["PYDANTIC_JSON_PATH"] = str(temp_json_config_dir)

        from pydantic.fields import FieldInfo
        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        source()  # Load config

        field_info = FieldInfo(annotation=str, default=None)
        value, name, is_set = source.get_field_value(field_info, "api_key")

        assert value == "json-api-key"
        assert name == "api_key"
        assert is_set is True

    def test_get_field_value_missing(
        self, temp_json_config_dir: Path, clean_env: None
    ) -> None:
        """Test get_field_value for missing field.

        :param temp_json_config_dir: Fixture with temp config directory
        :param clean_env: Fixture that cleans environment
        """
        os.environ["PYDANTIC_JSON_PATH"] = str(temp_json_config_dir)

        from pydantic.fields import FieldInfo
        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        source()  # Load config

        field_info = FieldInfo(annotation=str, default=None)
        value, name, is_set = source.get_field_value(field_info, "nonexistent")

        assert value is None
        assert name == "nonexistent"
        assert is_set is False

    def test_json_with_nested_types(self, tmp_path: Path, clean_env: None) -> None:
        """Test JSON loading with various data types.

        :param tmp_path: Pytest temporary directory
        :param clean_env: Fixture that cleans environment
        """
        config_data = {
            "string_field": "test",
            "int_field": 42,
            "float_field": 3.14,
            "bool_field": True,
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        result = source()

        assert result["string_field"] == "test"
        assert result["int_field"] == 42
        assert result["float_field"] == 3.14
        assert result["bool_field"] is True

    def test_empty_json_file(self, tmp_path: Path, clean_env: None) -> None:
        """Test loading empty JSON file.

        :param tmp_path: Pytest temporary directory
        :param clean_env: Fixture that cleans environment
        """
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        result = source()

        assert result == {}

    def test_permission_error_handling(
        self, tmp_path: Path, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test handling of permission errors.

        :param tmp_path: Pytest temporary directory
        :param clean_env: Fixture that cleans environment
        """
        config_file = tmp_path / "config.json"
        config_file.write_text('{"test": "value"}')

        os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        monkeypatch.setattr(
            Path,
            "open",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                PermissionError("unsafe operating-system detail")
            ),
        )

        with pytest.raises(JSONPermissionError):
            source()

    def test_non_object_document_is_an_error(
        self, tmp_path: Path, clean_env: None
    ) -> None:
        """A settings document must have a JSON object at its root."""
        (tmp_path / "config.json").write_text('["not", "an", "object"]')
        os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

        from pydantic_settings import BaseSettings

        source = PydanticJSONSource(settings_cls=BaseSettings)
        with pytest.raises(JSONStructureError):
            source()
