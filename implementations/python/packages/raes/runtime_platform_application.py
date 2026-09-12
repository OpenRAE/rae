"""Platform-application runtime inventory family (RuntimePlatformApplication).

The provider-neutral spine identifies an application and declares its
composable functional capabilities. A single application can expose threat
intelligence, exchange, case-management, analysis, workflow, and presentation
roles without being forced into one product category. The legacy
``platform_kind`` and ``content_objects`` fields remain accepted for compatible
document loading, but neither determines validity or implies the other.

The app's internal RBAC store is delegated to ``app_authorization`` via the
string ``authorization_ref`` (resolved by the semantic validator) and is never
re-typed here. Legacy content objects remain bounded parsed manifests — typed
kind + bounded attributes + typed references — never raw object bodies.
"""

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel
from .runtime_platform_application_content import (
    RuntimePlatformApplicationCapability,
    RuntimePlatformApplicationConnector,
    RuntimePlatformApplicationContentObject,
    RuntimePlatformApplicationExecutionPolicy,
    RuntimePlatformApplicationMarking,
    RuntimePlatformApplicationOrganization,
    RuntimePlatformApplicationSetting,
    RuntimePlatformApplicationTenant,
    RuntimePlatformApplicationUpstreamBinding,
)
from .runtime_platform_application_vocab import (
    RelationshipServiceIntegrationDirection,
    RelationshipServiceIntegrationKind,
    RuntimePlatformApplicationCapabilityKind,
    RuntimePlatformApplicationConnectorKind,
    RuntimePlatformApplicationContentObjectKind,
    RuntimePlatformApplicationKind,
    RuntimePlatformApplicationMarkingScheme,
    RuntimePlatformApplicationSettingClassification,
    RuntimePlatformApplicationSettingProvenance,
    RuntimePlatformApplicationUpstreamBindingRole,
)
from .runtime_values import parse_optional_bool_or_var, parse_runtime_enum_or_var, require_symbol

__all__ = [
    "RelationshipServiceIntegration",
    "RelationshipServiceIntegrationDirection",
    "RelationshipServiceIntegrationKind",
    "RuntimePlatformApplication",
    "RuntimePlatformApplicationCapability",
    "RuntimePlatformApplicationCapabilityKind",
    "RuntimePlatformApplicationConnector",
    "RuntimePlatformApplicationConnectorKind",
    "RuntimePlatformApplicationContentObject",
    "RuntimePlatformApplicationContentObjectKind",
    "RuntimePlatformApplicationExecutionPolicy",
    "RuntimePlatformApplicationKind",
    "RuntimePlatformApplicationMarking",
    "RuntimePlatformApplicationMarkingScheme",
    "RuntimePlatformApplicationOrganization",
    "RuntimePlatformApplicationSetting",
    "RuntimePlatformApplicationSettingClassification",
    "RuntimePlatformApplicationSettingProvenance",
    "RuntimePlatformApplicationTenant",
    "RuntimePlatformApplicationUpstreamBinding",
    "RuntimePlatformApplicationUpstreamBindingRole",
]


