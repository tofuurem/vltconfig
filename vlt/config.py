from typing import Self

from hvac.api.secrets_engines.kv_v2 import DEFAULT_MOUNT_POINT
from pydantic import Field, HttpUrl, field_validator, model_validator

from pydantic_settings import BaseSettings


class VaultAccess(BaseSettings):
    """HashiCorp Vault connection configuration.

    Supports multiple authentication methods:
    - Token-based authentication (VAULT_TOKEN)
    - Username/Password authentication (VAULT_USERNAME + VAULT_PASSWORD)

    All configuration is loaded from environment variables.

    Example:
        # Token authentication
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_TOKEN"] = "s.your-vault-token"
        os.environ["VAULT_APP_NAME"] = "myapp/config"

        config = VaultAccess()

        # Username/Password authentication
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_USERNAME"] = "readonly"
        os.environ["VAULT_PASSWORD"] = "secret-password"
        os.environ["VAULT_APP_NAME"] = "myapp/config"

        config = VaultAccess()
    """

    address: HttpUrl = Field(
        alias="VAULT_ADDRESS",
        description="URL of the Vault server (e.g., https://vault.example.com)",
    )
    token: str | None = Field(
        default=None, alias="VAULT_TOKEN", description="Vault authentication token"
    )
    username: str | None = Field(
        default=None,
        alias="VAULT_USERNAME",
        description="Username for userpass authentication",
    )
    password: str | None = Field(
        default=None,
        alias="VAULT_PASSWORD",
        description="Password for userpass authentication",
    )
    app_name: str = Field(
        alias="VAULT_APP_NAME",
        description="Path to secrets in Vault KV store (e.g., 'myapp/config')",
    )
    mount_point: str = Field(
        default=DEFAULT_MOUNT_POINT,
        alias="VAULT_MOUNT_POINT",
        description="Mount point for Vault KV engine (default: 'secret')",
    )

    @field_validator("address")
    @classmethod
    def validate_vault_address(cls, v: HttpUrl) -> HttpUrl:
        """Validate Vault address uses http or https scheme.

        :param v: URL to validate
        :return: Validated URL
        :raises ValueError: If URL scheme is not http or https
        """
        if v.scheme not in ["http", "https"]:
            raise ValueError(
                f"Vault address must use http or https scheme, got: {v.scheme}"
            )
        return v

    @model_validator(mode="after")
    def validate_creds(self) -> Self:
        """Validate that at least one authentication method is provided.

        :return: Validated VaultAccess instance
        :raises ValueError: If no valid authentication credentials provided
        """
        if self.token is None and (self.username is None or self.password is None):
            raise ValueError(
                "Must provide either VAULT_TOKEN or VAULT_USERNAME + VAULT_PASSWORD"
            )
        return self
