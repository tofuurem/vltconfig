"""Use vltconfig with JSON only, without Vault configuration."""

import os
import sys
from pathlib import Path

from loguru import logger
from pydantic import Field

from vltconfig import VaultJsonConfig


class AppConfig(VaultJsonConfig):
    """Application configuration loaded from JSON when Vault is absent."""

    database_url: str = Field(
        default="postgresql://localhost/mydb",
        description="Database connection string",
    )
    api_key: str = Field(
        default="example-api-key",
        description="API key for external service",
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    max_connections: int = Field(
        default=10,
        description="Maximum database connections",
    )


def main() -> None:
    """Load JSON settings and demonstrate a safe environment override."""
    logger.remove()
    logger.add(
        sys.stdout,
        level="TRACE",
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | <level>{message}</level>"
        ),
    )

    config_dir = Path(__file__).parent / "config"
    os.environ["PYDANTIC_JSON_PATH"] = str(config_dir)

    config = AppConfig()
    print(f"Loaded config from: {config_dir / 'config.json'}")
    print(f"  database_url: {config.database_url}")
    print("  api_key: <redacted>")
    print(f"  debug: {config.debug}")
    print(f"  max_connections: {config.max_connections}")

    os.environ["DEBUG"] = "true"
    overridden = AppConfig()
    print(f"Environment override applied: debug={overridden.debug}")


if __name__ == "__main__":
    main()
