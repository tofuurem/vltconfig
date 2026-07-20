"""Command-line adapter for the schema-driven Vault workflow."""

import argparse
import json
import os
import re
import stat
import sys
import tempfile
import traceback
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from vltconfig.config import VaultAccess
from vltconfig.errors import (
    CLIConfirmationError,
    CLIOutputError,
    ConfigurationApplyError,
    ProposedValuesError,
    VaultConfigurationError,
    VaultSourceError,
    VltConfigError,
)
from vltconfig.model_loader import load_model
from vltconfig.operations import (
    apply_configuration,
    check_configuration,
    plan_configuration,
)
from vltconfig.planning import (
    ConfigurationPath,
    ConfigurationPlan,
    render_configuration_plan,
)
from vltconfig.schema_export import render_json_schema, render_markdown_reference
from vltconfig.template import render_json_template, render_yaml_template
from vltconfig.validation import render_validation_report
from vltconfig.vault_gateway import (
    HvacVaultGateway,
    VersionedVaultGateway,
)

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_VAULT = 2
EXIT_USAGE = 3

GatewayFactory = Callable[[], VersionedVaultGateway]
_PATH_SEGMENT = re.compile(r"^(?P<key>[^\[\]]+)(?P<indexes>(?:\[\d+\])*)$")
_PATH_INDEX = re.compile(r"\[(\d+)\]")


class _ParserExit(Exception):
    """Internal control flow carrying an argparse exit status."""

    def __init__(self, status: int) -> None:
        super().__init__()
        self.status = status


class _SafeArgumentParser(argparse.ArgumentParser):
    """Map argparse failures to the CLI's stable usage status."""

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._print_message(message)
        raise _ParserExit(EXIT_OK if status == 0 else EXIT_USAGE)

    def error(self, message: str) -> NoReturn:
        if message.startswith("unrecognized arguments:"):
            message = "unrecognized arguments"
        self.print_usage()
        self.exit(EXIT_USAGE, f"vltconfig: error: {message}\n")


def _parse_configuration_path(value: str) -> ConfigurationPath:
    """Parse dotted keys and non-negative ``[index]`` list components."""
    path: list[str | int] = []
    for segment in value.split("."):
        match = _PATH_SEGMENT.fullmatch(segment)
        if match is None or match.group("key") == "*":
            raise argparse.ArgumentTypeError(
                "replacement paths use dotted keys and optional [index] components"
            )
        path.append(match.group("key"))
        path.extend(int(index) for index in _PATH_INDEX.findall(match.group("indexes")))
    if not path:
        raise argparse.ArgumentTypeError("replacement path cannot be empty")
    return tuple(path)


def build_parser() -> argparse.ArgumentParser:
    """Build the stable root parser without importing application models."""
    parser = _SafeArgumentParser(
        prog="vltconfig",
        description="Schema-driven HashiCorp Vault configuration workflow.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="include safe library traceback context for troubleshooting",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser(
        "template",
        help="render a required-field configuration template",
    )
    template.add_argument("model", help="import reference: <module>:<class>")
    template.add_argument(
        "--format",
        choices=("json", "yaml"),
        default="json",
        help="output format (default: json)",
    )
    template.add_argument(
        "--include-defaults",
        action="store_true",
        help="include static non-secret application defaults",
    )
    template.add_argument(
        "-o",
        "--output",
        type=Path,
        help="atomically replace this file instead of writing stdout",
    )

    schema = commands.add_parser(
        "schema",
        help="render sanitized schema or field reference",
    )
    schema.add_argument("model", help="import reference: <module>:<class>")
    schema.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="output format (default: json)",
    )
    schema.add_argument(
        "-o",
        "--output",
        type=Path,
        help="atomically replace this file instead of writing stdout",
    )

    check = commands.add_parser(
        "check",
        help="validate the raw payload stored in Vault",
    )
    check.add_argument("model", help="import reference: <module>:<class>")
    check.add_argument(
        "--strict",
        action="store_true",
        help="treat unknown Vault keys as validation errors",
    )
    check.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="report format (default: human)",
    )

    plan = commands.add_parser(
        "plan",
        help="preview schema changes without mutating Vault",
    )
    plan.add_argument("model", help="import reference: <module>:<class>")
    plan.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="report format (default: human)",
    )

    apply = commands.add_parser(
        "apply",
        help="apply missing keys and explicitly addressed replacements",
    )
    apply.add_argument("model", help="import reference: <module>:<class>")
    apply.add_argument(
        "--replace",
        action="append",
        type=_parse_configuration_path,
        default=[],
        metavar="PATH",
        help="replace one explicit path (repeatable; e.g. credentials.token)",
    )
    values = apply.add_mutually_exclusive_group()
    values.add_argument(
        "--values-file",
        type=Path,
        help="read proposed replacement values from a JSON file",
    )
    values.add_argument(
        "--values-stdin",
        action="store_true",
        help="read proposed JSON from stdin (recommended for secrets; requires --yes)",
    )
    apply.add_argument(
        "--yes",
        action="store_true",
        help="approve the displayed plan without an interactive prompt",
    )
    apply.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="report format (default: human; json emits event JSONL)",
    )
    return parser


