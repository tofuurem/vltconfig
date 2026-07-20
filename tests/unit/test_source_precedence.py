"""Regression coverage for the compatibility-sensitive settings-source order."""

from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict

from vltconfig import VaultJsonConfig
from vltconfig.json_source import PydanticJSONSource
from vltconfig.vault_source import PydanticVaultSource


@pytest.mark.unit
def test_complete_settings_source_priority_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each source wins only after every higher-priority source is absent."""
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("VALUE=dotenv\n", encoding="utf-8")
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "value").write_text("file-secret\n", encoding="utf-8")

    vault_payload = {"value": "vault"}
    json_payload = {"value": "json"}

    def load_vault(_source: PydanticVaultSource) -> dict[str, str]:
        return vault_payload.copy()

    def load_json(_source: PydanticJSONSource) -> dict[str, str]:
        return json_payload.copy()

    monkeypatch.setattr(PydanticVaultSource, "__call__", load_vault)
    monkeypatch.setattr(PydanticJSONSource, "__call__", load_json)

    class Settings(VaultJsonConfig):
        model_config = SettingsConfigDict(
            env_file=dotenv_path,
            secrets_dir=secrets_dir,
        )

        value: str

    monkeypatch.setenv("VALUE", "environment")
    assert Settings(value="initializer").value == "environment"

    monkeypatch.delenv("VALUE")
    assert Settings(value="initializer").value == "vault"

    vault_payload.clear()
    assert Settings(value="initializer").value == "json"

    json_payload.clear()
    assert Settings(value="initializer").value == "initializer"
    assert Settings().value == "dotenv"

    dotenv_path.unlink()
    assert Settings().value == "file-secret"
