"""Smoke optional YAML CLI behavior from the built wheel plus named extra."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    """Render YAML with the optional dependency installed explicitly."""
    executable = Path(sys.executable).with_name("vltconfig")
    assert executable.is_file()
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        module_name = "installed_wheel_yaml_settings"
        (workspace / f"{module_name}.py").write_text(
            "from pydantic import BaseModel\n"
            "class Settings(BaseModel):\n"
            "    endpoint: str\n"
        )
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        result = subprocess.run(
            [
                str(executable),
                "template",
                f"{module_name}:Settings",
                "--format",
                "yaml",
            ],
            cwd=workspace,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0
    assert "endpoint: __VLTCFG_REQUIRED__" in result.stdout
    assert result.stderr == ""


if __name__ == "__main__":
    main()
