"""Tests for deterministic Vault retry behavior."""

from collections.abc import Callable, Sequence

import hvac.exceptions
import pytest
import requests.exceptions

from vltconfig.retry import VaultRetry


class FailingOperation:
    """Raise configured failures before returning a success value."""

    def __init__(self, failures: Sequence[BaseException]) -> None:
        self._failures = iter(failures)
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        failure = next(self._failures, None)
        if failure is not None:
            raise failure
        return "success"


@pytest.mark.unit
@pytest.mark.parametrize(
    "failure_factory",
    [
        lambda: hvac.exceptions.VaultDown("vault detail"),
        lambda: requests.exceptions.ConnectionError("connection detail"),
        lambda: requests.exceptions.ConnectTimeout("connect timeout detail"),
        lambda: requests.exceptions.ReadTimeout("read timeout detail"),
        lambda: ConnectionError("legacy connection detail"),
        lambda: TimeoutError("legacy timeout detail"),
    ],
)
def test_real_transient_failures_are_retried_without_sleep(
    failure_factory: Callable[[], BaseException],
) -> None:
    """HTTP adapter and compatibility transient errors share one policy."""
    operation = FailingOperation([failure_factory()])
    waits: list[float] = []
    retry = VaultRetry(sleeper=waits.append)

    assert retry.call(operation) == "success"
    assert operation.calls == 2
    assert waits == [2.0]


@pytest.mark.unit
@pytest.mark.parametrize(
    "failure",
    [
        hvac.exceptions.Forbidden("authorization detail"),
        hvac.exceptions.InvalidPath("path detail"),
        ValueError("authentication detail"),
    ],
)
def test_non_transient_failures_are_not_retried(failure: BaseException) -> None:
    """Authorization, paths, and authentication fail immediately."""
    operation = FailingOperation([failure])
    retry = VaultRetry(sleeper=lambda _delay: pytest.fail("must not sleep"))

    with pytest.raises(type(failure)):
        retry.call(operation)

    assert operation.calls == 1


@pytest.mark.unit
def test_retry_attempts_backoff_and_callback_are_injectable() -> None:
    """Tests and consumers can replace all wall-clock retry behavior."""
    operation = FailingOperation(
        [
            requests.exceptions.ConnectionError("first"),
            requests.exceptions.ConnectionError("second"),
        ]
    )
    waits: list[float] = []
    events: list[tuple[int, int]] = []
    retry = VaultRetry(
        max_attempts=3,
        backoff=lambda attempt: float(attempt * 10),
        sleeper=waits.append,
        on_retry=lambda attempt, maximum: events.append((attempt, maximum)),
    )

    assert retry.call(operation) == "success"
    assert waits == [10.0, 20.0]
    assert events == [(1, 3), (2, 3)]


@pytest.mark.unit
def test_exhausted_retry_reraises_original_failure() -> None:
    """The final transient exception remains available for safe translation."""
    failures = [requests.exceptions.ReadTimeout(str(index)) for index in range(3)]
    operation = FailingOperation(failures)
    retry = VaultRetry(max_attempts=3, sleeper=lambda _delay: None)

    with pytest.raises(requests.exceptions.ReadTimeout):
        retry.call(operation)

    assert operation.calls == 3


@pytest.mark.unit
@pytest.mark.parametrize("max_attempts", [0, -1])
def test_retry_requires_at_least_one_attempt(max_attempts: int) -> None:
    """Invalid reliability configuration fails at construction time."""
    with pytest.raises(ValueError, match="max_attempts"):
        VaultRetry(max_attempts=max_attempts)
