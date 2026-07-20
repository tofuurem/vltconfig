"""Integration coverage for lossless CAS-protected Vault apply operations."""

import itertools
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel

from tests.integration.conftest import VaultIntegration
from vltconfig import REQUIRED_PLACEHOLDER, apply_configuration
from vltconfig.config import VaultAccess
from vltconfig.errors import VaultConflictError
from vltconfig.retry import VaultRetry
from vltconfig.vault_gateway import HvacVaultGateway, VersionedSecret

_PATH_COUNTER = itertools.count()


def _gateway(integration: VaultIntegration, path: str) -> HvacVaultGateway:
    """Build a write-capable production gateway for one unique path."""
    access = VaultAccess.model_validate(
        {
            "VAULT_ADDRESS": integration.address,
            "VAULT_TOKEN": integration.write_token,
            "VAULT_APP_NAME": path,
            "VAULT_MOUNT_POINT": "secret",
        }
    )
    return HvacVaultGateway(access, retry_policy=VaultRetry(max_attempts=1))


@pytest.mark.integration
def test_real_create_and_merge_preserve_existing_values(
    vault_integration: VaultIntegration,
) -> None:
    """Create-only initialization and versioned merge work against real Vault."""
    path = f"integration/apply-{next(_PATH_COUNTER)}"
    gateway = _gateway(vault_integration, path)

    class InitialSettings(BaseModel):
        endpoint: str

    created = apply_configuration(InitialSettings, gateway)
    first = gateway.read()
    gateway.update(
        {"endpoint": "real-existing", "legacy": "preserved"},
        version=first.version,
    )

    class ExpandedSettings(BaseModel):
        endpoint: str
        token: str
        workers: int = 4

    merged = apply_configuration(ExpandedSettings, gateway)
    final = gateway.read()

    assert created.applied is True
    assert merged.applied is True
    assert final.copy_data() == {
        "endpoint": "real-existing",
        "legacy": "preserved",
        "token": REQUIRED_PLACEHOLDER,
    }
    assert final.version == first.version + 2


@dataclass
class ConcurrentGateway:
    """Inject one real competing write immediately before the planned write."""

    planned: HvacVaultGateway
    competitor: HvacVaultGateway
    _observed: dict[str, Any] | None = None

    def read(self) -> VersionedSecret:
        secret = self.planned.read()
        self._observed = secret.copy_data()
        return secret

    def create(self, payload: Mapping[str, Any]) -> None:
        self.planned.create(payload)

    def update(self, payload: Mapping[str, Any], *, version: int) -> None:
        assert self._observed is not None
        competing_payload = deepcopy(self._observed)
        competing_payload["raced"] = True
        self.competitor.update(competing_payload, version=version)
        self.planned.update(payload, version=version)


@pytest.mark.integration
def test_real_concurrent_update_rejects_the_stale_apply(
    vault_integration: VaultIntegration,
) -> None:
    """Apply never retries a plan after another writer changes the version."""
    path = f"integration/apply-conflict-{next(_PATH_COUNTER)}"
    first = _gateway(vault_integration, path)
    second = _gateway(vault_integration, path)
    first.create({"endpoint": "service"})

    class Settings(BaseModel):
        endpoint: str
        token: str

    gateway = ConcurrentGateway(planned=first, competitor=second)

    with pytest.raises(VaultConflictError):
        apply_configuration(
            Settings,
            gateway,
            replacement_paths=(("endpoint",),),
            proposed_values={"endpoint": "replacement"},
        )

    assert first.read().copy_data() == {"endpoint": "service", "raced": True}


@pytest.mark.integration
def test_real_addressed_replacement_ignores_unlisted_values(
    vault_integration: VaultIntegration,
) -> None:
    """Only an explicitly listed key changes in the real stored payload."""
    path = f"integration/apply-replace-{next(_PATH_COUNTER)}"
    gateway = _gateway(vault_integration, path)
    gateway.create({"token": "old-token", "endpoint": "old-endpoint"})

    class Settings(BaseModel):
        token: str
        endpoint: str

    result = apply_configuration(
        Settings,
        gateway,
        replacement_paths=(("token",),),
        proposed_values={"token": "new-token", "endpoint": "ignored-endpoint"},
    )

    assert result.changed_paths == (("token",),)
    assert gateway.read().copy_data() == {
        "token": "new-token",
        "endpoint": "old-endpoint",
    }
