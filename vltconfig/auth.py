"""Isolated, injectable authentication for HashiCorp Vault."""

from typing import Protocol

import hvac
import hvac.exceptions
from loguru import logger

from vltconfig.config import VaultAccess


class VaultClientFactory(Protocol):
    """Construct an hvac client for one Vault address."""

    def __call__(self, *, url: str) -> hvac.Client:
        """Return a client connected to ``url``."""
        ...


class VaultAuthenticatorProtocol(Protocol):
    """Authenticate one validated Vault access configuration."""

    def authenticate(self, config: VaultAccess) -> hvac.Client:
        """Return an authenticated client or raise a safe failure."""
        ...


def _create_hvac_client(*, url: str) -> hvac.Client:
    """Build the production hvac client."""
    return hvac.Client(url=url)


class VaultAuthenticator:
    """Try configured Vault authentication methods in stable priority order."""

    def __init__(
        self, client_factory: VaultClientFactory = _create_hvac_client
    ) -> None:
        self._client_factory = client_factory

    def authenticate(self, config: VaultAccess) -> hvac.Client:
        """Authenticate with token, AppRole, then userpass fallback."""
        logger.trace("Starting Vault authentication")
        client = self._client_factory(url=str(config.address))
        failed_methods: list[str] = []

        if config.token:
            logger.trace("Trying token authentication")
            try:
                client.token = config.token.get_secret_value()
                if not client.is_authenticated():
                    raise ValueError("Token authentication was rejected")
                logger.trace("Successfully authenticated with token")
                return client
            except (
                ValueError,
                hvac.exceptions.Forbidden,
                hvac.exceptions.Unauthorized,
            ):
                failed_methods.append("token")
                logger.trace(
                    "Token authentication failed; trying next configured method"
                )

        if config.role_id and config.secret_id:
            logger.trace("Trying AppRole authentication")
            try:
                response = client.auth.approle.login(
                    role_id=config.role_id.get_secret_value(),
                    secret_id=config.secret_id.get_secret_value(),
                )
                client.token = response["auth"]["client_token"]
                logger.trace("Successfully authenticated with AppRole")
                return client
            except (
                hvac.exceptions.InvalidRequest,
                hvac.exceptions.Forbidden,
                hvac.exceptions.Unauthorized,
            ):
                failed_methods.append("AppRole")
                logger.trace(
                    "AppRole authentication failed; trying next configured method"
                )

        if config.username and config.password:
            logger.trace("Trying userpass authentication")
            try:
                response = client.auth.userpass.login(
                    username=config.username,
                    password=config.password.get_secret_value(),
                )
                client.token = response["auth"]["client_token"]
                logger.trace("Successfully authenticated with userpass")
                return client
            except (
                hvac.exceptions.InvalidRequest,
                hvac.exceptions.Forbidden,
                hvac.exceptions.Unauthorized,
            ):
                failed_methods.append("userpass")
                logger.trace("Userpass authentication failed")

        if failed_methods:
            methods = ", ".join(failed_methods)
            raise ValueError(f"All authentication methods failed ({methods})")
        raise ValueError("No authentication method configured")
