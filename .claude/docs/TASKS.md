# vault-pydantic-simple - Implementation Tasks

**Created**: 2025-10-21
**Status**: Planning
**Target Coverage**: 80%+

---

## 📋 Task Breakdown

All tasks organized by priority and phase. Each task is small and actionable.

---

## Phase 1: Critical Fixes (Week 1-2)

### Task 1.1: Add Type Hints to config.py ⏱️ 1h

**File**: `vlt/config.py`

**Subtasks**:
- [ ] Add return type to `validate_creds` method
- [ ] Ensure all Field definitions have explicit types
- [ ] Add type hints to any helper functions
- [ ] Run `mypy vlt/config.py` to verify

**Acceptance Criteria**:
- `mypy vlt/config.py` passes with no errors
- All public methods/functions fully typed

---

### Task 1.2: Add Type Hints to vault_source.py ⏱️ 2h

**File**: `vlt/vault_source.py`

**Subtasks**:
- [ ] Fix `get_field_value` return type from `Any` to specific union
- [ ] Add type hints to `_auth_by_userpass` parameters and return
- [ ] Add type hints to `_get_secret_from_vault`
- [ ] Add type hints to `__init__` and `__call__`
- [ ] Run `mypy vlt/vault_source.py` to verify

**Acceptance Criteria**:
- No `Any` types (except where unavoidable)
- All methods have complete type hints
- mypy passes

---

### Task 1.3: Add Type Hints to json_source.py ⏱️ 1h

**File**: `vlt/json_source.py`

**Subtasks**:
- [ ] Fix `get_field_value` return type
- [ ] Add type hints to all methods
- [ ] Run `mypy vlt/json_source.py` to verify

**Acceptance Criteria**:
- Complete type coverage
- mypy passes

---

### Task 1.4: Add Type Hints to __init__.py ⏱️ 30min

**File**: `vlt/__init__.py`

**Subtasks**:
- [ ] Add type hints to `settings_customise_sources` return type
- [ ] Verify all imports are typed
- [ ] Run `mypy vlt/__init__.py` to verify

---

### Task 1.5: Add English Docstrings to config.py ⏱️ 1h

**File**: `vlt/config.py`

**Subtasks**:
- [ ] Add class docstring to `VaultAccess`
- [ ] Add docstring to `validate_creds` method
- [ ] Document all fields with descriptions
- [ ] Follow Google/NumPy docstring style

**Example**:
```python
class VaultAccess(BaseSettings):
    """Vault connection configuration.

    Supports multiple authentication methods:
    - Token-based authentication (VAULT_TOKEN)
    - Username/Password authentication (VAULT_USERNAME + VAULT_PASSWORD)
    - AppRole authentication (VAULT_ROLE_ID + VAULT_SECRET_ID) [coming soon]

    All configuration is loaded from environment variables.
    """

    address: HttpUrl = Field(
        alias="VAULT_ADDRESS",
        description="URL of the Vault server (e.g., https://vault.example.com)"
    )
```

**Acceptance Criteria**:
- All classes have docstrings
- All public methods have docstrings
- Docstrings explain parameters and return values

---

### Task 1.6: Add English Docstrings to vault_source.py ⏱️ 1.5h

**File**: `vlt/vault_source.py`

**Subtasks**:
- [ ] Add class docstring to `PydanticVaultSource`
- [ ] Add docstring to `_auth_by_userpass`
- [ ] Add docstring to `_get_secret_from_vault`
- [ ] Add docstring to `__call__` and `get_field_value`

**Acceptance Criteria**:
- Complete docstring coverage
- Clear explanation of authentication flow

---

### Task 1.7: Add English Docstrings to json_source.py ⏱️ 1h

**File**: `vlt/json_source.py`

**Subtasks**:
- [ ] Add class docstring to `PydanticJSONSource`
- [ ] Add docstrings to all methods
- [ ] Explain file search logic

---

### Task 1.8: Add English Docstrings to __init__.py ⏱️ 30min

**File**: `vlt/__init__.py`

**Subtasks**:
- [ ] Add class docstring to `VaultJsonConfig`
- [ ] Document settings source priority
- [ ] Add docstring to `settings_customise_sources`

