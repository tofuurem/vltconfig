# vault-pydantic-simple - Analysis & Improvements

**Date**: 2025-10-21
**Version**: 0.5.0
**Status**: Comprehensive analysis and improvement plan

---

## 📊 Project Assessment

| Category | Score | Comment |
|----------|-------|---------|
| Functionality | 7/10 | Works but needs improvements |
| Type Hints | 4/10 | Partial, incomplete |
| Documentation | 3/10 | Missing docstrings |
| Testing | 0/10 | No tests at all |
| Security | 5/10 | Some risks |
| Performance | 4/10 | No caching, no retry |

---

## 🎯 Important Notes

### Project-Specific Rules

This project has **different rules** from standard CODESTYLE.md:

1. **NOT Async** - pydantic/pydantic-settings are synchronous, can't make async
2. **English Docstrings** - all documentation in English (not Russian)
3. **Synchronous I/O** - hvac client is sync, file I/O is sync
4. **Specific Exception Handling** - not `except Exception`, specific types

### What's Already OK

- `dev/` folder is in `.gitignore` - no security issue
- Current architecture is reasonable
- Settings sources pattern is good

---

## 🔴 Critical Issues

### 1. Missing Type Hints

**Problem**: Not all parameters and return types are annotated.

**Files**: All `vlt/*.py`

**Example**:
```python
# Current (BAD)
def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
    return self._result_config[field_name]

# Should be (GOOD)
def get_field_value(
    self, field: FieldInfo, field_name: str
) -> tuple[str | int | float | bool | None, str, bool]:
    """Get field value from config.

    :param field: Field information from pydantic
    :param field_name: Name of the field to retrieve
    :return: Tuple of (value, field_name, is_set)
    """
    return self._result_config.get(field_name, (None, field_name, False))
```

**Priority**: 🔴 CRITICAL

---

### 2. Missing Docstrings

**Problem**: No docstrings in English for any function/class.

**Files**: All `vlt/*.py`

**Example**:
```python
# Current (BAD)
class VaultAccess(BaseSettings):
    address: str = Field(alias="VAULT_ADDRESS")

# Should be (GOOD)
class VaultAccess(BaseSettings):
    """Vault connection configuration.

    Supports multiple authentication methods:
    - Token-based (VAULT_TOKEN)
    - Username/Password (VAULT_USERNAME + VAULT_PASSWORD)
    - AppRole (VAULT_ROLE_ID + VAULT_SECRET_ID) - to be added
    """
    address: str = Field(alias="VAULT_ADDRESS")
```

**Priority**: 🔴 CRITICAL

---

### 3. No Tests

**Problem**: Zero test coverage.

**Solution**: Create comprehensive test suite:

```
tests/
├── __init__.py
├── conftest.py                    # pytest fixtures
├── unit/
│   ├── test_config.py            # VaultAccess tests
│   ├── test_vault_source.py      # PydanticVaultSource tests
│   └── test_json_source.py       # PydanticJSONSource tests
└── integration/
    ├── test_vault_integration.py # Real Vault connection
    └── test_full_config.py       # Full config loading
```

**Priority**: 🔴 CRITICAL

---

### 4. Too Broad Exception Handling

**Problem**: `except Exception` catches everything.

**Files**: `vlt/vault_source.py:42-46`, `vlt/json_source.py:29-33`

**Current**:
```python
def __call__(self) -> dict[str, Any]:
    try:
        self._get_secret_from_vault()
    except Exception as ex:  # ❌ Too broad
        logger.error(ex)
    return self._result_config
```

**Should be**:
```python
def __call__(self) -> dict[str, Any]:
    """Load configuration from Vault.

    :return: Configuration dictionary
    """
    try:
        self._get_secret_from_vault()
    except hvac.exceptions.Forbidden as ex:
        logger.error("Access denied to Vault: {}", ex)
    except hvac.exceptions.InvalidPath as ex:
        logger.error("Path not found in Vault: {}", self.cfg.app_name)
    except hvac.exceptions.VaultError as ex:
        logger.error("Vault error: {}", ex)
    except (ConnectionError, TimeoutError) as ex:
        logger.error("Network error connecting to Vault: {}", ex)
    return self._result_config
```

**Priority**: 🔴 CRITICAL

---

### 5. No URL Validation

**Problem**: VAULT_ADDRESS not validated.

**File**: `vlt/config.py:10`

