"""Immutable, value-free plans for configuration changes."""

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from vltconfig.schema import FieldSchema, ModelSchema, build_model_schema
from vltconfig.validation import (
    FindingCode,
    PathPart,
    Severity,
    format_path,
    validate_payload,
)

SchemaTarget = type[BaseModel] | ModelSchema
ConfigurationPath = tuple[PathPart, ...]


class ChangeCategory(StrEnum):
    """Stable structural changes a caller may review before a Vault write."""

    ADD_REQUIRED = "add_required"
    UNRESOLVED_PLACEHOLDER = "unresolved_placeholder"
    OPTIONAL_NO_CHANGE = "optional_no_change"
    UNKNOWN_KEY = "unknown_key"
    TYPE_CHANGE = "type_change"
    REPLACE = "replace"
    PROPOSED_VALUE_IGNORED = "proposed_value_ignored"
    REPLACEMENT_VALUE_MISSING = "replacement_value_missing"
    REPLACEMENT_NOT_DECLARED = "replacement_not_declared"


@dataclass(frozen=True, slots=True)
class PlanChange:
    """One structural change containing no current or proposed value."""

    category: ChangeCategory
    severity: Severity
    path: ConfigurationPath
    expected_type: str | None
    message: str
    executable: bool

    def to_dict(self) -> dict[str, str | bool | None]:
        """Return the deterministic safe representation of this change."""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "path": format_path(self.path),
            "expected_type": self.expected_type,
            "message": self.message,
            "executable": self.executable,
        }


@dataclass(frozen=True, slots=True)
class ConfigurationPlan:
    """A reviewable plan which grants no durable write authorization."""

    model_name: str
    changes: tuple[PlanChange, ...]
    source_version: int | None = None

    @property
    def error_count(self) -> int:
        """Return the number of changes that block an apply operation."""
        return sum(change.severity is Severity.ERROR for change in self.changes)

    @property
    def warning_count(self) -> int:
        """Return the number of advisory changes."""
        return sum(change.severity is Severity.WARNING for change in self.changes)

    @property
    def write_count(self) -> int:
        """Return the number of explicitly executable changes."""
        return sum(change.executable for change in self.changes)

    @property
    def executable(self) -> bool:
        """Return whether the plan contains no blocking change."""
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-safe representation."""
        return {
            "model": self.model_name,
            "source_version": self.source_version,
            "executable": self.executable,
            "write_count": self.write_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "changes": [change.to_dict() for change in self.changes],
        }

    def to_json(self) -> str:
        """Serialize the safe representation for automation."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _flatten_fields(fields: tuple[FieldSchema, ...]) -> Iterator[FieldSchema]:
    """Yield all schema fields in declaration order."""
    for field in fields:
        yield field
        yield from _flatten_fields(field.children)


def _path_matches(pattern: ConfigurationPath, path: ConfigurationPath) -> bool:
    """Match an exact field path while honoring schema wildcards."""
    return len(pattern) == len(path) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(pattern, path, strict=True)
    )


def _find_field(
    schema: ModelSchema,
    path: ConfigurationPath,
) -> FieldSchema | None:
    """Find a declared field by any accepted Vault input path."""
    if not path or "*" in path:
        return None
    return next(
        (
            field
            for field in _flatten_fields(schema.fields)
            if any(_path_matches(pattern, path) for pattern in field.accepted_paths)
        ),
        None,
    )


def _lookup_path(value: Any, path: ConfigurationPath) -> tuple[bool, Any]:
    """Resolve a concrete path while distinguishing missing from null."""
    current = value
    for part in path:
        if isinstance(part, str) and isinstance(current, Mapping):
            if part not in current:
                return False, None
            current = current[part]
        elif (
            isinstance(part, int)
            and isinstance(current, Sequence)
            and not isinstance(current, (str, bytes, bytearray))
        ):
            if part < 0 or part >= len(current):
                return False, None
            current = current[part]
        else:
            return False, None
    return True, current


def _field_is_present(field: FieldSchema, payload: Mapping[str, Any]) -> bool:
    """Return whether any accepted concrete path is present in a payload."""
    return any(
        "*" not in path and _lookup_path(payload, path)[0]
        for path in field.accepted_paths
    )


def _proposed_leaf_paths(
    value: Any,
    *,
    prefix: ConfigurationPath = (),
) -> Iterator[ConfigurationPath]:
    """Yield only paths from a proposed-values document, never its values."""
    if isinstance(value, Mapping):
        if not value and prefix:
            yield prefix
        for raw_key, child in value.items():
            key: PathPart = (
                raw_key if isinstance(raw_key, (str, int)) else "<unsupported-key>"
            )
            yield from _proposed_leaf_paths(child, prefix=(*prefix, key))
    else:
        yield prefix


def _path_is_covered(path: ConfigurationPath, allowed: ConfigurationPath) -> bool:
    """Return whether an addressed replacement covers a proposed leaf."""
    return len(path) >= len(allowed) and path[: len(allowed)] == allowed


def _change_sort_key(change: PlanChange) -> tuple[str, str, str]:
    """Return a stable structural ordering for plan output."""
    return (
        format_path(change.path),
        change.category.value,
        change.severity.value,
    )


