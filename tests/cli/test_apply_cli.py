"""Tests for confirmed, addressed, CAS-safe Vault apply CLI behavior."""

import io
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.cli.helpers import CLIGateway
from vltconfig.cli import EXIT_OK, EXIT_USAGE, EXIT_VALIDATION, EXIT_VAULT, run
from vltconfig.errors import VaultConflictError
from vltconfig.vault_gateway import VersionedSecret


@pytest.fixture
def apply_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create an importable model used by apply command tests."""
    module_name = "vltconfig_cli_apply_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import BaseModel\n"
        "class Settings(BaseModel):\n"
        "    endpoint: str\n"
        "    token: str\n"
        "    workers: int = 4\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return f"{module_name}:Settings"


class TTYInput(io.StringIO):
    """String-backed stdin which behaves like an interactive terminal."""

    def isatty(self) -> bool:
        return True


@pytest.mark.unit
def test_noninteractive_apply_requires_yes_after_showing_plan(
    apply_model: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Automation cannot write merely because stdin is non-interactive."""
    gateway = CLIGateway(payload={"endpoint": "service"}, version=3)

    status = run(["apply", apply_model], gateway_factory=lambda: gateway)
    captured = capsys.readouterr()

    assert status == EXIT_USAGE
    assert "add required field" in captured.out
    assert "requires explicit --yes" in captured.err
    assert gateway.reads == 1
    assert gateway.writes == 0


@pytest.mark.unit
@pytest.mark.parametrize(("answer", "expected_writes"), [("n\n", 0), ("yes\n", 1)])
def test_interactive_confirmation_controls_the_write(
    apply_model: str,
    answer: str,
    expected_writes: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only an affirmative TTY response proceeds beyond the preview."""
    gateway = CLIGateway(payload={"endpoint": "service"}, version=4)
    monkeypatch.setattr(sys, "stdin", TTYInput(answer))

    status = run(["apply", apply_model], gateway_factory=lambda: gateway)
    captured = capsys.readouterr()

    assert status == EXIT_OK
    assert "Apply this plan?" in captured.err
    assert gateway.writes == expected_writes
    if expected_writes:
        assert "APPLIED" in captured.out
        assert gateway.reads == 2
    else:
        assert "ABORTED" in captured.out
        assert gateway.reads == 1


@pytest.mark.unit
def test_values_file_changes_only_explicit_replacement_and_redacts_output(
    apply_model: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unlisted proposed keys cannot change Vault and no value reaches output."""
    current_canary = "apply-cli-current-canary"
    proposed_canary = "apply-cli-proposed-canary"
    ignored_canary = "apply-cli-ignored-canary"
    values_file = tmp_path / "proposed.json"
    values_file.write_text(
        json.dumps({"token": proposed_canary, "endpoint": ignored_canary})
    )
    gateway = CLIGateway(
        payload={
            "endpoint": current_canary,
            "token": current_canary,
        },
        version=6,
    )

    status = run(
        [
            "apply",
            apply_model,
            "--replace",
            "token",
            "--values-file",
            str(values_file),
            "--yes",
            "--format",
            "json",
        ],
        gateway_factory=lambda: gateway,
    )
    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.out.splitlines()]

    assert status == EXIT_OK
    assert [event["event"] for event in events] == ["plan", "result"]
    assert gateway.written_payload == {
        "endpoint": current_canary,
        "token": proposed_canary,
    }
    assert gateway.written_version == 6
    for canary in (current_canary, proposed_canary, ignored_canary):
        assert canary not in captured.out + captured.err


