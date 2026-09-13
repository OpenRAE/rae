"""Typed child models for the platform-applications runtime family.

These are the bounded, typed sub-collections held by
:class:`~raes.runtime_platform_application.RuntimePlatformApplication`:
provider-neutral capabilities, legacy content objects (bounded parsed
manifests — never raw bodies), releasability markings, organizations, tenants,
outbound upstream bindings, connectors, the optional execution policy, and
provenance-bearing settings.
"""

from typing import Any

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, parse_int_or_var
from .runtime_platform_application_vocab import (
    RuntimePlatformApplicationCapabilityKind,
    RuntimePlatformApplicationConnectorKind,
    RuntimePlatformApplicationContentObjectKind,
    RuntimePlatformApplicationMarkingScheme,
    RuntimePlatformApplicationSettingClassification,
    RuntimePlatformApplicationSettingProvenance,
    RuntimePlatformApplicationUpstreamBindingRole,
)
from .runtime_values import (
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    require_symbol,
)

__all__ = [
    "RuntimePlatformApplicationCapability",
    "RuntimePlatformApplicationConnector",
    "RuntimePlatformApplicationContentObject",
    "RuntimePlatformApplicationExecutionPolicy",
    "RuntimePlatformApplicationMarking",
    "RuntimePlatformApplicationOrganization",
    "RuntimePlatformApplicationSetting",
    "RuntimePlatformApplicationTenant",
    "RuntimePlatformApplicationUpstreamBinding",
]

_OMIT_RAW_CLASSIFICATIONS = (
    RuntimePlatformApplicationSettingClassification.REDACTED,
    RuntimePlatformApplicationSettingClassification.OPERATOR_SECRET,
)


def _reject_duplicate_values(values: list[object], *, field_name: str, owner: str) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate runtime platform application {field_name} entry on '{owner}'")
        seen.add(value)


class RuntimePlatformApplicationOrganization(SDLModel):
    """An organization/owner tenant known to the platform application."""

    organization_id: str
    name: str = ""
    description: str = ""

    @field_validator("organization_id")
    @classmethod
    def validate_organization_id(cls, v: str) -> str:
        return require_symbol(v, field_name="organization_id")


class RuntimePlatformApplicationTenant(SDLModel):
    """A tenant/namespace scope within the platform application."""

    tenant_id: str
    name: str = ""
    description: str = ""

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        return require_symbol(v, field_name="tenant_id")


class RuntimePlatformApplicationCapability(SDLModel):
    """A provider-neutral functional role exposed by the application.

    Capability declarations are composable and independent of product
    categories, configuration completeness, loaded content, policy, and
    execution guarantees. ``evidence_refs`` may identify the evidence supporting
    the declared runtime contract without embedding backend payloads.
    """

    capability_id: str
    kind: GovernedVocabulary[RuntimePlatformApplicationCapabilityKind] = (
        RuntimePlatformApplicationCapabilityKind.UNKNOWN
    )
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("capability_id")
    @classmethod
    def validate_capability_id(cls, v: str) -> str:
        return require_symbol(v, field_name="capability_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimePlatformApplicationCapabilityKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimePlatformApplicationCapabilityKind, field_name="kind")

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def coerce_evidence_refs(cls, v: object) -> object:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_capability(self) -> "RuntimePlatformApplicationCapability":
        _reject_duplicate_values(self.evidence_refs, field_name="evidence_refs", owner=self.capability_id)
        return self


class RuntimePlatformApplicationContentObject(SDLModel):
    """A legacy typed platform content object as a bounded manifest entry.

    The object carries a typed ``kind``, bounded typed ``attributes``, typed
    ``references`` (to other ``content_object_id`` values), ``marking_refs``,
    and ``evidence_refs`` — structurally **never** a raw object body. Its
    presence does not imply an application capability.
    """

    content_object_id: str
    kind: GovernedVocabulary[RuntimePlatformApplicationContentObjectKind] = (
        RuntimePlatformApplicationContentObjectKind.UNKNOWN
    )
    name: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)
    marking_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("content_object_id")
    @classmethod
    def validate_content_object_id(cls, v: str) -> str:
        return require_symbol(v, field_name="content_object_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimePlatformApplicationContentObjectKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimePlatformApplicationContentObjectKind, field_name="kind")

    @field_validator("references", "marking_refs", "evidence_refs", mode="before")
    @classmethod
    def coerce_ref_lists(cls, v: object) -> object:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_content_object(self) -> "RuntimePlatformApplicationContentObject":
        _reject_duplicate_values(self.references, field_name="references", owner=self.content_object_id)
        _reject_duplicate_values(self.marking_refs, field_name="marking_refs", owner=self.content_object_id)
        _reject_duplicate_values(self.evidence_refs, field_name="evidence_refs", owner=self.content_object_id)
        return self


class RuntimePlatformApplicationMarking(SDLModel):
    """A releasability marking (TLP/PAP/distribution) defined by the platform."""

    marking_id: str
    scheme: GovernedVocabulary[RuntimePlatformApplicationMarkingScheme] = RuntimePlatformApplicationMarkingScheme.TLP
    level: str = ""
    value: str = ""
    description: str = ""

    @field_validator("marking_id")
    @classmethod
    def validate_marking_id(cls, v: str) -> str:
        return require_symbol(v, field_name="marking_id")

    @field_validator("scheme", mode="before")
    @classmethod
    def normalize_scheme(cls, v: RuntimePlatformApplicationMarkingScheme | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimePlatformApplicationMarkingScheme, field_name="scheme")


class RuntimePlatformApplicationUpstreamBinding(SDLModel):
    """An outbound binding to an upstream node/service (data source, backend)."""

    binding_id: str
    role: GovernedVocabulary[RuntimePlatformApplicationUpstreamBindingRole] = (
        RuntimePlatformApplicationUpstreamBindingRole.UNKNOWN
    )
    target_node_ref: str = ""
    target_service_ref: str = ""
    description: str = ""

    @field_validator("binding_id")
    @classmethod
    def validate_binding_id(cls, v: str) -> str:
        return require_symbol(v, field_name="binding_id")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: RuntimePlatformApplicationUpstreamBindingRole | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimePlatformApplicationUpstreamBindingRole, field_name="role")