---

### Task 1.9: Fix Exception Handling in vault_source.py ⏱️ 2h

**File**: `vlt/vault_source.py`

**Subtasks**:
- [ ] Replace `except Exception` with specific hvac exceptions
- [ ] Add handling for `hvac.exceptions.Forbidden`
- [ ] Add handling for `hvac.exceptions.InvalidPath`
- [ ] Add handling for `hvac.exceptions.VaultError`
- [ ] Add handling for `ConnectionError` and `TimeoutError`
- [ ] Update logging for each exception type
- [ ] Test each exception path

**Example**:
```python
try:
    self._get_secret_from_vault()
except hvac.exceptions.Forbidden as ex:
    logger.error("Access denied to Vault path {}: {}", cfg.app_name, ex)
except hvac.exceptions.InvalidPath as ex:
    logger.error("Path {} not found in Vault mount {}", cfg.app_name, cfg.mount_point)
except hvac.exceptions.VaultError as ex:
    logger.error("Vault error: {}", ex)
except (ConnectionError, TimeoutError) as ex:
    logger.error("Network error connecting to {}: {}", cfg.address, ex)
```

**Acceptance Criteria**:
- No broad `except Exception`
- Each exception type has specific handling
- Helpful error messages

---

### Task 1.10: Fix Exception Handling in json_source.py ⏱️ 1h

**File**: `vlt/json_source.py`

**Subtasks**:
- [ ] Replace `except Exception` with specific exceptions
- [ ] Handle `FileNotFoundError` separately
- [ ] Handle `json.JSONDecodeError` separately
- [ ] Handle `PermissionError` separately
- [ ] Update logging (remove warning for missing file)

**Example**:
```python
try:
    self._get_secret_from_json()
except FileNotFoundError:
    logger.trace("config.json not found, skipping JSON source")
except json.JSONDecodeError as ex:
    logger.error("Invalid JSON in config.json: {}", ex)
except PermissionError as ex:
    logger.error("Permission denied reading config.json: {}", ex)
```

**Acceptance Criteria**:
- Specific exception handling
- No warnings for missing files (use trace)

---

### Task 1.11: Add URL Validation ⏱️ 1.5h

**File**: `vlt/config.py`

**Subtasks**:
- [ ] Change `address` type to `HttpUrl`
- [ ] Add `field_validator` for address validation
- [ ] Ensure scheme is http/https
- [ ] Test with valid/invalid URLs
- [ ] Update tests

**Code**:
```python
from pydantic import HttpUrl, field_validator

class VaultAccess(BaseSettings):
    address: HttpUrl = Field(alias="VAULT_ADDRESS")

    @field_validator("address")
    @classmethod
    def validate_vault_address(cls, v: HttpUrl) -> HttpUrl:
        """Validate Vault address uses http or https scheme.

        :param v: URL to validate
        :return: Validated URL
        :raises ValueError: If URL scheme is not http/https
        """
        if v.scheme not in ["http", "https"]:
            raise ValueError(f"Vault address must use http or https, got: {v.scheme}")
        return v
```

**Acceptance Criteria**:
- URLs validated at model creation
- Invalid URLs raise clear errors
- Tests cover edge cases

---

### Task 1.12: Fix ValidationError Usage ⏱️ 30min

**File**: `vlt/config.py`

**Subtasks**:
- [ ] Replace `raise ValidationError(...)` with `raise ValueError(...)`
- [ ] Update error message for clarity
- [ ] Test validation works correctly

**Code**:
```python
@model_validator(mode="after")
def validate_creds(self) -> Self:
    """Validate at least one authentication method is provided.

    :return: Validated model instance
    :raises ValueError: If no valid authentication credentials provided
    """
    if self.token is None and (self.username is None or self.password is None):
        raise ValueError(
            "Must provide either VAULT_TOKEN or VAULT_USERNAME + VAULT_PASSWORD"
        )
    return self
```

**Acceptance Criteria**:
- No direct `ValidationError` raises
- Error message is clear
- Validation still works

---

## Phase 2: Testing (Week 2-3)

### Task 2.1: Setup Test Infrastructure ⏱️ 2h

