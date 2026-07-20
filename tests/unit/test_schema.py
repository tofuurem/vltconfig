"""Tests for side-effect-free Pydantic schema inspection."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from enum import StrEnum
from typing import Any, ClassVar, Literal, cast

import pytest
from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    SecretBytes,
    SecretStr,
)
from pydantic_settings import PydanticBaseSettingsSource

from vltconfig import VaultJsonConfig
from vltconfig.errors import RecursiveSchemaError, UnsupportedSchemaError
from vltconfig.schema import DefaultKind, build_model_schema


@pytest.mark.unit
def test_required_and_default_semantics_match_pydantic() -> None:
    """Requiredness comes from FieldInfo, including nullable required fields."""

    class Settings(BaseModel):
        required_text: str = Field(description="Required text")
        nullable_required: str | None
        static_default: int = 4
        optional_none: str | None = None

    schema = build_model_schema(Settings)
    fields = {field.name: field for field in schema.fields}

    assert schema.model_name.endswith(".Settings")
    assert [field.name for field in schema.fields] == [
        "required_text",
        "nullable_required",
        "static_default",
        "optional_none",
    ]
    assert fields["required_text"].required is True
    assert fields["required_text"].default_kind is DefaultKind.NONE
    assert fields["required_text"].description == "Required text"
    assert fields["nullable_required"].required is True
    assert fields["nullable_required"].nullable is True
    assert fields["static_default"].required is False
    assert fields["static_default"].default_kind is DefaultKind.STATIC
    assert fields["static_default"].default == 4
    assert fields["optional_none"].has_static_default is True
    assert fields["optional_none"].default is None


@pytest.mark.unit
def test_basic_scalar_type_names_are_stable() -> None:
    """Scalar annotations receive deterministic human-readable names."""

    class Settings(BaseModel):
        text: str
        integer: int
        decimal: float
        enabled: bool
        raw: bytes

    assert [field.type_name for field in build_model_schema(Settings).fields] == [
        "str",
        "int",
        "float",
        "bool",
        "bytes",
    ]


@pytest.mark.unit
def test_secret_defaults_and_examples_are_classified_and_redacted() -> None:
    """The schema never retains secret default/example canaries."""
    text_canary = "schema-secret-text-canary"
    bytes_canary = b"schema-secret-bytes-canary"

    class Settings(BaseModel):
        token: SecretStr = Field(
            default=SecretStr(text_canary),
            examples=[text_canary],
            description="External API token",
        )
        certificate: SecretBytes = Field(
            default=SecretBytes(bytes_canary),
            examples=[bytes_canary],
        )

    schema = build_model_schema(Settings)
    token, certificate = schema.fields

    assert token.secret is True
    assert token.type_name == "SecretStr"
    assert token.default_kind is DefaultKind.STATIC
    assert token.default is None
    assert token.default_redacted is True
    assert token.examples == ()
    assert token.examples_redacted is True
    assert certificate.secret is True
    assert certificate.type_name == "SecretBytes"
    assert text_canary not in repr(schema)
    assert bytes_canary.decode() not in repr(schema)


@pytest.mark.unit
def test_schema_contracts_are_frozen() -> None:
    """Callers cannot rewrite structural schema attributes."""

    class Settings(BaseModel):
        value: str

    schema = build_model_schema(Settings)
    attribute = "required"

    with pytest.raises(FrozenInstanceError):
        setattr(schema.fields[0], attribute, False)


@pytest.mark.unit
def test_nested_models_preserve_python_and_vault_paths() -> None:
    """Nested fields retain deterministic absolute structural paths."""

    class Database(BaseModel):
        host: str
        port: int = 5432

    class Settings(BaseModel):
        database: Database = Field(alias="db")
        debug: bool = False

    schema = build_model_schema(Settings)
    database = schema.fields[0]

    assert database.python_path == ("database",)
    assert database.vault_path == ("db",)
    assert [child.name for child in database.children] == ["host", "port"]
    assert database.children[0].python_path == ("database", "host")
    assert database.children[0].vault_path == ("db", "host")
    assert database.children[1].default == 5432


@pytest.mark.unit
def test_alias_choices_and_paths_keep_canonical_and_accepted_paths() -> None:
    """The first validation choice is canonical and alternatives stay visible."""

    class Settings(BaseModel):
        model_config = ConfigDict(validate_by_name=True)

        token: str = Field(
            validation_alias=AliasChoices(
                "primary_token",
                "legacy_token",
                AliasPath("credentials", "token"),
            )
        )
        region: str = Field(validation_alias=AliasPath("service", "region"))

    token, region = build_model_schema(Settings).fields

    assert token.vault_path == ("primary_token",)
    assert token.accepted_paths == (
        ("primary_token",),
        ("legacy_token",),
        ("credentials", "token"),
        ("token",),
    )
    assert region.vault_path == ("service", "region")
    assert region.accepted_paths == (
        ("service", "region"),
        ("region",),
    )


@pytest.mark.unit
def test_enum_literal_union_and_collection_shapes_are_described() -> None:
    """Advanced finite annotations receive stable type descriptions."""

    class Mode(StrEnum):
        SAFE = "safe"
        FAST = "fast"

    class Settings(BaseModel):
        mode: Mode
        level: Literal["info", "debug"]
        identifier: int | str
        tags: list[str]
        unique_ports: set[int]
        coordinates: tuple[float, float]
        aliases: dict[str, str]

    fields = build_model_schema(Settings).fields

    assert [field.type_name for field in fields] == [
        "Mode",
        "Literal['info', 'debug']",
        "int | str",
        "list[str]",
        "set[int]",
        "tuple[float, float]",
        "dict[str, str]",
    ]


@pytest.mark.unit
def test_constrained_field_metadata_is_preserved() -> None:
    """Pydantic constraints remain available to validation/export layers."""

    class Settings(BaseModel):
        workers: int = Field(gt=0, le=64)
        name: str = Field(min_length=2, max_length=40, pattern=r"^[a-z]+$")

    workers, name = build_model_schema(Settings).fields

    assert workers.type_name == "int"
    assert {type(item).__name__ for item in workers.metadata} >= {"Gt", "Le"}
    assert name.type_name == "str"
    assert {type(item).__name__ for item in name.metadata} >= {
        "MinLen",
        "MaxLen",
        "_PydanticGeneralMetadata",
    }


@pytest.mark.unit
def test_schema_paths_are_deterministic_across_runs() -> None:
    """Repeated inspection preserves declared field and nested order."""

    class Nested(BaseModel):
        second: int
        first: str

    class Settings(BaseModel):
        nested: Nested
        final: bool

    first = build_model_schema(Settings)
    second = build_model_schema(Settings)

    assert first == second
    assert [field.python_path for field in first.fields] == [
        ("nested",),
        ("final",),
    ]
    assert [field.python_path for field in first.fields[0].children] == [
        ("nested", "second"),
        ("nested", "first"),
    ]


@pytest.mark.unit
def test_recursive_model_is_rejected_with_safe_field_context() -> None:
    """Direct recursion fails without overflowing or exposing model values."""

    class Node(BaseModel):
        value: str
        child: "Node | None" = None

    with pytest.raises(RecursiveSchemaError) as captured:
        build_model_schema(Node)

    assert "child" in str(captured.value)
    assert "Node" in str(captured.value)


@pytest.mark.unit
def test_recursive_collection_model_is_rejected() -> None:
    """Recursion hidden inside a collection is still non-finite."""

    class Tree(BaseModel):
        name: str
        children: list["Tree"] = Field(default_factory=list)

    with pytest.raises(RecursiveSchemaError, match="children"):
        build_model_schema(Tree)


@pytest.mark.unit
@pytest.mark.parametrize(
    "model",
    [
        type(
            "CallableSettings",
            (BaseModel,),
            {
                "__annotations__": {"callback": Callable[[], str]},
            },
        ),
        type(
            "NonStringMappingSettings",
            (BaseModel,),
            {
                "__annotations__": {"values": dict[int, str]},
            },
        ),
    ],
)
def test_unsupported_payload_shapes_fail_explicitly(
    model: type[BaseModel],
) -> None:
    """Non-JSON structural shapes cannot be silently omitted."""
    with pytest.raises(UnsupportedSchemaError):
        build_model_schema(model)


@pytest.mark.unit
def test_non_model_target_fails_without_using_its_repr() -> None:
    """Invalid targets report only a safe type name."""

    class NotAModel:
        def __repr__(self) -> str:
            return "non-model-repr-canary"

    target = cast(Any, NotAModel())
    with pytest.raises(UnsupportedSchemaError) as captured:
        build_model_schema(target)

    assert "non-model-repr-canary" not in str(captured.value)


@pytest.mark.unit
def test_default_factory_is_classified_without_execution() -> None:
    """Inspection records a factory but never evaluates application code."""
    calls: list[str] = []

    def dangerous_factory() -> str:
        calls.append("default-factory-side-effect-canary")
        return "generated-value"

    class Settings(BaseModel):
        generated: str = Field(default_factory=dangerous_factory)

    generated = build_model_schema(Settings).fields[0]

    assert generated.default_kind is DefaultKind.FACTORY
    assert generated.default is None
    assert calls == []


@pytest.mark.unit
def test_settings_sources_are_not_executed_during_schema_inspection() -> None:
    """Inspecting VaultJsonConfig subclasses never reads env, JSON, or Vault."""
    calls: list[str] = []

    class Settings(VaultJsonConfig):
        source_calls: ClassVar[list[str]] = calls
        value: str

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseModel],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            cls.source_calls.append("settings-source-side-effect-canary")
            return (init_settings,)

    schema = build_model_schema(Settings)

    assert schema.fields[0].name == "value"
    assert calls == []
