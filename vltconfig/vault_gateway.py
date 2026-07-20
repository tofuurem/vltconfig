"""Typed, version-aware boundary for HashiCorp Vault KV v2."""

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

import hvac
import hvac.exceptions
import requests.exceptions

from vltconfig.auth import VaultAuthenticator, VaultAuthenticatorProtocol
from vltconfig.config import VaultAccess
from vltconfig.errors import (
    VaultAuthenticationError,
    VaultAuthorizationError,
    VaultConflictError,
    VaultPathNotFoundError,
    VaultResponseError,
    VaultUnavailableError,
)
from vltconfig.retry import VaultRetry, VaultRetryProtocol

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class VersionedSecret:
    """A KV payload and version whose representation is always redacted."""

    version: int
    _payload: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(
        cls,
        *,
        version: int,
        payload: Mapping[str, Any],
    ) -> "VersionedSecret":
        """Construct an isolated secret result for adapters and test fakes."""
        return cls(version=version, _payload=deepcopy(dict(payload)))

    def copy_data(self) -> dict[str, Any]:
        """Return an isolated copy for the shortest possible processing scope."""
        return deepcopy(self._payload)


class VersionedVaultGateway(Protocol):
    """Minimal Vault KV v2 operations required by the workflow."""

    def read(self) -> VersionedSecret:
        """Read the current payload and its KV v2 version."""
        ...

    def create(self, payload: Mapping[str, Any]) -> None:
        """Create a path only when no prior version exists."""
        ...

    def update(self, payload: Mapping[str, Any], *, version: int) -> None:
        """Replace a payload only when its current version matches ``version``."""
        ...


class HvacVaultGateway:
    """Production Vault gateway backed by an authenticated HVAC client."""

    def __init__(
        self,
        access: VaultAccess,
        *,
        authenticator: VaultAuthenticatorProtocol | None = None,
        retry_policy: VaultRetryProtocol | None = None,
    ) -> None:
        self._access = access
        self._authenticator = authenticator or VaultAuthenticator()
        self._retry_policy = retry_policy or VaultRetry()
        self._authenticated_client: hvac.Client | None = None

    def _context(self) -> str:
        """Return safe path context without address or credentials."""
        return f"mount {self._access.mount_point!r}, path {self._access.app_name!r}"

    def _client(self) -> hvac.Client:
        """Authenticate lazily and reuse the client for this gateway instance."""
        if self._authenticated_client is None:
            try:
                self._authenticated_client = self._retry_policy.call(
                    lambda: self._authenticator.authenticate(self._access)
                )
            except (
                hvac.exceptions.VaultDown,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                ConnectionError,
                TimeoutError,
            ) as cause:
                raise VaultUnavailableError(
                    "Vault is unavailable",
                    cause_type=type(cause).__name__,
                ) from None
            except (
                ValueError,
                KeyError,
                TypeError,
                hvac.exceptions.VaultError,
            ) as cause:
                raise VaultAuthenticationError(
                    "Vault authentication failed",
                    cause_type=type(cause).__name__,
                ) from None
        return self._authenticated_client

    def _request(
        self,
        operation: Callable[[], ResultT],
        *,
        write: bool,
    ) -> ResultT:
        """Execute and translate one HVAC operation without upstream messages."""
        try:
            return self._retry_policy.call(operation)
        except (hvac.exceptions.Forbidden, hvac.exceptions.Unauthorized) as cause:
            raise VaultAuthorizationError(
                f"Vault access was denied for {self._context()}",
                cause_type=type(cause).__name__,
            ) from None
        except hvac.exceptions.InvalidPath as cause:
            raise VaultPathNotFoundError(
                f"Vault secret was not found for {self._context()}",
                cause_type=type(cause).__name__,
            ) from None
        except hvac.exceptions.InvalidRequest as cause:
            if write:
                raise VaultConflictError(
                    "Vault rejected the write because the secret version changed; "
                    "read and plan again",
                    cause_type=type(cause).__name__,
                ) from None
            raise VaultResponseError(
                f"Vault rejected the read for {self._context()}",
                cause_type=type(cause).__name__,
            ) from None
        except (
            hvac.exceptions.VaultDown,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            ConnectionError,
            TimeoutError,
        ) as cause:
            raise VaultUnavailableError(
                "Vault is unavailable",
                cause_type=type(cause).__name__,
            ) from None
        except (ValueError, KeyError, TypeError) as cause:
            raise VaultResponseError(
                f"Vault returned an invalid response for {self._context()}",
                cause_type=type(cause).__name__,
            ) from None
        except hvac.exceptions.VaultError as cause:
            raise VaultUnavailableError(
                "Vault request failed",
                cause_type=type(cause).__name__,
            ) from None

    def read(self) -> VersionedSecret:
        """Read and narrow one KV v2 payload and version."""
        client = self._client()
        response = self._request(
            lambda: client.secrets.kv.v2.read_secret_version(
                path=self._access.app_name,
                mount_point=self._access.mount_point,
                raise_on_deleted_version=True,
            ),
            write=False,
        )
        try:
            envelope = response["data"]
            payload = envelope["data"]
            metadata = envelope["metadata"]
            version = metadata["version"]
            if not isinstance(payload, Mapping):
                raise TypeError
            if not all(isinstance(key, str) for key in payload):
                raise TypeError
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise TypeError
            copied_payload = deepcopy(dict(payload))
        except Exception as cause:
            raise VaultResponseError(
                f"Vault returned an invalid response for {self._context()}",
                cause_type=type(cause).__name__,
            ) from None
        return VersionedSecret(version=version, _payload=copied_payload)

    def _write(self, payload: Mapping[str, Any], *, cas: int) -> None:
        """Write one isolated payload with an exact KV v2 CAS value."""
        try:
            copied_payload = deepcopy(dict(payload))
            if not all(isinstance(key, str) for key in copied_payload):
                raise TypeError
        except Exception as cause:
            raise VaultResponseError(
                "Vault payload could not be prepared safely",
                cause_type=type(cause).__name__,
            ) from None
        client = self._client()
        self._request(
            lambda: client.secrets.kv.v2.create_or_update_secret(
                path=self._access.app_name,
                secret=copied_payload,
                mount_point=self._access.mount_point,
                cas=cas,
            ),
            write=True,
        )

    def create(self, payload: Mapping[str, Any]) -> None:
        """Create the configured path using KV v2 create-only semantics."""
        self._write(payload, cas=0)

    def update(self, payload: Mapping[str, Any], *, version: int) -> None:
        """Update the configured path only at the caller-approved version."""
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer")
        self._write(payload, cas=version)
