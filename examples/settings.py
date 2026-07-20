"""Typed settings model shared by the runnable examples and CLI snippets."""

from pydantic import Field, SecretStr

from vltconfig import VaultJsonConfig


class AppConfig(VaultJsonConfig):
    """Example application configuration with unmistakably fake local values."""

    database_url: str = Field(description="Application database URL")
    api_key: SecretStr = Field(description="External service API key")
    debug: bool = Field(default=False, description="Enable debug behavior")
    max_connections: int = Field(
        default=10,
        ge=1,
        description="Maximum database connections",
    )
