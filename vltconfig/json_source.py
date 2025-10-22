import json
import os
from pathlib import Path

from loguru import logger
from pydantic_settings import PydanticBaseSettingsSource, BaseSettings

from pydantic.fields import FieldInfo

from vltconfig.constants import PYDANTIC_JSON_PATH


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
        self._result_config: dict[str, str | int | float | bool] = {}

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[str | int | float | bool | None, str, bool]:
        """Get field value from loaded JSON configuration.

        :param field: Pydantic field information
        :param field_name: Name of the field to retrieve
        :return: Tuple of (value, field_name, is_set)
        """
        value = self._result_config.get(field_name)
        if value is None:
            return (None, field_name, False)
        return (value, field_name, True)

    def _get_config_from_json(self) -> None:
        """Load configuration from JSON file.

        Reads config.json from PYDANTIC_JSON_PATH or package directory.

        :raises FileNotFoundError: If config.json not found
        :raises json.JSONDecodeError: If JSON is invalid
        """
        path_env = os.getenv(PYDANTIC_JSON_PATH, default=None)
        config_path = Path(path_env or os.path.dirname(__file__), "config.json")

        with config_path.open("r", encoding="utf-8") as f:
            self._result_config = json.load(f)

    def __call__(self) -> dict[str, str | int | float | bool]:
        """Load configuration from JSON file.

        :return: Dictionary of configuration key-value pairs
        """
        try:
            self._get_config_from_json()
        except FileNotFoundError:
            logger.trace("config.json not found, skipping JSON source")
        except json.JSONDecodeError as ex:
            logger.error("Invalid JSON in config.json: {}", ex)
        except Exception as ex:
            logger.error("Error loading JSON config: {}", ex)
        return self._result_config