**Subtasks**:
- [ ] Create `tests/` directory structure
- [ ] Create `tests/__init__.py`
- [ ] Create `tests/conftest.py` with fixtures
- [ ] Add pytest dependencies to `pyproject.toml`:
  ```toml
  [dependency-groups]
  dev = [
      "pytest>=8.0.0",
      "pytest-cov>=4.1.0",
      "pytest-env>=1.1.0",
  ]
  ```
- [ ] Create basic fixture for VaultAccess

**Directory Structure**:
```
tests/
├── __init__.py
├── conftest.py
├── unit/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_vault_source.py
│   └── test_json_source.py
└── integration/
    ├── __init__.py
    └── test_full_config.py
```

---

### Task 2.2: Write Tests for config.py ⏱️ 3h

**File**: `tests/unit/test_config.py`

**Subtasks**:
- [ ] Test VaultAccess with token auth
- [ ] Test VaultAccess with userpass auth
- [ ] Test VaultAccess validation (no creds)
- [ ] Test VaultAccess with invalid URL
- [ ] Test field aliases work correctly
- [ ] Test default mount_point value

**Example Tests**:
```python
import pytest
from pydantic import ValidationError
from vlt.config import VaultAccess


def test_vault_access_with_token():
    """Test VaultAccess initialization with token."""
    config = VaultAccess(
        VAULT_ADDRESS="https://vault.example.com",
        VAULT_TOKEN="s.test-token",
        VAULT_APP_NAME="test-app"
    )
    assert str(config.address) == "https://vault.example.com/"
    assert config.token == "s.test-token"


def test_vault_access_missing_credentials():
    """Test VaultAccess raises error without credentials."""
    with pytest.raises(ValueError, match="Must provide either"):
        VaultAccess(
            VAULT_ADDRESS="https://vault.example.com",
            VAULT_APP_NAME="test-app"
        )


def test_vault_access_invalid_url():
    """Test VaultAccess rejects invalid URL scheme."""
    with pytest.raises(ValueError, match="Vault address must use http"):
        VaultAccess(
            VAULT_ADDRESS="ftp://vault.example.com",
            VAULT_TOKEN="s.test",
            VAULT_APP_NAME="test"
        )
```

**Acceptance Criteria**:
- All validation paths tested
- Edge cases covered
- 100% coverage of config.py

---

### Task 2.3: Write Tests for vault_source.py ⏱️ 4h

**File**: `tests/unit/test_vault_source.py`

**Subtasks**:
- [ ] Mock hvac.Client
- [ ] Test successful secret retrieval
- [ ] Test authentication failure
- [ ] Test invalid path
- [ ] Test network errors
- [ ] Test each exception type
- [ ] Test `__call__` returns empty dict on error

**Example**:
```python
from unittest.mock import Mock, patch
import hvac.exceptions
from vlt.vault_source import PydanticVaultSource


@patch("vlt.vault_source.hvac.Client")
@patch("vlt.vault_source.VaultAccess")
def test_vault_source_success(mock_config, mock_client):
    """Test successful secret retrieval from Vault."""
    # Setup mocks
    mock_config.return_value.address = "https://vault.example.com"
    mock_config.return_value.app_name = "test-app"
    mock_config.return_value.mount_point = "secret"
    mock_config.return_value.token = "s.test"

    mock_client_instance = Mock()
    mock_client.return_value = mock_client_instance
    mock_client_instance.is_authenticated.return_value = True
    mock_client_instance.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"key1": "value1", "key2": "value2"}}
    }

    # Test
    source = PydanticVaultSource(settings_cls=Mock())
    result = source()

    assert result == {"key1": "value1", "key2": "value2"}
```

**Acceptance Criteria**:
- All code paths tested
- Mocks verify correct hvac calls
- 80%+ coverage

---

### Task 2.4: Write Tests for json_source.py ⏱️ 3h

**File**: `tests/unit/test_json_source.py`

**Subtasks**:
- [ ] Create temporary config.json files
- [ ] Test successful JSON loading
- [ ] Test missing file (should not warn)
- [ ] Test invalid JSON
- [ ] Test PYDANTIC_JSON_PATH environment variable
- [ ] Test permission errors

