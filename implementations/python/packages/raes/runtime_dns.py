"""Observed DNS service logical-state runtime inventory models.

These models express node-scoped DNS service state: authoritative zones,
RRsets, typed common RDATA, resolver policy, forwarding, DNSSEC validation,
dynamic-update posture, logging posture, and provenance/evidence file refs.

The surface is observed runtime state attached to ``Node.runtime``. It is
distinct from ``Node.services`` transport bindings, ``runtime.network`` host or
container DNS settings, ``runtime.software_components`` server identity,
``content`` file payloads, and generic top-level relationships. Raw BIND,
CoreDNS, PowerDNS, AXFR, and zone-file payloads remain evidence inputs rather
than the portable SDL model.
"""

import ipaddress

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, is_variable_ref
from .runtime_dns_records import (
    DnsMxRdata,
    DnsResourceRecord,
    DnsResourceRecordSet,
    DnsSoaRdata,
    DnsSrvRdata,
    _dns_name_or_var,
    _parse_port_or_var,
)
from .runtime_dns_vocab import (
    DnsForwarderTransport,
    DnsForwardingPolicy,
    DnsRecordClass,
    DnsRecordProvenance,
    DnsRecordType,
    DnssecValidationMode,
    DnsServerImplementation,
    DnsServiceRole,
    DnsSettingProvenance,
    DnsZoneKind,
    DnsZonePurpose,
)
from .runtime_filesystem import RuntimeSensitivityClassification
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    reject_duplicates,
    require_non_empty,
    require_symbol,
)

__all__ = [
    "DnsDynamicUpdatePolicy",
    "DnsForwarder",
    "DnsForwarderTransport",
    "DnsForwardingPolicy",
    "DnsMxRdata",
    "DnsRecordClass",
    "DnsRecordProvenance",
    "DnsRecordType",
    "DnsResolverPolicy",
    "DnsResourceRecord",
    "DnsResourceRecordSet",
    "DnsRuntimeSetting",
    "DnsSettingProvenance",
    "DnsSrvRdata",
    "DnsSoaRdata",
    "DnsZone",
    "DnsZoneKind",
    "DnsZonePurpose",
    "DnsZoneTransferPolicy",
    "DnssecValidationMode",
    "RuntimeDnsService",
    "DnsServerImplementation",
    "DnsServiceRole",
]

_REDACTED_SENSITIVITIES = (
    RuntimeSensitivityClassification.REDACTED,
    RuntimeSensitivityClassification.OPERATOR_SECRET,
)
_DUPLICATE_DNS_TEMPLATE = "Duplicate DNS {label} '{value}' in {container_label}"


def _policy_selector_or_var(value: str, *, field_name: str) -> str:
    if is_variable_ref(value):
        return value
    require_non_empty(value, field_name=field_name)
    if any(ch.isspace() for ch in value):
        raise ValueError(f"{field_name} must not contain whitespace")
    try:
        if "/" in value:
            ipaddress.ip_network(value, strict=False)
        else:
            ipaddress.ip_address(value)
    except ValueError:
        # BIND/CoreDNS-style ACL labels such as "trusted" are allowed data.
        pass
    return value


class DnsForwarder(SDLModel):
    """Recursive upstream resolver endpoint."""

    address: str
    port: int | str = 53
    transport: GovernedVocabulary[DnsForwarderTransport] = DnsForwarderTransport.UDP
    tls_server_name: str = ""
    description: str = ""

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return _policy_selector_or_var(v, field_name="forwarder address")

    @field_validator("port", mode="before")
    @classmethod
    def parse_port(cls, v: object) -> int | str:
        return _parse_port_or_var(v, field_name="forwarder port")

    @field_validator("transport", mode="before")
    @classmethod
    def normalize_transport(cls, v: DnsForwarderTransport | str) -> DnsForwarderTransport | str:
        return parse_runtime_enum_or_var(v, DnsForwarderTransport, field_name="forwarder transport")


