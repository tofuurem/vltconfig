"""Tests for sanitized schema and reference CLI output."""

import json
from pathlib import Path

import pytest

from vltconfig.cli import EXIT_OK, run


@pytest.fixture
def schema_model_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create one model with descriptions, constraints, and secret metadata."""
    module_name = "vltconfig_cli_schema_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import BaseModel, Field, SecretStr\n"
        "class Settings(BaseModel):\n"
        "    endpoint: str = Field(description='Service endpoint')\n"
        "    workers: int = Field(default=4, ge=1)\n"
        "    token: SecretStr = Field(examples=['schema-cli-secret-canary'])\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return module_name


@pytest.mark.unit
def test_schema_json_is_sanitized_and_deterministic(
    schema_model_module: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """JSON Schema contains field metadata but no defaults or secret examples."""
    reference = f"{schema_model_module}:Settings"

    assert run(["schema", reference]) == EXIT_OK
    first = capsys.readouterr()
    assert run(["schema", reference, "--format", "json"]) == EXIT_OK
    second = capsys.readouterr()

    document = json.loads(first.out)
    assert first.out == second.out
    assert document["$schema"].endswith("2020-12/schema")
    assert "schema-cli-secret-canary" not in first.out
    assert '"default"' not in first.out


@pytest.mark.unit
def test_markdown_reference_can_be_written_to_a_new_private_file(
    schema_model_module: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Markdown output uses the same schema and defaults to mode 0600."""
    output = tmp_path / "configuration.md"

    status = run(
        [
            "schema",
            f"{schema_model_module}:Settings",
            "--format",
            "markdown",
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()

    assert status == EXIT_OK
    assert output.read_text().startswith("# Configuration reference\n")
    assert "Service endpoint" in output.read_text()
    assert "schema-cli-secret-canary" not in output.read_text()
    assert output.stat().st_mode & 0o777 == 0o600
    assert captured.out == ""
    assert captured.err == ""
