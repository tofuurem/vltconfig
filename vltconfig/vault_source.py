from typing import Any

import hvac
import hvac.exceptions
import requests.exceptions
from loguru import logger
from pydantic import ValidationError
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from vltconfig.auth import VaultAuthenticator, VaultAuthenticatorProtocol
from vltconfig.cache import VaultCache
from vltconfig.config import VaultAccess, vault_environment_present
from vltconfig.errors import (
    VaultAuthenticationError,
    VaultAuthorizationError,
    VaultConfigurationError,
    VaultPathNotFoundError,
    VaultResponseError,
    VaultSourceError,
    VaultUnavailableError,
)
from vltconfig.policy import VaultFailurePolicy
from vltconfig.retry import VaultRetry, VaultRetryProtocol


def _authenticate_vault(cfg: VaultAccess) -> hvac.Client:
    """Compatibility adapter around the isolated production authenticator."""
    return VaultAuthenticator().authenticate(cfg)


class PydanticVaultSource(PydanticBaseSettingsSource):
    """Pydantic settings source that loads configuration from HashiCorp Vault KV v2.

    Retrieves secrets from Vault and makes them available to pydantic-settings.
    Implements caching with configurable TTL to reduce Vault load.
    """

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        *,
        failure_policy: VaultFailurePolicy = VaultFailurePolicy.STRICT,
        authenticator: VaultAuthenticatorProtocol | None = None,
        retry_policy: VaultRetryProtocol | None = None,
        cache: VaultCache | None = None,
    ) -> None:
        """Initialize Vault settings source.

        :param settings_cls: Pydantic settings class
        """
        super().__init__(settings_cls)
        self._result_config: dict[str, Any] = {}
        self._failure_policy = failure_policy
        self._authenticator = authenticator
        self._retry_policy = retry_policy if retry_policy is not None else VaultRetry()
        self._cache = cache if cache is not None else VaultCache.from_environment()

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        """Get field value from loaded Vault secrets.

        :param field: Pydantic field information
        :param field_name: Name of the field to retrieve
        :return: Tuple of (value, field_name, is_set)
        """
        value = self._result_config.get(field_name)
        if value is None:
            return (None, field_name, False)
        return (value, field_name, True)

    def _get_secret_from_vault(self, cfg: VaultAccess) -> None:
        """Fetch secrets from Vault KV v2 store with retry logic.

        Retries up to 3 times with exponential backoff for transient errors:
        - Vault server down
        - Connection errors
        - Timeouts

        Does NOT retry for:
        - Authentication failures
        - Permission errors (Forbidden)
        - Invalid paths

        :raises hvac.exceptions.VaultError: If all retries exhausted or non-retryable error
        """
        client = (
            self._authenticator.authenticate(cfg)
            if self._authenticator is not None
            else _authenticate_vault(cfg)
        )

        logger.trace(
            "Requesting secrets from Vault: path={}, mount={}",
            cfg.app_name,
            cfg.mount_point,
        )

        secret = client.secrets.kv.v2.read_secret_version(
            path=cfg.app_name,
            mount_point=cfg.mount_point,
            raise_on_deleted_version=True,
        )
        self._result_config = secret["data"]["data"]

        logger.info(
            "Successfully loaded {} secrets from Vault", len(self._result_config)
        )

    def _handle_failure(self, error: VaultSourceError) -> dict[str, Any]:
        """Apply the configured strict or explicit fallback failure policy."""
        if self._failure_policy is VaultFailurePolicy.FALLBACK:
            logger.warning(
                "Vault source failed with {}; using explicit fallback policy",
                type(error).__name__,
            )
            return {}
        raise error from None

    @staticmethod
    def _context(cfg: VaultAccess) -> str:
        """Return safe operational context without an address or credentials."""
        return f"mount {cfg.mount_point!r}, path {cfg.app_name!r}"

    def invalidate_cache(self) -> None:
        """Invalidate every entry owned by this source's cache collaborator."""
        self._cache.invalidate()

    def __call__(self) -> dict[str, Any]:
        """Load configuration from Vault with caching support.

        Caches secrets for TTL seconds to reduce Vault load.
        Cache can be disabled via VAULT_CACHE_DISABLED env var.

        If Vault configuration is not available (missing env vars),
        returns empty dict and allows other sources to provide values.

        :return: Dictionary of configuration key-value pairs
        """
        if not vault_environment_present():
            logger.trace("Vault configuration is absent; skipping Vault source")
            return {}

        try:
            cfg = VaultAccess()
        except ValidationError as cause:
            return self._handle_failure(
                VaultConfigurationError(
                    "Vault configuration is partial or invalid",
                    cause_type=type(cause).__name__,
                )
            )

        cache_key = self._cache.key_for(cfg)
        cached_data = self._cache.get(cache_key)
        if cached_data is not None:
            logger.trace(
                "Vault cache hit for path={}, mount={}",
                cfg.app_name,
                cfg.mount_point,
            )
            self._result_config = cached_data
            return self._result_config

        # Load from Vault
        try:
            self._retry_policy.call(lambda: self._get_secret_from_vault(cfg))

            self._cache.put(cache_key, self._result_config)
            logger.trace(
                "Vault response cached for path={}, mount={}",
                cfg.app_name,
                cfg.mount_point,
            )

        except (
            hvac.exceptions.Forbidden,
            hvac.exceptions.Unauthorized,
        ) as cause:
            return self._handle_failure(
                VaultAuthorizationError(
                    f"Vault access was denied for {self._context(cfg)}",
                    cause_type=type(cause).__name__,
                )
            )
        except hvac.exceptions.InvalidPath as cause:
            return self._handle_failure(
                VaultPathNotFoundError(
                    f"Vault secret was not found for {self._context(cfg)}",
                    cause_type=type(cause).__name__,
                )
            )
        except (
            hvac.exceptions.VaultDown,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            ConnectionError,
            TimeoutError,
        ) as cause:
            return self._handle_failure(
                VaultUnavailableError(
                    "Vault is unavailable", cause_type=type(cause).__name__
                )
            )
        except ValueError as cause:
            return self._handle_failure(
                VaultAuthenticationError(
                    "Vault authentication failed",
                    cause_type=type(cause).__name__,
                )
            )
        except ValidationError as cause:
            return self._handle_failure(
                VaultConfigurationError(
                    "Vault configuration became invalid while loading",
                    cause_type=type(cause).__name__,
                )
            )
        except (KeyError, TypeError) as cause:
            return self._handle_failure(
                VaultResponseError(
                    f"Vault returned an invalid response for {self._context(cfg)}",
                    cause_type=type(cause).__name__,
                )
            )
        except hvac.exceptions.VaultError as cause:
            return self._handle_failure(
                VaultUnavailableError(
                    "Vault request failed", cause_type=type(cause).__name__
                )
            )

        return self._result_config