class DnsResolverPolicy(SDLModel):
    """Recursive/forwarding resolver policy for a DNS service."""

    recursion_enabled: bool | str | None = None
    allow_recursion: list[str] = Field(default_factory=list)
    forwarders: list[DnsForwarder] = Field(default_factory=list)
    forwarding_policy: GovernedVocabulary[DnsForwardingPolicy] = DnsForwardingPolicy.UNKNOWN
    dnssec_validation: GovernedVocabulary[DnssecValidationMode] = DnssecValidationMode.UNKNOWN
    query_logging: bool | str | None = None
    default_logging: bool | str | None = None
    description: str = ""

    @field_validator("recursion_enabled", "query_logging", "default_logging", mode="before")
    @classmethod
    def parse_optional_bool(cls, v: object, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)

    @field_validator("allow_recursion", mode="before")
    @classmethod
    def coerce_allow_recursion(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("allow_recursion")
    @classmethod
    def validate_allow_recursion(cls, v: list[str]) -> list[str]:
        return [_policy_selector_or_var(item, field_name="allow_recursion") for item in v]

    @field_validator("forwarding_policy", mode="before")
    @classmethod
    def normalize_forwarding_policy(cls, v: DnsForwardingPolicy | str) -> DnsForwardingPolicy | str:
        return parse_runtime_enum_or_var(v, DnsForwardingPolicy, field_name="forwarding_policy")

    @field_validator("dnssec_validation", mode="before")
    @classmethod
    def normalize_dnssec_validation(cls, v: DnssecValidationMode | str) -> DnssecValidationMode | str:
        return parse_runtime_enum_or_var(v, DnssecValidationMode, field_name="dnssec_validation")


class DnsZoneTransferPolicy(SDLModel):
    """Observed zone-transfer posture for a DNS zone."""

    axfr_enabled: bool | str | None = None
    ixfr_enabled: bool | str | None = None
    allowed_clients: list[str] = Field(default_factory=list)
    primary_servers: list[str] = Field(default_factory=list)
    secondary_servers: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("axfr_enabled", "ixfr_enabled", mode="before")
    @classmethod
    def parse_optional_bool(cls, v: object, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)

    @field_validator("allowed_clients", "primary_servers", "secondary_servers", mode="before")
    @classmethod
    def coerce_lists(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("allowed_clients", "primary_servers", "secondary_servers")
    @classmethod
    def validate_selectors(cls, v: list[str], info: ValidationInfo) -> list[str]:
        return [_policy_selector_or_var(item, field_name=info.field_name) for item in v]


class DnsDynamicUpdatePolicy(SDLModel):
    """Observed dynamic-update posture without raw update credentials."""

    enabled: bool | str | None = None
    allowed_clients: list[str] = Field(default_factory=list)
    key_names: list[str] = Field(default_factory=list)
    policy: str = ""
    description: str = ""

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_enabled(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="dynamic update enabled")

    @field_validator("allowed_clients", "key_names", mode="before")
    @classmethod
    def coerce_lists(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("allowed_clients")
    @classmethod
    def validate_allowed_clients(cls, v: list[str]) -> list[str]:
        return [_policy_selector_or_var(item, field_name="dynamic update allowed_clients") for item in v]

    @field_validator("key_names")
    @classmethod
    def validate_key_names(cls, v: list[str]) -> list[str]:
        for item in v:
            require_non_empty(item, field_name="dynamic update key_names")
        if len(v) != len(set(v)):
            raise ValueError("Duplicate DNS dynamic update key_names entry")
        return v


class DnsRuntimeSetting(SDLModel):
    """Bounded DNS runtime setting with provenance and redaction."""

    name: str
    value: str = ""
    value_classification: GovernedVocabulary[RuntimeSensitivityClassification] = (
        RuntimeSensitivityClassification.UNKNOWN
    )
    provenance: GovernedVocabulary[DnsSettingProvenance] = DnsSettingProvenance.UNKNOWN
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="DNS setting name")

    @field_validator("value_classification", mode="before")
    @classmethod
    def normalize_value_classification(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="value_classification")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: DnsSettingProvenance | str) -> DnsSettingProvenance | str:
        return parse_runtime_enum_or_var(v, DnsSettingProvenance, field_name="provenance")

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "DnsRuntimeSetting":
        enforce_observed_value_redaction(
            owner_label=f"DNS setting '{self.name}'",
            value=self.value,
            classification=self.value_classification,
            redacted_classifications=_REDACTED_SENSITIVITIES,
        )
        return self


class DnsZone(SDLModel):
    """An observed authoritative or forwarding DNS zone."""

    zone_id: str
    name: str
    kind: GovernedVocabulary[DnsZoneKind] = DnsZoneKind.UNKNOWN
    purpose: GovernedVocabulary[DnsZonePurpose] = DnsZonePurpose.UNKNOWN
    zone_class: GovernedVocabulary[DnsRecordClass] = DnsRecordClass.IN
    provenance: GovernedVocabulary[DnsRecordProvenance] = DnsRecordProvenance.UNKNOWN
    zone_file_refs: list[str] = Field(default_factory=list)
    transfer: DnsZoneTransferPolicy | None = None
    rrsets: list[DnsResourceRecordSet] = Field(default_factory=list)
    description: str = ""

    @field_validator("zone_id")
    @classmethod
    def validate_zone_id(cls, v: str) -> str:
        return require_symbol(v, field_name="zone_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _dns_name_or_var(v, field_name="zone name")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: DnsZoneKind | str) -> DnsZoneKind | str:
        return parse_runtime_enum_or_var(v, DnsZoneKind, field_name="zone kind")

    @field_validator("purpose", mode="before")
    @classmethod
    def normalize_purpose(cls, v: DnsZonePurpose | str) -> DnsZonePurpose | str:
        return parse_runtime_enum_or_var(v, DnsZonePurpose, field_name="zone purpose")

    @field_validator("zone_class", mode="before")
    @classmethod
    def normalize_zone_class(cls, v: DnsRecordClass | str) -> DnsRecordClass | str:
        return parse_runtime_enum_or_var(v, DnsRecordClass, field_name="zone_class")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: DnsRecordProvenance | str) -> DnsRecordProvenance | str:
        return parse_runtime_enum_or_var(v, DnsRecordProvenance, field_name="provenance")

    @field_validator("zone_file_refs", mode="before")
    @classmethod
    def coerce_zone_file_refs(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("zone_file_refs")
    @classmethod
    def validate_zone_file_refs(cls, v: list[str]) -> list[str]:
        return [absolute_path_or_var(item, field_name="zone_file_refs") for item in v]

    @model_validator(mode="after")
    def validate_zone(self) -> "DnsZone":
        reject_duplicates(
            (rrset.rrset_id for rrset in self.rrsets),
            label="rrset_id",
            container_label=f"zone '{self.zone_id}'",
            duplicate_template=_DUPLICATE_DNS_TEMPLATE,
        )
        seen_bindings: set[tuple[str, str, str]] = set()
        for rrset in self.rrsets:
            record_type = (
                rrset.record_type.value if isinstance(rrset.record_type, DnsRecordType) else str(rrset.record_type)
            )
            zone_class = (
                rrset.zone_class.value if isinstance(rrset.zone_class, DnsRecordClass) else str(rrset.zone_class)
            )
            binding = (rrset.owner.lower(), zone_class.lower(), record_type.lower())
            if binding in seen_bindings:
                raise ValueError(
                    f"Duplicate DNS RRset binding '{rrset.owner} {zone_class} {record_type}' in zone '{self.zone_id}'"
                )
            seen_bindings.add(binding)
        return self


class RuntimeDnsService(SDLModel):
    """An observed DNS service hosted by a node."""

    dns_service_id: str
    service: str = ""
    implementation: GovernedVocabulary[DnsServerImplementation] = DnsServerImplementation.UNKNOWN
    version: str = ""
    name: str = ""
    roles: list[GovernedVocabulary[DnsServiceRole]] = Field(default_factory=list)
    configuration_file_refs: list[str] = Field(default_factory=list)
    log_file_refs: list[str] = Field(default_factory=list)
    resolver_policy: DnsResolverPolicy | None = None
    dynamic_update: DnsDynamicUpdatePolicy | None = None
    zones: list[DnsZone] = Field(default_factory=list)
    settings: list[DnsRuntimeSetting] = Field(default_factory=list)
    description: str = ""

    @field_validator("dns_service_id")
    @classmethod
    def validate_dns_service_id(cls, v: str) -> str:
        return require_symbol(v, field_name="dns_service_id")

    @field_validator("implementation", mode="before")
    @classmethod
    def normalize_implementation(cls, v: DnsServerImplementation | str) -> DnsServerImplementation | str:
        return parse_runtime_enum_or_var(v, DnsServerImplementation, field_name="implementation")

    @field_validator("roles", mode="before")
    @classmethod
    def coerce_roles(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, v: list[DnsServiceRole | str]) -> list[DnsServiceRole | str]:
        return [parse_runtime_enum_or_var(item, DnsServiceRole, field_name="role") for item in v]

    @field_validator("configuration_file_refs", "log_file_refs", mode="before")
    @classmethod
    def coerce_file_refs(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("configuration_file_refs", "log_file_refs")
    @classmethod
    def validate_file_refs(cls, v: list[str], info: ValidationInfo) -> list[str]:
        return [absolute_path_or_var(item, field_name=info.field_name) for item in v]

    @model_validator(mode="after")
    def validate_service(self) -> "RuntimeDnsService":
        reject_duplicates(
            (zone.zone_id for zone in self.zones),
            label="zone_id",
            container_label=f"DNS service '{self.dns_service_id}'",
            duplicate_template=_DUPLICATE_DNS_TEMPLATE,
        )
        reject_duplicates(
            (setting.name for setting in self.settings),
            label="setting",
            container_label=f"DNS service '{self.dns_service_id}'",
            duplicate_template=_DUPLICATE_DNS_TEMPLATE,
        )
        return self
