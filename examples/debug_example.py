"""
Example: How to debug vltconfig with detailed logging and custom JSON path.

This example shows:
1. How to set custom JSON config path
2. How to enable detailed TRACE logging
3. How to see what's happening during configuration loading
"""

import os
import sys
from pathlib import Path

# 1. Configure detailed logging BEFORE importing vltconfig
from loguru import logger

logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    level="TRACE",  # Maximum verbosity
    format=(
        "<green>{time:HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}:{function}</cyan> - "
        "<level>{message}</level>"
    ),
)

# 2. Set environment variables for configuration
os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
os.environ["VAULT_TOKEN"] = "s.your-token"  # Or use AppRole/Userpass
os.environ["VAULT_APP_NAME"] = "myapp/config"
os.environ["VAULT_MOUNT_POINT"] = "secret"  # Optional, default is "secret"

# 3. Set custom JSON config path
# This should point to the DIRECTORY containing config.json
config_dir = Path(__file__).parent / "config"
os.environ["PYDANTIC_JSON_PATH"] = str(config_dir)

print(f"Looking for config.json in: {config_dir}")
print(f"Full path: {config_dir / 'config.json'}")
print("-" * 80)

# 4. Import vltconfig AFTER configuring logging
from vltconfig import VaultJsonConfig
from pydantic import Field


# 5. Define your configuration model
class AppConfig(VaultJsonConfig):
    """Application configuration loaded from multiple sources."""

    database_url: str = Field(
        default="postgresql://localhost/mydb",
        description="Database connection string",
    )
    api_key: str = Field(
        default="default-key",
        description="API key for external service",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )
    max_connections: int = Field(
        default=10,
        description="Maximum database connections",
    )


# 6. Load configuration
print("\n" + "=" * 80)
print("LOADING CONFIGURATION")
print("=" * 80 + "\n")

try:
    config = AppConfig()

    print("\n" + "=" * 80)
    print("CONFIGURATION LOADED SUCCESSFULLY")
    print("=" * 80 + "\n")

    # Print loaded configuration
    print("Configuration values:")
    print(f"  database_url: {config.database_url}")
    print(
        f"  api_key: {config.api_key[:10]}..."
        if len(config.api_key) > 10
        else f"  api_key: {config.api_key}"
    )
    print(f"  debug: {config.debug}")
    print(f"  max_connections: {config.max_connections}")

except Exception as e:
    print("\n" + "=" * 80)
    print("ERROR LOADING CONFIGURATION")
    print("=" * 80 + "\n")
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()


# Example of what you'll see in TRACE logs:
"""
18:30:15.123 | TRACE    | vltconfig.vault_source:__call__ - Starting Vault authentication to https://vault.example.com
18:30:15.124 | TRACE    | vltconfig.vault_source:_authenticate_vault - Trying token authentication
18:30:15.456 | TRACE    | vltconfig.vault_source:_authenticate_vault - Successfully authenticated with token
18:30:15.457 | TRACE    | vltconfig.vault_source:_get_secret_from_vault - Requesting secrets: path=myapp/config, mount=secret
18:30:15.789 | INFO     | vltconfig.vault_source:_get_secret_from_vault - Successfully loaded 5 secrets from Vault
18:30:15.790 | TRACE    | vltconfig.vault_source:__call__ - Cached secrets for https://vault.example.com:myapp/config:secret (TTL: 300s)
18:30:15.791 | TRACE    | vltconfig.json_source:_get_secret_from_json - Looking for config.json at: /path/to/config/config.json
18:30:15.792 | INFO     | vltconfig.json_source:__call__ - Successfully loaded config from JSON
"""
