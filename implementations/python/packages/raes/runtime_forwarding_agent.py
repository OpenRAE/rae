"""Forwarding / intel-sync agent runtime inventory family (SCN-010 §5.5).

A single node-scoped family, :class:`RuntimeForwardingAgent`, typing the
agent-side ``(source, transform, ship-target, buffer)`` shipping state that
``runtime.security_monitoring_managers`` (the *manager* half) and
``runtime.network_detection_engines`` (the *consumer* of generated content)
provably cannot shape. It covers both the log-shipping sidecars
(``agent_kind = log_forwarder``) and the intel-sync co-process
(``agent_kind = content_sync``) — the same ``source -> transform -> target``
shape in the intel-to-content direction — so the second never forks a third
family.

The OPEN ``agent_kind`` discriminator selects the family member; the
``require_profile_for_agent_kind`` after-validator makes each member's defining
profile executable so an under-populated instance FAILS validation rather than
silently shallow-encoding a defining shipping fact. A ``${var}`` discriminator
is exempt (nothing concrete is asserted); the ``unknown`` / ``other`` tail is
permissive.

This is observed runtime state attached to ``Node.runtime``. Secret-bearing
setting values are scenario content unless explicitly classified
``redacted`` / ``operator_secret``; ship-target enrollment identities use the
closed enrollment lattice because they intentionally carry no raw value field.
"""

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, is_variable_ref, parse_int_or_var
from ._identifiers import require_qualified_identifier
from .runtime_forwarding_agent_vocab import (
    RuntimeForwardingAgentImplementation,
    RuntimeForwardingAgentKind,
    RuntimeForwardingAgentOwnershipRole,
    RuntimeForwardingBufferCrypto,
    RuntimeForwardingEnrollmentClassification,
    RuntimeForwardingParseFormat,
    RuntimeForwardingProtocol,
    RuntimeForwardingReloadChannelKind,
    RuntimeForwardingSettingClassification,
    RuntimeForwardingSettingProvenance,
    RuntimeForwardingSourceKind,
    RuntimeForwardingTransformKind,
)
from .runtime_forwarding_buffer import RuntimeForwardingBufferPolicy
from .runtime_security_monitoring import RuntimeSecurityMonitoringListenerRole
from .runtime_values import (
    enforce_observed_value_redaction,
    parse_runtime_enum_or_var,
    require_symbol,
)

__all__ = [
    "RelationshipForwardingEdge",
    "RuntimeForwardingAgent",
    "RuntimeForwardingAgentImplementation",
    "RuntimeForwardingAgentKind",
    "RuntimeForwardingAgentOwnershipRole",
    "RuntimeForwardingBufferCrypto",
    "RuntimeForwardingBufferPolicy",
    "RuntimeForwardingEnrollmentClassification",
    "RuntimeForwardingParseFormat",
    "RuntimeForwardingProtocol",
    "RuntimeForwardingReloadChannel",
    "RuntimeForwardingReloadChannelKind",
    "RuntimeForwardingSetting",
    "RuntimeForwardingSettingClassification",
    "RuntimeForwardingSettingProvenance",
    "RuntimeForwardingShipTarget",
    "RuntimeForwardingSource",
    "RuntimeForwardingSourceKind",
    "RuntimeForwardingTransform",
    "RuntimeForwardingTransformKind",
]

# Enrollment classifications that mark a present (but unrecorded) credential.
_PRESENT_ENROLLMENT_CLASSIFICATIONS = frozenset(
    {
        RuntimeForwardingEnrollmentClassification.REDACTED,
        RuntimeForwardingEnrollmentClassification.OPERATOR_SECRET,
    }
)
# Setting classifications whose raw value must never be recorded.
_REDACTED_SETTING_CLASSIFICATIONS = (
    RuntimeForwardingSettingClassification.REDACTED,
    RuntimeForwardingSettingClassification.OPERATOR_SECRET,
)


