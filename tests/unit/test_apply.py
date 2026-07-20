"""Tests for additive, CAS-protected Vault apply operations."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import BaseModel

from vltconfig import REQUIRED_PLACEHOLDER, apply_configuration
from vltconfig.errors import (
    ConfigurationApplyError,
    VaultConflictError,
    VaultPathNotFoundError,
)
from vltconfig.vault_gateway import VersionedSecret


@dataclass
class RecordingGateway:
    """In-memory versioned gateway with captured, isolated write calls."""

    payload: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    missing: bool = False
    conflict: bool = False
    write_attempts: int = 0
    create_calls: list[dict[str, Any]] = field(default_factory=list)
    update_calls: list[tuple[dict[str, Any], int]] = field(default_factory=list)

    def read(self) -> VersionedSecret:
        if self.missing:
            raise VaultPathNotFoundError("fake path is missing")
        return VersionedSecret.from_payload(version=self.version, payload=self.payload)

    def create(self, payload: Mapping[str, Any]) -> None:
        self.write_attempts += 1
        if self.conflict:
            raise VaultConflictError("safe create conflict")
        self.create_calls.append(deepcopy(dict(payload)))

    def update(self, payload: Mapping[str, Any], *, version: int) -> None:
        self.write_attempts += 1
        if self.conflict:
            raise VaultConflictError("safe update conflict")
        self.update_calls.append((deepcopy(dict(payload)), version))


@pytest.mark.unit
def test_missing_path_creates_only_required_placeholders() -> None:
    """Initialization uses create-only gateway semantics and omits defaults."""

    class Database(BaseModel):
        host: str
        port: int = 5432

    class Settings(BaseModel):
        database: Database
        token: str
        workers: int = 4

    gateway = RecordingGateway(missing=True)

    result = apply_configuration(Settings, gateway)

    assert gateway.create_calls == [
        {
            "database": {"host": REQUIRED_PLACEHOLDER},
            "token": REQUIRED_PLACEHOLDER,
        }
    ]
    assert gateway.update_calls == []
    assert result.applied is True
    assert result.plan.source_version == 0
    assert result.changed_paths == (("database", "host"), ("token",))


@pytest.mark.unit
def test_existing_payload_is_merged_without_overwrite_or_deletion() -> None:
    """Apply preserves known and unknown values while adding only missing keys."""
    existing_canary = "apply-existing-value-canary"

    class Database(BaseModel):
        host: str
        password: str

    class Settings(BaseModel):
        database: Database
        token: str

    original = {
        "database": {"host": existing_canary},
        "token": existing_canary,
        "legacy": {"preserved": existing_canary},
    }
    gateway = RecordingGateway(payload=deepcopy(original), version=8)

    result = apply_configuration(Settings, gateway)

    assert gateway.create_calls == []
    assert gateway.update_calls == [
        (
            {
                "database": {
                    "host": existing_canary,
                    "password": REQUIRED_PLACEHOLDER,
                },
                "token": existing_canary,
                "legacy": {"preserved": existing_canary},
            },
            8,
        )
    ]
    assert gateway.payload == original
    assert result.changed_paths == (("database", "password"),)
    assert existing_canary not in repr(result)
    assert existing_canary not in result.to_json()


@pytest.mark.unit
def test_complete_payload_is_a_noop() -> None:
    """Apply does not write when every required path is already present."""

    class Settings(BaseModel):
        endpoint: str

    gateway = RecordingGateway(payload={"endpoint": "service"}, version=3)

    result = apply_configuration(Settings, gateway)

    assert result.applied is False
    assert result.changed_paths == ()
    assert gateway.create_calls == []
    assert gateway.update_calls == []


@pytest.mark.unit
def test_incompatible_or_placeholder_payload_blocks_before_mutation() -> None:
    """Apply cannot overwrite an invalid existing value under additive mode."""

    class Settings(BaseModel):
        workers: int

    for payload in ({"workers": "invalid"}, {"workers": REQUIRED_PLACEHOLDER}):
        gateway = RecordingGateway(payload=payload)

        with pytest.raises(ConfigurationApplyError):
            apply_configuration(Settings, gateway)

        assert gateway.create_calls == []
        assert gateway.update_calls == []


@pytest.mark.unit
def test_concurrent_create_or_update_is_not_retried() -> None:
    """A stale plan propagates its safe conflict after exactly one write."""

    class Settings(BaseModel):
        endpoint: str
        token: str

    for gateway in (
        RecordingGateway(missing=True, conflict=True),
        RecordingGateway(payload={"endpoint": "service"}, version=5, conflict=True),
    ):
        with pytest.raises(VaultConflictError):
            apply_configuration(Settings, gateway)

        assert gateway.write_attempts == 1


@pytest.mark.unit
def test_addressed_replacement_changes_only_the_explicit_path() -> None:
    """Extra proposed keys are ignored and every existing value is preserved."""
    current_canary = "apply-replacement-current-canary"
    proposed_canary = "apply-replacement-proposed-canary"
    ignored_canary = "apply-replacement-ignored-canary"

    class Settings(BaseModel):
        token: str
        endpoint: str

    gateway = RecordingGateway(
        payload={"token": current_canary, "endpoint": current_canary},
        version=14,
    )

    result = apply_configuration(
        Settings,
        gateway,
        replacement_paths=(("token",),),
        proposed_values={"token": proposed_canary, "endpoint": ignored_canary},
    )

    assert gateway.update_calls == [
        (
            {"token": proposed_canary, "endpoint": current_canary},
            14,
        )
    ]
    assert result.changed_paths == (("token",),)
    diagnostics = repr(result) + result.to_json()
    assert current_canary not in diagnostics
    assert proposed_canary not in diagnostics
    assert ignored_canary not in diagnostics


@pytest.mark.unit
def test_invalid_replacement_is_rejected_before_vault_mutation() -> None:
    """Pydantic field validation runs against proposed data before CAS write."""
    canary = "apply-invalid-proposed-canary"

    class Settings(BaseModel):
        workers: int

    gateway = RecordingGateway(payload={"workers": 3}, version=2)

    with pytest.raises(ConfigurationApplyError) as captured:
        apply_configuration(
            Settings,
            gateway,
            replacement_paths=(("workers",),),
            proposed_values={"workers": canary},
        )

    assert gateway.write_attempts == 0
    assert canary not in str(captured.value)
    assert canary not in repr(captured.value)


@pytest.mark.unit
def test_replacement_can_repair_an_existing_invalid_field() -> None:
    """An explicitly addressed valid value resolves a blocking type change."""

    class Settings(BaseModel):
        workers: int

    gateway = RecordingGateway(payload={"workers": "invalid"}, version=6)

    result = apply_configuration(
        Settings,
        gateway,
        replacement_paths=(("workers",),),
        proposed_values={"workers": 8},
    )

    assert result.applied is True
    assert gateway.update_calls == [({"workers": 8}, 6)]


@pytest.mark.unit
def test_replacing_a_parent_validates_the_complete_proposed_subtree() -> None:
    """A whole-model replacement cannot omit a newly missing child."""

    class Database(BaseModel):
        host: str
        password: str

    class Settings(BaseModel):
        database: Database

    gateway = RecordingGateway(
        payload={"database": {"host": "db", "password": "old"}},
        version=10,
    )

    with pytest.raises(ConfigurationApplyError):
        apply_configuration(
            Settings,
            gateway,
            replacement_paths=(("database",),),
            proposed_values={"database": {"host": "replacement"}},
        )

    assert gateway.write_attempts == 0


@pytest.mark.unit
def test_expected_preview_version_rejects_a_changed_secret_before_write() -> None:
    """A CLI-approved preview cannot authorize a newly re-read Vault version."""

    class Settings(BaseModel):
        endpoint: str
        token: str

    gateway = RecordingGateway(payload={"endpoint": "service"}, version=9)

    with pytest.raises(VaultConflictError):
        apply_configuration(Settings, gateway, expected_version=8)

    assert gateway.write_attempts == 0
