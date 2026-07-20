"""Smoke test executed with the built wheel, outside the source import path."""

import json
import os
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

from vltconfig import VaultJsonConfig


def _run_cli(
    executable: str,
    *arguments: str,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the installed console script outside the repository source path."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [executable, *arguments],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    """Verify public API, metadata, settings loading, and base CLI behavior."""
    assert metadata.version("vltconfig") == os.environ["VLTCONFIG_EXPECTED_VERSION"]
    distribution = metadata.distribution("vltconfig")
    scripts = {
        entry.name: entry.value
        for entry in distribution.entry_points
        if entry.group == "console_scripts"
    }
    assert scripts["vltconfig"] == "vltconfig.cli:main"
    executable = Path(sys.executable).with_name("vltconfig")
    assert executable.is_file()

    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        config_path = workspace / "config.json"
        config_path.write_text(json.dumps({"service_name": "wheel-smoke"}))
        os.environ["PYDANTIC_JSON_PATH"] = directory

        class Settings(VaultJsonConfig):
            service_name: str

        settings = Settings()
        assert settings.service_name == "wheel-smoke"

        module_name = "installed_wheel_settings"
        (workspace / f"{module_name}.py").write_text(
            "from pydantic import BaseModel, Field\n"
            "class Settings(BaseModel):\n"
            "    endpoint: str = Field(description='Service endpoint')\n"
            "    token: str\n"
            "    workers: int = 4\n"
        )
        reference = f"{module_name}:Settings"

        help_result = _run_cli(str(executable), "--help", cwd=workspace)
        assert help_result.returncode == 0
        assert "template" in help_result.stdout
        assert "apply" in help_result.stdout

        template = _run_cli(str(executable), "template", reference, cwd=workspace)
        assert template.returncode == 0
        assert json.loads(template.stdout) == {
            "endpoint": "__VLTCFG_REQUIRED__",
            "token": "__VLTCFG_REQUIRED__",
        }

        schema = _run_cli(str(executable), "schema", reference, cwd=workspace)
        assert schema.returncode == 0
        assert json.loads(schema.stdout)["title"] == "Settings"

        missing_yaml = _run_cli(
            str(executable),
            "template",
            reference,
            "--format",
            "yaml",
            cwd=workspace,
        )
        assert missing_yaml.returncode == 3
        assert "vltconfig[yaml]" in missing_yaml.stderr
        assert "Traceback" not in missing_yaml.stderr


if __name__ == "__main__":
    main()
