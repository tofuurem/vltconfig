import os
from datetime import datetime, timedelta
from typing import Any, ClassVar

from loguru import logger
from pydantic.fields import FieldInfo
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

import hvac

from vltconfig.config import VaultAccess


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log retry attempt details.

    :param retry_state: Current retry state information
    """
    logger.warning(
        "Retrying after error: {} (attempt {}/{})",
        retry_state.outcome.exception() if retry_state.outcome else "unknown",
        retry_state.attempt_number,
        3,  # max attempts
    )


def _authenticate_vault(cfg: VaultAccess) -> hvac.Client:
    """Authenticate to Vault using configured method with fallback support.

    Tries authentication methods in priority order, falling back to next method if current fails:
    1. Token authentication (VAULT_TOKEN)
    2. AppRole authentication (VAULT_ROLE_ID + VAULT_SECRET_ID)
    3. Username/Password authentication (VAULT_USERNAME + VAULT_PASSWORD)

    If multiple methods are configured and one fails, the next available method is tried.
    This provides resilience if one authentication method is temporarily unavailable.

    :param cfg: Vault configuration with credentials
    :return: Authenticated hvac Client instance
    :raises ValueError: If all configured authentication methods fail
    """
    logger.trace("Starting Vault authentication to {}", cfg.address)
    client = hvac.Client(url=str(cfg.address))
    errors: list[str] = []

    # Try token authentication
    if cfg.token:
        logger.trace("Trying token authentication")
        try:
            client.token = cfg.token
            if not client.is_authenticated():
                raise ValueError("Token is invalid or expired")
            logger.trace("Successfully authenticated with token")
            return client
        except (
            ValueError,
            hvac.exceptions.Forbidden,
            hvac.exceptions.Unauthorized,
        ) as ex:
            error_msg = f"Token auth failed: {ex}"
            errors.append(error_msg)
            logger.trace("Token authentication failed, trying next method: {}", ex)

    # Try AppRole authentication
    if cfg.role_id and cfg.secret_id:
        logger.trace("Trying AppRole authentication")
        try:
            resp = client.auth.approle.login(
                role_id=cfg.role_id, secret_id=cfg.secret_id
            )
            client.token = resp["auth"]["client_token"]
            logger.trace("Successfully authenticated with AppRole")
            return client
        except (hvac.exceptions.InvalidRequest, hvac.exceptions.Forbidden) as ex:
            error_msg = f"AppRole auth failed: {ex}"
            errors.append(error_msg)
            logger.trace("AppRole authentication failed, trying next method: {}", ex)

    # Try userpass authentication
    if cfg.username and cfg.password:
        logger.trace("Trying userpass authentication")
        try:
            resp = client.auth.userpass.login(
                username=cfg.username, password=cfg.password
            )
            client.token = resp["auth"]["client_token"]
            logger.trace("Successfully authenticated with userpass")
            return client
        except (hvac.exceptions.InvalidRequest, hvac.exceptions.Forbidden) as ex:
            error_msg = f"Userpass auth failed: {ex}"
            errors.append(error_msg)
            logger.trace("Userpass authentication failed: {}", ex)

    # All methods failed
    if errors:
        combined_errors = "; ".join(errors)
        raise ValueError(f"All authentication methods failed: {combined_errors}")
    else:
        raise ValueError("No authentication method configured")


class PydanticVaultSource(PydanticBaseSettingsSource):
    """Pydantic settings source that loads configuration from HashiCorp Vault KV v2.

    Retrieves secrets from Vault and makes them available to pydantic-settings.
    Implements caching with configurable TTL to reduce Vault load.
    """

    _cache: ClassVar[dict[str, tuple[dict[str, Any], datetime]]] = {}
    _cache_ttl_seconds: ClassVar[int] = 300  # 5 minutes default
    _cache_enabled: ClassVar[bool] = True

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        """Initialize Vault settings source.

        :param settings_cls: Pydantic settings class
        """
        super().__init__(settings_cls)
        self._result_config: dict[str, str | int | float | bool] = {}

        # Allow disabling cache via environment variable
        cache_disabled = os.getenv("VAULT_CACHE_DISABLED", "").lower() in (
            "true",
            "1",
            "yes",
        )
        if cache_disabled:
            PydanticVaultSource._cache_enabled = False

        # Allow custom TTL via environment variable
        cache_ttl = os.getenv("VAULT_CACHE_TTL")
        if cache_ttl and cache_ttl.isdigit():
            PydanticVaultSource._cache_ttl_seconds = int(cache_ttl)

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (
                hvac.exceptions.VaultDown,
                ConnectionError,
                TimeoutError,
            )
        ),
        before_sleep=_log_retry_attempt,
        reraise=True,
    )
    def _get_secret_from_vault(self) -> None:
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
        cfg = VaultAccess()  # type: ignore[call-arg]
        client = _authenticate_vault(cfg)

        logger.trace(
            "Requesting secrets from Vault: path={}, mount={}",
            cfg.app_name,
            cfg.mount_point,
        )

        secret = client.secrets.kv.v2.read_secret_version(
            path=cfg.app_name, mount_point=cfg.mount_point
        )
        self._result_config = secret["data"]["data"]

        logger.info(
            "Successfully loaded {} secrets from Vault", len(self._result_config)
        )

    def __call__(self) -> dict[str, str | int | float | bool]:
        """Load configuration from Vault with caching support.

        Caches secrets for TTL seconds to reduce Vault load.
        Cache can be disabled via VAULT_CACHE_DISABLED env var.

        If Vault configuration is not available (missing env vars),
        returns empty dict and allows other sources to provide values.

        :return: Dictionary of configuration key-value pairs
        """
        # Try to create VaultAccess configuration
        try:
            cfg = VaultAccess()  # type: ignore[call-arg]
        except Exception as ex:
            # Vault configuration not available (missing env vars or validation error)
            logger.trace(
                "Vault configuration not available, skipping Vault source: {}", ex
            )
            return self._result_config

        cache_key = f"{cfg.address}:{cfg.app_name}:{cfg.mount_point}"

        # Check cache if enabled
        if self._cache_enabled and cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            age = datetime.now() - timestamp

            if age < timedelta(seconds=self._cache_ttl_seconds):
                logger.trace(
                    "Cache hit for {} (age: {}s, TTL: {}s)",
                    cache_key,
                    int(age.total_seconds()),
                    self._cache_ttl_seconds,
                )
                self._result_config = cached_data
                return self._result_config
            else:
                logger.trace(
                    "Cache expired for {} (age: {}s > TTL: {}s)",
                    cache_key,
                    int(age.total_seconds()),
                    self._cache_ttl_seconds,
                )

        # Load from Vault
        try:
            self._get_secret_from_vault()

            # Store in cache if enabled
            if self._cache_enabled:
                self._cache[cache_key] = (self._result_config.copy(), datetime.now())
                logger.trace(
                    "Cached secrets for {} (TTL: {}s)",
                    cache_key,
                    self._cache_ttl_seconds,
                )

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
