import json
import os
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from vltconfig.constants import PYDANTIC_JSON_PATH
from vltconfig.errors import (
    JSONDecodeError,
    JSONFileNotFoundError,
    JSONPermissionError,
    JSONSourceError,
    JSONStructureError,
)


class PydanticJSONSource(PydanticBaseSettingsSource):
    """Pydantic settings source that loads configuration from a JSON file.

    Searches for config.json in the path specified by PYDANTIC_JSON_PATH
    environment variable, or in the package directory if not set.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        """Initialize JSON settings source.

        :param settings_cls: Pydantic settings class
        """
        super().__init__(settings_cls)
        self._result_config: dict[str, Any] = {}

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        """Get field value from loaded JSON configuration.

        :param field: Pydantic field information
        :param field_name: Name of the field to retrieve
        :return: Tuple of (value, field_name, is_set)
        """
        value = self._result_config.get(field_name)
        if value is None:
            return (None, field_name, False)
        return (value, field_name, True)

    @staticmethod
    def _config_path() -> tuple[Path, bool]:
        """Resolve the historical directory-based JSON path contract."""
        path_env = os.getenv(PYDANTIC_JSON_PATH)
        return (
            Path(path_env or os.path.dirname(__file__), "config.json"),
            bool(path_env),
        )

    def __call__(self) -> dict[str, Any]:
        """Load configuration from JSON file.

        :return: Dictionary of configuration key-value pairs
        """
        config_path, explicitly_configured = self._config_path()
        try:
            with config_path.open("r", encoding="utf-8") as config_file:
                document: Any = json.load(config_file)
        except FileNotFoundError as cause:
            if not explicitly_configured:
                logger.trace("Default config.json is absent; skipping JSON source")
                return {}
            raise JSONFileNotFoundError(
                f"JSON configuration file was not found at {config_path}",
                cause_type=type(cause).__name__,
            ) from None
        except PermissionError as cause:
            raise JSONPermissionError(
                f"JSON configuration file is not readable at {config_path}",
                cause_type=type(cause).__name__,
            ) from None
        except (json.JSONDecodeError, UnicodeError) as cause:
            raise JSONDecodeError(
                f"JSON configuration file is malformed at {config_path}",
                cause_type=type(cause).__name__,
            ) from None
        except OSError as cause:
            raise JSONSourceError(
                f"JSON configuration file could not be read at {config_path}",
                cause_type=type(cause).__name__,
            ) from None

        if not isinstance(document, dict):
            raise JSONStructureError(
                f"JSON configuration must contain an object at {config_path}"
            )

        self._result_config = document
        return self._result_config
