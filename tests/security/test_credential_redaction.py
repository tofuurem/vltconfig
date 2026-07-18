"""Credential redaction regression tests."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock, patch

import hvac.exceptions
import pytest
from loguru import logger

from vltconfig.config import VaultAccess
from vltconfig.vault_source import _authenticate_vault


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Capture Loguru messages without changing application-wide logging."""
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="TRACE")
    try:
        yield messages
    finally:
        logger.remove(sink_id)


@pytest.mark.unit
def test_credentials_are_redacted_at_model_and_auth_boundaries(
    clean_env: None,
) -> None:
    """Credential canaries must not escape through normal diagnostic paths."""
    canaries = {
        "VAULT_TOKEN": "redaction-token-canary",
        "VAULT_PASSWORD": "redaction-password-canary",
        "VAULT_ROLE_ID": "redaction-role-canary",
        "VAULT_SECRET_ID": "redaction-secret-id-canary",
    }
    os.environ.update(
        {
            "VAULT_ADDRESS": "https://vault.example.com",
            "VAULT_USERNAME": "redaction-user",
            "VAULT_APP_NAME": "redaction/config",
            **canaries,
        }
    )
    config = VaultAccess()

    client = Mock()
    client.is_authenticated.return_value = False
    client.auth.approle.login.side_effect = hvac.exceptions.InvalidRequest(
        canaries["VAULT_SECRET_ID"]
    )
    client.auth.userpass.login.side_effect = hvac.exceptions.InvalidRequest(
        canaries["VAULT_PASSWORD"]
    )

    with (
        patch("vltconfig.vault_source.hvac.Client", return_value=client),
        _captured_logs() as messages,
        pytest.raises(ValueError) as captured_error,
    ):
        _authenticate_vault(config)

    diagnostics = "\n".join(
        [
            str(config),
            repr(config),
            config.model_dump_json(),
            str(config.model_dump()),
            str(captured_error.value),
            repr(captured_error.value),
            *messages,
        ]
    )
    for canary in canaries.values():
        assert canary not in diagnostics