def _atomic_write(path: Path, content: str) -> None:
    """Replace an explicit output file atomically with restrictive permissions."""
    parent = path.parent
    temporary_path: Path | None = None
    try:
        existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary_path, existing_mode)
        os.replace(temporary_path, path)
    except OSError as cause:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise CLIOutputError(
            f"Could not write output file {str(path)!r}",
            cause_type=type(cause).__name__,
        ) from None


def _emit(content: str, output: Path | None) -> None:
    """Write deterministic command output to stdout or one explicit file."""
    if output is None:
        sys.stdout.write(content)
        sys.stdout.flush()
    else:
        _atomic_write(output, content)


def _run_template(arguments: argparse.Namespace) -> int:
    """Render a value-free model template."""
    model = load_model(arguments.model)
    if arguments.format == "yaml":
        rendered = render_yaml_template(
            model,
            include_defaults=arguments.include_defaults,
        )
    else:
        rendered = render_json_template(
            model,
            include_defaults=arguments.include_defaults,
        )
    _emit(rendered, arguments.output)
    return EXIT_OK


def _run_schema(arguments: argparse.Namespace) -> int:
    """Render sanitized JSON Schema or a Markdown field reference."""
    model = load_model(arguments.model)
    rendered = (
        render_markdown_reference(model)
        if arguments.format == "markdown"
        else render_json_schema(model)
    )
    _emit(rendered, arguments.output)
    return EXIT_OK


def _default_gateway_factory() -> VersionedVaultGateway:
    """Build a production gateway from validated Vault environment settings."""
    try:
        access = VaultAccess()
    except ValidationError as cause:
        raise VaultConfigurationError(
            "Vault environment configuration is missing or invalid",
            cause_type=type(cause).__name__,
        ) from None
    return HvacVaultGateway(access)


def _run_check(
    arguments: argparse.Namespace,
    gateway_factory: GatewayFactory,
) -> int:
    """Validate one freshly read Vault payload and render a redacted result."""
    model = load_model(arguments.model)
    result = check_configuration(
        model,
        gateway_factory(),
        strict=arguments.strict,
    )
    rendered = (
        result.to_json() + "\n"
        if arguments.format == "json"
        else f"VERSION {result.version}\n" + render_validation_report(result.report)
    )
    _emit(rendered, None)
    return EXIT_OK if result.valid else EXIT_VALIDATION


def _run_plan(
    arguments: argparse.Namespace,
    gateway_factory: GatewayFactory,
) -> int:
    """Build a redacted, read-only plan for one fresh Vault version."""
    model = load_model(arguments.model)
    plan = plan_configuration(model, gateway_factory())
    rendered = (
        plan.to_json() + "\n"
        if arguments.format == "json"
        else f"VERSION {plan.source_version}\n" + render_configuration_plan(plan)
    )
    _emit(rendered, None)
    return EXIT_OK if plan.executable else EXIT_VALIDATION


def _read_proposed_values(arguments: argparse.Namespace) -> dict[str, Any]:
    """Read one JSON object without echoing its contents or decoder details."""
    if arguments.values_stdin:
        if not arguments.yes:
            raise CLIConfirmationError("--values-stdin requires explicit --yes")
        raw = sys.stdin.read()
        source = "stdin"
    elif arguments.values_file is not None:
        source = str(arguments.values_file)
        try:
            raw = arguments.values_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as cause:
            raise ProposedValuesError(
                f"Could not read proposed values from {source!r}",
                cause_type=type(cause).__name__,
            ) from None
    else:
        return {}

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError, TypeError) as cause:
        raise ProposedValuesError(
            f"Proposed values from {source!r} are not valid JSON",
            cause_type=type(cause).__name__,
        ) from None
    if not isinstance(parsed, Mapping) or not all(
        isinstance(key, str) for key in parsed
    ):
        raise ProposedValuesError(
            f"Proposed values from {source!r} must be a JSON object"
        )
    return dict(parsed)


