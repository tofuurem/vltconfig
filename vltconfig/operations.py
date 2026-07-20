"""Side-effect-free orchestration around an injected Vault gateway."""

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from vltconfig.errors import (
    ConfigurationApplyError,
    VaultConflictError,
    VaultPathNotFoundError,
)
from vltconfig.planning import (
    ConfigurationPath,
    ConfigurationPlan,
    build_plan,
)
from vltconfig.schema import ModelSchema, build_model_schema
from vltconfig.template import build_template
from vltconfig.validation import (
    FindingCode,
    Severity,
    ValidationReport,
    format_path,
    validate_payload,
)
from vltconfig.vault_gateway import VersionedVaultGateway

SchemaTarget = type[BaseModel] | ModelSchema


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Immutable validation result for one exact Vault secret version."""

    version: int
    report: ValidationReport

    @property
    def valid(self) -> bool:
        """Return whether the raw Vault payload satisfies the schema."""
        return self.report.valid

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic redacted representation."""
        return {
            "version": self.version,
            "validation": self.report.to_dict(),
        }

    def to_json(self) -> str:
        """Serialize the redacted result for automation."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """Redacted result of one no-overwrite, CAS-protected apply operation."""

    plan: ConfigurationPlan
    applied: bool
    changed_paths: tuple[ConfigurationPath, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic redacted representation."""
        return {
            "applied": self.applied,
            "source_version": self.plan.source_version,
            "changed_paths": [format_path(path) for path in self.changed_paths],
            "plan": self.plan.to_dict(),
        }

    def to_json(self) -> str:
        """Serialize the redacted result for automation."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def check_configuration(
    target: SchemaTarget,
    gateway: VersionedVaultGateway,
    *,
    strict: bool = False,
) -> CheckResult:
    """Read and validate exactly one Vault version without printing."""
    secret = gateway.read()
    payload = secret.copy_data()
    try:
        report = validate_payload(target, payload, strict=strict)
    finally:
        payload.clear()
    return CheckResult(version=secret.version, report=report)


def plan_configuration(
    target: SchemaTarget,
    gateway: VersionedVaultGateway,
    *,
    replacement_paths: Sequence[ConfigurationPath] = (),
    proposed_values: Mapping[str, Any] | None = None,
) -> ConfigurationPlan:
    """Read and plan one existing or not-yet-created Vault path."""
    try:
        secret = gateway.read()
    except VaultPathNotFoundError:
        payload: dict[str, Any] = {}
        source_version = 0
    else:
        payload = secret.copy_data()
        source_version = secret.version

    try:
        return build_plan(
            target,
            payload,
            replacement_paths=replacement_paths,
            proposed_values=proposed_values,
            source_version=source_version,
        )
    finally:
        payload.clear()


def _added_leaf_paths(value: Any, prefix: ConfigurationPath) -> list[ConfigurationPath]:
    """Return structural leaf paths for a newly inserted template subtree."""
    paths: list[ConfigurationPath] = []
    if isinstance(value, Mapping):
        if not value:
            return [prefix]
        for key, child in value.items():
            paths.extend(_added_leaf_paths(child, (*prefix, key)))
    elif isinstance(value, list):
        if not value:
            return [prefix]
        for index, child in enumerate(value):
            paths.extend(_added_leaf_paths(child, (*prefix, index)))
    else:
        paths.append(prefix)
    return paths


def _merge_missing(
    current: dict[str, Any] | list[Any],
    required: dict[str, Any] | list[Any],
    *,
    prefix: ConfigurationPath = (),
) -> list[ConfigurationPath]:
    """Add missing template structure while preserving every existing value."""
    added: list[ConfigurationPath] = []
    if isinstance(current, dict) and isinstance(required, dict):
        for key, required_value in required.items():
            path = (*prefix, key)
            if key not in current:
                current[key] = deepcopy(required_value)
                added.extend(_added_leaf_paths(required_value, path))
                continue
            current_value = current[key]
            if isinstance(current_value, (dict, list)) and isinstance(
                required_value, (dict, list)
            ):
                added.extend(_merge_missing(current_value, required_value, prefix=path))
        return added

    if isinstance(current, list) and isinstance(required, list):
        for index, required_value in enumerate(required):
            path = (*prefix, index)
            if index >= len(current):
                current.append(deepcopy(required_value))
                added.extend(_added_leaf_paths(required_value, path))
                continue
            current_value = current[index]
            if isinstance(current_value, (dict, list)) and isinstance(
                required_value, (dict, list)
            ):
                added.extend(_merge_missing(current_value, required_value, prefix=path))
    return added


def _lookup_value(value: Any, path: ConfigurationPath) -> tuple[bool, Any]:
    """Read one concrete path without treating null as missing."""
    current = value
    for part in path:
        if isinstance(part, str) and isinstance(current, Mapping):
            if part not in current:
                return False, None
            current = current[part]
        elif isinstance(part, int) and isinstance(current, list):
            if part < 0 or part >= len(current):
                return False, None
            current = current[part]
        else:
            return False, None
    return True, current


def _set_value(
    document: dict[str, Any],
    path: ConfigurationPath,
    value: Any,
) -> None:
    """Set one explicitly addressed value in an isolated candidate payload."""
    if not path or not isinstance(path[0], str):
        raise ConfigurationApplyError("Replacement path must start with a key")

    current: dict[str, Any] | list[Any] = document
    for index, part in enumerate(path):
        final = index == len(path) - 1
        next_part = None if final else path[index + 1]
        if isinstance(current, dict):
            if not isinstance(part, str):
                raise ConfigurationApplyError(
                    "Replacement path does not match the payload structure"
                )
            if final:
                current[part] = deepcopy(value)
                return
            expected_type = list if isinstance(next_part, int) else dict
            child = current.get(part)
            if child is None:
                child = expected_type()
                current[part] = child
            if not isinstance(child, expected_type):
                raise ConfigurationApplyError(
                    "Replacement path does not match the payload structure"
                )
            current = child
            continue

        if not isinstance(part, int) or part < 0:
            raise ConfigurationApplyError(
                "Replacement path does not match the payload structure"
            )
        while len(current) <= part:
            current.append(None)
        if final:
            current[part] = deepcopy(value)
            return
        expected_type = list if isinstance(next_part, int) else dict
        child = current[part]
        if child is None:
            child = expected_type()
            current[part] = child
        if not isinstance(child, expected_type):
            raise ConfigurationApplyError(
                "Replacement path does not match the payload structure"
            )
        current = child


def _apply_replacements(
    candidate: dict[str, Any],
    replacement_paths: Sequence[ConfigurationPath],
    proposed_values: Mapping[str, Any],
) -> tuple[ConfigurationPath, ...]:
    """Copy only explicitly addressed proposed values into a candidate."""
    changed: list[ConfigurationPath] = []
    for path in dict.fromkeys(replacement_paths):
        present, value = _lookup_value(proposed_values, path)
        if not present:
            continue
        _set_value(candidate, path, value)
        changed.append(path)
    return tuple(changed)


def apply_configuration(
    target: SchemaTarget,
    gateway: VersionedVaultGateway,
    *,
    replacement_paths: Sequence[ConfigurationPath] = (),
    proposed_values: Mapping[str, Any] | None = None,
    expected_version: int | None = None,
) -> ApplyResult:
    """Apply additions and addressed replacements against one fresh CAS plan."""
    schema = target if isinstance(target, ModelSchema) else build_model_schema(target)
    try:
        secret = gateway.read()
    except VaultPathNotFoundError:
        payload: dict[str, Any] = {}
        source_version = 0
    else:
        payload = secret.copy_data()
        source_version = secret.version

    try:
        if expected_version is not None and source_version != expected_version:
            raise VaultConflictError(
                "Vault changed after the approved preview; read and plan again"
            )
        proposed = proposed_values or {}
        plan = build_plan(
            schema,
            payload,
            replacement_paths=replacement_paths,
            proposed_values=proposed_values,
            source_version=source_version,
        )
        if not plan.executable:
            raise ConfigurationApplyError(
                "Configuration cannot be applied until blocking plan findings are resolved"
            )

        candidate = deepcopy(payload)
        required_template = build_template(schema)
        initial_candidate = deepcopy(payload)
        initial_additions = set(_merge_missing(initial_candidate, required_template))
        initial_candidate.clear()
        original_missing = {
            finding.path
            for finding in validate_payload(schema, payload).findings
            if finding.code is FindingCode.MISSING_REQUIRED
        }
        replaced_paths = _apply_replacements(
            candidate,
            replacement_paths,
            proposed,
        )
        if replaced_paths:
            replacement_report = validate_payload(schema, candidate)
            replacement_blocked = any(
                finding.severity is Severity.ERROR
                and not (
                    finding.code is FindingCode.MISSING_REQUIRED
                    and (
                        finding.path in original_missing
                        or finding.path in initial_additions
                    )
                )
                for finding in replacement_report.findings
            )
            if replacement_blocked:
                raise ConfigurationApplyError(
                    "Proposed replacements do not satisfy the configuration schema"
                )

        added_paths = tuple(_merge_missing(candidate, required_template))
        changed_paths = (*added_paths, *replaced_paths)
        if not changed_paths:
            return ApplyResult(plan=plan, applied=False, changed_paths=())

        if source_version == 0:
            gateway.create(candidate)
        else:
            gateway.update(candidate, version=source_version)
        return ApplyResult(
            plan=plan,
            applied=True,
            changed_paths=changed_paths,
        )
    finally:
        payload.clear()
