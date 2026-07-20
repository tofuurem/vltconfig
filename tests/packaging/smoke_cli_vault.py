"""Exercise the installed CLI against one disposable real Vault server."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import hvac


def _run(
    executable: str,
    environment: dict[str, str],
    workspace: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Run one installed CLI command with captured, value-free diagnostics."""
    return subprocess.run(
        [executable, *arguments],
        cwd=workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    """Prove plan/apply/check and no-op semantics through the wheel artifact."""
    address = os.environ["VLTCONFIG_INTEGRATION_VAULT_ADDRESS"]
    root_token = os.environ["VLTCONFIG_INTEGRATION_VAULT_ROOT_TOKEN"]
    executable = Path(sys.executable).with_name("vltconfig")
    assert executable.is_file()

    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        module_name = "installed_wheel_vault_settings"
        (workspace / f"{module_name}.py").write_text(
            "from pydantic import BaseModel\n"
            "class Settings(BaseModel):\n"
            "    endpoint: str\n"
            "    token: str\n"
            "    workers: int = 4\n"
        )
        reference = f"{module_name}:Settings"
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.update(
            {
                "VAULT_ADDRESS": address,
                "VAULT_TOKEN": root_token,
                "VAULT_APP_NAME": "integration/installed-wheel-cli",
                "VAULT_MOUNT_POINT": "secret",
            }
        )

        initial_plan = _run(
            str(executable),
            environment,
            workspace,
            "plan",
            reference,
            "--format",
            "json",
        )
        assert initial_plan.returncode == 0
        assert json.loads(initial_plan.stdout)["source_version"] == 0

        initialized = _run(
            str(executable),
            environment,
            workspace,
            "apply",
            reference,
            "--yes",
            "--format",
            "json",
        )
        assert initialized.returncode == 0
        assert [
            json.loads(line)["event"] for line in initialized.stdout.splitlines()
        ] == ["plan", "result"]

        client = hvac.Client(url=address, token=root_token)
        stored = client.secrets.kv.v2.read_secret_version(
            path="integration/installed-wheel-cli",
            mount_point="secret",
            raise_on_deleted_version=True,
        )
        version = stored["data"]["metadata"]["version"]
        client.secrets.kv.v2.create_or_update_secret(
            path="integration/installed-wheel-cli",
            mount_point="secret",
            cas=version,
            secret={"endpoint": "wheel-service", "token": "wheel-fake-token"},
        )

        checked = _run(
            str(executable),
            environment,
            workspace,
            "check",
            reference,
            "--format",
            "json",
        )
        assert checked.returncode == 0
        assert json.loads(checked.stdout)["validation"]["valid"] is True

        before_plan = client.secrets.kv.v2.read_secret_metadata(
            path="integration/installed-wheel-cli",
            mount_point="secret",
        )["data"]["current_version"]
        final_plan = _run(str(executable), environment, workspace, "plan", reference)
        assert final_plan.returncode == 0
        after_plan = client.secrets.kv.v2.read_secret_metadata(
            path="integration/installed-wheel-cli",
            mount_point="secret",
        )["data"]["current_version"]
        assert after_plan == before_plan

        no_change = _run(
            str(executable),
            environment,
            workspace,
            "apply",
            reference,
            "--yes",
            "--format",
            "json",
        )
        assert no_change.returncode == 0
        assert [
            json.loads(line)["event"] for line in no_change.stdout.splitlines()
        ] == [
            "plan",
            "noop",
        ]
        after_noop = client.secrets.kv.v2.read_secret_metadata(
            path="integration/installed-wheel-cli",
            mount_point="secret",
        )["data"]["current_version"]
        assert after_noop == before_plan


if __name__ == "__main__":
    main()
