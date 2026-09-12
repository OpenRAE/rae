"""Element models for the runtime mail-service inventory.

These are the typed leaf records (components, listeners, domains, mailbox
stores, mailboxes, aliases, routing rules, queues, and settings) aggregated by
:class:`raes.runtime_mail_service.RuntimeMailService`.
"""

import re

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from .._base import SDLModel, is_variable_ref, parse_int_or_var
from ..runtime_filesystem import RuntimeSensitivityClassification
from ..runtime_mail_vocab import (
    RuntimeMailAuthMechanism,
    RuntimeMailComponentKind,
    RuntimeMailCredentialClassification,
    RuntimeMailDomainRole,
    RuntimeMailListenerRole,
    RuntimeMailMailboxRole,
    RuntimeMailMailboxStatus,
    RuntimeMailMailboxStoreKind,
    RuntimeMailProtocol,
    RuntimeMailQueueKind,
    RuntimeMailQueueStability,
    RuntimeMailRoutingKind,
    RuntimeMailSettingProvenance,
    RuntimeMailTlsMode,
)
from ..runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_runtime_enum_or_var,
    require_non_empty,
    require_symbol,
)

_EMAIL_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+$")
_REDACTED_SENSITIVITIES = (
    RuntimeSensitivityClassification.REDACTED,
    RuntimeSensitivityClassification.OPERATOR_SECRET,
)


def _mail_address_or_var(value: str, *, field_name: str) -> str:
    if is_variable_ref(value):
        return value
    if not isinstance(value, str) or not _EMAIL_ADDRESS.fullmatch(value):
        raise ValueError(f"{field_name} must be a mailbox address of the form local@domain")
    return value


def _domain_name_or_var(value: str, *, field_name: str) -> str:
    if is_variable_ref(value):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if any(ch.isspace() for ch in value):
        raise ValueError(f"{field_name} must not contain whitespace")
    return value


class RuntimeMailComponent(SDLModel):
    """A mail-service engine/component such as Postfix, Dovecot, or a filter."""

    component_id: str
    kind: GovernedVocabulary[RuntimeMailComponentKind] = RuntimeMailComponentKind.OTHER
    name: str
    version: str = ""
    description: str = ""

    @field_validator("component_id")
    @classmethod
    def validate_component_id(cls, v: str) -> str:
        return require_symbol(v, field_name="component_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeMailComponentKind | str) -> RuntimeMailComponentKind | str:
        return parse_runtime_enum_or_var(v, RuntimeMailComponentKind, field_name="kind")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="component name")


