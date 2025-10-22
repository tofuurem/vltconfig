from typing import Self

from hvac.api.secrets_engines.kv_v2 import DEFAULT_MOUNT_POINT
from pydantic import Field, HttpUrl, field_validator, model_validator

from pydantic_settings import BaseSettings


class VaultAccess(BaseSettings):
    """HashiCorp Vault connection configuration.

    Supports multiple authentication methods:
    - Token-based authentication (VAULT_TOKEN)
    - Username/Password authentication (VAULT_USERNAME + VAULT_PASSWORD)
    - AppRole authentication (VAULT_ROLE_ID + VAULT_SECRET_ID)

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

        # AppRole authentication
        os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
        os.environ["VAULT_ROLE_ID"] = "your-role-id"
        os.environ["VAULT_SECRET_ID"] = "your-secret-id"
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
    role_id: str | None = Field(
        default=None,
        alias="VAULT_ROLE_ID",
        description="Role ID for AppRole authentication",
    )
    secret_id: str | None = Field(
        default=None,
        alias="VAULT_SECRET_ID",
        description="Secret ID for AppRole authentication",
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

        Accepts one of three authentication methods:
        1. Token (VAULT_TOKEN)
        2. Username/Password (VAULT_USERNAME + VAULT_PASSWORD)
        3. AppRole (VAULT_ROLE_ID + VAULT_SECRET_ID)

        :return: Validated VaultAccess instance
        :raises ValueError: If no valid authentication credentials provided
        """
        has_token = self.token is not None
        has_userpass = self.username is not None and self.password is not None
        has_approle = self.role_id is not None and self.secret_id is not None

        if not (has_token or has_userpass or has_approle):
            raise ValueError(
                "Must provide one of: VAULT_TOKEN, "
                "VAULT_USERNAME + VAULT_PASSWORD, or "
                "VAULT_ROLE_ID + VAULT_SECRET_ID"
            )
        return self
