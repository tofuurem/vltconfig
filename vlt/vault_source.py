from loguru import logger
from pydantic.fields import FieldInfo

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

import hvac

from vlt.config import VaultAccess


def _auth_by_userpass(cfg: VaultAccess) -> hvac.Client:
    """Authenticate to Vault using token or username/password.

    :param cfg: Vault configuration with credentials
    :return: Authenticated hvac Client instance
    :raises ValueError: If authentication fails
    """
    if cfg.token:
        client = hvac.Client(url=str(cfg.address), token=cfg.token)
        if not client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault token")
        return client
    else:
        client = hvac.Client(url=str(cfg.address))
        resp = client.auth.userpass.login(username=cfg.username, password=cfg.password)
        client.token = resp["auth"]["client_token"]
        return client


class PydanticVaultSource(PydanticBaseSettingsSource):
    """Pydantic settings source that loads configuration from HashiCorp Vault KV v2.

    Retrieves secrets from Vault and makes them available to pydantic-settings.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        """Initialize Vault settings source.

        :param settings_cls: Pydantic settings class
        """
        super().__init__(settings_cls)
        self._result_config: dict[str, str | int | float | bool] = {}

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[str | int | float | bool | None, str, bool]:
        """Get field value from loaded Vault secrets.

        :param field: Pydantic field information
        :param field_name: Name of the field to retrieve
        :return: Tuple of (value, field_name, is_set)
        """
        value = self._result_config.get(field_name)
        if value is None:
            return (None, field_name, False)
        return (value, field_name, True)

    def _get_secret_from_vault(self) -> None:
        """Fetch secrets from Vault KV v2 store.

        :raises hvac.exceptions.VaultError: If Vault request fails
        """
        cfg = VaultAccess()  # type: ignore[call-arg]
        client = _auth_by_userpass(cfg)
        secret = client.secrets.kv.v2.read_secret_version(
            path=cfg.app_name, mount_point=cfg.mount_point
        )
        self._result_config = secret["data"]["data"]

    def __call__(self) -> dict[str, str | int | float | bool]:
        """Load configuration from Vault.

        :return: Dictionary of configuration key-value pairs
        """
        try:
            self._get_secret_from_vault()
        except hvac.exceptions.Forbidden as ex:
            logger.error("Access denied to Vault: {}", ex)
        except hvac.exceptions.InvalidPath as ex:
            logger.error("Path not found in Vault: {}", ex)
        except hvac.exceptions.VaultDown as ex:
            logger.error("Vault server is down: {}", ex)
        except hvac.exceptions.VaultError as ex:
            logger.error("Vault error: {}", ex)
        except (ConnectionError, TimeoutError) as ex:
            logger.error("Network error connecting to Vault: {}", ex)
        except ValueError as ex:
            logger.error("Authentication failed: {}", ex)
        except Exception as ex:
            logger.exception("Unexpected error loading from Vault: {}", ex)
        return self._result_config