@pytest.mark.unit
def test_values_stdin_requires_yes_and_supports_indexed_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Secret-bearing stdin cannot be reused for a confirmation prompt."""
    module_name = "vltconfig_cli_apply_list_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import AliasPath, BaseModel, Field\n"
        "class Settings(BaseModel):\n"
        "    token: str = Field(validation_alias=AliasPath('items', 0, 'token'))\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    reference = f"{module_name}:Settings"
    gateway = CLIGateway(payload={"items": [{"token": "old"}]}, version=2)

    monkeypatch.setattr(sys, "stdin", io.StringIO('{"items":[{"token":"new"}]}'))
    assert (
        run(
            [
                "apply",
                reference,
                "--replace",
                "items[0].token",
                "--values-stdin",
            ],
            gateway_factory=lambda: gateway,
        )
        == EXIT_USAGE
    )
    missing_yes = capsys.readouterr()
    assert "requires explicit --yes" in missing_yes.err
    assert gateway.reads == 0

    monkeypatch.setattr(sys, "stdin", io.StringIO('{"items":[{"token":"new"}]}'))
    assert (
        run(
            [
                "apply",
                reference,
                "--replace",
                "items[0].token",
                "--values-stdin",
                "--yes",
            ],
            gateway_factory=lambda: gateway,
        )
        == EXIT_OK
    )
    capsys.readouterr()
    assert gateway.written_payload == {"items": [{"token": "new"}]}


@pytest.mark.unit
def test_invalid_values_and_inline_set_are_rejected_before_write(
    apply_model: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Malformed documents and shell-visible inline values are usage errors."""
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"token":"secret-canary"')
    gateway = CLIGateway(payload={"endpoint": "service", "token": "old"})

    assert (
        run(
            [
                "apply",
                apply_model,
                "--replace",
                "token",
                "--values-file",
                str(invalid),
                "--yes",
            ],
            gateway_factory=lambda: gateway,
        )
        == EXIT_USAGE
    )
    malformed = capsys.readouterr()
    assert "secret-canary" not in malformed.out + malformed.err
    assert gateway.reads == 0

    assert (
        run(
            ["apply", apply_model, "--set", "token=secret-canary", "--yes"],
            gateway_factory=lambda: gateway,
        )
        == EXIT_USAGE
    )
    inline = capsys.readouterr()
    assert "unrecognized arguments" in inline.err
    assert "secret-canary" not in inline.out + inline.err
    assert gateway.writes == 0


@pytest.mark.unit
def test_invalid_proposed_value_uses_exit_one_without_mutation(
    apply_model: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Schema-invalid replacement data fails before the gateway write."""
    values = tmp_path / "invalid-type.json"
    values.write_text(json.dumps({"workers": "invalid-value-canary"}))
    gateway = CLIGateway(
        payload={"endpoint": "service", "token": "token", "workers": 2},
        version=5,
    )

    status = run(
        [
            "apply",
            apply_model,
            "--replace",
            "workers",
            "--values-file",
            str(values),
            "--yes",
        ],
        gateway_factory=lambda: gateway,
    )
    captured = capsys.readouterr()

    assert status == EXIT_VALIDATION
    assert "invalid-value-canary" not in captured.out + captured.err
    assert gateway.writes == 0


@pytest.mark.unit
def test_cas_conflict_is_safe_exit_two_requiring_a_new_plan(
    apply_model: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A version change between preview and write is never silently re-planned."""

    class ChangingGateway(CLIGateway):
        def read(self) -> VersionedSecret:
            secret = super().read()
            if self.reads == 2:
                self.version += 1
                return type(secret).from_payload(
                    version=self.version,
                    payload=self.payload,
                )
            return secret

    gateway = ChangingGateway(payload={"endpoint": "service"}, version=10)

    status = run(
        ["apply", apply_model, "--yes"],
        gateway_factory=lambda: gateway,
    )
    captured = capsys.readouterr()

    assert status == EXIT_VAULT
    assert "read and plan again" in captured.err
    assert gateway.writes == 0


@pytest.mark.unit
def test_gateway_conflict_error_remains_exit_two(
    apply_model: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A CAS error from the adapter is operational and value-free."""

    class ConflictGateway(CLIGateway):
        def update(
            self,
            payload: Mapping[str, Any],
            *,
            version: int,
        ) -> None:
            raise VaultConflictError("Vault version conflict; read and plan again")

    gateway = ConflictGateway(payload={"endpoint": "service"})
    status = run(
        ["apply", apply_model, "--yes"],
        gateway_factory=lambda: gateway,
    )
    captured = capsys.readouterr()

    assert status == EXIT_VAULT
    assert "read and plan again" in captured.err
