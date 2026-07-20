"""Deterministic, value-free configuration template rendering."""

import importlib
import json
from collections.abc import Iterator
from copy import deepcopy
from io import StringIO
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from vltconfig.errors import UnsupportedSchemaError, YAMLDependencyError
from vltconfig.schema import DefaultKind, FieldSchema, ModelSchema, build_model_schema

REQUIRED_PLACEHOLDER = "__VLTCFG_REQUIRED__"

SchemaTarget = type[BaseModel] | ModelSchema


def _schema_for(target: SchemaTarget) -> ModelSchema:
    """Return a schema for either supported public input form."""
    return target if isinstance(target, ModelSchema) else build_model_schema(target)


def _field_values(
    field: FieldSchema, *, include_defaults: bool
) -> Iterator[tuple[tuple[str | int, ...], Any]]:
    """Yield canonical path/value pairs for one field subtree."""
    collection_children = field.children and any(
        "*" in child.vault_path[len(field.vault_path) :] for child in field.children
    )
    if field.children and not collection_children:
        if field.required:
            children = tuple(
                value
                for child in field.children
                for value in _field_values(
                    child,
                    include_defaults=include_defaults,
                )
            )
            if children:
                yield from children
            else:
                yield (field.vault_path, {})
        elif (
            include_defaults
            and field.default_kind is DefaultKind.STATIC
            and not field.secret
        ):
            yield (field.vault_path, to_jsonable_python(deepcopy(field.default)))
        return

    if field.required:
        yield (field.vault_path, REQUIRED_PLACEHOLDER)
    elif (
        include_defaults
        and field.default_kind is DefaultKind.STATIC
        and not field.secret
    ):
        yield (field.vault_path, to_jsonable_python(deepcopy(field.default)))


def _set_path(
    document: dict[str, Any], path: tuple[str | int, ...], value: Any
) -> None:
    """Insert a value into a mapping/list path without losing field order."""
    if not path or not isinstance(path[0], str):
        raise UnsupportedSchemaError("A template field path must start with a key")

    current: dict[str, Any] | list[Any] = document
    for index, part in enumerate(path):
        final = index == len(path) - 1
        next_part = None if final else path[index + 1]
        if isinstance(current, dict):
            if not isinstance(part, str):
                raise UnsupportedSchemaError(
                    f"Template path {'.'.join(str(item) for item in path)!r} "
                    "uses an index inside an object"
                )
            if final:
                current[part] = value
                return
            expected_type = list if isinstance(next_part, int) else dict
            existing = current.get(part)
            if existing is None:
                existing = expected_type()
                current[part] = existing
            if not isinstance(existing, expected_type):
                raise UnsupportedSchemaError(
                    f"Template path {'.'.join(str(item) for item in path)!r} "
                    "conflicts with another canonical field path"
                )
            current = existing
            continue

        if not isinstance(part, int) or part < 0:
            raise UnsupportedSchemaError(
                f"Template path {'.'.join(str(item) for item in path)!r} "
                "uses a key inside a list"
            )
        while len(current) <= part:
            current.append(None)
        if final:
            current[part] = value
            return
        expected_type = list if isinstance(next_part, int) else dict
        existing = current[part]
        if existing is None:
            existing = expected_type()
            current[part] = existing
        if not isinstance(existing, expected_type):
            raise UnsupportedSchemaError(
                f"Template path {'.'.join(str(item) for item in path)!r} "
                "conflicts with another canonical field path"
            )
        current = existing


def build_template(
    target: SchemaTarget, *, include_defaults: bool = False
) -> dict[str, Any]:
    """Build a value-free JSON-compatible template mapping."""
    schema = _schema_for(target)
    document: dict[str, Any] = {}
    for field in schema.fields:
        for path, value in _field_values(
            field,
            include_defaults=include_defaults,
        ):
            _set_path(document, path, value)
    return document


def render_json_template(
    target: SchemaTarget, *, include_defaults: bool = False
) -> str:
    """Render a deterministic UTF-8 JSON template with a trailing newline."""
    return (
        json.dumps(
            build_template(target, include_defaults=include_defaults),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def _load_yaml_renderer() -> tuple[Any, Any, Any]:
    """Load the optional YAML implementation only when explicitly requested."""
    try:
        yaml_module = importlib.import_module("ruamel.yaml")
        comments_module = importlib.import_module("ruamel.yaml.comments")
    except ModuleNotFoundError as cause:
        if cause.name is None or cause.name.startswith("ruamel"):
            raise YAMLDependencyError(
                "YAML rendering requires the optional dependency; "
                "install 'vltconfig[yaml]'",
                cause_type=type(cause).__name__,
            ) from None
        raise
    return (
        yaml_module.YAML,
        comments_module.CommentedMap,
        comments_module.CommentedSeq,
    )


def _commented_value(value: Any, map_type: Any, sequence_type: Any) -> Any:
    """Convert JSON-compatible containers to comment-aware YAML containers."""
    if isinstance(value, dict):
        return map_type(
            (key, _commented_value(item, map_type, sequence_type))
            for key, item in value.items()
        )
    if isinstance(value, list):
        return sequence_type(
            _commented_value(item, map_type, sequence_type) for item in value
        )
    return value


def _flatten_fields(fields: tuple[FieldSchema, ...]) -> Iterator[FieldSchema]:
    """Yield schema fields in deterministic pre-order."""
    for field in fields:
        yield field
        yield from _flatten_fields(field.children)


def _safe_comment(field: FieldSchema) -> str:
    """Build a one-line value-free YAML comment."""
    description = " ".join((field.description or "").split())
    return f"{field.type_name} — {description}" if description else field.type_name


def _add_field_comment(document: Any, field: FieldSchema) -> None:
    """Attach a comment when the field's canonical path exists in the template."""
    if "*" in field.vault_path or not field.vault_path:
        return
    current = document
    for part in field.vault_path[:-1]:
        try:
            current = current[part]
        except (KeyError, IndexError, TypeError):
            return
    key = field.vault_path[-1]
    try:
        current[key]
    except (KeyError, IndexError, TypeError):
        return
    current.yaml_add_eol_comment(_safe_comment(field), key=key)


def render_yaml_template(
    target: SchemaTarget, *, include_defaults: bool = False
) -> str:
    """Render deterministic commented YAML through the optional ``yaml`` extra."""
    yaml_type, map_type, sequence_type = _load_yaml_renderer()
    schema = _schema_for(target)
    document = _commented_value(
        build_template(schema, include_defaults=include_defaults),
        map_type,
        sequence_type,
    )
    for field in _flatten_fields(schema.fields):
        _add_field_comment(document, field)

    yaml = yaml_type(typ="rt")
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    output = StringIO()
    yaml.dump(document, output)
    return output.getvalue()