def build_plan(
    target: SchemaTarget,
    current_payload: Mapping[str, Any],
    *,
    replacement_paths: Sequence[ConfigurationPath] = (),
    proposed_values: Mapping[str, Any] | None = None,
    source_version: int | None = None,
) -> ConfigurationPlan:
    """Compare a payload with a schema without retaining any payload value."""
    schema = target if isinstance(target, ModelSchema) else build_model_schema(target)
    replacements = tuple(dict.fromkeys(replacement_paths))
    replacement_set = set(replacements)
    proposed = proposed_values or {}
    changes: list[PlanChange] = []

    for finding in validate_payload(schema, current_payload).findings:
        if any(_path_is_covered(finding.path, path) for path in replacements):
            continue
        if finding.code is FindingCode.MISSING_REQUIRED:
            category = ChangeCategory.ADD_REQUIRED
            severity = Severity.INFO
            message = "required field will be initialized"
            executable = True
        elif finding.code is FindingCode.PLACEHOLDER:
            category = ChangeCategory.UNRESOLVED_PLACEHOLDER
            severity = Severity.ERROR
            message = "required placeholder must be replaced"
            executable = False
        elif finding.code is FindingCode.UNKNOWN_KEY:
            category = ChangeCategory.UNKNOWN_KEY
            severity = Severity.WARNING
            message = "unknown key will be preserved"
            executable = False
        else:
            category = ChangeCategory.TYPE_CHANGE
            severity = Severity.ERROR
            message = "existing field is incompatible with the schema"
            executable = False
        changes.append(
            PlanChange(
                category=category,
                severity=severity,
                path=finding.path,
                expected_type=finding.expected_type,
                message=message,
                executable=executable,
            )
        )

    for field in _flatten_fields(schema.fields):
        canonical_path = field.vault_path
        if field.required or "*" in canonical_path:
            continue
        if canonical_path in replacement_set or _field_is_present(
            field, current_payload
        ):
            continue
        changes.append(
            PlanChange(
                category=ChangeCategory.OPTIONAL_NO_CHANGE,
                severity=Severity.INFO,
                path=canonical_path,
                expected_type=field.type_name,
                message="optional field remains managed by application defaults",
                executable=False,
            )
        )

    for path in replacements:
        replacement_field = _find_field(schema, path)
        value_present, _ = _lookup_path(proposed, path)
        if replacement_field is None:
            changes.append(
                PlanChange(
                    category=ChangeCategory.REPLACEMENT_NOT_DECLARED,
                    severity=Severity.ERROR,
                    path=path,
                    expected_type=None,
                    message="replacement path is not declared by the schema",
                    executable=False,
                )
            )
        elif not value_present:
            changes.append(
                PlanChange(
                    category=ChangeCategory.REPLACEMENT_VALUE_MISSING,
                    severity=Severity.ERROR,
                    path=path,
                    expected_type=replacement_field.type_name,
                    message="replacement path has no proposed value",
                    executable=False,
                )
            )
        else:
            changes.append(
                PlanChange(
                    category=ChangeCategory.REPLACE,
                    severity=Severity.INFO,
                    path=path,
                    expected_type=replacement_field.type_name,
                    message="field will be replaced explicitly",
                    executable=True,
                )
            )

    for path in _proposed_leaf_paths(proposed):
        if any(_path_is_covered(path, allowed) for allowed in replacements):
            continue
        changes.append(
            PlanChange(
                category=ChangeCategory.PROPOSED_VALUE_IGNORED,
                severity=Severity.WARNING,
                path=path,
                expected_type=None,
                message="proposed value is ignored without explicit replacement",
                executable=False,
            )
        )

    return ConfigurationPlan(
        model_name=schema.model_name,
        changes=tuple(sorted(changes, key=_change_sort_key)),
        source_version=source_version,
    )


def render_configuration_plan(plan: ConfigurationPlan) -> str:
    """Render a human-readable plan containing structural metadata only."""
    labels = {
        ChangeCategory.ADD_REQUIRED: "add required field",
        ChangeCategory.UNRESOLVED_PLACEHOLDER: "replace unresolved placeholder",
        ChangeCategory.OPTIONAL_NO_CHANGE: "optional; no change",
        ChangeCategory.UNKNOWN_KEY: "preserve unknown key",
        ChangeCategory.TYPE_CHANGE: "incompatible field",
        ChangeCategory.REPLACE: "replace field",
        ChangeCategory.PROPOSED_VALUE_IGNORED: "ignore unaddressed proposed value",
        ChangeCategory.REPLACEMENT_VALUE_MISSING: "replacement value missing",
        ChangeCategory.REPLACEMENT_NOT_DECLARED: "replacement path not declared",
    }
    lines = []
    for change in plan.changes:
        expected = (
            f" (expected {change.expected_type})"
            if change.expected_type is not None
            else ""
        )
        lines.append(
            f"{change.severity.value.upper():<7}"
            f"{format_path(change.path)}  {labels[change.category]}{expected}"
        )
    status = "READY" if plan.executable else "BLOCKED"
    write_label = "write" if plan.write_count == 1 else "writes"
    lines.append(
        f"{status:<7}{plan.write_count} {write_label}, "
        f"{plan.warning_count} warnings, {plan.error_count} errors"
    )
    return "\n".join(lines) + "\n"
