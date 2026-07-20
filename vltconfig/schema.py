"""Immutable, side-effect-free schema inspection for Pydantic models."""

from collections.abc import Callable as CallableABC
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import AliasChoices, AliasPath, BaseModel, SecretBytes, SecretStr

from vltconfig.errors import RecursiveSchemaError, UnsupportedSchemaError


class DefaultKind(StrEnum):
    """How a Pydantic field receives an application-level default."""

    NONE = "none"
    STATIC = "static"
    FACTORY = "factory"


@dataclass(frozen=True, slots=True)
class FieldSchema:
    """One immutable field in a configuration payload schema."""

    name: str
    python_path: tuple[str, ...]
    vault_path: tuple[str | int, ...]
    canonical_key: str
    accepted_paths: tuple[tuple[str | int, ...], ...]
    annotation: Any
    type_name: str
    required: bool
    nullable: bool
    default_kind: DefaultKind
    default: Any
    default_redacted: bool
    description: str | None
    examples: tuple[Any, ...]
    examples_redacted: bool
    secret: bool
    metadata: tuple[Any, ...]
    children: tuple["FieldSchema", ...]

    @property
    def has_static_default(self) -> bool:
        """Return whether application code declares a static default."""
        return self.default_kind is DefaultKind.STATIC

    @property
    def has_default_factory(self) -> bool:
        """Return whether application code declares an unevaluated factory."""
        return self.default_kind is DefaultKind.FACTORY


@dataclass(frozen=True, slots=True)
class ModelSchema:
    """Immutable structural description of one Pydantic model class."""

    model: type[BaseModel]
    model_name: str
    fields: tuple[FieldSchema, ...]


def _is_nullable(annotation: Any) -> bool:
    """Return whether an annotation explicitly includes ``None``."""
    origin = get_origin(annotation)
    return origin in (Union, UnionType) and type(None) in get_args(annotation)


def _is_secret(annotation: Any) -> bool:
    """Return whether an annotation contains a Pydantic secret type."""
    if annotation in (SecretStr, SecretBytes):
        return True
    return any(_is_secret(argument) for argument in get_args(annotation))


def _type_name(annotation: Any) -> str:
    """Render a stable finite type name without evaluating the annotation."""
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in (Union, UnionType):
        return " | ".join(_type_name(argument) for argument in arguments)
    if origin is Literal:
        values = ", ".join(repr(argument) for argument in arguments)
        return f"Literal[{values}]"
    if origin in (list, set, frozenset, tuple, dict):
        rendered = ", ".join(
            "..." if argument is Ellipsis else _type_name(argument)
            for argument in arguments
        )
        return f"{origin.__name__}[{rendered}]"
    name = getattr(annotation, "__name__", None)
    return str(name) if name is not None else str(annotation)


def _alias_paths(
    *, name: str, field: Any, validate_by_name: bool
) -> tuple[tuple[str | int, ...], ...]:
    """Return Pydantic validation paths in their documented priority order."""
    validation_alias = field.validation_alias
    paths: tuple[tuple[str | int, ...], ...]
    if isinstance(validation_alias, str):
        paths = ((validation_alias,),)
    elif isinstance(validation_alias, AliasPath):
        paths = (tuple(validation_alias.convert_to_aliases()),)
    elif isinstance(validation_alias, AliasChoices):
        paths = tuple(tuple(choice) for choice in validation_alias.convert_to_aliases())
    elif isinstance(field.alias, str):
        paths = ((field.alias,),)
    else:
        paths = ((name,),)

    name_path = (name,)
    if validate_by_name and name_path not in paths:
        return (*paths, name_path)
    return paths


def _without_none(annotation: Any) -> Any:
    """Unwrap the non-null member of a simple optional annotation."""
    if get_origin(annotation) not in (Union, UnionType):
        return annotation
    candidates = tuple(
        argument for argument in get_args(annotation) if argument is not type(None)
    )
    return candidates[0] if len(candidates) == 1 else annotation


def _as_model(annotation: Any) -> type[BaseModel] | None:
    """Narrow one annotation to a Pydantic model class."""
    target = _without_none(annotation)
    if isinstance(target, type) and issubclass(target, BaseModel):
        return target
    return None


def _referenced_models(annotation: Any) -> tuple[type[BaseModel], ...]:
    """Return model classes referenced anywhere in an annotation."""
    direct = _as_model(annotation)
    if direct is not None:
        return (direct,)
    models: list[type[BaseModel]] = []
    for argument in get_args(annotation):
        if argument is Ellipsis or argument is type(None):
            continue
        for model in _referenced_models(argument):
            if model not in models:
                models.append(model)
    return tuple(models)


def _nested_shape(
    annotation: Any,
) -> tuple[type[BaseModel], tuple[str, ...]] | None:
    """Return one unambiguous nested model and a collection wildcard path."""
    direct = _as_model(annotation)
    if direct is not None:
        return (direct, ())

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    target: Any = None
    if origin in (list, set, frozenset) and len(arguments) == 1:
        target = arguments[0]
    elif origin is tuple and arguments:
        concrete = tuple(argument for argument in arguments if argument is not Ellipsis)
        if concrete and all(argument == concrete[0] for argument in concrete):
            target = concrete[0]
    elif origin is dict and len(arguments) == 2:
        target = arguments[1]

    nested = _as_model(target)
    return (nested, ("*",)) if nested is not None else None


