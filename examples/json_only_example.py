"""
Example: Using vltconfig with JSON only (without Vault).

This example shows how to use vltconfig when you don't have Vault
or want to use only JSON configuration for local development.
"""

import os
import sys
from pathlib import Path

# 1. Configure logging to see what's happening
from loguru import logger

logger.remove()
logger.add(
    sys.stdout,
    level="TRACE",  # Use TRACE to see that Vault is skipped
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)

# 2. Set path to config.json (NO Vault env vars!)
config_dir = Path(__file__).parent / "config"
os.environ["PYDANTIC_JSON_PATH"] = str(config_dir)

print(f"Loading config from: {config_dir / 'config.json'}")
print("No Vault env vars set - will use JSON only")
print("-" * 80)

# 3. Import and define configuration
from vltconfig import VaultJsonConfig
from pydantic import Field


class AppConfig(VaultJsonConfig):
    """Application configuration - loads from JSON when Vault not available."""

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


# 4. Load configuration
print("\n" + "=" * 80)
print("LOADING CONFIGURATION")
print("=" * 80 + "\n")

config = AppConfig()

print("\n" + "=" * 80)
print("CONFIGURATION LOADED")
print("=" * 80 + "\n")

# Print configuration
print("Configuration values:")
print(f"  database_url: {config.database_url}")
print(f"  api_key: {config.api_key}")
print(f"  debug: {config.debug}")
print(f"  max_connections: {config.max_connections}")

print("\n" + "=" * 80)
print("Configuration sources used:")
print("  1. ❌ Vault - skipped (no env vars)")
print("  2. ✅ JSON - loaded from config.json")
print("  3. ✅ Defaults - used for fields not in JSON")
print("=" * 80)

# What you'll see in logs:
"""
18:30:15 | TRACE    | Vault configuration not available, skipping Vault source: ...
18:30:15 | TRACE    | Looking for config.json at: /path/to/config/config.json
18:30:15 | INFO     | Successfully loaded config from JSON
"""

# You can also override with environment variables
print("\n" + "=" * 80)
print("EXAMPLE: Override with environment variable")
print("=" * 80)

os.environ["DEBUG"] = "true"
config2 = AppConfig()
print(f"debug value: {config2.debug}")  # Will be True from env var

print("\n✅ JSON-only configuration works perfectly!")
