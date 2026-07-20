"""Stable, value-free exception categories exposed by vltconfig."""


class VltConfigError(Exception):
    """Base class for library-defined operational errors."""

    def __init__(self, message: str, *, cause_type: str | None = None) -> None:
        """Store a safe upstream type without retaining its value-bearing error."""
        super().__init__(message)
        self.cause_type = cause_type


class ConfigurationSourceError(VltConfigError):
    """Base class for errors raised while loading a configuration source."""


class SchemaError(VltConfigError):
    """Base class for safe Pydantic schema inspection failures."""


class UnsupportedSchemaError(SchemaError):
    """A model or field shape cannot be represented as a Vault payload."""


class RecursiveSchemaError(UnsupportedSchemaError):
    """A recursive model cannot produce a finite Vault payload schema."""


class YAMLDependencyError(VltConfigError):
    """YAML rendering was requested without the named optional dependency."""


class ConfigurationApplyError(VltConfigError):
    """A configuration plan cannot be applied safely."""


class JSONSourceError(ConfigurationSourceError):
    """Base class for an explicitly configured JSON source failure."""


class JSONFileNotFoundError(JSONSourceError):
    """The explicitly configured JSON file does not exist."""


class JSONDecodeError(JSONSourceError):
    """The configured file is not valid UTF-8 JSON."""


class JSONPermissionError(JSONSourceError):
    """The configured JSON file cannot be read due to its permissions."""


class JSONStructureError(JSONSourceError):
    """The configured JSON document has an unsupported root structure."""


class VaultSourceError(ConfigurationSourceError):
    """Base class for failures from a configured Vault source."""


class VaultConfigurationError(VaultSourceError):
    """Vault environment configuration is partial or invalid."""


class VaultAuthenticationError(VaultSourceError):
    """None of the configured Vault authentication methods succeeded."""


class VaultAuthorizationError(VaultSourceError):
    """Vault denied access to the configured secret path."""


class VaultPathNotFoundError(VaultSourceError):
    """The configured Vault KV path does not exist."""


class VaultUnavailableError(VaultSourceError):
    """Vault could not be reached or was unavailable."""


class VaultResponseError(VaultSourceError):
    """Vault returned a response that could not be consumed safely."""


class VaultConflictError(VaultSourceError):
    """Vault rejected a create or update because its CAS version was stale."""