def _mapping_key_is_supported(annotation: Any) -> bool:
    """Return whether a mapping key has a JSON-object representation."""
    if annotation in (str, Any):
        return True
    return get_origin(annotation) is Literal and all(
        isinstance(value, str) for value in get_args(annotation)
    )


def _validate_shape(annotation: Any, python_path: tuple[str, ...]) -> None:
    """Reject shapes that cannot map to a finite JSON/Vault payload."""
    origin = get_origin(annotation)
    rendered_path = ".".join(python_path)
    if origin in (CallableABC, type):
        raise UnsupportedSchemaError(
            f"Field {rendered_path!r} uses an unsupported callable/type shape"
        )
    arguments = get_args(annotation)
    if origin is dict and arguments and not _mapping_key_is_supported(arguments[0]):
        raise UnsupportedSchemaError(
            f"Field {rendered_path!r} requires string-compatible mapping keys"
        )
    for argument in arguments:
        if argument is not Ellipsis:
            _validate_shape(argument, python_path)


def _field_schema(
    *,
    name: str,
    field: Any,
    validate_by_name: bool,
    python_prefix: tuple[str, ...] = (),
    vault_prefix: tuple[str | int, ...] = (),
    accepted_prefixes: tuple[tuple[str | int, ...], ...] = ((),),
    active_models: tuple[type[BaseModel], ...] = (),
) -> FieldSchema:
    """Inspect one FieldInfo without instantiating its owning model."""
    annotation = field.annotation
    secret = _is_secret(annotation)
    local_paths = _alias_paths(
        name=name,
        field=field,
        validate_by_name=validate_by_name,
    )
    canonical_path = local_paths[0]
    accepted_paths = tuple(
        (*prefix, *local_path)
        for prefix in accepted_prefixes
        for local_path in local_paths
    )
    python_path = (*python_prefix, name)
    vault_path = (*vault_prefix, *canonical_path)
    _validate_shape(annotation, python_path)
    nested_shape = _nested_shape(annotation)
    referenced_models = _referenced_models(annotation)
    if referenced_models and nested_shape is None:
        raise UnsupportedSchemaError(
            f"Field {'.'.join(python_path)!r} has an ambiguous nested model shape"
        )
    if field.default_factory is not None:
        default_kind = DefaultKind.FACTORY
        default = None
    elif field.is_required():
        default_kind = DefaultKind.NONE
        default = None
    else:
        default_kind = DefaultKind.STATIC
        default = None if secret else deepcopy(field.default)

    raw_examples = tuple(field.examples or ())
    nested_model, wildcard_path = nested_shape or (None, ())
    children = (
        _model_fields(
            nested_model,
            python_prefix=(*python_path, *wildcard_path),
            vault_prefix=(*vault_path, *wildcard_path),
            accepted_prefixes=tuple((*path, *wildcard_path) for path in accepted_paths),
            active_models=active_models,
        )
        if nested_model is not None
        else ()
    )
    return FieldSchema(
        name=name,
        python_path=python_path,
        vault_path=vault_path,
        canonical_key=".".join(str(part) for part in canonical_path),
        accepted_paths=accepted_paths,
        annotation=annotation,
        type_name=_type_name(annotation),
        required=field.is_required(),
        nullable=_is_nullable(annotation),
        default_kind=default_kind,
        default=default,
        default_redacted=secret and default_kind is DefaultKind.STATIC,
        description=field.description,
        examples=() if secret else deepcopy(raw_examples),
        examples_redacted=secret and bool(raw_examples),
        secret=secret,
        metadata=tuple(field.metadata),
        children=children,
    )


def _model_fields(
    model: type[BaseModel],
    *,
    python_prefix: tuple[str, ...] = (),
    vault_prefix: tuple[str | int, ...] = (),
    accepted_prefixes: tuple[tuple[str | int, ...], ...] = ((),),
    active_models: tuple[type[BaseModel], ...] = (),
) -> tuple[FieldSchema, ...]:
    """Inspect model fields in their declaration order."""
    if model in active_models:
        model_name = f"{model.__module__}.{model.__qualname__}"
        field_path = ".".join(python_prefix) or "<root>"
        raise RecursiveSchemaError(
            f"Recursive model {model_name!r} encountered at field {field_path!r}"
        )
    current_models = (*active_models, model)
    validate_by_name = bool(
        model.model_config.get("validate_by_name")
        or model.model_config.get("populate_by_name")
    )
    return tuple(
        _field_schema(
            name=name,
            field=field,
            validate_by_name=validate_by_name,
            python_prefix=python_prefix,
            vault_prefix=vault_prefix,
            accepted_prefixes=accepted_prefixes,
            active_models=current_models,
        )
        for name, field in model.model_fields.items()
    )


def build_model_schema(model: type[BaseModel]) -> ModelSchema:
    """Build an immutable schema without instantiating ``model`` or its sources."""
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        model_name = getattr(model, "__qualname__", type(model).__qualname__)
        raise UnsupportedSchemaError(
            f"Schema target {model_name!r} is not a Pydantic model class"
        )

    return ModelSchema(
        model=model,
        model_name=f"{model.__module__}.{model.__qualname__}",
        fields=_model_fields(model),
    )