class RuntimeForwardingSource(SDLModel):
    """An observed forwarder input source (tailed path, API pull, or queue)."""

    source_id: str
    kind: GovernedVocabulary[RuntimeForwardingSourceKind] = RuntimeForwardingSourceKind.UNKNOWN
    location: str = ""
    parse_format: GovernedVocabulary[RuntimeForwardingParseFormat] = RuntimeForwardingParseFormat.UNKNOWN
    selector: str = ""
    description: str = ""

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        return require_symbol(v, field_name="source_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeForwardingSourceKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingSourceKind, field_name="kind")

    @field_validator("parse_format", mode="before")
    @classmethod
    def normalize_parse_format(cls, v: RuntimeForwardingParseFormat | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingParseFormat, field_name="parse_format")


class RuntimeForwardingTransform(SDLModel):
    """An observed transform applied between a source and a ship target."""

    transform_id: str
    kind: GovernedVocabulary[RuntimeForwardingTransformKind] = RuntimeForwardingTransformKind.UNKNOWN
    sid_namespace: str = ""
    description: str = ""

    @field_validator("transform_id")
    @classmethod
    def validate_transform_id(cls, v: str) -> str:
        return require_symbol(v, field_name="transform_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeForwardingTransformKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingTransformKind, field_name="kind")


class RuntimeForwardingShipTarget(SDLModel):
    """An observed downstream ship target (event ingest and/or enrollment).

    ``ingestion_port`` is the event-ingest endpoint (e.g. ``wazuh.manager:1514``);
    ``enrollment_port`` is the enrollment endpoint (e.g. ``:1515``). The
    enrollment identity itself is never recorded — only the closed
    ``enrollment_identity_classification`` lattice (``none`` / ``redacted`` /
    ``operator_secret``).
    """

    target_id: str
    target_node_ref: str = ""
    target_service_ref: str = ""
    ingestion_port: int | str | None = None
    enrollment_port: int | str | None = None
    protocol: GovernedVocabulary[RuntimeForwardingProtocol] = RuntimeForwardingProtocol.UNKNOWN
    enrollment_identity_classification: GovernedVocabulary[RuntimeForwardingEnrollmentClassification] = (
        RuntimeForwardingEnrollmentClassification.NONE
    )
    description: str = ""

    @field_validator("target_id")
    @classmethod
    def validate_target_id(cls, v: str) -> str:
        return require_symbol(v, field_name="target_id")

    @field_validator("ingestion_port", "enrollment_port", mode="before")
    @classmethod
    def parse_ports(cls, v: object, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=0, maximum=65535, field_name=info.field_name) if v is not None else v

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, v: RuntimeForwardingProtocol | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingProtocol, field_name="protocol")

    @field_validator("enrollment_identity_classification", mode="before")
    @classmethod
    def normalize_enrollment_classification(cls, v: RuntimeForwardingEnrollmentClassification | str) -> object:
        return parse_runtime_enum_or_var(
            v, RuntimeForwardingEnrollmentClassification, field_name="enrollment_identity_classification"
        )

    def has_ingestion_endpoint(self) -> bool:
        """Return whether this target carries a concrete event-ingest endpoint."""
        return self.ingestion_port is not None

    def has_enrollment_endpoint(self) -> bool:
        """Return whether this target carries an enrollment endpoint or identity."""
        if self.enrollment_port is not None:
            return True
        classification = self.enrollment_identity_classification
        return (
            isinstance(classification, RuntimeForwardingEnrollmentClassification)
            and classification in _PRESENT_ENROLLMENT_CLASSIFICATIONS
        )


class RuntimeForwardingReloadChannel(SDLModel):
    """An observed downstream reload channel a content-sync agent drives.

    References the downstream consumer's control channel (e.g. the Suricata
    rule-reload socket) rather than inventing a parallel socket model; the
    inter-node trust edge is carried by ``RelationshipForwardingEdge``.
    """

    reload_channel_id: str
    target_ref: str = ""
    kind: GovernedVocabulary[RuntimeForwardingReloadChannelKind] = RuntimeForwardingReloadChannelKind.UNKNOWN
    description: str = ""

    @field_validator("reload_channel_id")
    @classmethod
    def validate_reload_channel_id(cls, v: str) -> str:
        return require_symbol(v, field_name="reload_channel_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeForwardingReloadChannelKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingReloadChannelKind, field_name="kind")


class RuntimeForwardingSetting(SDLModel):
    """An observed forwarding-agent runtime setting with provenance and class.

    Explicit ``redacted`` / ``operator_secret`` classifications omit raw values;
    credential-shaped names remain scenario content unless the author marks the
    value withheld.
    """

    setting_id: str
    name: str = ""
    value: str = ""
    provenance: GovernedVocabulary[RuntimeForwardingSettingProvenance] = RuntimeForwardingSettingProvenance.UNKNOWN
    classification: GovernedVocabulary[RuntimeForwardingSettingClassification] = (
        RuntimeForwardingSettingClassification.PLAIN
    )
    description: str = ""

    @field_validator("setting_id")
    @classmethod
    def validate_setting_id(cls, v: str) -> str:
        return require_symbol(v, field_name="setting_id")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: RuntimeForwardingSettingProvenance | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingSettingProvenance, field_name="provenance")

    @field_validator("classification", mode="before")
    @classmethod
    def normalize_classification(cls, v: RuntimeForwardingSettingClassification | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingSettingClassification, field_name="classification")

    @model_validator(mode="after")
    def validate_setting(self) -> "RuntimeForwardingSetting":
        enforce_observed_value_redaction(
            owner_label=f"forwarding setting '{self.setting_id}'",
            value=self.value,
            classification=self.classification,
            redacted_classifications=_REDACTED_SETTING_CLASSIFICATIONS,
        )
        return self


class RuntimeForwardingAgent(SDLModel):
    """Node-scoped runtime inventory for a forwarding / intel-sync agent.

    The single forwarder spine. The ``agent_kind`` discriminator selects the
    required profile the ``require_profile_for_agent_kind`` guard enforces.
    Cadence composes a ``runtime.scheduled_jobs`` entry; the inter-node trust
    edge composes a ``RelationshipForwardingEdge`` — neither is re-typed here.
    """

    forwarding_agent_id: str
    implementation: GovernedVocabulary[RuntimeForwardingAgentImplementation] = (
        RuntimeForwardingAgentImplementation.UNKNOWN
    )
    agent_kind: GovernedVocabulary[RuntimeForwardingAgentKind] = RuntimeForwardingAgentKind.UNKNOWN
    ownership_role: GovernedVocabulary[RuntimeForwardingAgentOwnershipRole] = (
        RuntimeForwardingAgentOwnershipRole.SYSTEM_UNDER_TEST
    )
    version: str = ""
    name: str = ""
    sources: list[RuntimeForwardingSource] = Field(default_factory=list)
    transforms: list[RuntimeForwardingTransform] = Field(default_factory=list)
    ship_targets: list[RuntimeForwardingShipTarget] = Field(default_factory=list)
    buffer_policy: RuntimeForwardingBufferPolicy | None = None
    reload_channels: list[RuntimeForwardingReloadChannel] = Field(default_factory=list)
    settings: list[RuntimeForwardingSetting] = Field(default_factory=list)
    description: str = ""

    @field_validator("forwarding_agent_id")
    @classmethod
    def validate_forwarding_agent_id(cls, v: str) -> str:
        return require_qualified_identifier(v, field_name="forwarding_agent_id")

    @field_validator("implementation", mode="before")
    @classmethod
    def normalize_implementation(cls, v: RuntimeForwardingAgentImplementation | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingAgentImplementation, field_name="implementation")

    @field_validator("agent_kind", mode="before")
    @classmethod
    def normalize_agent_kind(cls, v: RuntimeForwardingAgentKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingAgentKind, field_name="agent_kind")

    @field_validator("ownership_role", mode="before")
    @classmethod
    def normalize_ownership_role(cls, v: RuntimeForwardingAgentOwnershipRole | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingAgentOwnershipRole, field_name="ownership_role")

    @model_validator(mode="after")
    def validate_forwarding_agent(self) -> "RuntimeForwardingAgent":
        self._reject_duplicate_local_ref_ids()
        self.require_profile_for_agent_kind()
        return self

    # ------------------------------------------------------------------ #
    # Local stable-id uniqueness
    # ------------------------------------------------------------------ #

    def _reject_duplicate_local_ref_ids(self) -> None:
        entries: list[tuple[str, str]] = [("forwarding_agent_id", self.forwarding_agent_id)]
        if self.buffer_policy is not None:
            entries.append(("buffer_policy_id", self.buffer_policy.buffer_policy_id))
        for label, collection_name in (
            ("source_id", "sources"),
            ("transform_id", "transforms"),
            ("target_id", "ship_targets"),
            ("reload_channel_id", "reload_channels"),
            ("setting_id", "settings"),
        ):
            entries.extend((label, getattr(item, label)) for item in getattr(self, collection_name))

        seen: dict[str, str] = {}
        for label, value in entries:
            prior = seen.get(value)
            if prior is not None:
                raise ValueError(
                    f"Duplicate runtime forwarding agent stable id '{value}' in agent "
                    f"'{self.forwarding_agent_id}' across {prior} and {label}"
                )
            seen[value] = label

    # ------------------------------------------------------------------ #
    # Required-profile guard
    # ------------------------------------------------------------------ #

    def require_profile_for_agent_kind(self) -> None:
        """Fail validation when a concrete ``agent_kind`` lacks its profile.

        A ``${var}`` placeholder discriminator is exempt (nothing concrete is
        asserted); the OPEN ``unknown`` / ``other`` sentinels impose no profile
        (permissive tail). ``log_forwarder`` and ``content_sync`` each REQUIRE
        (and REJECT) specific child state per SCN-010 §5.5.
        """
        kind = self.agent_kind
        if is_variable_ref(kind) or not isinstance(kind, RuntimeForwardingAgentKind):
            return
        if kind is RuntimeForwardingAgentKind.LOG_FORWARDER:
            self._require_log_forwarder_profile()
        elif kind is RuntimeForwardingAgentKind.CONTENT_SYNC:
            self._require_content_sync_profile()
        # UNKNOWN / OTHER impose no profile by the enum-sentinel discipline.

    def _profile_error(self, requirement: str) -> ValueError:
        return ValueError(
            f"forwarding agent '{self.forwarding_agent_id}' agent_kind '{self.agent_kind.value}' requires {requirement}"
        )

    def _has_transform_kind(self, kind: RuntimeForwardingTransformKind) -> bool:
        return any(t.kind is kind for t in self.transforms)

    def _has_source_kind(self, kind: RuntimeForwardingSourceKind) -> bool:
        return any(s.kind is kind for s in self.sources)

    def _require_log_forwarder_profile(self) -> None:
        # REQUIRES a buffer_policy AND >=1 ship_target with an ingestion endpoint.
        if self.buffer_policy is None:
            raise self._profile_error("a buffer_policy")
        if not any(target.has_ingestion_endpoint() for target in self.ship_targets):
            raise self._profile_error(">=1 ship_target carrying an ingestion endpoint")
        # REJECTS any ioc_to_rule transform — that is the content_sync shape.
        if self._has_transform_kind(RuntimeForwardingTransformKind.IOC_TO_RULE):
            raise ValueError(
                f"forwarding agent '{self.forwarding_agent_id}' agent_kind 'log_forwarder' must not carry "
                f"a transform of kind 'ioc_to_rule'"
            )

    def _require_content_sync_profile(self) -> None:
        # REQUIRES >=1 api_pull source AND >=1 ioc_to_rule transform AND >=1 reload_channel.
        if not self._has_source_kind(RuntimeForwardingSourceKind.API_PULL):
            raise self._profile_error(">=1 source of kind 'api_pull'")
        if not self._has_transform_kind(RuntimeForwardingTransformKind.IOC_TO_RULE):
            raise self._profile_error(">=1 transform of kind 'ioc_to_rule'")
        if not self.reload_channels:
            raise self._profile_error(">=1 reload_channel")
        # REJECTS a buffer_policy and any ship_target enrollment endpoint.
        if self.buffer_policy is not None:
            raise ValueError(
                f"forwarding agent '{self.forwarding_agent_id}' agent_kind 'content_sync' must not carry "
                f"a buffer_policy"
            )
        offending = next((t for t in self.ship_targets if t.has_enrollment_endpoint()), None)
        if offending is not None:
            raise ValueError(
                f"forwarding agent '{self.forwarding_agent_id}' agent_kind 'content_sync' must not carry "
                f"a ship_target enrollment endpoint (ship_target '{offending.target_id}')"
            )


class RelationshipForwardingEdge(SDLModel):
    """Typed forwarding-trust detail carried by a top-level relationship edge.

    The inter-node trust edge between a forwarding / intel-sync agent
    (``forwarder_ref``, a ``forwarding_agent_id``) and the downstream consumer
    it ships to. The consumer's transport listener is named by
    ``target_listener_role`` — REUSING the manager-side
    ``RuntimeSecurityMonitoringListenerRole`` lattice rather than forking a
    parallel enum (SCN-010 §5.7).

    The agent enrollment identity itself is never recorded: only the closed
    ``RuntimeForwardingEnrollmentClassification`` lattice (``none`` /
    ``redacted`` / ``operator_secret``). A present enrollment-identity ref must
    classify ``redacted`` / ``operator_secret`` — a raw identity is never the
    portable model.
    """

    forwarder_ref: str
    target_listener_role: GovernedVocabulary[RuntimeSecurityMonitoringListenerRole] = (
        RuntimeSecurityMonitoringListenerRole.OTHER
    )
    enrollment_identity_ref: str = ""
    enrollment_identity_classification: GovernedVocabulary[RuntimeForwardingEnrollmentClassification] = (
        RuntimeForwardingEnrollmentClassification.NONE
    )
    protocol: str = ""
    crypto_method: str = ""
    parse_format: GovernedVocabulary[RuntimeForwardingParseFormat] = RuntimeForwardingParseFormat.UNKNOWN
    description: str = ""

    @field_validator("forwarder_ref")
    @classmethod
    def validate_forwarder_ref(cls, v: str) -> str:
        # A ref may carry a ``${var}`` placeholder; only emptiness is rejected.
        if not isinstance(v, str) or not v.strip():
            raise ValueError("forwarder_ref must be a non-empty string")
        return v

    @field_validator("target_listener_role", mode="before")
    @classmethod
    def normalize_target_listener_role(cls, v: RuntimeSecurityMonitoringListenerRole | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeSecurityMonitoringListenerRole, field_name="target_listener_role")

    @field_validator("enrollment_identity_classification", mode="before")
    @classmethod
    def normalize_enrollment_classification(cls, v: RuntimeForwardingEnrollmentClassification | str) -> object:
        return parse_runtime_enum_or_var(
            v, RuntimeForwardingEnrollmentClassification, field_name="enrollment_identity_classification"
        )

    @field_validator("parse_format", mode="before")
    @classmethod
    def normalize_parse_format(cls, v: RuntimeForwardingParseFormat | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeForwardingParseFormat, field_name="parse_format")

    @model_validator(mode="after")
    def validate_enrollment_identity(self) -> "RelationshipForwardingEdge":
        # The enrollment identity is secret-bearing by construction: a present
        # ref must be classified ``redacted`` / ``operator_secret`` so a raw
        # credential never lands in the model. A ``${var}`` classification is
        # deferred to instantiation revalidation.
        if not self.enrollment_identity_ref:
            return self
        classification = self.enrollment_identity_classification
        if is_variable_ref(classification):
            return self
        if classification not in _PRESENT_ENROLLMENT_CLASSIFICATIONS:
            raise ValueError(
                "forwarding edge enrollment_identity_ref is present; enrollment_identity_classification "
                "must be 'redacted' or 'operator_secret'"
            )
        return self
