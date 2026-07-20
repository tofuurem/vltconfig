"""Tests for redacted and strictly read-only Vault planning CLI behavior."""

import json
from pathlib import Path

import pytest

from tests.cli.helpers import CLIGateway
from vltconfig.cli import EXIT_OK, EXIT_VALIDATION, run


@pytest.fixture
def plan_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create an importable model with required and optional fields."""
    module_name = "vltconfig_cli_plan_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import BaseModel\n"
        "class Settings(BaseModel):\n"
        "    endpoint: str\n"
        "    token: str\n"
        "    workers: int = 4\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return f"{module_name}:Settings"


@pytest.mark.unit
def test_plan_is_redacted_read_only_and_reports_source_version(
    plan_model: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Planning additions returns success but never invokes a gateway write."""
    canary = "plan-cli-current-payload-canary"
    gateway = CLIGateway(payload={"endpoint": canary}, version=5)

    status = run(["plan", plan_model], gateway_factory=lambda: gateway)
    captured = capsys.readouterr()

    assert status == EXIT_OK
    assert "token" in captured.out
    assert "add required field" in captured.out
    assert canary not in captured.out + captured.err
    assert gateway.reads == 1
    assert gateway.writes == 0


@pytest.mark.unit
def test_plan_json_is_stable_and_blocking_mismatch_uses_exit_one(
    plan_model: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Machine output carries the version and blocking state without values."""
    gateway = CLIGateway(
        payload={"endpoint": "service", "token": "token", "workers": "invalid"},
        version=8,
    )

    status = run(
        ["plan", plan_model, "--format", "json"],
        gateway_factory=lambda: gateway,
    )
    captured = capsys.readouterr()
    document = json.loads(captured.out)

    assert status == EXIT_VALIDATION
    assert document["source_version"] == 8
    assert document["executable"] is False
    assert "invalid" not in captured.out + captured.err
    assert gateway.writes == 0
