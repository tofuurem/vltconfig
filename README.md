# vltconfig

`vltconfig` is a typed configuration library for projects that use Pydantic
Settings, HashiCorp Vault KV v2, and an optional local `config.json`. It also
provides a schema-driven CLI for generating value-free configuration templates,
checking Vault contents, previewing changes, and applying only safe,
CAS-protected updates.

[![PyPI version](https://badge.fury.io/py/vltconfig.svg)](https://pypi.org/project/vltconfig/)
[![Python 3.11-3.14](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

## What it provides

- `VaultJsonConfig`, a Pydantic Settings base class with stable source priority.
- Vault token, AppRole, and userpass authentication in a defined order.
- Typed, redacted failures instead of silently hiding configured-source errors.
- Transient-only retries and bounded, thread-safe, per-source caching.
- Model inspection without instantiating settings or contacting Vault.
- JSON templates and optional commented YAML templates containing no defaults by
  default and no secret values.
- Sanitized JSON Schema and Markdown field references.
- Value-free `check`, `plan`, and `apply` reports.
- KV v2 check-and-set writes that preserve existing and unknown keys.
- Inline typing metadata through the packaged `py.typed` marker.

Python 3.11, 3.12, 3.13, and 3.14 are blocking CI targets. Python 3.15 is a
non-blocking prerelease target and is not yet advertised as stable support.

## Installation

With `uv`:

```bash
uv add vltconfig
```

With `pip`:

```bash
python -m pip install vltconfig
```

YAML is only needed when rendering YAML templates. It is intentionally optional:

```bash
uv add 'vltconfig[yaml]'
```

## Define and load settings

```python
from pydantic import Field, SecretStr

from vltconfig import VaultJsonConfig


class AppConfig(VaultJsonConfig):
    database_url: str = Field(description="Application database URL")
    api_token: SecretStr = Field(description="External service token")
    workers: int = Field(default=4, ge=1)


settings = AppConfig()
```

Do not log or print a settings model that may contain credentials. Use the
validated object only at the application boundary that needs it.

### Source priority

Earlier sources have higher priority:

1. Environment variables.
2. HashiCorp Vault KV v2.
3. `config.json`.
4. Initializer arguments.
5. Dotenv values.
6. Docker/Kubernetes file secrets.

Model defaults are applied by Pydantic after source resolution. This ordering is
compatibility-sensitive.

Vault is optional only when every Vault environment variable is absent. Once any
Vault variable is present, partial configuration, authentication failure,
authorization failure, a missing path, an invalid response, or an unavailable
server raises a typed `VaultSourceError` subclass by default. Lower-priority JSON
or initializer values cannot hide that failure.

To retain the v1 fail-open Vault behavior temporarily during migration, opt in on
one settings class:

```python
from vltconfig import VaultFailurePolicy, VaultJsonConfig


class LegacyConfig(VaultJsonConfig):
    vault_failure_policy = VaultFailurePolicy.FALLBACK

    endpoint: str
```

## Schema-driven Vault workflow

A model is addressed as `<importable-module>:<class>`. Run the installed command
from the project directory so local modules are importable. The repository
examples use `examples.settings:AppConfig`.

Generate a base document containing placeholders only for required values:

```bash
vltconfig template examples.settings:AppConfig -o /tmp/app-config.json
```

Generate a commented YAML variant or a value-free field reference:

```bash
vltconfig template examples.settings:AppConfig --format yaml -o /tmp/app-config.yaml
vltconfig schema examples.settings:AppConfig --format markdown -o /tmp/app-config-fields.md
```

New output files are created with mode `0600`; replacing an existing file keeps
its mode. Writes are atomic. By default, static application defaults remain in
code. `template --include-defaults` includes only static, non-secret defaults and
never evaluates default factories.

Upload the generated base document through your normal Vault process, replace
every `__VLTCFG_REQUIRED__` marker, and validate the stored payload:

```bash
vltconfig check examples.settings:AppConfig
vltconfig check examples.settings:AppConfig --strict --format json
```

Unknown keys are warnings by default, which supports rolling deployments.
`--strict` turns them into errors.

Preview schema additions without writing:

```bash
vltconfig plan examples.settings:AppConfig
vltconfig plan examples.settings:AppConfig --format json
```

Apply missing required structure after reviewing the plan:

```bash
vltconfig apply examples.settings:AppConfig
vltconfig apply examples.settings:AppConfig --yes
```

Interactive use asks for confirmation. Non-interactive use must pass `--yes`.
An apply always displays its redacted plan first. Missing required fields receive
the required placeholder; existing values and unknown keys are preserved.

Replacing an existing value is never implicit. Address each replacement and
provide a JSON object through stdin or a permission-protected file:

```bash
vltconfig apply examples.settings:AppConfig \
  --replace api_key \
  --values-stdin \
  --yes
```

`--values-stdin` requires `--yes` because stdin cannot also be used for an
interactive prompt. Inline value flags such as `--set` are rejected so secrets do
not enter shell history or process arguments. JSON output from `apply` is JSONL:
one `plan` event followed by `result`, `noop`, or `aborted`.

### CAS and update safety

- `plan` is read-only and reports the current KV v2 version.
- `apply` re-reads the payload after approval.
- A new path is created with CAS `0`.
- An existing path is updated with its exact current version.
- If Vault changes after the preview, apply fails and requires a new plan.
- Only missing required paths and explicitly addressed replacements can change.
- A no-op apply performs no Vault write and does not create a new version.

The tool deliberately does not continuously synchronize or overwrite the whole
configuration.

### CLI exit statuses

| Status | Meaning |
| --- | --- |
| `0` | Command succeeded, including a declined or no-op apply. |
| `1` | Schema mismatch or a plan/replacement that cannot be applied. |
| `2` | Vault access, availability, authorization, path, response, or CAS failure. |
| `3` | Invalid CLI usage, model reference, input document, output, or missing optional dependency. |

Place global `--debug` before the command to include library traceback context.
Upstream exception messages and configuration values remain excluded.

## Python API

The public imports from `vltconfig` are grouped around the same workflow:

- Settings: `VaultJsonConfig`, `VaultFailurePolicy`.
- Schema: `build_model_schema`, `ModelSchema`, `FieldSchema`, `DefaultKind`.
- Templates: `build_template`, `render_json_template`,
  `render_yaml_template`, `REQUIRED_PLACEHOLDER`.
- Reference export: `export_json_schema`, `render_json_schema`,
  `render_markdown_reference`.
- Validation: `validate_payload`, `ValidationReport`, `Finding`,
  `FindingCode`, `Severity`, `render_validation_report`.
- Planning: `build_plan`, `ConfigurationPlan`, `PlanChange`,
  `ChangeCategory`, `render_configuration_plan`.
- Vault operations: `HvacVaultGateway`, `VersionedVaultGateway`,
  `VersionedSecret`, `check_configuration`, `plan_configuration`,
  `apply_configuration`, `CheckResult`, and `ApplyResult`.

Schema inspection and local validation do not instantiate a settings model or
invoke its configured sources:

```python
from vltconfig import build_model_schema, build_template, validate_payload

from examples.settings import AppConfig


schema = build_model_schema(AppConfig)
template = build_template(schema)
report = validate_payload(schema, template)

assert report.valid is False  # Required placeholders still need real Vault values.
```

For programmatic Vault operations, construct `HvacVaultGateway` from validated
environment settings. Callers of `apply_configuration` are responsible for their
own authorization/confirmation UX; the CLI supplies that safety boundary:

```python
from vltconfig import HvacVaultGateway, plan_configuration
from vltconfig.config import VaultAccess

from examples.settings import AppConfig


gateway = HvacVaultGateway(VaultAccess())
plan = plan_configuration(AppConfig, gateway)
assert plan.source_version is not None
```

All reports and result representations are structural and value-free. They may
contain model names, paths, types, counts, and Vault versions, but not payload
values.

## Vault environment

| Variable | Purpose |
| --- | --- |
| `VAULT_ADDRESS` | Vault HTTP(S) address. |
| `VAULT_APP_NAME` | KV v2 secret path. |
| `VAULT_MOUNT_POINT` | KV mount; defaults to `secret`. |
| `VAULT_TOKEN` | Token authentication. |
| `VAULT_ROLE_ID`, `VAULT_SECRET_ID` | AppRole authentication pair. |
| `VAULT_USERNAME`, `VAULT_PASSWORD` | Userpass authentication pair. |
| `VAULT_CACHE_DISABLED` | `true`, `1`, or `yes` disables the source cache. |
| `VAULT_CACHE_TTL` | Non-negative cache TTL in seconds; defaults to `300`. |
| `VAULT_CACHE_MAX_ENTRIES` | Positive cache bound; defaults to `128`. |

When multiple complete authentication methods are configured, the order is
token, AppRole, then userpass. Credential fields use redacting secret types.

Only confirmed transient network/Vault-down failures are retried. The default is
three total attempts with 2- and 4-second waits before the final attempt.
Authentication, authorization, invalid paths, malformed responses, and CAS
conflicts are not treated as generic retryable failures.

## JSON configuration

`PYDANTIC_JSON_PATH` is a directory, not a filename. The source reads
`$PYDANTIC_JSON_PATH/config.json` as UTF-8 and requires a JSON object at the root:

```bash
export PYDANTIC_JSON_PATH="$PWD/examples/config"
python -m examples.json_only_example
```

When `PYDANTIC_JSON_PATH` is absent, a missing built-in default file means the
source is omitted. Once the directory is explicitly configured, a missing,
unreadable, malformed, or non-object file raises a typed `JSONSourceError`
subclass instead of silently falling through.

## Migration to 2.0

The source order, `VaultJsonConfig` import, environment aliases, and authentication
order are preserved. The intentional breaking change is failure handling:

- Configured Vault failures are strict by default. Use
  `VaultFailurePolicy.FALLBACK` only as a temporary compatibility bridge.
- Explicit JSON configuration errors are raised instead of being treated as an
  empty source.
- Retries cover only known transient failures rather than every exception.
- Cache state is bounded and isolated per source instead of relying on mutable
  process-wide state.

Applications that previously depended on JSON or initializer values after a
broken Vault configuration should migrate before upgrading. Remove partial Vault
variables when Vault is intentionally absent, or explicitly opt into the fallback
policy while correcting the deployment.

Projects migrating from the pre-1.0 package name must continue to use:

```python
from vltconfig import VaultJsonConfig
```

## Examples

- `examples/settings.py`: reusable typed model for Python and CLI examples.
- `examples/json_only_example.py`: deterministic JSON-only loading without
  displaying configuration values.
- `examples/schema_workflow_example.py`: offline template and validation API.

Run them from the repository after installing the project:

```bash
python -m examples.json_only_example
python -m examples.schema_workflow_example
```

Every credential and endpoint in the examples is intentionally fake. The
examples never print settings objects or payload contents.

## Development

```bash
uv sync --group dev
uv run pre-commit install --install-hooks

uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy vltconfig tests
uv run ty check
uv build
```

Run the disposable Vault integration suite separately:

```bash
./scripts/test-vault-integration.sh
```

Repository-local plans and audit material live under ignored `docs/` and are not
part of the published repository.

## License

MIT. See [LICENSE](LICENSE).
