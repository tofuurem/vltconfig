"""Tests for public configuration check and planning operations."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import BaseModel

from vltconfig import check_configuration, plan_configuration
from vltconfig.errors import VaultPathNotFoundError
from vltconfig.planning import ChangeCategory
from vltconfig.vault_gateway import VersionedSecret


@dataclass
class FakeGateway:
    """Small in-memory gateway proving operations have no hidden state."""

    payload: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    missing: bool = False
    read_calls: int = 0
    write_calls: int = 0

    def read(self) -> VersionedSecret:
        self.read_calls += 1
        if self.missing:
            raise VaultPathNotFoundError("fake path is missing")
        return VersionedSecret.from_payload(version=self.version, payload=self.payload)

    def create(self, payload: Mapping[str, Any]) -> None:
        self.write_calls += 1

    def update(self, payload: Mapping[str, Any], *, version: int) -> None:
        self.write_calls += 1


class Settings(BaseModel):
    """Shared schema for pure operation tests."""

    endpoint: str
    workers: int = 4


@pytest.mark.unit
def test_check_returns_the_exact_version_and_redacted_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Check reads once and returns data without printing or writing."""
    canary = "operation-check-payload-canary"
    gateway = FakeGateway(payload={"endpoint": canary}, version=9)

    result = check_configuration(Settings, gateway)
    captured = capsys.readouterr()

    assert result.version == 9
    assert result.valid is True
    assert gateway.read_calls == 1
    assert gateway.write_calls == 0
    assert captured.out == ""
    assert captured.err == ""
    assert canary not in repr(result)
    assert canary not in result.to_json()


@pytest.mark.unit
def test_check_strictness_is_forwarded_to_raw_validation() -> None:
    """Strict check turns unknown keys into validation errors."""
    gateway = FakeGateway(payload={"endpoint": "service", "retired": True})

    advisory = check_configuration(Settings, gateway)
    strict = check_configuration(Settings, gateway, strict=True)

    assert advisory.valid is True
    assert strict.valid is False


@pytest.mark.unit
def test_plan_returns_source_version_without_mutating_vault() -> None:
    """Planning composes gateway and schema while remaining read-only."""
    gateway = FakeGateway(payload={}, version=12)

    plan = plan_configuration(Settings, gateway)

    assert plan.source_version == 12
    assert [change.category for change in plan.changes] == [
        ChangeCategory.ADD_REQUIRED,
        ChangeCategory.OPTIONAL_NO_CHANGE,
    ]
    assert gateway.read_calls == 1
    assert gateway.write_calls == 0


@pytest.mark.unit
def test_plan_treats_a_missing_path_as_create_version_zero() -> None:
    """A missing secret can be planned for create-only initialization."""
    gateway = FakeGateway(missing=True)

    plan = plan_configuration(Settings, gateway)

    assert plan.source_version == 0
    assert plan.write_count == 1
    assert gateway.write_calls == 0


@pytest.mark.unit
def test_plan_forwards_only_explicit_replacement_inputs() -> None:
    """The public operation preserves the planning permission boundary."""
    gateway = FakeGateway(payload={"endpoint": "old"}, version=4)

    plan = plan_configuration(
        Settings,
        gateway,
        replacement_paths=(("endpoint",),),
        proposed_values={"endpoint": "new", "workers": 99},
    )

    assert [change.category for change in plan.changes] == [
        ChangeCategory.REPLACE,
        ChangeCategory.OPTIONAL_NO_CHANGE,
        ChangeCategory.PROPOSED_VALUE_IGNORED,
    ]
    assert plan.source_version == 4