class RuntimeMailListener(SDLModel):
    """A protocol listener bound to a same-node transport service."""

    listener_id: str
    service: str = ""
    protocol: GovernedVocabulary[RuntimeMailProtocol] = RuntimeMailProtocol.OTHER
    role: GovernedVocabulary[RuntimeMailListenerRole] = RuntimeMailListenerRole.OTHER
    component_ref: str = ""
    banner: str = ""
    advertised_identity: str = ""
    capabilities: list[str] = Field(default_factory=list)
    auth_mechanisms: list[GovernedVocabulary[RuntimeMailAuthMechanism]] = Field(default_factory=list)
    tls_mode: GovernedVocabulary[RuntimeMailTlsMode] = RuntimeMailTlsMode.UNKNOWN
    tls_versions: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("listener_id")
    @classmethod
    def validate_listener_id(cls, v: str) -> str:
        return require_symbol(v, field_name="listener_id")

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, v: RuntimeMailProtocol | str) -> RuntimeMailProtocol | str:
        return parse_runtime_enum_or_var(v, RuntimeMailProtocol, field_name="protocol")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: RuntimeMailListenerRole | str) -> RuntimeMailListenerRole | str:
        return parse_runtime_enum_or_var(v, RuntimeMailListenerRole, field_name="role")

    @field_validator("capabilities", "tls_versions", mode="before")
    @classmethod
    def coerce_string_lists(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("auth_mechanisms", mode="before")
    @classmethod
    def coerce_auth_mechanisms(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("auth_mechanisms")
    @classmethod
    def normalize_auth_mechanisms(cls, v: list[RuntimeMailAuthMechanism | str]) -> list[RuntimeMailAuthMechanism | str]:
        return [parse_runtime_enum_or_var(item, RuntimeMailAuthMechanism, field_name="auth_mechanism") for item in v]

    @field_validator("tls_mode", mode="before")
    @classmethod
    def normalize_tls_mode(cls, v: RuntimeMailTlsMode | str) -> RuntimeMailTlsMode | str:
        return parse_runtime_enum_or_var(v, RuntimeMailTlsMode, field_name="tls_mode")


class RuntimeMailDomain(SDLModel):
    """A domain known to the runtime mail service."""

    domain_id: str
    name: str
    role: GovernedVocabulary[RuntimeMailDomainRole] = RuntimeMailDomainRole.OTHER
    description: str = ""

    @field_validator("domain_id")
    @classmethod
    def validate_domain_id(cls, v: str) -> str:
        return require_symbol(v, field_name="domain_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _domain_name_or_var(v, field_name="domain name")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: RuntimeMailDomainRole | str) -> RuntimeMailDomainRole | str:
        return parse_runtime_enum_or_var(v, RuntimeMailDomainRole, field_name="role")


class RuntimeMailMailboxStore(SDLModel):
    """Mailbox storage backing for service-local mailboxes."""

    store_id: str
    kind: GovernedVocabulary[RuntimeMailMailboxStoreKind] = RuntimeMailMailboxStoreKind.OTHER
    path: str = ""
    description: str = ""

    @field_validator("store_id")
    @classmethod
    def validate_store_id(cls, v: str) -> str:
        return require_symbol(v, field_name="store_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeMailMailboxStoreKind | str) -> RuntimeMailMailboxStoreKind | str:
        return parse_runtime_enum_or_var(v, RuntimeMailMailboxStoreKind, field_name="kind")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v:
            return v
        return absolute_path_or_var(v, field_name="mailbox store path")


class RuntimeMailMailbox(SDLModel):
    """A service-local mailbox/account record.

    Raw credentials are intentionally unrepresentable. The model records only
    authentication mechanisms and credential-strength classification.
    """

    mailbox_id: str
    address: str
    local_part: str = ""
    domain_ref: str = ""
    role: GovernedVocabulary[RuntimeMailMailboxRole] = RuntimeMailMailboxRole.USER
    status: GovernedVocabulary[RuntimeMailMailboxStatus] = RuntimeMailMailboxStatus.UNKNOWN
    auth_mechanisms: list[GovernedVocabulary[RuntimeMailAuthMechanism]] = Field(default_factory=list)
    credential_classification: GovernedVocabulary[RuntimeMailCredentialClassification] = (
        RuntimeMailCredentialClassification.UNKNOWN
    )
    store_ref: str = ""
    account_ref: str = ""
    local_user_ref: str = ""
    description: str = ""

    @field_validator("mailbox_id")
    @classmethod
    def validate_mailbox_id(cls, v: str) -> str:
        return require_symbol(v, field_name="mailbox_id")

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return _mail_address_or_var(v, field_name="mailbox address")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: RuntimeMailMailboxRole | str) -> RuntimeMailMailboxRole | str:
        return parse_runtime_enum_or_var(v, RuntimeMailMailboxRole, field_name="role")

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: RuntimeMailMailboxStatus | str) -> RuntimeMailMailboxStatus | str:
        return parse_runtime_enum_or_var(v, RuntimeMailMailboxStatus, field_name="status")

    @field_validator("auth_mechanisms", mode="before")
    @classmethod
    def coerce_auth_mechanisms(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("auth_mechanisms")
    @classmethod
    def normalize_auth_mechanisms(cls, v: list[RuntimeMailAuthMechanism | str]) -> list[RuntimeMailAuthMechanism | str]:
        return [parse_runtime_enum_or_var(item, RuntimeMailAuthMechanism, field_name="auth_mechanism") for item in v]

    @field_validator("credential_classification", mode="before")
    @classmethod
    def normalize_credential_classification(
        cls,
        v: RuntimeMailCredentialClassification | str,
    ) -> RuntimeMailCredentialClassification | str:
        return parse_runtime_enum_or_var(
            v,
            RuntimeMailCredentialClassification,
            field_name="credential_classification",
        )


class RuntimeMailAlias(SDLModel):
    """A service-local mailbox alias or forwarding address."""

    alias_id: str
    address: str = ""
    domain_ref: str = ""
    target_refs: list[str] = Field(default_factory=list)
    external_targets: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("alias_id")
    @classmethod
    def validate_alias_id(cls, v: str) -> str:
        return require_symbol(v, field_name="alias_id")

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        if not v:
            return v
        return _mail_address_or_var(v, field_name="alias address")

    @field_validator("target_refs", "external_targets", mode="before")
    @classmethod
    def coerce_targets(cls, v: object) -> list[str]:
        return coerce_string_list(v)

    @field_validator("external_targets")
    @classmethod
    def validate_external_targets(cls, v: list[str]) -> list[str]:
        return [_mail_address_or_var(item, field_name="external target") for item in v]


class RuntimeMailRoutingRule(SDLModel):
    """A portable routing, aliasing, local-delivery, or relay rule."""

    rule_id: str
    kind: GovernedVocabulary[RuntimeMailRoutingKind] = RuntimeMailRoutingKind.OTHER
    source_ref: str = ""
    target_ref: str = ""
    relay_host: str = ""
    description: str = ""

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, v: str) -> str:
        return require_symbol(v, field_name="rule_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeMailRoutingKind | str) -> RuntimeMailRoutingKind | str:
        return parse_runtime_enum_or_var(v, RuntimeMailRoutingKind, field_name="kind")


class RuntimeMailQueue(SDLModel):
    """Shape of a mail queue; dynamic content is explicitly classified."""

    queue_id: str
    kind: GovernedVocabulary[RuntimeMailQueueKind] = RuntimeMailQueueKind.OTHER
    name: str = ""
    message_count: int | str | None = None
    stability: GovernedVocabulary[RuntimeMailQueueStability] = RuntimeMailQueueStability.DYNAMIC
    description: str = ""

    @field_validator("queue_id")
    @classmethod
    def validate_queue_id(cls, v: str) -> str:
        return require_symbol(v, field_name="queue_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeMailQueueKind | str) -> RuntimeMailQueueKind | str:
        return parse_runtime_enum_or_var(v, RuntimeMailQueueKind, field_name="kind")

    @field_validator("message_count", mode="before")
    @classmethod
    def parse_message_count(cls, v: int | str | None) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name="message_count") if v is not None else v

    @field_validator("stability", mode="before")
    @classmethod
    def normalize_stability(cls, v: RuntimeMailQueueStability | str) -> RuntimeMailQueueStability | str:
        return parse_runtime_enum_or_var(v, RuntimeMailQueueStability, field_name="stability")


class RuntimeMailSetting(SDLModel):
    """A mail-service runtime setting with source/provenance and redaction."""

    setting_id: str
    component_ref: str = ""
    name: str
    value: str = ""
    value_classification: GovernedVocabulary[RuntimeSensitivityClassification] = (
        RuntimeSensitivityClassification.UNKNOWN
    )
    provenance: GovernedVocabulary[RuntimeMailSettingProvenance] = RuntimeMailSettingProvenance.UNKNOWN
    source_path: str = ""
    description: str = ""

    @field_validator("setting_id")
    @classmethod
    def validate_setting_id(cls, v: str) -> str:
        return require_symbol(v, field_name="setting_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="setting name")

    @field_validator("value_classification", mode="before")
    @classmethod
    def normalize_value_classification(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="value_classification")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: RuntimeMailSettingProvenance | str) -> RuntimeMailSettingProvenance | str:
        return parse_runtime_enum_or_var(v, RuntimeMailSettingProvenance, field_name="provenance")

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, v: str) -> str:
        if not v:
            return v
        return absolute_path_or_var(v, field_name="source_path")

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "RuntimeMailSetting":
        enforce_observed_value_redaction(
            owner_label=f"mail setting '{self.name}'",
            value=self.value,
            classification=self.value_classification,
            redacted_classifications=_REDACTED_SENSITIVITIES,
        )
        return self