**Solution**:
```python
from pydantic import Field, HttpUrl, field_validator

class VaultAccess(BaseSettings):
    """Vault connection configuration."""

    address: HttpUrl = Field(alias="VAULT_ADDRESS")  # Auto-validates URL

    @field_validator("address")
    @classmethod
    def validate_vault_address(cls, v: HttpUrl) -> HttpUrl:
        """Validate Vault address is http/https.

        :param v: URL to validate
        :return: Validated URL
        :raises ValueError: If URL scheme is invalid
        """
        if v.scheme not in ["http", "https"]:
            raise ValueError("Vault address must use http or https")
        return v
```

**Priority**: 🔴 CRITICAL

---

### 6. Incorrect ValidationError Usage

**Problem**: Using `raise ValidationError()` directly in model_validator.

**File**: `vlt/config.py:18-22`

**Current**:
```python
@model_validator(mode="after")
def validate_creds(self) -> Self:
    if self.token is None and (self.username is None or self.password is None):
        raise ValidationError(  # ❌ Wrong
            "Must be some fields for auth token or username + password"
        )
    return self
```

**Should be**:
```python
@model_validator(mode="after")
def validate_creds(self) -> Self:
    """Validate authentication credentials are provided.

    :return: Validated model instance
    :raises ValueError: If no valid credentials provided
    """
    if self.token is None and (self.username is None or self.password is None):
        raise ValueError(
            "Must provide either VAULT_TOKEN or VAULT_USERNAME + VAULT_PASSWORD"
        )
    return self
```

**Priority**: 🔴 CRITICAL

---

## 🟠 High Priority Improvements

### 7. Improve Logging

**Problem**: Too verbose, logs when files not found.

**Changes needed**:

1. **Use TRACE for auth flow**:
```python
logger.trace("Starting Vault authentication: {}", cfg.address)
logger.trace("Using auth method: {}", "token" if cfg.token else "userpass")
```

2. **Remove warnings for missing files**:
```python
# Current (BAD)
except Exception as ex:
    logger.warning(f"Load config without config.json - {ex}")

# Should be (GOOD)
except FileNotFoundError:
    logger.trace("config.json not found, skipping JSON source")
except Exception as ex:
    logger.error("Error loading JSON config: {}", ex)
```

3. **Success/failure only**:
```python
logger.info("Successfully loaded secrets from Vault")
logger.error("Failed to load secrets from Vault")
```

**Priority**: 🟠 HIGH

---

### 8. Add Caching

**Problem**: Every config instance queries Vault.

**Solution**:
```python
from datetime import datetime, timedelta
from typing import ClassVar

class PydanticVaultSource(PydanticBaseSettingsSource):
    """Vault configuration source with caching.

    Caches secrets for TTL seconds to reduce Vault load.
    """

    _cache: ClassVar[dict[str, tuple[dict[str, Any], datetime]]] = {}
    _cache_ttl: ClassVar[int] = 300  # 5 minutes

    def __call__(self) -> dict[str, Any]:
        """Load configuration from Vault with caching.

        :return: Configuration dictionary
        """
        cfg = VaultAccess()
        cache_key = f"{cfg.address}:{cfg.app_name}:{cfg.mount_point}"

        # Check cache
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self._cache_ttl):
                logger.trace("Using cached Vault secrets")
                return data

        # Load from Vault
        try:
            self._get_secret_from_vault()
            self._cache[cache_key] = (self._result_config, datetime.now())
            logger.info("Loaded secrets from Vault ({} keys)", len(self._result_config))
        except Exception as ex:
            logger.error("Failed to load from Vault: {}", ex)

        return self._result_config
```

**Priority**: 🟠 HIGH

---

### 9. Add Retry Logic

**Problem**: Network failures cause immediate failure.

**Solution**:
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