class RuntimePlatformApplicationConnector(SDLModel):
    """A connector/integration wired into the platform.

    A connector never carries a raw credential value; its credential posture is
    recorded purely via :attr:`credential_classification`.
    """

    connector_id: str
    kind: GovernedVocabulary[RuntimePlatformApplicationConnectorKind] = RuntimePlatformApplicationConnectorKind.UNKNOWN
    name: str = ""
    enabled: bool | str | None = None
    credential_classification: GovernedVocabulary[RuntimePlatformApplicationSettingClassification] = (
        RuntimePlatformApplicationSettingClassification.PLAIN
    )
    description: str = ""

    @field_validator("connector_id")
    @classmethod
    def validate_connector_id(cls, v: str) -> str:
        return require_symbol(v, field_name="connector_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimePlatformApplicationConnectorKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimePlatformApplicationConnectorKind, field_name="kind")

    @field_validator("credential_classification", mode="before")
    @classmethod
    def normalize_credential_classification(
        cls,
        v: RuntimePlatformApplicationSettingClassification | str,
    ) -> object:
        return parse_runtime_enum_or_var(
            v,
            RuntimePlatformApplicationSettingClassification,
            field_name="credential_classification",
        )

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_enabled(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="enabled")

    @model_validator(mode="after")
    def validate_connector(self) -> "RuntimePlatformApplicationConnector":
        return self


class RuntimePlatformApplicationExecutionPolicy(SDLModel):
    """The platform's job/analyzer execution model (rate limits, runner)."""

    policy_id: str = ""
    runner: str = ""
    max_concurrent_jobs: int | str | None = None
    job_timeout: str = ""
    rate_limit: str = ""
    description: str = ""

    @field_validator("policy_id")
    @classmethod
    def validate_policy_id(cls, v: str) -> str:
        return require_symbol(v, field_name="policy_id") if v else v

    @field_validator("max_concurrent_jobs", mode="before")
    @classmethod
    def parse_max_concurrent_jobs(cls, v: object) -> object:
        return parse_int_or_var(v, minimum=0, field_name="max_concurrent_jobs") if v is not None else v


class RuntimePlatformApplicationSetting(SDLModel):
    """An observed platform setting with provenance and sensitivity.

    Explicitly redacted/operator-secret settings must omit their raw ``value``.
    A setting name does not by itself redact SDL scenario content.
    """

    setting_id: str
    name: str = ""
    value: str = ""
    provenance: GovernedVocabulary[RuntimePlatformApplicationSettingProvenance] = (
        RuntimePlatformApplicationSettingProvenance.UNKNOWN
    )
    classification: GovernedVocabulary[RuntimePlatformApplicationSettingClassification] = (
        RuntimePlatformApplicationSettingClassification.PLAIN
    )
    redaction: str = ""
    description: str = ""

    @field_validator("setting_id")
    @classmethod
    def validate_setting_id(cls, v: str) -> str:
        return require_symbol(v, field_name="setting_id")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: RuntimePlatformApplicationSettingProvenance | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimePlatformApplicationSettingProvenance, field_name="provenance")

    @field_validator("classification", mode="before")
    @classmethod
    def normalize_classification(cls, v: RuntimePlatformApplicationSettingClassification | str) -> object:
        return parse_runtime_enum_or_var(
            v, RuntimePlatformApplicationSettingClassification, field_name="classification"
        )

    @model_validator(mode="after")
    def validate_setting(self) -> "RuntimePlatformApplicationSetting":
        enforce_observed_value_redaction(
            owner_label=f"platform setting '{self.name}'",
            value=self.value,
            classification=self.classification,
            redacted_classifications=_OMIT_RAW_CLASSIFICATIONS,
        )
        return self
