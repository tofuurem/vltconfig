"""Tests for safe importable Pydantic model references."""

import sys
from pathlib import Path

import pytest

from vltconfig.errors import ModelReferenceError
from vltconfig.model_loader import load_model


@pytest.mark.unit
def test_loads_a_pydantic_model_without_instantiating_it(tmp_path: Path) -> None:
    """Resolution imports the class but never executes settings construction."""
    module_name = "vltconfig_loader_valid_model"
    (tmp_path / f"{module_name}.py").write_text(
        "from pydantic import BaseModel\n"
        "calls = []\n"
        "class Settings(BaseModel):\n"
        "    token: str\n"
        "    def __init__(self, **values):\n"
        "        calls.append('constructed')\n"
        "        super().__init__(**values)\n"
    )
    sys.path.insert(0, str(tmp_path))
    try:
        model = load_model(f"{module_name}:Settings")
        module = sys.modules[module_name]
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop(module_name, None)

    assert model.__name__ == "Settings"
    assert module.calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "reference",
    ["", "module", ":Settings", "module:", "module:Settings:Extra", "module:.Settings"],
)
def test_rejects_malformed_references(reference: str) -> None:
    """Malformed input receives one stable usage category."""
    with pytest.raises(ModelReferenceError):
        load_model(reference)


@pytest.mark.unit
def test_import_attribute_and_type_failures_are_safe(tmp_path: Path) -> None:
    """Loader errors omit import-time exception messages and require BaseModel."""
    canary = "model-loader-import-error-canary"
    broken_module = "vltconfig_loader_broken_model"
    plain_module = "vltconfig_loader_plain_object"
    (tmp_path / f"{broken_module}.py").write_text(f"raise RuntimeError({canary!r})\n")
    (tmp_path / f"{plain_module}.py").write_text("Settings = object()\n")
    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(ModelReferenceError) as broken:
            load_model(f"{broken_module}:Settings")
        with pytest.raises(ModelReferenceError) as missing:
            load_model(f"{plain_module}:Missing")
        with pytest.raises(ModelReferenceError) as plain:
            load_model(f"{plain_module}:Settings")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop(broken_module, None)
        sys.modules.pop(plain_module, None)

    diagnostics = "\n".join(
        (str(broken.value), repr(broken.value), str(missing.value), str(plain.value))
    )
    assert canary not in diagnostics
