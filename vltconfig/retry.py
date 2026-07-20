"""Injectable retry policy for transient Vault operations."""

import time
from collections.abc import Callable
from typing import Protocol, TypeVar

import hvac.exceptions
import requests.exceptions
from loguru import logger

ResultT = TypeVar("ResultT")

TRANSIENT_VAULT_EXCEPTIONS = (
    hvac.exceptions.VaultDown,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    ConnectionError,
    TimeoutError,
)


class VaultRetryProtocol(Protocol):
    """Execute one Vault operation with a configured transient policy."""

    def call(self, operation: Callable[[], ResultT]) -> ResultT:
        """Return the operation result or re-raise its final failure."""
        ...


def exponential_backoff(failed_attempt: int) -> float:
    """Return the historical 2, 4, 8 second exponential schedule."""
    return float(min(10, 2**failed_attempt))


def log_retry_attempt(failed_attempt: int, max_attempts: int) -> None:
    """Log value-free retry telemetry."""
    logger.warning(
        "Retrying transient Vault request (attempt {}/{})",
        failed_attempt,
        max_attempts,
    )


class VaultRetry:
    """Retry only confirmed transient Vault and Requests failures."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        backoff: Callable[[int], float] = exponential_backoff,
        sleeper: Callable[[float], None] | None = None,
        on_retry: Callable[[int, int], None] = log_retry_attempt,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._max_attempts = max_attempts
        self._backoff = backoff
        self._sleeper = sleeper or time.sleep
        self._on_retry = on_retry

    def call(self, operation: Callable[[], ResultT]) -> ResultT:
        """Run ``operation`` until success or the transient budget is exhausted."""
        for attempt in range(1, self._max_attempts + 1):
            try:
                return operation()
            except TRANSIENT_VAULT_EXCEPTIONS:
                if attempt == self._max_attempts:
                    raise
                self._on_retry(attempt, self._max_attempts)
                self._sleeper(self._backoff(attempt))

        raise RuntimeError("unreachable retry state")
