"""Typed fake Vault gateway for CLI tests."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from vltconfig.errors import VaultSourceError
from vltconfig.vault_gateway import VersionedSecret


@dataclass
class CLIGateway:
    """Capture read/write activity without relying on environment state."""

    payload: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    read_error: VaultSourceError | None = None
    reads: int = 0
    writes: int = 0
    written_payload: dict[str, Any] | None = None
    written_version: int | None = None

    def read(self) -> VersionedSecret:
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        return VersionedSecret.from_payload(version=self.version, payload=self.payload)

    def create(self, payload: Mapping[str, Any]) -> None:
        self.writes += 1
        self.written_payload = deepcopy(dict(payload))
        self.written_version = 0

    def update(self, payload: Mapping[str, Any], *, version: int) -> None:
        self.writes += 1
        self.written_payload = deepcopy(dict(payload))
        self.written_version = version
