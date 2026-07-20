"""Tests for the common vltconfig command foundation."""

import json
import sys
from pathlib import Path

import pytest

from vltconfig.cli import EXIT_OK, EXIT_USAGE, main, run


@pytest.mark.unit
def test_help_is_successful_and_lists_the_workflow(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Root help is concise and exits with the stable success status."""
    status = run(["--help"])
    captured = capsys.readouterr()

    assert status == EXIT_OK
    assert "Schema-driven HashiCorp Vault" in captured.out
    assert captured.err == ""


@pytest.mark.unit
def test_missing_or_unknown_command_uses_exit_three(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI usage errors never collide with validation or Vault failures."""
    assert run([]) == EXIT_USAGE
    missing = capsys.readouterr()
    assert "required: command" in missing.err

    assert run(["unknown"]) == EXIT_USAGE
    unknown = capsys.readouterr()
    assert "invalid choice" in unknown.err
    assert "Traceback" not in missing.err + unknown.err


@pytest.mark.unit
def test_console_entrypoint_imports_a_model_from_the_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An installed script resolves the documented local module reference."""
    module_name = "vltconfig_cli_working_directory_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import BaseModel\n"
        "class Settings(BaseModel):\n"
        "    endpoint: str\n"
    )
    original_import_path = sys.path.copy()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["vltconfig", "template", f"{module_name}:Settings"],
    )

    try:
        assert main() == EXIT_OK
    finally:
        sys.modules.pop(module_name, None)

    assert json.loads(capsys.readouterr().out) == {"endpoint": "__VLTCFG_REQUIRED__"}
    assert sys.path == original_import_path
