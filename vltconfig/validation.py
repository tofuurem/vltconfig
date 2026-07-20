"""Value-free validation findings for configuration payloads."""

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, get_origin

from pydantic import BaseModel, ValidationError

from vltconfig.schema import FieldSchema, ModelSchema, build_model_schema
from vltconfig.template import REQUIRED_PLACEHOLDER


class Severity(StrEnum):
    """Machine-readable importance assigned to one finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FindingCode(StrEnum):
    """Stable categories emitted by configuration checks."""

    MISSING_REQUIRED = "missing_required"
    PLACEHOLDER = "placeholder"
    UNKNOWN_KEY = "unknown_key"
    INVALID_VALUE = "invalid_value"


PathPart = str | int
SchemaTarget = type[BaseModel] | ModelSchema


def format_path(path: tuple[PathPart, ...]) -> str:
    """Render a structural path without reading the value at that path."""
    if not path:
        return "<root>"
    rendered = ""
    for part in path:
        if isinstance(part, int):
            rendered += f"[{part}]"
        elif rendered:
            rendered += f".{part}"
        else:
            rendered = part
    return rendered


@dataclass(frozen=True, slots=True)
class Finding:
    """One immutable diagnostic which never retains a configuration value."""

    severity: Severity
    code: FindingCode
    path: tuple[PathPart, ...]
    message: str
    expected_type: str | None = None
    detail_code: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Return a deterministic JSON-safe representation."""
        return {
            "severity": self.severity.value,
            "code": self.code.value,
            "path": format_path(self.path),
            "message": self.message,
            "expected_type": self.expected_type,
            "detail_code": self.detail_code,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Immutable result of checking one raw configuration payload."""

    model_name: str
    findings: tuple[Finding, ...]
    validated_fields: int

    @property
    def error_count(self) -> int:
        """Return the number of findings which make the payload invalid."""
        return sum(finding.severity is Severity.ERROR for finding in self.findings)

    @property
    def warning_count(self) -> int:
        """Return the number of advisory findings."""
        return sum(finding.severity is Severity.WARNING for finding in self.findings)

    @property
    def valid(self) -> bool:
        """Return whether validation found no errors."""
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-safe representation."""
        return {
            "model": self.model_name,
            "valid": self.valid,
            "validated_fields": self.validated_fields,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def to_json(self) -> str:
        """Serialize the safe representation for automation."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _safe_location(location: tuple[Any, ...]) -> tuple[PathPart, ...]:
    """Keep only finite field/index components from a Pydantic location."""
    return tuple(part for part in location if isinstance(part, (str, int)))


def sanitize_validation_error(
    error: ValidationError,
    *,
    model_name: str,
) -> ValidationReport:
    """Translate Pydantic errors without retaining inputs, context, or messages."""
    findings = []
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        detail_code = str(item.get("type", "validation_error"))
        missing = detail_code == "missing"
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code=(
                    FindingCode.MISSING_REQUIRED
                    if missing
                    else FindingCode.INVALID_VALUE
                ),
                path=_safe_location(tuple(item.get("loc", ()))),
                message=(
                    "required value is missing" if missing else "value is invalid"
                ),
                detail_code=detail_code,
            )
        )
    return ValidationReport(
        model_name=model_name,
        findings=tuple(findings),
        validated_fields=0,
    )


def _flatten_fields(fields: tuple[FieldSchema, ...]) -> Iterator[FieldSchema]:
    """Yield all schema fields in declaration order."""
    for field in fields:
        yield field
        yield from _flatten_fields(field.children)


def _parts_match(pattern: tuple[PathPart, ...], path: tuple[PathPart, ...]) -> bool:
    """Return whether a complete path matches a schema wildcard pattern."""
    return len(pattern) == len(path) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(pattern, path, strict=True)
    )


def _prefix_matches(pattern: tuple[PathPart, ...], path: tuple[PathPart, ...]) -> bool:
    """Return whether ``path`` is a known prefix of a schema path."""
    return len(path) <= len(pattern) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(pattern, path, strict=False)
    )


def _path_is_below(prefix: tuple[PathPart, ...], path: tuple[PathPart, ...]) -> bool:
    """Return whether a path is inside an unconstrained mapping field."""
    return len(path) > len(prefix) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(prefix, path, strict=False)
    )


def _schema_paths(
    fields: tuple[FieldSchema, ...],
) -> tuple[tuple[tuple[PathPart, ...], ...], tuple[tuple[PathPart, ...], ...]]:
    """Collect accepted field paths and unconstrained mapping roots."""
    accepted: list[tuple[PathPart, ...]] = []
    open_mappings: list[tuple[PathPart, ...]] = []
    for field in _flatten_fields(fields):
        accepted.extend(field.accepted_paths)
        if get_origin(field.annotation) is dict and not field.children:
            open_mappings.extend(field.accepted_paths)
    return tuple(accepted), tuple(open_mappings)


def _is_known_path(
    path: tuple[PathPart, ...],
    *,
    accepted: tuple[tuple[PathPart, ...], ...],
    open_mappings: tuple[tuple[PathPart, ...], ...],
) -> bool:
    """Return whether a structural payload path belongs to the schema."""
    return any(
        _parts_match(pattern, path) or _prefix_matches(pattern, path)
        for pattern in accepted
    ) or any(_path_is_below(prefix, path) for prefix in open_mappings)


def _unknown_paths(
    value: Any,
    *,
    accepted: tuple[tuple[PathPart, ...], ...],
    open_mappings: tuple[tuple[PathPart, ...], ...],
    prefix: tuple[PathPart, ...] = (),
) -> Iterator[tuple[PathPart, ...]]:
    """Yield unrecognized mapping-key paths without retaining their values."""
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key: PathPart = (
                raw_key if isinstance(raw_key, (str, int)) else "<unsupported-key>"
            )
            path = (*prefix, key)
            known = _is_known_path(
                path,
                accepted=accepted,
                open_mappings=open_mappings,
            )
            if not known:
                yield path
                continue
            yield from _unknown_paths(
                child,
                accepted=accepted,
                open_mappings=open_mappings,
                prefix=path,
            )
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _unknown_paths(
                child,
                accepted=accepted,
                open_mappings=open_mappings,
                prefix=(*prefix, index),
            )


def _placeholder_paths(
    value: Any,
    *,
    prefix: tuple[PathPart, ...] = (),
) -> Iterator[tuple[PathPart, ...]]:
    """Yield paths whose values still contain the required template sentinel."""
    if value == REQUIRED_PLACEHOLDER:
        yield prefix
    elif isinstance(value, Mapping):
        for raw_key, child in value.items():
            key: PathPart = (
                raw_key if isinstance(raw_key, (str, int)) else "<unsupported-key>"
            )
            yield from _placeholder_paths(child, prefix=(*prefix, key))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _placeholder_paths(child, prefix=(*prefix, index))


def _field_for_path(
    fields: tuple[FieldSchema, ...], path: tuple[PathPart, ...]
) -> FieldSchema | None:
    """Find the schema field represented by one Pydantic/payload path."""
    return next(
        (
            field
            for field in _flatten_fields(fields)
            if any(_parts_match(pattern, path) for pattern in field.accepted_paths)
        ),
        None,
    )


def _validation_findings(
    error: ValidationError,
    *,
    schema: ModelSchema,
    placeholders: set[tuple[PathPart, ...]],
) -> Iterator[Finding]:
    """Translate model errors while suppressing duplicate structural findings."""
    safe_report = sanitize_validation_error(error, model_name=schema.model_name)
    for finding in safe_report.findings:
        if finding.detail_code == "extra_forbidden":
            continue
        if finding.path in placeholders:
            continue
        field = _field_for_path(schema.fields, finding.path)
        yield Finding(
            severity=finding.severity,
            code=finding.code,
            path=finding.path,
            message=finding.message,
            expected_type=field.type_name if field is not None else None,
            detail_code=finding.detail_code,
        )


def _finding_sort_key(finding: Finding) -> tuple[str, str, str]:
    """Return a stable order independent of Pydantic implementation details."""
    return (
        format_path(finding.path),
        finding.code.value,
        finding.severity.value,
    )


def validate_payload(
    target: SchemaTarget,
    payload: Mapping[str, Any],
    *,
    strict: bool = False,
) -> ValidationReport:
    """Validate only the supplied payload, without invoking settings sources."""
    schema = target if isinstance(target, ModelSchema) else build_model_schema(target)
    placeholders = set(_placeholder_paths(payload))
    accepted, open_mappings = _schema_paths(schema.fields)
    findings: list[Finding] = []

    try:
        instance = schema.model.__new__(schema.model)
        schema.model.__pydantic_validator__.validate_python(
            payload,
            self_instance=instance,
        )
    except ValidationError as error:
        findings.extend(
            _validation_findings(
                error,
                schema=schema,
                placeholders=placeholders,
            )
        )
    except Exception:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code=FindingCode.INVALID_VALUE,
                path=(),
                message="model validation failed",
                detail_code="validator_exception",
            )
        )

    for path in placeholders:
        field = _field_for_path(schema.fields, path)
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code=FindingCode.PLACEHOLDER,
                path=path,
                message="required placeholder has not been replaced",
                expected_type=field.type_name if field is not None else None,
                detail_code="required_placeholder",
            )
        )

    unknown_severity = Severity.ERROR if strict else Severity.WARNING
    findings.extend(
        Finding(
            severity=unknown_severity,
            code=FindingCode.UNKNOWN_KEY,
            path=path,
            message="key is not declared by the schema",
            detail_code="extra_forbidden",
        )
        for path in _unknown_paths(
            payload,
            accepted=accepted,
            open_mappings=open_mappings,
        )
    )

    return ValidationReport(
        model_name=schema.model_name,
        findings=tuple(sorted(findings, key=_finding_sort_key)),
        validated_fields=sum(1 for _ in _flatten_fields(schema.fields)),
    )


def render_validation_report(report: ValidationReport) -> str:
    """Render a concise human-readable report containing no payload values."""
    if not report.findings:
        return f"OK     {report.validated_fields} fields validated\n"

    lines = []
    for finding in report.findings:
        expected = (
            f" (expected {finding.expected_type})"
            if finding.expected_type is not None
            else ""
        )
        lines.append(
            f"{finding.severity.value.upper():<7}"
            f"{format_path(finding.path)}  {finding.message}{expected}"
        )
    return "\n".join(lines) + "\n"