def _emit_apply_plan(
    arguments: argparse.Namespace,
    plan: ConfigurationPlan,
) -> None:
    """Show the redacted preview before any confirmation or write."""
    if arguments.format == "json":
        _emit(
            json.dumps(
                {"event": "plan", "plan": plan.to_dict()},
                sort_keys=True,
            )
            + "\n",
            None,
        )
    else:
        _emit(
            f"VERSION {plan.source_version}\n" + render_configuration_plan(plan),
            None,
        )


def _confirm_apply(arguments: argparse.Namespace) -> bool:
    """Require explicit automation approval or an affirmative TTY response."""
    if arguments.yes:
        return True
    if not sys.stdin.isatty():
        raise CLIConfirmationError("Non-interactive apply requires explicit --yes")
    sys.stderr.write("Apply this plan? [y/N] ")
    sys.stderr.flush()
    return sys.stdin.readline().strip().casefold() in {"y", "yes"}


def _run_apply(
    arguments: argparse.Namespace,
    gateway_factory: GatewayFactory,
) -> int:
    """Preview, confirm, re-read, and CAS-apply one safe configuration plan."""
    model = load_model(arguments.model)
    proposed_values = _read_proposed_values(arguments)
    replacement_paths = tuple(arguments.replace)
    gateway = gateway_factory()
    plan = plan_configuration(
        model,
        gateway,
        replacement_paths=replacement_paths,
        proposed_values=proposed_values,
    )
    _emit_apply_plan(arguments, plan)
    if not plan.executable:
        return EXIT_VALIDATION
    if plan.write_count == 0:
        if arguments.format == "json":
            _emit('{"event":"noop"}\n', None)
        else:
            _emit("NO CHANGES\n", None)
        return EXIT_OK
    if not _confirm_apply(arguments):
        if arguments.format == "json":
            _emit('{"event":"aborted"}\n', None)
        else:
            _emit("ABORTED\n", None)
        return EXIT_OK

    result = apply_configuration(
        model,
        gateway,
        replacement_paths=replacement_paths,
        proposed_values=proposed_values,
        expected_version=plan.source_version,
    )
    if arguments.format == "json":
        _emit(
            json.dumps(
                {"event": "result", "result": result.to_dict()},
                sort_keys=True,
            )
            + "\n",
            None,
        )
    else:
        noun = "change" if len(result.changed_paths) == 1 else "changes"
        _emit(f"APPLIED {len(result.changed_paths)} {noun}\n", None)
    return EXIT_OK


def _report_cli_error(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    error: VltConfigError,
) -> None:
    """Print a safe error and optional traceback without upstream exception text."""
    parser._print_message(f"vltconfig: {error}\n")
    if arguments.debug:
        traceback.print_exception(error, file=sys.stderr)


def run(
    argv: Sequence[str] | None = None,
    *,
    gateway_factory: GatewayFactory | None = None,
) -> int:
    """Parse CLI input and return a stable process status."""
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
        if arguments.command == "template":
            return _run_template(arguments)
        elif arguments.command == "schema":
            return _run_schema(arguments)
        elif arguments.command == "check":
            return _run_check(
                arguments,
                gateway_factory or _default_gateway_factory,
            )
        elif arguments.command == "plan":
            return _run_plan(
                arguments,
                gateway_factory or _default_gateway_factory,
            )
        elif arguments.command == "apply":
            return _run_apply(
                arguments,
                gateway_factory or _default_gateway_factory,
            )
        else:
            parser.error(f"unknown command: {arguments.command}")
    except _ParserExit as outcome:
        return outcome.status
    except VaultSourceError as error:
        _report_cli_error(parser, arguments, error)
        return EXIT_VAULT
    except ConfigurationApplyError as error:
        _report_cli_error(parser, arguments, error)
        return EXIT_VALIDATION
    except VltConfigError as error:
        _report_cli_error(parser, arguments, error)
        return EXIT_USAGE


def main() -> int:
    """Run from a project directory while preserving the caller's import path."""
    original_import_path = sys.path.copy()
    sys.path.insert(0, str(Path.cwd()))
    try:
        return run()
    finally:
        sys.path[:] = original_import_path
