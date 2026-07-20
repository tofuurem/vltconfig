"""Tests for the optional commented YAML template renderer."""

import importlib

import pytest
from pydantic import AliasPath, BaseModel, Field, SecretStr
from ruamel.yaml import YAML

from vltconfig.errors import YAMLDependencyError
from vltconfig.template import REQUIRED_PLACEHOLDER, render_yaml_template


@pytest.mark.unit
def test_yaml_template_preserves_order_and_adds_safe_comments() -> None:
    """Required nested leaves render in model order with type descriptions."""

    class Database(BaseModel):
        host: str = Field(description="Primary database host")
        port: int = 5432

    class Settings(BaseModel):
        database: Database = Field(description="Database connection")
        api_token: SecretStr = Field(description="External API token")
        workers: int = 4

    rendered = render_yaml_template(Settings)

    assert rendered == render_yaml_template(Settings)
    assert rendered.index("database:") < rendered.index("api_token:")
    assert "database:  # Database — Database connection" in rendered
    assert "host: __VLTCFG_REQUIRED__  # str — Primary database host" in rendered
    assert "api_token: __VLTCFG_REQUIRED__ # SecretStr — External API token" in rendered
    assert "workers:" not in rendered

    loaded = YAML(typ="safe").load(rendered)
    assert loaded == {
        "database": {"host": REQUIRED_PLACEHOLDER},
        "api_token": REQUIRED_PLACEHOLDER,
    }


@pytest.mark.unit
def test_yaml_include_defaults_never_renders_secret_values() -> None:
    """YAML and JSON share the same secret/default inclusion semantics."""
    canary = "yaml-secret-default-canary"

    class Settings(BaseModel):
        endpoint: str
        workers: int = Field(default=4, description="Worker count")
        token: SecretStr = Field(
            default=SecretStr(canary),
            examples=[canary],
            description="Secret token",
        )

    rendered = render_yaml_template(Settings, include_defaults=True)

    assert canary not in rendered
    assert "endpoint: __VLTCFG_REQUIRED__  # str" in rendered
    assert "workers: 4 # int — Worker count" in rendered
    assert "token:" not in rendered


@pytest.mark.unit
def test_yaml_comments_sanitize_multiline_and_comment_markers() -> None:
    """Descriptions stay on one comment line without changing YAML data."""

    class Settings(BaseModel):
        value: str = Field(description="Line one\nline two # metadata")

    rendered = render_yaml_template(Settings)

    assert "# str — Line one line two # metadata" in rendered
    assert YAML(typ="safe").load(rendered) == {"value": REQUIRED_PLACEHOLDER}


@pytest.mark.unit
def test_yaml_dependency_missing_has_concise_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A base-only install fails lazily with the named extra hint."""
    real_import_module = importlib.import_module

    def missing_ruamel(name: str) -> object:
        if name.startswith("ruamel"):
            raise ModuleNotFoundError("optional dependency unavailable", name=name)
        return real_import_module(name)

    monkeypatch.setattr(importlib, "import_module", missing_ruamel)

    class Settings(BaseModel):
        value: str

    with pytest.raises(YAMLDependencyError, match=r"vltconfig\[yaml\]"):
        render_yaml_template(Settings)


@pytest.mark.unit
def test_yaml_renders_indexed_alias_paths() -> None:
    """Comment-aware conversion preserves list structures from canonical paths."""

    class Settings(BaseModel):
        value: str = Field(validation_alias=AliasPath("items", 0, "value"))

    rendered = render_yaml_template(Settings)

    assert YAML(typ="safe").load(rendered) == {
        "items": [{"value": REQUIRED_PLACEHOLDER}]
    }


@pytest.mark.unit
def test_yaml_loader_reraises_unrelated_missing_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only absence of ruamel itself is translated into the extra hint."""

    def unrelated_missing(_name: str) -> object:
        raise ModuleNotFoundError("unrelated dependency", name="unrelated")

    monkeypatch.setattr(importlib, "import_module", unrelated_missing)

    class Settings(BaseModel):
        value: str

    with pytest.raises(ModuleNotFoundError, match="unrelated dependency"):
        render_yaml_template(Settings)
