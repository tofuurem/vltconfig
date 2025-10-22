from typing import Type

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
)

from vltconfig.json_source import PydanticJSONSource
from vltconfig.vault_source import PydanticVaultSource


class VaultJsonConfig(BaseSettings):
    """Base settings class that loads configuration from multiple sources.

    Configuration is loaded in the following priority order (highest to lowest):
    1. Environment variables
    2. HashiCorp Vault KV store
    3. JSON file (config.json)
    4. Initialization parameters
    5. .env file
    6. Docker/Kubernetes secrets

    To use, inherit from this class and define your configuration fields:

    Example:
        class AppConfig(VaultJsonConfig):
            database_url: str
            api_key: str
            debug: bool = False
    """

    model_config = SettingsConfigDict(populate_by_name=True)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources and their priority.

        :param settings_cls: The settings class being instantiated
        :param init_settings: Settings from __init__ parameters
        :param env_settings: Settings from environment variables
        :param dotenv_settings: Settings from .env file
        :param file_secret_settings: Settings from Docker/K8s secrets
        :return: Tuple of settings sources in priority order
        """
        return (
            env_settings,
            PydanticVaultSource(settings_cls),
            PydanticJSONSource(settings_cls),
            init_settings,
            dotenv_settings,
            file_secret_settings,
        )


__all__ = ["VaultJsonConfig"]
