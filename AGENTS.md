# Repository Guidelines

## Scope

These instructions apply to the entire repository. A more specific `AGENTS.md` in a subdirectory may refine them for that subtree.

`vltconfig` is a Python library that extends Pydantic Settings with HashiCorp Vault KV v2 and file-based configuration sources. Treat public imports, configuration precedence, environment-variable names, authentication order, and failure behavior as compatibility-sensitive API.

## Repository Map

- `vltconfig/__init__.py`: public `VaultJsonConfig` base class and settings-source ordering.
- `vltconfig/config.py`: Vault connection and authentication settings.
- `vltconfig/vault_source.py`: Vault authentication, reads, retries, logging, and caching.
- `vltconfig/json_source.py`: JSON settings source.
- `vltconfig/constants.py`: shared environment-variable names and constants.
- `tests/unit/`: isolated behavior and regression tests.
- `tests/integration/`: opt-in tests that may use real infrastructure; keep the default suite offline.
- `examples/`: runnable, secret-free usage examples.
- `pyproject.toml`, `uv.lock`, and `pytest.ini`: packaging, dependencies, and quality configuration.
- `.github/workflows/`: pull-request validation and release automation.

Do not migrate layouts, rename the package, or change the public import path unless the task explicitly calls for a breaking change.

## Public Behavior

The current settings-source priority is, from highest to lowest:

1. Environment variables.
2. HashiCorp Vault.
3. JSON configuration.
4. Initializer arguments.
5. Dotenv values.
6. File secrets.

Pydantic Settings gives earlier sources higher priority. Preserve this order unless a deliberately breaking change is requested. Any change must include precedence tests, README updates, and release notes.

Vault authentication currently tries token, AppRole, and userpass in that order. Preserve environment-variable aliases and authentication order unless the change is intentional and tested.

## Environment and Dependency Management

Use `uv` as the canonical project and dependency manager. Do not maintain parallel requirements files unless a downstream integration requires one.

Typical setup:

```bash
uv sync --group dev
```

