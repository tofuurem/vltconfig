"""Debug vltconfig with detailed logging and a custom JSON path."""

import os
import sys
import traceback
from pathlib import Path

from loguru import logger
from pydantic import Field

from vltconfig import VaultJsonConfig


class AppConfig(VaultJsonConfig):
    """Application configuration loaded from multiple sources."""

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
    """Configure logging, load settings, and show safe diagnostics."""
    logger.remove()
    logger.add(
        sys.stdout,
        level="TRACE",
        format=(
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
    os.environ["VAULT_TOKEN"] = "example-only-token"
    os.environ["VAULT_APP_NAME"] = "myapp/config"
    os.environ["VAULT_MOUNT_POINT"] = "secret"

    config_dir = Path(__file__).parent / "config"
    os.environ["PYDANTIC_JSON_PATH"] = str(config_dir)

    print(f"Looking for config.json in: {config_dir}")
    print(f"Full path: {config_dir / 'config.json'}")

    try:
        config = AppConfig()
    except Exception:
        print("Configuration loading failed; inspect the redacted traceback.")
        traceback.print_exc()
        raise

    print("Configuration loaded successfully")
    print(f"  database_url: {config.database_url}")
    print("  api_key: <redacted>")
    print(f"  debug: {config.debug}")
    print(f"  max_connections: {config.max_connections}")


if __name__ == "__main__":
    main()
