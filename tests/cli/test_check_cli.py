"""Tests for redacted Vault check CLI behavior and statuses."""

import json
from pathlib import Path

import pytest

from tests.cli.helpers import CLIGateway
from vltconfig.cli import EXIT_OK, EXIT_VALIDATION, EXIT_VAULT, run
from vltconfig.errors import VaultAuthorizationError


@pytest.fixture
def check_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create an importable constrained model for CLI validation."""
    module_name = "vltconfig_cli_check_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import BaseModel, Field\n"
        "class Settings(BaseModel):\n"
        "    endpoint: str\n"
        "    workers: int = Field(ge=1)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return f"{module_name}:Settings"


@pytest.mark.unit
def test_valid_check_human_and_json_outputs_are_redacted(
    check_model: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Success reports version and structure without values in either format."""
    canary = "check-cli-valid-payload-canary"
    gateway = CLIGateway(payload={"endpoint": canary, "workers": 2}, version=7)

    assert run(["check", check_model], gateway_factory=lambda: gateway) == EXIT_OK
    human = capsys.readouterr()
    assert "VERSION 7" in human.out
    assert "2 fields validated" in human.out

    assert (
        run(
            ["check", check_model, "--format", "json"],
            gateway_factory=lambda: gateway,
        )
        == EXIT_OK
    )
    machine = capsys.readouterr()
    assert json.loads(machine.out)["version"] == 7
    assert canary not in human.out + human.err + machine.out + machine.err


@pytest.mark.unit
def test_validation_mismatch_and_strict_unknown_use_exit_one(
    check_model: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Schema errors use status one while advisory unknown keys remain valid."""
    invalid = CLIGateway(payload={"endpoint": "service", "workers": 0})
    assert (
        run(["check", check_model], gateway_factory=lambda: invalid) == EXIT_VALIDATION
    )
    mismatch = capsys.readouterr()
    assert "ERROR" in mismatch.out

    unknown = CLIGateway(payload={"endpoint": "service", "workers": 2, "retired": True})
    assert run(["check", check_model], gateway_factory=lambda: unknown) == EXIT_OK
    capsys.readouterr()
    assert (
        run(
            ["check", check_model, "--strict"],
            gateway_factory=lambda: unknown,
        )
        == EXIT_VALIDATION
    )
    strict = capsys.readouterr()
    assert "retired" in strict.out


@pytest.mark.unit
def test_vault_failures_use_exit_two_without_upstream_details(
    check_model: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operational access failure is distinct from schema and usage errors."""
    canary = "check-cli-vault-error-canary"
    gateway = CLIGateway(
        read_error=VaultAuthorizationError("Vault access denied", cause_type=canary)
    )

    status = run(
        ["--debug", "check", check_model],
        gateway_factory=lambda: gateway,
    )
    captured = capsys.readouterr()

    assert status == EXIT_VAULT
    assert "Vault access denied" in captured.err
    assert canary not in captured.out + captured.err
    assert "Traceback" in captured.err
