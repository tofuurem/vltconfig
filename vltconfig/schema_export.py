"""Sanitized JSON Schema and Markdown exports for configuration models."""

import json
from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from vltconfig.schema import FieldSchema, ModelSchema, build_model_schema

SchemaTarget = type[BaseModel] | ModelSchema

_CONSTRAINT_ATTRIBUTES = (
    "gt",
    "ge",
    "lt",
    "le",
    "multiple_of",
    "min_length",
    "max_length",
    "pattern",
    "strict",
)


def _schema_for(target: SchemaTarget) -> ModelSchema:
    """Return a schema for either supported public input form."""
    return target if isinstance(target, ModelSchema) else build_model_schema(target)


def _is_secret_schema(node: dict[str, Any]) -> bool:
    """Return whether a JSON Schema node describes a write-only secret."""
    if node.get("writeOnly") is True or node.get("format") == "password":
        return True
    return any(
        _is_secret_schema(value) for value in node.values() if isinstance(value, dict)
    ) or any(
        _is_secret_schema(item)
        for value in node.values()
        if isinstance(value, list)
        for item in value
        if isinstance(item, dict)
    )


def _sanitize_json_schema(value: Any) -> Any:
    """Recursively remove defaults and secret examples from JSON Schema."""
    if isinstance(value, dict):
        secret = _is_secret_schema(value)
        return {
            key: _sanitize_json_schema(item)
            for key, item in value.items()
            if key != "default" and not (key == "examples" and secret)
        }
    if isinstance(value, list):
        return [_sanitize_json_schema(item) for item in value]
    return deepcopy(value)


def _path_text(path: tuple[str | int, ...]) -> str:
    """Render a mapping/list path without ambiguity."""
    rendered = ""
    for part in path:
        if isinstance(part, int) or part == "*":
            rendered += f"[{part}]"
        elif rendered:
            rendered += f".{part}"
        else:
            rendered = part
    return rendered


def _constraints(field: FieldSchema) -> dict[str, str | int | float | bool]:
    """Extract only known scalar constraint metadata."""
    result: dict[str, str | int | float | bool] = {}
    for metadata in field.metadata:
        for attribute in _CONSTRAINT_ATTRIBUTES:
            value = getattr(metadata, attribute, None)
            if value is not None and isinstance(value, (str, int, float, bool)):
                result[attribute] = value
    return result


def _flatten(fields: tuple[FieldSchema, ...]) -> tuple[FieldSchema, ...]:
    """Flatten fields in deterministic pre-order."""
    return tuple(
        item for field in fields for item in (field, *_flatten(field.children))
    )


def _field_metadata(field: FieldSchema) -> dict[str, Any]:
    """Return a value-free JSON-compatible field description."""
    return {
        "python_path": ".".join(field.python_path),
        "vault_path": _path_text(field.vault_path),
        "accepted_paths": [_path_text(path) for path in field.accepted_paths],
        "type": field.type_name,
        "required": field.required,
        "nullable": field.nullable,
        "secret": field.secret,
        "description": field.description,
        "constraints": _constraints(field),
    }


def export_json_schema(target: SchemaTarget) -> dict[str, Any]:
    """Export Pydantic JSON Schema with value-bearing metadata removed."""
    schema = _schema_for(target)
    raw_schema = schema.model.model_json_schema(by_alias=True, mode="validation")
    sanitized = _sanitize_json_schema(raw_schema)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **sanitized,
        "x-vltconfig-fields": [
            _field_metadata(field) for field in _flatten(schema.fields)
        ],
    }


def render_json_schema(target: SchemaTarget) -> str:
    """Render deterministic sanitized JSON Schema with a trailing newline."""
    return (
        json.dumps(
            export_json_schema(target),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _escape_markdown(value: str) -> str:
    """Escape table-sensitive characters in a Markdown cell."""
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _code(value: str) -> str:
    """Render a safe Markdown code span."""
    escaped = _escape_markdown(value).replace("`", "\\`")
    return f"`{escaped}`"


def render_markdown_reference(target: SchemaTarget) -> str:
    """Render a deterministic value-free field reference table."""
    schema = _schema_for(target)
    lines = [
        "# Configuration reference",
        "",
        f"Model: {_code(schema.model_name)}",
        "",
        (
            "| Vault path | Python path | Accepted inputs | Type | Required | "
            "Flags | Constraints | Description |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for field in _flatten(schema.fields):
        constraints = _constraints(field)
        constraint_text = ", ".join(
            f"{name}={value}" for name, value in constraints.items()
        )
        flags = "secret" if field.secret else "—"
        accepted = "<br>".join(_code(_path_text(path)) for path in field.accepted_paths)
        lines.append(
            "| "
            + " | ".join(
                (
                    _code(_path_text(field.vault_path)),
                    _code(".".join(field.python_path)),
                    accepted,
                    _code(field.type_name),
                    "yes" if field.required else "no",
                    flags,
                    _escape_markdown(constraint_text) if constraint_text else "—",
                    _escape_markdown(field.description or "—"),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"