class PydanticVaultSource(PydanticBaseSettingsSource):
    """Vault configuration source with retry logic."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            hvac.exceptions.VaultDown,
            ConnectionError,
            TimeoutError
        )),
        reraise=True
    )
    def _get_secret_from_vault(self) -> None:
        """Fetch secrets from Vault with retry.

        Retries up to 3 times with exponential backoff for:
        - Vault down
        - Connection errors
        - Timeouts

        :raises VaultError: If all retries fail
        """
        cfg = VaultAccess()
        client = _auth_by_userpass(cfg)

        logger.trace("Requesting secrets: path={}, mount={}", cfg.app_name, cfg.mount_point)

        secret = client.secrets.kv.v2.read_secret_version(
            path=cfg.app_name,
            mount_point=cfg.mount_point
        )
        self._result_config = secret["data"]["data"]
```

**Dependencies**: Add `tenacity>=8.0.0` to `pyproject.toml`

**Priority**: 🟠 HIGH

---

### 10. Add AppRole Authentication

**Problem**: Only supports token and userpass.

**Solution**:
```python
class VaultAccess(BaseSettings):
    """Vault connection configuration.

    Supported authentication methods:
    1. Token (VAULT_TOKEN)
    2. Username/Password (VAULT_USERNAME + VAULT_PASSWORD)
    3. AppRole (VAULT_ROLE_ID + VAULT_SECRET_ID)
    """

    address: HttpUrl = Field(alias="VAULT_ADDRESS")
    token: str | None = Field(alias="VAULT_TOKEN", default=None)
    username: str | None = Field(alias="VAULT_USERNAME", default=None)
    password: str | None = Field(alias="VAULT_PASSWORD", default=None)
    role_id: str | None = Field(alias="VAULT_ROLE_ID", default=None)
    secret_id: str | None = Field(alias="VAULT_SECRET_ID", default=None)
    app_name: str = Field(alias="VAULT_APP_NAME")
    mount_point: str = Field(alias="VAULT_MOUNT_POINT", default=DEFAULT_MOUNT_POINT)

    @model_validator(mode="after")
    def validate_creds(self) -> Self:
        """Validate at least one auth method is provided.

        :return: Validated instance
        :raises ValueError: If no valid auth credentials
        """
        has_token = self.token is not None
        has_userpass = self.username is not None and self.password is not None
        has_approle = self.role_id is not None and self.secret_id is not None

        if not (has_token or has_userpass or has_approle):
            raise ValueError(
                "Must provide one of: VAULT_TOKEN, "
                "VAULT_USERNAME+PASSWORD, or VAULT_ROLE_ID+SECRET_ID"
            )
        return self


def _authenticate_vault(cfg: VaultAccess) -> hvac.Client:
    """Authenticate to Vault using configured method.

    Tries authentication methods in order:
    1. Token
    2. AppRole
    3. Username/Password

    :param cfg: Vault configuration
    :return: Authenticated Vault client
    :raises ValueError: If authentication fails
    """
    client = hvac.Client(url=str(cfg.address))

    # Try token first
    if cfg.token:
        client.token = cfg.token
        if not client.is_authenticated():
            raise ValueError("Failed to authenticate with token")
        logger.trace("Authenticated with token")
        return client

    # Try AppRole
    if cfg.role_id and cfg.secret_id:
        try:
            resp = client.auth.approle.login(
                role_id=cfg.role_id,
                secret_id=cfg.secret_id
            )
            client.token = resp["auth"]["client_token"]
            logger.trace("Authenticated with AppRole")
            return client
        except hvac.exceptions.InvalidRequest as ex:
            raise ValueError(f"AppRole authentication failed: {ex}") from ex

    # Try userpass
    if cfg.username and cfg.password:
        try:
            resp = client.auth.userpass.login(
                username=cfg.username,
                password=cfg.password
            )
            client.token = resp["auth"]["client_token"]
            logger.trace("Authenticated with username/password")
            return client
        except hvac.exceptions.InvalidRequest as ex:
            raise ValueError(f"Userpass authentication failed: {ex}") from ex

    raise ValueError("No valid authentication method provided")
```

**Priority**: 🟠 HIGH

---

## 🟡 Medium Priority

### 11. Unified Source (Optional)

**Idea**: Single source that handles both Vault and JSON.

**Pros**:
- Single point of logging
- Clear which source is used
- Less duplicate code

**Cons**:
- More complex
- Violates single responsibility

**Discussion needed**: Is this worth it?

---

### 12. GitHub Actions for Tests

**File**: `.github/workflows/tests.yml`

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync --group dev

      - name: Run ruff
        run: |
          uv run ruff check .
          uv run ruff format --check .

      - name: Run mypy
        run: uv run mypy vlt/

      - name: Run tests
        run: uv run pytest --cov=vlt --cov-report=xml --cov-report=term

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        if: matrix.python-version == '3.13'
        with:
          file: ./coverage.xml
```

**Priority**: 🟡 MEDIUM

---

### 13. Expand README.md

**Add**:
- Badges (PyPI version, tests, coverage, Python versions, license)
- Detailed usage examples
- How it works section
- FAQ
- Troubleshooting

**Example badges**:
```markdown
[![PyPI version](https://badge.fury.io/py/vault-pydantic-simple.svg)](https://badge.fury.io/py/vault-pydantic-simple)
[![Tests](https://github.com/user/vault-config/workflows/Tests/badge.svg)](https://github.com/user/vault-config/actions)
[![Coverage](https://codecov.io/gh/user/vault-config/branch/main/graph/badge.svg)](https://codecov.io/gh/user/vault-config)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
```

**Priority**: 🟡 MEDIUM

---

### 14. Add ruff.toml

**File**: `ruff.toml`

```toml
[lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "UP",     # pyupgrade
    "ANN",    # annotations
    "B",      # bugbear
    "C4",     # comprehensions
    "RUF",    # ruff specific
]

ignore = [
    "ANN101",  # Missing type annotation for self
    "ANN102",  # Missing type annotation for cls
]

[lint.per-file-ignores]
"__init__.py" = ["F401"]
"tests/*" = ["ANN201", "ANN001"]

[format]
quote-style = "double"
indent-style = "space"
line-ending = "auto"
line-length = 120
```

**Priority**: 🟡 MEDIUM

---

## 🟢 Low Priority

### 15. CLI Utility

**Purpose** (needs discussion):
- Test Vault connection
- Validate configuration
- Show loaded config
- Debug authentication

**Example**:
```bash
# Test connection
vault-config test-connection

# Show config (masked secrets)
vault-config show-config

# Validate setup
vault-config validate
```

**Implementation**: `vlt/cli.py` with click

**Priority**: 🟢 LOW (discuss purpose first)

---

### 16. Add .env.example

**File**: `.env.example`

```bash
# Vault Configuration
VAULT_ADDRESS=https://vault.example.com

# Authentication - choose ONE method:

# Method 1: Token
VAULT_TOKEN=s.your-vault-token-here

# Method 2: Username/Password
# VAULT_USERNAME=your-username
# VAULT_PASSWORD=your-password

# Method 3: AppRole
# VAULT_ROLE_ID=your-role-id
# VAULT_SECRET_ID=your-secret-id

# Application Settings
VAULT_APP_NAME=myapp/config
VAULT_MOUNT_POINT=secret

# Optional: JSON config
# PYDANTIC_JSON_PATH=/path/to/config
```

**Priority**: 🟢 LOW

---

### 17. Add SECURITY.md

```markdown
# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.5.x   | :white_check_mark: |
| < 0.5   | :x:                |

## Reporting a Vulnerability

Please report security vulnerabilities to: rabbit_1399@icloud.com

**Do not open public issues for security vulnerabilities.**

## Security Best Practices

1. Use AppRole or Token authentication (prefer AppRole)
2. Never commit credentials to version control
3. Use environment variables for all secrets
4. Rotate tokens regularly
5. Use short-lived tokens when possible
```

**Priority**: 🟢 LOW

---

### 18. CHANGELOG.md

**Format**: TBD (needs discussion on format preference)

**Priority**: 🟢 LOW

---

## 📋 Summary

### Must Do (Critical)
- [ ] Add complete type hints
- [ ] Add English docstrings
- [ ] Create test suite (>80% coverage)
- [ ] Fix exception handling (specific types)
- [ ] Add URL validation
- [ ] Fix ValidationError usage

### Should Do (High Priority)
- [ ] Improve logging (trace, remove warnings)
- [ ] Add caching
- [ ] Add retry logic
- [ ] Add AppRole authentication

### Nice to Have (Medium)
- [ ] GitHub Actions
- [ ] Expand README
- [ ] Add ruff.toml

### Future (Low)
- [ ] CLI utility (discuss purpose)
- [ ] .env.example
- [ ] SECURITY.md
- [ ] CHANGELOG.md

### Not Needed (Excluded)
- ❌ Async (pydantic is sync)
- ❌ Prometheus metrics
- ❌ YAML support
- ❌ pre-commit hooks
- ❌ mypy.ini
- ❌ pytest.ini
- ❌ CONTRIBUTING.md

---

**Next Steps**:
1. Create detailed task breakdown in TASKS.md
2. Update CLAUDE.md with docs location
3. Start implementation phase by phase
