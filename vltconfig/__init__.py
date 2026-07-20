from typing import ClassVar

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from vltconfig.json_source import PydanticJSONSource
from vltconfig.operations import (
    ApplyResult,
    CheckResult,
    apply_configuration,
    check_configuration,
    plan_configuration,
)
from vltconfig.planning import (
    ChangeCategory,
    ConfigurationPath,
    ConfigurationPlan,
    PlanChange,
    build_plan,
    render_configuration_plan,
)
from vltconfig.policy import VaultFailurePolicy
from vltconfig.schema import DefaultKind, FieldSchema, ModelSchema, build_model_schema
from vltconfig.schema_export import (
    export_json_schema,
    render_json_schema,
    render_markdown_reference,
)
from vltconfig.template import (
    REQUIRED_PLACEHOLDER,
    build_template,
    render_json_template,
    render_yaml_template,
)
from vltconfig.validation import (
    Finding,
    FindingCode,
    Severity,
    ValidationReport,
    render_validation_report,
    validate_payload,
)
from vltconfig.vault_gateway import (
    HvacVaultGateway,
    VersionedSecret,
    VersionedVaultGateway,
)
from vltconfig.vault_source import PydanticVaultSource


class VaultJsonConfig(BaseSettings):
    """Base settings class that loads configuration from multiple sources.

    Configuration is loaded in the following priority order (highest to lowest):
    1. Environment variables
    2. HashiCorp Vault KV store
    3. JSON file (config.json)
    4. Initialization parameters
    5. .env file
    6. Docker/Kubernetes secrets

    To use, inherit from this class and define your configuration fields:

    Example:
        class AppConfig(VaultJsonConfig):
            service_name: str
            database_host: str
            debug: bool = False
    """

    model_config = SettingsConfigDict(populate_by_name=True)
    vault_failure_policy: ClassVar[VaultFailurePolicy] = VaultFailurePolicy.STRICT

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources and their priority.

        :param settings_cls: The settings class being instantiated
        :param init_settings: Settings from __init__ parameters
        :param env_settings: Settings from environment variables
        :param dotenv_settings: Settings from .env file
        :param file_secret_settings: Settings from Docker/K8s secrets
        :return: Tuple of settings sources in priority order
        """
        return (
            env_settings,
            PydanticVaultSource(
                settings_cls,
                failure_policy=cls.vault_failure_policy,
            ),
            PydanticJSONSource(settings_cls),
            init_settings,
            dotenv_settings,
            file_secret_settings,
        )


__all__ = [
    "REQUIRED_PLACEHOLDER",
    "ApplyResult",
    "ChangeCategory",
    "CheckResult",
    "ConfigurationPath",
    "ConfigurationPlan",
    "DefaultKind",
    "FieldSchema",
    "Finding",
    "FindingCode",
    "HvacVaultGateway",
    "ModelSchema",
    "PlanChange",
    "Severity",
    "ValidationReport",
    "VaultFailurePolicy",
    "VaultJsonConfig",
    "VersionedSecret",
    "VersionedVaultGateway",
    "apply_configuration",
    "build_model_schema",
    "build_plan",
    "build_template",
    "check_configuration",
    "export_json_schema",
    "plan_configuration",
    "render_configuration_plan",
    "render_json_schema",
    "render_json_template",
    "render_markdown_reference",
    "render_validation_report",
    "render_yaml_template",
    "validate_payload",
]
