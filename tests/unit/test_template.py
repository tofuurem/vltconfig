"""Tests for deterministic value-free JSON templates."""

import json

import pytest
from pydantic import AliasPath, BaseModel, Field, SecretStr

from vltconfig.errors import UnsupportedSchemaError
from vltconfig.schema import build_model_schema
from vltconfig.template import (
    REQUIRED_PLACEHOLDER,
    build_template,
    render_json_template,
)


@pytest.mark.unit
def test_json_template_contains_only_required_leaf_placeholders() -> None:
    """Application defaults stay in code instead of being frozen into Vault."""

    class Database(BaseModel):
        host: str
        port: int = 5432

    class Credentials(BaseModel):
        token: SecretStr
        username: str = "service-user"

    class Settings(BaseModel):
        database: Database
        credentials: Credentials
        workers: int = 4
        optional_note: str | None = None

    assert build_template(Settings) == {
        "database": {"host": REQUIRED_PLACEHOLDER},
        "credentials": {"token": REQUIRED_PLACEHOLDER},
    }


@pytest.mark.unit
def test_json_template_can_include_static_non_secret_defaults() -> None:
    """The opt-in includes safe static defaults but never secret defaults."""
    secret_canary = "template-secret-default-canary"

    class Nested(BaseModel):
        endpoint: str
        retries: int = 3

    class Settings(BaseModel):
        nested: Nested
        workers: int = 4
        labels: list[str] = ["api", "worker"]
        token: SecretStr = SecretStr(secret_canary)

    template = build_template(Settings, include_defaults=True)

    assert template == {
        "nested": {
            "endpoint": REQUIRED_PLACEHOLDER,
            "retries": 3,
        },
        "workers": 4,
        "labels": ["api", "worker"],
    }
    assert secret_canary not in repr(template)


@pytest.mark.unit
def test_default_factory_is_never_executed_by_template_generation() -> None:
    """Even include-defaults mode cannot evaluate a default factory."""
    calls: list[str] = []

    def dangerous_factory() -> str:
        calls.append("template-factory-side-effect-canary")
        return "generated"

    class Settings(BaseModel):
        required: str
        generated: str = Field(default_factory=dangerous_factory)

    assert build_template(Settings, include_defaults=True) == {
        "required": REQUIRED_PLACEHOLDER
    }
    assert calls == []


@pytest.mark.unit
def test_required_nullable_field_still_receives_placeholder() -> None:
    """Nullable without a default remains required by Pydantic semantics."""

    class Settings(BaseModel):
        callback_url: str | None

    assert build_template(Settings) == {"callback_url": REQUIRED_PLACEHOLDER}


@pytest.mark.unit
def test_alias_path_builds_nested_json_structure() -> None:
    """Canonical validation paths can contain mappings and list indexes."""

    class Settings(BaseModel):
        token: str = Field(validation_alias=AliasPath("credentials", 0, "token"))

    assert build_template(Settings) == {
        "credentials": [{"token": REQUIRED_PLACEHOLDER}]
    }


@pytest.mark.unit
def test_json_rendering_is_byte_for_byte_deterministic() -> None:
    """Repeated model/schema rendering uses stable order, indent, and newline."""

    class Settings(BaseModel):
        second: int
        first: str

    schema = build_model_schema(Settings)
    expected = (
        '{\n  "second": "__VLTCFG_REQUIRED__",\n  "first": "__VLTCFG_REQUIRED__"\n}\n'
    )

    assert render_json_template(Settings) == expected
    assert render_json_template(schema) == expected
    assert json.loads(expected) == build_template(Settings)


@pytest.mark.unit
def test_required_nested_model_with_only_defaults_renders_empty_object() -> None:
    """A required model remains present even when every child defaults in code."""

    class Nested(BaseModel):
        retries: int = 3

    class Settings(BaseModel):
        nested: Nested

    assert build_template(Settings) == {"nested": {}}


@pytest.mark.unit
def test_optional_nested_static_default_is_included_only_when_requested() -> None:
    """An opt-in nested default is serialized as one safe value."""

    class Nested(BaseModel):
        name: str

    class Settings(BaseModel):
        nested: Nested = Nested(name="default-name")

    assert build_template(Settings) == {}
    assert build_template(Settings, include_defaults=True) == {
        "nested": {"name": "default-name"}
    }


@pytest.mark.unit
def test_required_collection_of_models_uses_one_collection_placeholder() -> None:
    """Templates cannot invent a number of nested collection elements."""

    class Worker(BaseModel):
        name: str

    class Settings(BaseModel):
        workers: list[Worker]

    assert build_template(Settings) == {"workers": REQUIRED_PLACEHOLDER}


@pytest.mark.unit
def test_alias_path_supports_multiple_list_indexes() -> None:
    """List containers are created deterministically for indexed aliases."""

    class Settings(BaseModel):
        value: str = Field(validation_alias=AliasPath("matrix", 0, 1))

    assert build_template(Settings) == {"matrix": [[None, REQUIRED_PLACEHOLDER]]}


@pytest.mark.unit
def test_conflicting_canonical_paths_fail_explicitly() -> None:
    """One field cannot silently overwrite a container required by another."""

    class Settings(BaseModel):
        scalar: str = Field(validation_alias=AliasPath("items", 0))
        nested: str = Field(validation_alias=AliasPath("items", 0, "value"))

    with pytest.raises(UnsupportedSchemaError, match="conflicts"):
        build_template(Settings)


@pytest.mark.unit
def test_negative_alias_index_is_rejected() -> None:
    """Negative indexes do not have a deterministic JSON template shape."""

    class Settings(BaseModel):
        value: str = Field(validation_alias=AliasPath("items", -1))

    with pytest.raises(UnsupportedSchemaError, match="uses a key inside a list"):
        build_template(Settings)
