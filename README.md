# vltconfig

> Pydantic settings from HashiCorp Vault KV and JSON with caching and retry

[![PyPI version](https://badge.fury.io/py/vltconfig.svg)](https://pypi.org/project/vltconfig/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- ✨ **Multi-source configuration**: Load from Vault KV v2, JSON files, and environment variables
- 🔒 **Type-safe**: Full pydantic v2 validation with complete type hints
- 🔁 **Retry logic**: Automatic retries with exponential backoff for transient failures
- 💾 **Caching**: In-memory cache with configurable TTL (5 min default)
- 🔐 **Multiple auth methods**: Token, AppRole, and Username/Password authentication
- 🎯 **Fallback support**: Automatic fallback between authentication methods
- 📝 **Comprehensive logging**: Structured logging with loguru
- ✅ **Well tested**: 96%+ test coverage with 53 tests

## Installation

```bash
pip install vltconfig
```

## Quick Start

```python
from vltconfig import VaultJsonConfig
from pydantic import Field

# Define your configuration model
class AppConfig(VaultJsonConfig):
    database_url: str = Field(description="Database connection string")
    api_key: str = Field(description="API key for external service")
    debug: bool = Field(default=False, description="Debug mode")
    max_connections: int = Field(default=10, description="Max DB connections")

# Configuration is automatically loaded from:
# 1. Environment variables (highest priority)
# 2. HashiCorp Vault KV store
# 3. JSON file (config.json)
# 4. Default values (lowest priority)
config = AppConfig()

print(config.database_url)
print(config.api_key)
```

## Authentication

### Token Authentication

```python
import os

os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
os.environ["VAULT_TOKEN"] = "s.your-vault-token"
os.environ["VAULT_APP_NAME"] = "myapp/config"

config = AppConfig()
```

### AppRole Authentication

```python
import os

os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
os.environ["VAULT_ROLE_ID"] = "your-role-id"
os.environ["VAULT_SECRET_ID"] = "your-secret-id"
os.environ["VAULT_APP_NAME"] = "myapp/config"

config = AppConfig()
```

### Username/Password Authentication

```python
import os

os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
os.environ["VAULT_USERNAME"] = "readonly"
os.environ["VAULT_PASSWORD"] = "your-password"
os.environ["VAULT_APP_NAME"] = "myapp/config"

config = AppConfig()
```

### Authentication Fallback

If multiple authentication methods are configured, `vltconfig` will automatically try them in order:

1. Token authentication (`VAULT_TOKEN`)
2. AppRole authentication (`VAULT_ROLE_ID` + `VAULT_SECRET_ID`)
3. Username/Password authentication (`VAULT_USERNAME` + `VAULT_PASSWORD`)

This provides resilience if one authentication method is temporarily unavailable.

## Configuration

### Environment Variables

#### Required

- `VAULT_ADDRESS`: URL of the Vault server (e.g., `https://vault.example.com`)
- `VAULT_APP_NAME`: Path to secrets in Vault KV store (e.g., `myapp/config`)

#### Authentication (provide at least one method)

- `VAULT_TOKEN`: Vault authentication token
- `VAULT_USERNAME` + `VAULT_PASSWORD`: Username/password authentication
- `VAULT_ROLE_ID` + `VAULT_SECRET_ID`: AppRole authentication

#### Optional

- `VAULT_MOUNT_POINT`: Mount point for Vault KV engine (default: `secret`)
- `PYDANTIC_JSON_PATH`: Path to directory containing `config.json`
- `VAULT_CACHE_DISABLED`: Set to `true` to disable caching
- `VAULT_CACHE_TTL`: Cache TTL in seconds (default: `300`)

## Caching

`vltconfig` caches secrets from Vault for 5 minutes by default to reduce load on Vault servers:

```python
import os

# Disable caching
os.environ["VAULT_CACHE_DISABLED"] = "true"

# Or set custom TTL (in seconds)
os.environ["VAULT_CACHE_TTL"] = "600"  # 10 minutes

config = AppConfig()
```

## Retry Logic

Transient failures are automatically retried with exponential backoff:

- **Retries**: Up to 3 attempts
- **Backoff**: Exponential (2s, 4s, 8s)
- **Retryable errors**: Vault server down, connection errors, timeouts
- **Non-retryable errors**: Authentication failures, permission errors, invalid paths

## Custom Mount Point

If your Vault KV engine uses a custom mount point:

```python
import os

os.environ["VAULT_MOUNT_POINT"] = "custom-kv"
os.environ["VAULT_APP_NAME"] = "myapp/config"

config = AppConfig()
```

## JSON Configuration

You can also load configuration from a JSON file:

```python
import os

# Create config.json
os.makedirs("config", exist_ok=True)
with open("config/config.json", "w") as f:
    f.write('{"database_url": "postgresql://localhost/mydb", "debug": true}')

# Point to config directory
os.environ["PYDANTIC_JSON_PATH"] = "./config"

config = AppConfig()
```

## Configuration Priority

Values are loaded in the following priority order (highest to lowest):

1. **Environment variables** (highest priority)
2. **Vault KV store**
3. **JSON file** (`config.json`)
4. **Initialization parameters**
5. **.env file**
6. **Default values** (lowest priority)

## How It Works

`vltconfig` extends `pydantic-settings` to add custom settings sources:

```python
from vltconfig import VaultJsonConfig

class AppConfig(VaultJsonConfig):
    # Your fields here
    pass

# When you instantiate AppConfig(), it:
# 1. Connects to Vault using configured authentication
# 2. Fetches secrets from the specified path
# 3. Loads config.json if available
# 4. Merges all sources according to priority
# 5. Validates using pydantic
# 6. Returns type-safe configuration object
```

## Migration from vault-pydantic-simple

**⚠️ Breaking Change in v1.0.0**: The import path has changed.

If you're upgrading from `vault-pydantic-simple`:

```bash
# Uninstall old package
pip uninstall vault-pydantic-simple

# Install new package
pip install vltconfig
```

**Update your imports**:

```python
# Old (v0.x)
from vlt import VaultJsonConfig

# New (v1.0.0+)
from vltconfig import VaultJsonConfig
```

## Requirements

- Python >= 3.11
- pydantic >= 2.10.6
- pydantic-settings >= 2.7.1
- hvac >= 2.3.0 (HashiCorp Vault client)
- loguru >= 0.7.3 (logging)
- tenacity >= 9.0.0 (retry logic)

## Examples

The repository includes practical examples in the `examples/` directory:

### 📝 Available Examples

1. **[debug_example.py](examples/debug_example.py)** - Complete debugging setup
   - Shows how to enable detailed TRACE logging
   - Demonstrates custom JSON config path setup
   - Full example with all configuration sources

2. **[json_only_example.py](examples/json_only_example.py)** - JSON-only configuration
   - Using vltconfig without Vault (local development)
   - Shows graceful fallback when Vault is not configured
   - Environment variable override examples

### 🚀 Running Examples

```bash
# Clone the repository
git clone https://github.com/tofuurem/vltconfig.git
cd vltconfig

# Run the debug example
python examples/debug_example.py

# Run the JSON-only example
python examples/json_only_example.py
```

### 📂 Example Config Files

The `examples/config/` directory contains sample `config.json` files you can use as templates:

```json
{
  "database_url": "postgresql://localhost:5432/mydb",
  "api_key": "your-api-key-here",
  "debug": true,
  "max_connections": 20
}
```

## Development

```bash
# Clone repository
git clone https://github.com/tofuurem/vltconfig.git
cd vltconfig

# Install dependencies with uv
uv sync --group dev

# Run tests
uv run pytest --cov=vltconfig

# Run linters
uv run ruff check .
uv run mypy vltconfig/
```

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=vltconfig --cov-report=term-missing

# Run specific test file
uv run pytest tests/unit/test_config.py -v
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Links

- **PyPI**: https://pypi.org/project/vltconfig/
- **GitHub**: https://github.com/tofuurem/vltconfig
- **Issues**: https://github.com/tofuurem/vltconfig/issues

## Author

**tofuurem** - [rabbit_1399@icloud.com](mailto:rabbit_1399@icloud.com)

---

Made with ❤️ using Python and Pydantic
