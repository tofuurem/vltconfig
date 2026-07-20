"""Tests for raw-payload validation and redacted reports."""

import json
from dataclasses import FrozenInstanceError

import pytest
from pydantic import (
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from vltconfig import VaultJsonConfig
from vltconfig.template import REQUIRED_PLACEHOLDER
from vltconfig.validation import (
    Finding,
    FindingCode,
    Severity,
    ValidationReport,
    render_validation_report,
    sanitize_validation_error,
    validate_payload,
)


@pytest.mark.unit
def test_report_contract_is_immutable_and_json_safe() -> None:
    """Reports contain structural findings only and serialize deterministically."""
    finding = Finding(
        severity=Severity.ERROR,
        code=FindingCode.INVALID_VALUE,
        path=("database", "port"),
        message="value is invalid",
        expected_type="int",
        detail_code="int_parsing",
    )
    report = ValidationReport(
        model_name="example.Settings",
        findings=(finding,),
        validated_fields=2,
    )

    assert report.valid is False
    assert report.error_count == 1
    assert report.warning_count == 0
    assert json.loads(report.to_json()) == report.to_dict()
    assert report.to_dict()["findings"][0]["path"] == "database.port"
    assert "ERROR  database.port  value is invalid (expected int)" in (
        render_validation_report(report)
    )

    attribute = "message"
    with pytest.raises(FrozenInstanceError):
        setattr(finding, attribute, "changed")


@pytest.mark.unit
def test_sanitized_pydantic_report_omits_input_context_and_custom_messages() -> None:
    """Unique payload canaries cannot survive validation-error translation."""
    canary = "validation-report-payload-canary"

    class Settings(BaseModel):
        count: int
        token: str

        @field_validator("token")
        @classmethod
        def reject_token(cls, value: str) -> str:
            raise ValueError(f"custom validator rejected {value}")

    with pytest.raises(ValidationError) as captured:
        Settings.model_validate({"count": canary, "token": canary})

    report = sanitize_validation_error(captured.value, model_name="Settings")
    diagnostics = "\n".join(
        (repr(report), str(report), report.to_json(), render_validation_report(report))
    )

    assert canary not in diagnostics
    assert [finding.path for finding in report.findings] == [("count",), ("token",)]
    assert [finding.detail_code for finding in report.findings] == [
        "int_parsing",
        "value_error",
    ]
    assert all(finding.code is FindingCode.INVALID_VALUE for finding in report.findings)


@pytest.mark.unit
def test_valid_empty_report_has_stable_human_and_json_output() -> None:
    """Successful validation has one concise automation-safe representation."""
    report = ValidationReport(
        model_name="example.Settings",
        findings=(),
        validated_fields=3,
    )

    assert report.valid is True
    assert render_validation_report(report) == "OK     3 fields validated\n"
    assert report.to_dict() == {
        "model": "example.Settings",
        "valid": True,
        "validated_fields": 3,
        "error_count": 0,
        "warning_count": 0,
        "findings": [],
    }


@pytest.mark.unit
def test_validate_payload_checks_raw_data_without_running_settings_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment and custom settings sources cannot fill a missing Vault key."""
    source_calls: list[str] = []

    class Settings(VaultJsonConfig):
        required_token: str

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            source_calls.append("settings-sources-called")
            return (env_settings,)

    monkeypatch.setenv("REQUIRED_TOKEN", "environment-value-canary")

    report = validate_payload(Settings, {})

    assert report.valid is False
    assert source_calls == []
    assert [(finding.code, finding.path) for finding in report.findings] == [
        (FindingCode.MISSING_REQUIRED, ("required_token",))
    ]


@pytest.mark.unit
def test_validate_payload_finds_placeholders_and_invalid_types_once() -> None:
    """Template sentinels take precedence over derivative type errors."""

    class Database(BaseModel):
        port: int

    class Settings(BaseModel):
        database: Database
        workers: int

    report = validate_payload(
        Settings,
        {
            "database": {"port": REQUIRED_PLACEHOLDER},
            "workers": "not-an-integer",
        },
    )

    assert report.valid is False
    assert [(finding.code, finding.path) for finding in report.findings] == [
        (FindingCode.PLACEHOLDER, ("database", "port")),
        (FindingCode.INVALID_VALUE, ("workers",)),
    ]
    assert report.findings[0].expected_type == "int"
    assert report.findings[1].detail_code == "int_parsing"


@pytest.mark.unit
def test_unknown_keys_warn_by_default_and_fail_in_strict_mode() -> None:
    """Unknown fields are visible without changing Pydantic's model policy."""

    class Database(BaseModel):
        model_config = ConfigDict(extra="forbid")
        host: str

    class Settings(BaseModel):
        model_config = ConfigDict(extra="forbid")
        database: Database

    payload = {
        "database": {"host": "db", "legacy_port": 5432},
        "legacy_root": True,
    }

    advisory = validate_payload(Settings, payload)
    strict = validate_payload(Settings, payload, strict=True)

    assert [(finding.path, finding.severity) for finding in advisory.findings] == [
        (("database", "legacy_port"), Severity.WARNING),
        (("legacy_root",), Severity.WARNING),
    ]
    assert advisory.valid is True
    assert all(
        finding.detail_code == "extra_forbidden" for finding in advisory.findings
    )
    assert all(finding.severity is Severity.ERROR for finding in strict.findings)
    assert strict.valid is False


@pytest.mark.unit
def test_alias_paths_collections_and_free_form_mappings_are_understood() -> None:
    """Unknown-key detection follows aliases and nested collection wildcards."""

    class Node(BaseModel):
        address: str

    class Settings(BaseModel):
        token: str = Field(validation_alias=AliasPath("credentials", 0, "token"))
        nodes: list[Node]
        labels: dict[str, str]

    report = validate_payload(
        Settings,
        {
            "credentials": [{"token": "token"}],
            "nodes": [
                {"address": "primary"},
                {"address": "secondary", "retired": True},
            ],
            "labels": {"team": "platform", "tier": "backend"},
        },
    )

    assert [(finding.code, finding.path) for finding in report.findings] == [
        (FindingCode.UNKNOWN_KEY, ("nodes", 1, "retired"))
    ]
    assert report.valid is True


@pytest.mark.unit
def test_valid_payload_reports_the_inspected_schema_field_count() -> None:
    """A clean report identifies how much schema structure was checked."""

    class Nested(BaseModel):
        endpoint: str
        retries: int = 3

    class Settings(BaseModel):
        nested: Nested
        enabled: bool = True

    report = validate_payload(Settings, {"nested": {"endpoint": "service"}})

    assert report.valid is True
    assert report.validated_fields == 4
    assert report.findings == ()
