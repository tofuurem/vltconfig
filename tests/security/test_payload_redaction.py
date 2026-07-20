"""Payload and planning redaction regression tests."""

import traceback
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from pprint import pformat
from typing import Any

import pytest
from loguru import logger
from pydantic import BaseModel, field_validator, model_validator

from tests.cli.helpers import CLIGateway
from vltconfig import apply_configuration
from vltconfig.cli import EXIT_OK, run
from vltconfig.errors import ConfigurationApplyError
from vltconfig.planning import build_plan, render_configuration_plan
from vltconfig.validation import render_validation_report, validate_payload
from vltconfig.vault_gateway import VersionedSecret


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Capture Loguru messages without changing process-wide configuration."""
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="TRACE")
    try:
        yield messages
    finally:
        logger.remove(sink_id)


def _report_diagnostics(report: object, json_text: str, human_text: str) -> str:
    """Combine common normal and debug representations for one safe object."""
    return "\n".join(
        (str(report), repr(report), pformat(report), json_text, human_text)
    )


@pytest.mark.unit
def test_nested_valid_and_invalid_payload_values_never_reach_output_channels(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Values remain absent from reports, stdout, stderr, logs, and snapshots."""
    valid_canary = "payload-valid-nested-canary"
    invalid_canary = "payload-invalid-validator-canary"

    class Credentials(BaseModel):
        token: str

    class Settings(BaseModel):
        credentials: Credentials
        workers: int
        reject_me: str

        @field_validator("reject_me")
        @classmethod
        def reject_value(cls, value: str) -> str:
            raise ValueError(f"rejected payload {value}")

    report = validate_payload(
        Settings,
        {
            "credentials": {"token": valid_canary},
            "workers": 7,
            "reject_me": invalid_canary,
        },
    )
    json_text = report.to_json()
    human_text = render_validation_report(report)

    with _captured_logs() as messages:
        print(human_text, end="")
        logger.debug("safe validation report: {}", human_text)
    captured = capsys.readouterr()
    diagnostics = "\n".join(
        (
            _report_diagnostics(report, json_text, human_text),
            captured.out,
            captured.err,
            *messages,
        )
    )

    assert report.valid is False
    assert report.findings[0].detail_code == "value_error"
    assert valid_canary not in diagnostics
    assert invalid_canary not in diagnostics


@pytest.mark.unit
def test_non_pydantic_validator_exception_is_converted_without_a_traceback() -> None:
    """Unexpected validator exceptions cannot expose values through debug output."""
    canary = "payload-runtime-exception-canary"

    class Settings(BaseModel):
        token: str

        @model_validator(mode="after")
        def reject_model(self) -> "Settings":
            raise RuntimeError(f"validator failed for {self.token}")

    report = validate_payload(Settings, {"token": canary})
    synthetic_debug = "".join(
        traceback.format_exception(RuntimeError("safe validation boundary"))
    )
    diagnostics = (
        _report_diagnostics(
            report,
            report.to_json(),
            render_validation_report(report),
        )
        + synthetic_debug
    )

    assert report.valid is False
    assert report.findings[0].detail_code == "validator_exception"
    assert canary not in diagnostics


@pytest.mark.unit
def test_current_and_proposed_values_never_reach_plan_channels(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Plan rendering stays redacted even for explicit and ignored replacements."""
    current_canary = "plan-current-nested-canary"
    proposed_canary = "plan-proposed-nested-canary"
    ignored_canary = "plan-ignored-value-canary"

    class Credentials(BaseModel):
        token: str

    class Settings(BaseModel):
        credentials: Credentials
        endpoint: str

    plan = build_plan(
        Settings,
        {
            "credentials": {"token": current_canary},
            "endpoint": "current-endpoint",
        },
        replacement_paths=(("credentials", "token"),),
        proposed_values={
            "credentials": {"token": proposed_canary},
            "endpoint": ignored_canary,
        },
    )
    json_text = plan.to_json()
    human_text = render_configuration_plan(plan)

    with _captured_logs() as messages:
        print(human_text, end="")
        logger.info("safe configuration plan: {}", human_text)
    captured = capsys.readouterr()
    diagnostics = "\n".join(
        (
            _report_diagnostics(plan, json_text, human_text),
            captured.out,
            captured.err,
            *messages,
        )
    )

    for canary in (current_canary, proposed_canary, ignored_canary):
        assert canary not in diagnostics


@dataclass
class _ReplacementGateway:
    """Capture a replacement write while keeping it out of public results."""

    payload: dict[str, Any]
    written: dict[str, Any] | None = None

    def read(self) -> VersionedSecret:
        return VersionedSecret.from_payload(version=3, payload=self.payload)

    def create(self, payload: Mapping[str, Any]) -> None:
        self.written = deepcopy(dict(payload))

    def update(self, payload: Mapping[str, Any], *, version: int) -> None:
        self.written = deepcopy(dict(payload))


@pytest.mark.unit
def test_addressed_apply_result_and_errors_never_expose_values() -> None:
    """Replacement success and validation failure share the redaction boundary."""
    current_canary = "apply-security-current-canary"
    proposed_canary = "apply-security-proposed-canary"
    invalid_canary = "apply-security-invalid-canary"

    class Settings(BaseModel):
        token: str
        workers: int

    gateway = _ReplacementGateway(payload={"token": current_canary, "workers": 2})
    result = apply_configuration(
        Settings,
        gateway,
        replacement_paths=(("token",),),
        proposed_values={"token": proposed_canary},
    )

    invalid_gateway = _ReplacementGateway(
        payload={"token": current_canary, "workers": 2}
    )
    with pytest.raises(ConfigurationApplyError) as captured:
        apply_configuration(
            Settings,
            invalid_gateway,
            replacement_paths=(("workers",),),
            proposed_values={"workers": invalid_canary},
        )

    diagnostics = "\n".join(
        (
            repr(result),
            str(result),
            result.to_json(),
            repr(captured.value),
            str(captured.value),
        )
    )
    for canary in (current_canary, proposed_canary, invalid_canary):
        assert canary not in diagnostics


@pytest.mark.unit
def test_apply_cli_jsonl_and_debug_channels_are_value_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Secret file input stays absent from CLI plan/result events and stderr."""
    current_canary = "apply-cli-security-current-canary"
    proposed_canary = "apply-cli-security-proposed-canary"
    ignored_canary = "apply-cli-security-ignored-canary"
    module_name = "vltconfig_security_apply_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import BaseModel\n"
        "class Settings(BaseModel):\n"
        "    token: str\n"
        "    endpoint: str\n"
    )
    values = tmp_path / "proposed.json"
    values.write_text(
        '{"token":"' + proposed_canary + '","endpoint":"' + ignored_canary + '"}'
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    gateway = CLIGateway(
        payload={"token": current_canary, "endpoint": current_canary},
        version=4,
    )

    status = run(
        [
            "--debug",
            "apply",
            f"{module_name}:Settings",
            "--replace",
            "token",
            "--values-file",
            str(values),
            "--yes",
            "--format",
            "json",
        ],
        gateway_factory=lambda: gateway,
    )
    captured = capsys.readouterr()

    assert status == EXIT_OK
    for canary in (current_canary, proposed_canary, ignored_canary):
        assert canary not in captured.out + captured.err
