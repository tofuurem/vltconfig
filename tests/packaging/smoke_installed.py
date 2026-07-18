"""Smoke test executed with the built wheel, outside the source import path."""

import json
import os
import tempfile
from importlib import metadata
from pathlib import Path

from vltconfig import VaultJsonConfig


def main() -> None:
    """Verify public import, metadata, and JSON-only settings loading."""
    assert metadata.version("vltconfig") == "1.0.1"

    with tempfile.TemporaryDirectory() as directory:
        config_path = Path(directory) / "config.json"
        config_path.write_text(json.dumps({"service_name": "wheel-smoke"}))
        os.environ["PYDANTIC_JSON_PATH"] = directory

        class Settings(VaultJsonConfig):
            service_name: str

        settings = Settings()
        assert settings.service_name == "wheel-smoke"


if __name__ == "__main__":
    main()