Run project tools through the synchronized environment:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy vltconfig tests
uv run ty check
uv build
```

These are the target mandatory gates. During modernization, a gate may expose a pre-existing repository failure or may not yet be configured. Do not hide that by lowering thresholds, adding broad ignores, or dropping the gate. Separate the baseline failure from changes introduced by the task, and update this file once the gate becomes established.

Use `uv run --frozen ...` in CI after the lock file is intentionally regenerated. When changing dependencies, update `pyproject.toml` and `uv.lock` together with a supported `uv` version, review the full resolution, and test every supported Python minor.

## Python Compatibility

- Python 3.11 is the minimum runtime and syntax baseline.
- Python 3.11, 3.12, 3.13, and 3.14 are blocking support targets.
- Do not introduce syntax or standard-library APIs unavailable on Python 3.11.
- Python 3.15 remains a non-blocking prerelease CI target until CPython 3.15 and the dependency stack have stable compatible releases.
- Promote Python 3.15 to blocking support and add stable-support metadata only after dependency installation, the full suite, type checks, build, and wheel-import tests pass.

Classifiers and README claims must describe versions validated in CI, not merely versions allowed by `requires-python`.

## Code Quality and Typing

Ruff owns linting, formatting, and import sorting. Do not add a second formatter or keep redundant import-sorting configuration when Ruff can enforce the rule.

Run both mypy and ty. They are complementary gates:

- Type public functions, methods, class attributes, and owned internal boundaries.
- Prefer built-in generics and PEP 604 unions supported by Python 3.11.
- Use `Protocol`, `TypedDict`, enums, literals, and precise aliases when they clarify a contract.
- Keep `Any` at genuinely dynamic third-party boundaries and narrow it immediately.
- Use a focused suppression only after documenting why the boundary cannot be typed.
- Do not weaken one checker merely to silence the other.

Package source imports must be explicit and type-checker friendly. If code references a third-party submodule, import that submodule directly rather than relying on incidental package initialization.

## Settings Source Design

Keep each source responsible for loading one kind of data. Source composition and priority belong in one obvious place.

When adding JSON, YAML, TOML, or pyproject support:

- Prefer maintained Pydantic Settings sources over a redundant local parser.
- Support nested values, lists, dictionaries, `null`, encodings, and `Path` inputs consistently.
- Define whether a path means a file or directory; do not infer both ambiguously.
- Make missing-file, malformed-file, and permission-error behavior explicit and test it.
- Support multiple files or deep merging only with a documented priority contract.
- Put optional parser dependencies behind named extras, such as `vltconfig[yaml]`.
- Keep users able to customize or omit sources without copying the entire base class.

Do not silently swallow malformed configuration by default. If an optional or fail-open mode is retained for backward compatibility, make strict behavior available and document the distinction.

## Vault Security

Never place real credentials in source files, tests, examples, documentation, generated reports, logs, commits, issue text, or tool output. This includes Vault tokens, passwords, role IDs, and secret IDs.

- Use unmistakably fake values in examples.
- Represent credential fields with redacting secret types such as Pydantic `SecretStr`.
- Never interpolate credentials or secret payloads into exceptions, logs, cache keys, or object representations.
- Avoid logging full Vault responses or settings models.
- If a real credential is discovered, stop exposing it, report its location without repeating the value, rotate it immediately, and assess Git history. Deleting the current file is not sufficient.
- Do not add live credentials to CI. Use GitHub OIDC and PyPI Trusted Publishing for releases.

Library code must not configure application-wide logging handlers. Log actionable context at the appropriate level while redacting security-sensitive data.

## Vault Reliability and Caching

Retry only confirmed transient exceptions from the actual HTTP client stack. Authentication, authorization, invalid paths, invalid configuration, and malformed responses are not automatically retryable.

- Keep retry attempt counts and backoff policy in named configuration.
- Make retry waits replaceable or disabled in unit tests.
- Preserve exception causality when translating errors.
- Avoid broad `except Exception` handlers that convert every defect into an empty source.
- Make strict versus fallback behavior explicit at the public boundary.

Secret caches must be bounded, thread-safe, and independently configurable per consumer or source instance. Use a monotonic clock for expiration. Do not let one instance mutate process-wide cache settings for unrelated instances. Include every non-secret isolation dimension in cache identity, but never raw credentials. Provide an explicit invalidation seam and test concurrency, expiration, credential rotation, and mutation isolation.

## Testing

Every behavior change needs a regression test. Prefer observable behavior over assertions against implementation details.

- Keep the default test suite offline and deterministic.
- Use `monkeypatch` or fixtures for environment variables and restore all touched state.
- Reset cache and retry state between tests; no test may depend on execution order.
- Replace real retry sleeps with a no-wait strategy or injected sleeper.
- Assert specific exception types and messages; do not use `pytest.raises(Exception)`.
- Exercise nested and collection-valued settings, aliases, source precedence, absent optional sources, malformed inputs, and permission errors.
- Test the network exception classes that `hvac` and its HTTP adapter actually raise.
- Add opt-in integration coverage for a disposable Vault server when changing the Vault contract.

The supported Python matrix must run the same unit suite. Keep coverage configuration in one canonical place and measure `vltconfig`, not a historical package name.

Release validation must also:

1. Build both sdist and wheel.
2. Inspect artifact contents and metadata.
3. Install the wheel into a clean environment.
4. Import the public API and run a minimal JSON-only smoke test.

## Packaging

Runtime dependencies belong in `[project.dependencies]`; development-only tools belong in the dev dependency group; optional source dependencies belong in extras.

- Keep the runtime dependency surface minimal.
- Include an actual license file and use current SPDX-compatible metadata.
- Include `vltconfig/py.typed` and package it when distributing inline type information.
- Keep package version, lock metadata, built artifact metadata, and release tag consistent.
- Add `Typing :: Typed` and Python classifiers only when the artifact satisfies those claims.
- Do not commit virtual environments, caches, coverage HTML, egg-info directories, or built distributions.

## CI/CD and Releases

Pull-request CI and publishing are separate concerns.

Pull-request CI must include:

- Ruff lint and format checks.
- mypy and ty.
- Tests on Python 3.11 through 3.14.
- A non-blocking Python 3.15 prerelease job while applicable.
- Coverage enforcement on one canonical Python version.
- Build, metadata, wheel-install, and import smoke checks.

Publishing must consume artifacts produced by a successful build job rather than rebuilding an arbitrary working tree. Publish only from an intentional versioned tag or approved release, verify that the tag matches package metadata, use a protected PyPI environment and Trusted Publishing, and grant each job only the permissions it needs. Pin third-party actions to immutable revisions where practical and use automated update tooling to keep pins current.

Never publish when any blocking compatibility or packaging check is failing.

## Documentation and Examples

Keep README claims, examples, source precedence, environment variables, and error semantics synchronized with the code. Examples must be runnable and must use fake credentials. Avoid examples that print secret-bearing settings.

Repository-local design notes, review dossiers, and audit artifacts belong under ignored `docs/` unless the user explicitly changes that policy. Do not force-add ignored documentation.

## Change Discipline

- Inspect the worktree before editing and preserve unrelated user changes.
- Use `rg` and `rg --files` for repository search.
- Keep changes scoped to the request; avoid opportunistic rewrites.
- Preserve public behavior unless the task explicitly authorizes a breaking change.
- Do not use destructive Git operations or rewrite user commits without explicit approval.
- Do not commit changes unless the workflow or user explicitly requires it.
- Do not bypass failing hooks or checks.

When encountering a pre-existing failure, record the exact command and distinguish it from failures introduced by the current change. Fix it when it is in scope; otherwise report it clearly.

## Completion Checklist

Before declaring work complete:

- Relevant tests pass on the applicable Python versions.
- Ruff formatting and lint checks pass.
- mypy and ty pass for the configured scope.
- Coverage measures the correct package and meets the project threshold.
- Packaging builds without unexplained warnings.
- A clean environment can install and import the wheel.
- Security-sensitive values are absent from changes and output.
- README and examples match any changed public behavior.
- `git diff --check` passes and unrelated files remain untouched.

Report the commands run, their results, and any validation that could not be completed.
