"""Tests for sanitized JSON Schema and Markdown reference export."""

import json

import pytest
from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field, SecretStr

from vltconfig.schema import build_model_schema
from vltconfig.schema_export import (
    export_json_schema,
    render_json_schema,
    render_markdown_reference,
)


def _contains_key(value: object, key: str) -> bool:
    """Return whether a nested JSON-compatible value contains ``key``."""
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


@pytest.mark.unit
def test_json_schema_removes_defaults_and_secret_examples() -> None:
    """No code default or secret example may enter exported schema artifacts."""
    secret_canary = "schema-export-secret-canary"
    public_default_canary = "schema-export-public-default-canary"

    class Settings(BaseModel):
        token: SecretStr = Field(
            default=SecretStr(secret_canary),
            examples=[secret_canary],
            description="External token",
        )
        service_name: str = Field(
            default=public_default_canary,
            examples=["safe-service-example"],
        )

    exported = export_json_schema(Settings)
    rendered = json.dumps(exported, sort_keys=True)

    assert exported["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert _contains_key(exported, "default") is False
    assert secret_canary not in rendered
    assert public_default_canary not in rendered
    assert exported["properties"]["service_name"]["examples"] == [
        "safe-service-example"
    ]


@pytest.mark.unit
def test_json_schema_exports_paths_aliases_types_and_constraints() -> None:
    """Structured field metadata supports tools without parsing Markdown."""

    class Database(BaseModel):
        host: str = Field(description="Database hostname")
        port: int = Field(default=5432, gt=0, le=65535)

    class Settings(BaseModel):
        model_config = ConfigDict(validate_by_name=True)

        database: Database = Field(alias="db")
        region: str = Field(validation_alias=AliasChoices("region", "legacy_region"))

    exported = export_json_schema(Settings)
    fields = {field["python_path"]: field for field in exported["x-vltconfig-fields"]}

    assert fields["database"]["vault_path"] == "db"
    assert fields["database.host"] == {
        "python_path": "database.host",
        "vault_path": "db.host",
        "accepted_paths": ["db.host", "database.host"],
        "type": "str",
        "required": True,
        "nullable": False,
        "secret": False,
        "description": "Database hostname",
        "constraints": {},
    }
    assert fields["database.port"]["constraints"] == {"gt": 0, "le": 65535}
    assert fields["region"]["accepted_paths"] == [
        "region",
        "legacy_region",
    ]


@pytest.mark.unit
def test_markdown_reference_is_deterministic_and_value_free() -> None:
    """Markdown lists structural metadata without defaults or examples."""
    secret_canary = "markdown-secret-canary"

    class Settings(BaseModel):
        token: SecretStr = Field(
            default=SecretStr(secret_canary),
            examples=[secret_canary],
            description="API token | never printed",
        )
        workers: int = Field(gt=0, description="Worker count")

    schema = build_model_schema(Settings)
    first = render_markdown_reference(schema)
    second = render_markdown_reference(Settings)

    assert first == second
    assert secret_canary not in first
    assert "| `token` | `token` | `token` | `SecretStr` | no | secret" in first
    assert "API token \\| never printed" in first
    assert "gt=0" in first
    assert "Worker count" in first


@pytest.mark.unit
def test_rendered_json_schema_is_deterministic_valid_json() -> None:
    """The renderer produces stable parseable JSON with a trailing newline."""

    class Settings(BaseModel):
        value: str

    rendered = render_json_schema(Settings)

    assert rendered.endswith("\n")
    assert json.loads(rendered) == export_json_schema(Settings)
    assert render_json_schema(Settings) == rendered


@pytest.mark.unit
def test_export_formats_indexed_alias_paths() -> None:
    """Structured metadata distinguishes list indexes from mapping keys."""

    class Settings(BaseModel):
        value: str = Field(validation_alias=AliasPath("items", 0, "value"))

    field = export_json_schema(Settings)["x-vltconfig-fields"][0]

    assert field["vault_path"] == "items[0].value"
