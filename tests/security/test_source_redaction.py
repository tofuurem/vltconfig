"""Configuration-source error redaction regression tests."""

import os
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import hvac.exceptions
import pytest
from loguru import logger
from pydantic_settings import BaseSettings

from vltconfig.errors import JSONDecodeError, VaultAuthorizationError
from vltconfig.json_source import PydanticJSONSource
from vltconfig.vault_source import PydanticVaultSource, _log_retry_attempt


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Capture Loguru messages without installing a process-wide handler."""
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="TRACE")
    try:
        yield messages
    finally:
        logger.remove(sink_id)


def _diagnostics(error: BaseException, messages: list[str]) -> str:
    """Render the normal diagnostics a caller or debug CLI could expose."""
    return "\n".join(
        [
            str(error),
            repr(error),
            "".join(traceback.format_exception(error)),
            *messages,
        ]
    )


@pytest.mark.unit
def test_vault_upstream_details_are_absent_from_errors_and_logs(
    vault_env_vars: dict[str, str], clean_env: None
) -> None:
    """Vault exception messages must not cross the settings-source boundary."""
    canary = "vault-source-redaction-canary"
    os.environ.update(vault_env_vars)
    source = PydanticVaultSource(BaseSettings)

    with (
        patch.object(
            source,
            "_get_secret_from_vault",
            side_effect=hvac.exceptions.Forbidden(canary),
        ),
        _captured_logs() as messages,
        pytest.raises(VaultAuthorizationError) as captured,
    ):
        source()

    assert canary not in _diagnostics(captured.value, messages)
    assert captured.value.cause_type == "Forbidden"


@pytest.mark.unit
def test_retry_log_omits_upstream_exception_text() -> None:
    """Retry telemetry exposes attempt counts, not exception payloads."""
    canary = "retry-redaction-canary"
    retry_state = Mock()
    retry_state.outcome.exception.return_value = hvac.exceptions.VaultDown(canary)
    retry_state.attempt_number = 2

    with _captured_logs() as messages:
        _log_retry_attempt(retry_state)

    assert canary not in "\n".join(messages)
    assert any("attempt 2/3" in message for message in messages)


@pytest.mark.unit
def test_malformed_json_content_is_absent_from_errors_and_logs(
    tmp_path: Path, clean_env: None
) -> None:
    """Malformed file contents must never be echoed in diagnostics."""
    canary = "json-source-redaction-canary"
    (tmp_path / "config.json").write_text(f'{{"secret": "{canary}"')
    os.environ["PYDANTIC_JSON_PATH"] = str(tmp_path)
    source = PydanticJSONSource(BaseSettings)

    with (
        _captured_logs() as messages,
        pytest.raises(JSONDecodeError) as captured,
    ):
        source()

    assert canary not in _diagnostics(captured.value, messages)
    assert captured.value.cause_type == "JSONDecodeError"
