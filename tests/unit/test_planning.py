"""Tests for immutable, value-free configuration change plans."""

import json
from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel, Field

from vltconfig.planning import (
    ChangeCategory,
    ConfigurationPlan,
    PlanChange,
    build_plan,
    render_configuration_plan,
)
from vltconfig.validation import Severity


@pytest.mark.unit
def test_plan_classifies_schema_changes_without_deletions() -> None:
    """Missing, optional, unknown, and incompatible fields remain structural."""

    class Database(BaseModel):
        host: str
        port: int = 5432

    class Settings(BaseModel):
        database: Database
        token: str
        workers: int = 4

    plan = build_plan(
        Settings,
        {
            "database": {"host": "db", "retired": True},
            "token": 123,
            "legacy": "kept",
        },
    )

    assert [change.category for change in plan.changes] == [
        ChangeCategory.OPTIONAL_NO_CHANGE,
        ChangeCategory.UNKNOWN_KEY,
        ChangeCategory.UNKNOWN_KEY,
        ChangeCategory.TYPE_CHANGE,
        ChangeCategory.OPTIONAL_NO_CHANGE,
    ]
    assert [change.path for change in plan.changes] == [
        ("database", "port"),
        ("database", "retired"),
        ("legacy",),
        ("token",),
        ("workers",),
    ]
    assert plan.executable is False
    assert "delete" not in plan.to_json().lower()


@pytest.mark.unit
def test_plan_marks_missing_required_fields_as_safe_additions() -> None:
    """Initialization additions are actionable without embedding a value."""

    class Settings(BaseModel):
        endpoint: str
        retries: int = 3

    plan = build_plan(Settings, {})

    assert [
        (change.category, change.path, change.expected_type) for change in plan.changes
    ] == [
        (ChangeCategory.ADD_REQUIRED, ("endpoint",), "str"),
        (ChangeCategory.OPTIONAL_NO_CHANGE, ("retries",), "int"),
    ]
    assert plan.executable is True
    assert plan.write_count == 1


@pytest.mark.unit
def test_explicit_replacement_uses_separate_values_without_retaining_them() -> None:
    """A replacement plan records permission and shape, never either value."""
    current_canary = "planning-current-value-canary"
    proposed_canary = "planning-proposed-value-canary"

    class Settings(BaseModel):
        token: str
        endpoint: str

    plan = build_plan(
        Settings,
        {"token": current_canary, "endpoint": "service"},
        replacement_paths=(("token",),),
        proposed_values={"token": proposed_canary},
    )
    rendered = "\n".join(
        (repr(plan), str(plan), plan.to_json(), render_configuration_plan(plan))
    )

    assert [(change.category, change.path) for change in plan.changes] == [
        (ChangeCategory.REPLACE, ("token",))
    ]
    assert plan.executable is True
    assert current_canary not in rendered
    assert proposed_canary not in rendered


@pytest.mark.unit
def test_extra_proposed_values_are_ignored_with_a_warning() -> None:
    """A proposed value grants no implicit permission to replace its key."""

    class Settings(BaseModel):
        token: str
        endpoint: str

    plan = build_plan(
        Settings,
        {"token": "old", "endpoint": "service"},
        replacement_paths=(("token",),),
        proposed_values={"token": "new", "endpoint": "must-be-ignored"},
    )

    assert [
        (change.category, change.path, change.severity) for change in plan.changes
    ] == [
        (ChangeCategory.PROPOSED_VALUE_IGNORED, ("endpoint",), Severity.WARNING),
        (ChangeCategory.REPLACE, ("token",), Severity.INFO),
    ]
    assert plan.executable is True
    assert plan.warning_count == 1


@pytest.mark.unit
def test_missing_or_undeclared_replacement_values_block_execution() -> None:
    """Every replacement needs both schema membership and an addressed value."""

    class Settings(BaseModel):
        token: str

    plan = build_plan(
        Settings,
        {"token": "old"},
        replacement_paths=(("token",), ("not_declared",)),
        proposed_values={},
    )

    assert [(change.category, change.path) for change in plan.changes] == [
        (ChangeCategory.REPLACEMENT_NOT_DECLARED, ("not_declared",)),
        (ChangeCategory.REPLACEMENT_VALUE_MISSING, ("token",)),
    ]
    assert plan.executable is False
    assert plan.error_count == 2


@pytest.mark.unit
def test_aliases_and_mapping_replacements_are_matched_structurally() -> None:
    """An explicit mapping replacement covers its nested proposed values."""

    class Settings(BaseModel):
        api_token: str = Field(validation_alias="token")
        labels: dict[str, str]

    plan = build_plan(
        Settings,
        {"token": "old", "labels": {"team": "old"}},
        replacement_paths=(("token",), ("labels",)),
        proposed_values={"token": "new", "labels": {"team": "new"}},
    )

    assert [change.category for change in plan.changes] == [
        ChangeCategory.REPLACE,
        ChangeCategory.REPLACE,
    ]
    assert plan.warning_count == 0


@pytest.mark.unit
def test_plan_contract_is_frozen_and_has_stable_serialization() -> None:
    """Automation receives deterministic metadata and summary counts."""
    change = PlanChange(
        category=ChangeCategory.ADD_REQUIRED,
        severity=Severity.INFO,
        path=("token",),
        expected_type="str",
        message="required field will be initialized",
        executable=True,
    )
    plan = ConfigurationPlan(model_name="example.Settings", changes=(change,))

    assert json.loads(plan.to_json()) == plan.to_dict()
    assert render_configuration_plan(plan) == (
        "INFO   token  add required field (expected str)\n"
        "READY  1 write, 0 warnings, 0 errors\n"
    )
    attribute = "message"
    with pytest.raises(FrozenInstanceError):
        setattr(change, attribute, "changed")
