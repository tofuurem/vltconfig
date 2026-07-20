"""Tests for deterministic template CLI output."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from vltconfig.cli import EXIT_OK, EXIT_USAGE, run


@pytest.fixture
def model_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create one importable model whose constructor records side effects."""
    module_name = "vltconfig_cli_template_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import BaseModel\n"
        "calls = []\n"
        "class Database(BaseModel):\n"
        "    host: str\n"
        "    port: int = 5432\n"
        "class Settings(BaseModel):\n"
        "    database: Database\n"
        "    token: str\n"
        "    workers: int = 4\n"
        "    def __init__(self, **values):\n"
        "        calls.append('constructed')\n"
        "        super().__init__(**values)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return module_name


@pytest.mark.unit
def test_template_json_writes_stdout_without_instantiating_model(
    model_module: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The default command emits only required placeholders as JSON."""
    status = run(["template", f"{model_module}:Settings"])
    captured = capsys.readouterr()
    imported = __import__(model_module)

    assert status == EXIT_OK
    assert json.loads(captured.out) == {
        "database": {"host": "__VLTCFG_REQUIRED__"},
        "token": "__VLTCFG_REQUIRED__",
    }
    assert captured.err == ""
    assert imported.calls == []


@pytest.mark.unit
def test_template_output_file_is_replaced_and_preserves_mode(
    model_module: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Explicit files are replaced completely without partial stdout output."""
    output = tmp_path / "vault-template.json"
    output.write_text("stale")
    output.chmod(0o640)

    status = run(
        [
            "template",
            f"{model_module}:Settings",
            "--include-defaults",
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()

    assert status == EXIT_OK
    assert json.loads(output.read_text()) == {
        "database": {"host": "__VLTCFG_REQUIRED__", "port": 5432},
        "token": "__VLTCFG_REQUIRED__",
        "workers": 4,
    }
    assert output.stat().st_mode & 0o777 == 0o640
    assert captured.out == ""
    assert captured.err == ""
    assert not list(tmp_path.glob(".vault-template.json.*"))


@pytest.mark.unit
def test_yaml_template_and_missing_extra_message_are_actionable(
    model_module: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """YAML works when installed and names the exact extra when unavailable."""
    assert run(["template", f"{model_module}:Settings", "--format", "yaml"]) == EXIT_OK
    rendered = capsys.readouterr()
    assert "database:" in rendered.out
    assert "__VLTCFG_REQUIRED__" in rendered.out

    import vltconfig.template as template_module

    original_import = template_module.importlib.import_module

    def missing_ruamel(name: str) -> object:
        if not name.startswith("ruamel"):
            return original_import(name)
        error = ModuleNotFoundError("optional dependency missing")
        error.name = "ruamel.yaml"
        raise error

    monkeypatch.setattr(template_module.importlib, "import_module", missing_ruamel)

    assert (
        run(["template", f"{model_module}:Settings", "--format", "yaml"]) == EXIT_USAGE
    )
    missing = capsys.readouterr()
    assert "vltconfig[yaml]" in missing.err
    assert "Traceback" not in missing.err


@pytest.mark.unit
def test_invalid_model_and_output_path_are_safe_usage_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Import and filesystem failures return exit three without traceback."""
    assert run(["template", "missing_module:Settings"]) == EXIT_USAGE
    imported = capsys.readouterr()
    assert "Could not import model module" in imported.err

    class Settings(BaseModel):
        token: str

    import vltconfig.cli as cli

    monkeypatch.setattr(cli, "load_model", lambda reference: Settings)
    status = run(
        [
            "template",
            "example:Settings",
            "--output",
            str(tmp_path / "missing" / "output.json"),
        ]
    )
    output = capsys.readouterr()

    assert status == EXIT_USAGE
    assert "Could not write output file" in output.err
    assert "Traceback" not in imported.err + output.err