**Example**:
```python
import json
import tempfile
from pathlib import Path
from vlt.json_source import PydanticJSONSource


def test_json_source_success(tmp_path):
    """Test successful JSON config loading."""
    # Create temp config
    config_file = tmp_path / "config.json"
    config_data = {"key1": "value1", "key2": "value2"}
    config_file.write_text(json.dumps(config_data))

    # Set environment
    import os
    os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)

    # Test
    source = PydanticJSONSource(settings_cls=Mock())
    result = source()

    assert result == config_data
```

---

### Task 2.5: Write Integration Tests ⏱️ 2h

**File**: `tests/integration/test_full_config.py`

**Subtasks**:
- [ ] Test full VaultJsonConfig initialization
- [ ] Test source priority (env > vault > json)
- [ ] Test with real JSON file
- [ ] Test with missing sources (graceful degradation)

---

## Phase 3: Logging Improvements (Week 3)

### Task 3.1: Update Logging Levels ⏱️ 1.5h

**Files**: `vlt/vault_source.py`, `vlt/json_source.py`

**Subtasks**:
- [ ] Change auth flow logs to `logger.trace(...)`
- [ ] Keep only success/failure at `logger.info/error`
- [ ] Remove `logger.warning` for missing config.json
- [ ] Add trace logging for:
  - Starting authentication
  - Auth method used
  - Requesting secrets
  - Cache hits/misses (when added)

**Example**:
```python
def _auth_by_userpass(cfg: VaultAccess) -> hvac.Client:
    """Authenticate to Vault using token or userpass."""
    logger.trace("Starting Vault authentication to {}", cfg.address)

    if cfg.token:
        logger.trace("Using token authentication")
        client = hvac.Client(url=str(cfg.address), token=cfg.token)
        if not client.is_authenticated():
            raise ValueError("Token authentication failed")
        logger.trace("Successfully authenticated with token")
        return client

    # ... userpass flow ...
    logger.trace("Using userpass authentication")
```

**Acceptance Criteria**:
- Auth details only in trace
- Success/failure in info/error
- No warnings for normal operation

---

## Phase 4: Caching (Week 3-4)

### Task 4.1: Implement Cache in vault_source.py ⏱️ 3h

**File**: `vlt/vault_source.py`

**Subtasks**:
- [ ] Add `_cache` class variable (dict)
- [ ] Add `_cache_ttl` class variable (300 seconds default)
- [ ] Implement cache key generation
- [ ] Check cache before Vault request
- [ ] Store result in cache with timestamp
- [ ] Add cache hit/miss logging (trace level)
- [ ] Add ability to disable cache via env var

**Code**:
```python
from datetime import datetime, timedelta
from typing import ClassVar

class PydanticVaultSource(PydanticBaseSettingsSource):
    """Vault settings source with caching."""

    _cache: ClassVar[dict[str, tuple[dict[str, Any], datetime]]] = {}
    _cache_ttl: ClassVar[int] = 300  # 5 minutes

    def __call__(self) -> dict[str, Any]:
        """Load secrets from Vault with caching."""
        cfg = VaultAccess()
        cache_key = f"{cfg.address}:{cfg.app_name}:{cfg.mount_point}"

        # Check cache
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            age = datetime.now() - timestamp
            if age < timedelta(seconds=self._cache_ttl):
                logger.trace("Cache hit for {} (age: {}s)", cache_key, age.seconds)
                return data
            else:
                logger.trace("Cache expired for {} (age: {}s)", cache_key, age.seconds)

        # Load from Vault
        try:
            self._get_secret_from_vault()
            self._cache[cache_key] = (self._result_config, datetime.now())
            logger.trace("Cached secrets for {}", cache_key)
            logger.info("Loaded {} keys from Vault", len(self._result_config))
        except Exception as ex:
            logger.error("Failed to load from Vault: {}", ex)

        return self._result_config
```

**Acceptance Criteria**:
- Cache works correctly
- TTL respected
- Cache can be disabled
- Tests verify caching behavior

---

### Task 4.2: Add Cache Tests ⏱️ 2h