class RuntimePlatformApplication(SDLModel):
    """Node-scoped runtime inventory for a security platform application.

    ``service`` references the owning same-node ``Node.services[].name``. The
    inventory is application state above transport; it never duplicates the
    inbound HTTP route surface (``runtime.applications``) or mutates
    ``Node.services``. ``capabilities`` declare composable provider-neutral
    functional roles without implying content or configuration completeness.
    ``authorization_ref`` is the ``app_authorization_id`` of the platform's
    internal RBAC store (resolved by the semantic validator).
    """

    platform_application_id: str
    service: str = ""
    platform_kind: GovernedVocabulary[RuntimePlatformApplicationKind] = Field(
        default=RuntimePlatformApplicationKind.UNKNOWN,
        description=(
            "Legacy product-family category retained for compatibility; does not imply capabilities "
            "or configuration completeness. Use capabilities for new documents."
        ),
        json_schema_extra={"deprecated": True},
    )
    product: str = ""
    version: str = ""
    name: str = ""
    capabilities: list[RuntimePlatformApplicationCapability] = Field(default_factory=list)
    organizations: list[RuntimePlatformApplicationOrganization] = Field(default_factory=list)
    tenants: list[RuntimePlatformApplicationTenant] = Field(default_factory=list)
    content_objects: list[RuntimePlatformApplicationContentObject] = Field(
        default_factory=list,
        description=(
            "Legacy bounded platform-content manifests retained for compatibility; content presence "
            "does not define application capabilities."
        ),
        json_schema_extra={"deprecated": True},
    )
    markings: list[RuntimePlatformApplicationMarking] = Field(default_factory=list)
    upstream_bindings: list[RuntimePlatformApplicationUpstreamBinding] = Field(default_factory=list)
    connectors: list[RuntimePlatformApplicationConnector] = Field(default_factory=list)
    execution_policy: RuntimePlatformApplicationExecutionPolicy | None = None
    settings: list[RuntimePlatformApplicationSetting] = Field(default_factory=list)
    authorization_ref: str = ""
    description: str = ""

    @field_validator("platform_application_id")
    @classmethod
    def validate_platform_application_id(cls, v: str) -> str:
        return require_symbol(v, field_name="platform_application_id")

    @field_validator("platform_kind", mode="before")
    @classmethod
    def normalize_platform_kind(cls, v: RuntimePlatformApplicationKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimePlatformApplicationKind, field_name="platform_kind")

    @model_validator(mode="after")
    def validate_platform_application(self) -> "RuntimePlatformApplication":
        self._reject_duplicate_local_ref_ids()
        return self

    # ------------------------------------------------------------------ #
    # Local stable-id uniqueness
    # ------------------------------------------------------------------ #

    def _reject_duplicate_local_ref_ids(self) -> None:
        entries: list[tuple[str, str]] = [("platform_application_id", self.platform_application_id)]
        for label, collection_name in (
            ("capability_id", "capabilities"),
            ("organization_id", "organizations"),
            ("tenant_id", "tenants"),
            ("content_object_id", "content_objects"),
            ("marking_id", "markings"),
            ("binding_id", "upstream_bindings"),
            ("connector_id", "connectors"),
            ("setting_id", "settings"),
        ):
            entries.extend((label, getattr(item, label)) for item in getattr(self, collection_name))

        seen: dict[str, str] = {}
        for label, value in entries:
            prior = seen.get(value)
            if prior is not None:
                raise ValueError(
                    f"Duplicate runtime platform application stable id '{value}' in application "
                    f"'{self.platform_application_id}' across {prior} and {label}"
                )
            seen[value] = label


class RelationshipServiceIntegration(SDLModel):
    """Typed service-integration detail carried by a top-level relationship edge.

    When a consumer application integrates with a platform engine (analyzer,
    responder, webhook, notification, or enrichment), the relationship's
    endpoints resolve to the two platform applications and this block keeps the
    ``integration_kind``, ``auth_principal_ref`` (an ``app_authorization``
    ``principal_id`` in the target), and ``direction`` structurally validated
    rather than recorded as prose. ``consumer_ref``/``engine_ref`` are the
    ``platform_application_id`` symbols of the two endpoints; a ``${var}``
    placeholder is permitted in those refs.
    """

    consumer_ref: str = ""
    engine_ref: str = ""
    integration_kind: GovernedVocabulary[RelationshipServiceIntegrationKind] = (
        RelationshipServiceIntegrationKind.UNKNOWN
    )
    auth_principal_ref: str = ""
    enabled: bool | str | None = None
    direction: GovernedVocabulary[RelationshipServiceIntegrationDirection] = (
        RelationshipServiceIntegrationDirection.BIDIRECTIONAL
    )
    description: str = ""

    @field_validator("integration_kind", mode="before")
    @classmethod
    def normalize_integration_kind(
        cls, v: RelationshipServiceIntegrationKind | str
    ) -> RelationshipServiceIntegrationKind | str:
        return parse_runtime_enum_or_var(v, RelationshipServiceIntegrationKind, field_name="integration_kind")

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(
        cls, v: RelationshipServiceIntegrationDirection | str
    ) -> RelationshipServiceIntegrationDirection | str:
        return parse_runtime_enum_or_var(v, RelationshipServiceIntegrationDirection, field_name="direction")

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_enabled(cls, v: bool | str | None) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="enabled")
