"""Load the example JSON source without contacting Vault or printing values."""

import os
from pathlib import Path

from examples.settings import AppConfig

_VAULT_VARIABLES = (
    "VAULT_ADDRESS",
    "VAULT_TOKEN",
    "VAULT_USERNAME",
    "VAULT_PASSWORD",
    "VAULT_ROLE_ID",
    "VAULT_SECRET_ID",
    "VAULT_APP_NAME",
    "VAULT_MOUNT_POINT",
)


def main() -> None:
    """Load and validate local JSON while keeping configuration values private."""
    for variable in _VAULT_VARIABLES:
        os.environ.pop(variable, None)
    config_dir = Path(__file__).parent / "config"
    os.environ["PYDANTIC_JSON_PATH"] = str(config_dir)

    settings = AppConfig()
    assert len(type(settings).model_fields) == 4
    print("Configuration loaded and validated; values were not displayed.")


if __name__ == "__main__":
    main()