**File**: `tests/unit/test_vault_source.py`

**Subtasks**:
- [ ] Test cache hit on second call
- [ ] Test cache miss after TTL
- [ ] Test different cache keys
- [ ] Test cache disabled
- [ ] Test cache with errors

---

## Phase 5: Retry Logic (Week 4)

### Task 5.1: Add tenacity Dependency ⏱️ 15min

**File**: `pyproject.toml`

**Subtasks**:
- [ ] Add `tenacity>=8.0.0` to dependencies
- [ ] Run `uv sync` to install
- [ ] Verify import works

---

### Task 5.2: Implement Retry in vault_source.py ⏱️ 2h

**File**: `vlt/vault_source.py`

**Subtasks**:
- [ ] Import tenacity decorators
- [ ] Add `@retry` decorator to `_get_secret_from_vault`
- [ ] Configure retry for network errors
- [ ] Configure exponential backoff
- [ ] Add logging for retries
- [ ] Test retry behavior

**Code**:
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from loguru import logger

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((
        hvac.exceptions.VaultDown,
        ConnectionError,
        TimeoutError,
    )),
    before_sleep=before_sleep_log(logger, "warning"),
    reraise=True
)
def _get_secret_from_vault(self) -> None:
    """Fetch secrets from Vault with retry logic.

    Retries up to 3 times with exponential backoff for:
    - Vault server down
    - Connection errors
    - Timeouts

    :raises VaultError: If all retries exhausted
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

**Acceptance Criteria**:
- Retries on transient failures
- Does not retry on auth failures
- Logs retry attempts
- Eventually raises if all fail

---

### Task 5.3: Add Retry Tests ⏱️ 2h

**File**: `tests/unit/test_vault_source.py`

**Subtasks**:
- [ ] Test successful retry after failure
- [ ] Test all retries exhausted
- [ ] Test no retry on auth error
- [ ] Verify exponential backoff
- [ ] Mock sleep to speed up tests

---

## Phase 6: AppRole Authentication (Week 4-5)

### Task 6.1: Add AppRole Fields to VaultAccess ⏱️ 1h

**File**: `vlt/config.py`

**Subtasks**:
- [ ] Add `role_id` field with alias `VAULT_ROLE_ID`
- [ ] Add `secret_id` field with alias `VAULT_SECRET_ID`
- [ ] Update `validate_creds` to accept AppRole
- [ ] Update docstring
- [ ] Add tests

**Code**:
```python
class VaultAccess(BaseSettings):
    """Vault connection configuration.

    Supports three authentication methods:
    1. Token (VAULT_TOKEN)
    2. Username/Password (VAULT_USERNAME + VAULT_PASSWORD)
    3. AppRole (VAULT_ROLE_ID + VAULT_SECRET_ID)
    """

    address: HttpUrl = Field(alias="VAULT_ADDRESS")
    token: str | None = Field(default=None, alias="VAULT_TOKEN")
    username: str | None = Field(default=None, alias="VAULT_USERNAME")
    password: str | None = Field(default=None, alias="VAULT_PASSWORD")
    role_id: str | None = Field(default=None, alias="VAULT_ROLE_ID")
    secret_id: str | None = Field(default=None, alias="VAULT_SECRET_ID")
    app_name: str = Field(alias="VAULT_APP_NAME")
    mount_point: str = Field(default=DEFAULT_MOUNT_POINT, alias="VAULT_MOUNT_POINT")

    @model_validator(mode="after")
    def validate_creds(self) -> Self:
        """Validate at least one auth method provided."""
        has_token = self.token is not None
        has_userpass = self.username is not None and self.password is not None
        has_approle = self.role_id is not None and self.secret_id is not None

        if not (has_token or has_userpass or has_approle):
            raise ValueError(
                "Must provide one of: "
                "VAULT_TOKEN, VAULT_USERNAME+PASSWORD, or VAULT_ROLE_ID+SECRET_ID"
            )
        return self
```

---

### Task 6.2: Implement AppRole Authentication ⏱️ 2h

**File**: `vlt/vault_source.py`

**Subtasks**:
- [ ] Rename `_auth_by_userpass` to `_authenticate_vault`
- [ ] Add AppRole authentication logic
- [ ] Try methods in order: token, approle, userpass
- [ ] Add proper error handling
- [ ] Add logging for each method
- [ ] Update docstrings

**Code**:
```python
def _authenticate_vault(cfg: VaultAccess) -> hvac.Client:
    """Authenticate to Vault using configured method.

    Tries authentication in order:
    1. Token
    2. AppRole
    3. Username/Password

    :param cfg: Vault configuration
    :return: Authenticated Vault client
    :raises ValueError: If authentication fails
    """
    client = hvac.Client(url=str(cfg.address))

    # Try token
    if cfg.token:
        logger.trace("Attempting token authentication")
        client.token = cfg.token
        if not client.is_authenticated():
            raise ValueError("Token authentication failed")
        logger.trace("Authenticated with token")
        return client

    # Try AppRole
    if cfg.role_id and cfg.secret_id:
        logger.trace("Attempting AppRole authentication")
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
        logger.trace("Attempting userpass authentication")
        try:
            resp = client.auth.userpass.login(
                username=cfg.username,
                password=cfg.password
            )
            client.token = resp["auth"]["client_token"]
            logger.trace("Authenticated with userpass")
            return client
        except hvac.exceptions.InvalidRequest as ex:
            raise ValueError(f"Userpass authentication failed: {ex}") from ex

    raise ValueError("No valid authentication method configured")
```

---

### Task 6.3: Add AppRole Tests ⏱️ 2h

**File**: `tests/unit/test_vault_source.py`

**Subtasks**:
- [ ] Test AppRole successful auth
- [ ] Test AppRole auth failure
- [ ] Test AppRole takes precedence over userpass
- [ ] Test token takes precedence over AppRole
- [ ] Test all auth methods fail

---

## Phase 7: Infrastructure (Week 5)

### Task 7.1: Create ruff.toml ⏱️ 30min

**File**: `ruff.toml`

**Subtasks**:
- [ ] Create file with lint rules
- [ ] Configure format settings
- [ ] Add per-file ignores
- [ ] Run `ruff check .` to verify
- [ ] Run `ruff format .` to format
- [ ] Fix any issues

---

### Task 7.2: Create GitHub Actions Workflow ⏱️ 2h

**File**: `.github/workflows/tests.yml`

**Subtasks**:
- [ ] Create workflow file
- [ ] Add matrix for Python 3.11, 3.12, 3.13
- [ ] Add ruff check step
- [ ] Add mypy check step
- [ ] Add pytest step with coverage
- [ ] Add codecov upload
- [ ] Test workflow runs

---

### Task 7.3: Create .env.example ⏱️ 30min

**File**: `.env.example`

**Subtasks**:
- [ ] Create file with all env vars
- [ ] Add comments explaining each
- [ ] Show all auth methods
- [ ] Add to README

---

### Task 7.4: Create SECURITY.md ⏱️ 30min

**File**: `SECURITY.md`

**Subtasks**:
- [ ] Create file with security policy
- [ ] Add supported versions table
- [ ] Add vulnerability reporting instructions
- [ ] Add security best practices

---

## Phase 8: Documentation (Week 5-6)

### Task 8.1: Expand README.md ⏱️ 3h

**File**: `README.md`

**Subtasks**:
- [ ] Add badges (PyPI, tests, coverage, Python, license)
- [ ] Expand features section
- [ ] Add detailed examples for each auth method
- [ ] Add "How it Works" section
- [ ] Add troubleshooting section
- [ ] Add FAQ
- [ ] Add contributing info (even if solo)
- [ ] Add links to documentation

---

### Task 8.2: Update CLAUDE.md ⏱️ 30min

**File**: `CLAUDE.md`

**Subtasks**:
- [ ] Add note that all project docs are in `.claude/docs/`
- [ ] Link to IMPROVEMENTS.md
- [ ] Link to TASKS.md
- [ ] Update project info if needed

---

### Task 8.3: Create CHANGELOG.md (Optional) ⏱️ 1h

**File**: `CHANGELOG.md`

**Subtasks**:
- [ ] Decide on format (Keep a Changelog, custom, etc.)
- [ ] Document version 0.5.0
- [ ] Add unreleased section
- [ ] Link from README

---

## Optional Tasks (Low Priority)

### Task 9.1: CLI Utility (If Needed) ⏱️ 4h

**Files**: `vlt/cli.py`, `pyproject.toml`

**Purpose** (to discuss):
- Test Vault connectivity
- Validate configuration
- Debug authentication
- Show loaded config (masked)

**Subtasks**:
- [ ] Discuss and confirm utility purpose
- [ ] Add click dependency
- [ ] Create `vlt/cli.py`
- [ ] Add commands:
  - `vault-config test` - test connection
  - `vault-config show` - show config
  - `vault-config validate` - validate setup
- [ ] Add entry point to pyproject.toml
- [ ] Add tests
- [ ] Document in README

---

### Task 9.2: Unified Source (If Desired) ⏱️ 4h

**Discussion needed**: Merge Vault and JSON sources into one?

**Pros**:
- Single logging point
- Clear which source used
- Less code duplication

**Cons**:
- More complex
- Violates single responsibility
- Harder to test

**Decision**: TBD

---

## Task Summary

| Phase | Tasks | Estimated Time | Priority |
|-------|-------|----------------|----------|
| 1. Critical Fixes | 12 tasks | ~15h | 🔴 Critical |
| 2. Testing | 5 tasks | ~14h | 🔴 Critical |
| 3. Logging | 1 task | ~1.5h | 🟠 High |
| 4. Caching | 2 tasks | ~5h | 🟠 High |
| 5. Retry | 3 tasks | ~4.25h | 🟠 High |
| 6. AppRole | 3 tasks | ~5h | 🟠 High |
| 7. Infrastructure | 4 tasks | ~3.5h | 🟡 Medium |
| 8. Documentation | 3 tasks | ~4.5h | 🟡 Medium |
| 9. Optional | 2 tasks | ~8h | 🟢 Low |

**Total Estimated Time**: ~60 hours (without optional tasks)

---

## Implementation Order

Recommended order for implementation:

1. **Week 1-2**: Phase 1 (Critical Fixes)
   - Type hints first (enables better IDE support)
   - Docstrings second (better understanding)
   - Fix exceptions and validation

2. **Week 2-3**: Phase 2 (Testing)
   - Setup test infrastructure
   - Write unit tests
   - Achieve 80%+ coverage

3. **Week 3**: Phase 3-4 (Logging & Caching)
   - Update logging levels
   - Add caching

4. **Week 4**: Phase 5-6 (Retry & AppRole)
   - Add retry logic
   - Implement AppRole

5. **Week 5**: Phase 7 (Infrastructure)
   - Add ruff.toml
   - Setup GitHub Actions
   - Security docs

6. **Week 5-6**: Phase 8 (Documentation)
   - Expand README
   - Update project docs

7. **Later**: Phase 9 (Optional)
   - CLI if needed
   - Unified source if desired

---

## Success Criteria

**Phase 1-2 Complete When**:
- ✅ All files have complete type hints
- ✅ All functions have English docstrings
- ✅ mypy passes with no errors
- ✅ Specific exception handling (no `except Exception`)
- ✅ URL validation works
- ✅ Test coverage > 80%
- ✅ All tests pass

**Phase 3-6 Complete When**:
- ✅ Logging uses trace for details
- ✅ No warnings for missing files
- ✅ Caching works and is tested
- ✅ Retry logic handles transient failures
- ✅ AppRole authentication works
- ✅ All three auth methods tested

**Phase 7-8 Complete When**:
- ✅ GitHub Actions runs and passes
- ✅ README has badges and examples
- ✅ Security policy documented
- ✅ .env.example provided

**Project Complete When**:
- ✅ All critical and high priority tasks done
- ✅ Test coverage > 80%
- ✅ Documentation complete
- ✅ CI/CD working
- ✅ Ready for v0.6.0 release

---

## Notes

- Each task should be done in a separate commit
- Run tests after each task
- Update CHANGELOG.md as you go
- Keep PRs small and focused
- Ask for review/feedback as needed

---

**Ready to start?** Begin with Task 1.1!
