"""Portable contracts for run-local typed fact binding."""

from __future__ import annotations

from enum import Enum, auto
from typing import Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

from ..versions import RUNTIME_FACT_BINDING_PLANE_V1_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString


class _LowercaseNameEnum(str, Enum):
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str:
        return name.lower()


class RuntimeFactValueType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    REFERENCE = "reference"


class RuntimeFactSourceKind(_LowercaseNameEnum):
    OBSERVATION = "observation"
    DERIVED = "derived"
    TOOL_RESULT = "tool_result"
    SECRET_REFERENCE = auto()


class RuntimeFactScopeKind(str, Enum):
    RUN = "run"
    PARTICIPANT = "participant"
    EPISODE = "episode"
    WORKFLOW = "workflow"


class RuntimeFactSensitivity(_LowercaseNameEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    SECRET = auto()


class RuntimeFactAudience(str, Enum):
    PARTICIPANT = "participant"
    WORKFLOW = "workflow"
    PROTECTED_SINK = "protected_sink"


class RuntimeFactAbsenceDisposition(str, Enum):
    BLOCK = "block"
    FAIL = "fail"
    INAPPLICABLE = "inapplicable"


class RuntimeFactBindingDisposition(_LowercaseNameEnum):
    BOUND = "bound"
    ABSENT = "absent"
    STALE = "stale"
    AMBIGUOUS = "ambiguous"
    UNAUTHORIZED = "unauthorized"
    UNSUPPORTED = "unsupported"
    WRONG_TYPE = "wrong_type"
    WRONG_SCOPE = "wrong_scope"
    SECRET_UNAVAILABLE = auto()
    DISPATCH_FAILED = "dispatch_failed"


RuntimeFactScalar = StrictBool | StrictInt | StrictFloat | StrictStr


def _unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} entries must be unique")
    return values


class RuntimeFactVisibilityModel(ContractModel):
    participant_addresses: list[NonEmptyString] = Field(default_factory=list)
    workflow_addresses: list[NonEmptyString] = Field(default_factory=list)
    operator_visible: bool = True

    @field_validator("participant_addresses", "workflow_addresses")
    @classmethod
    def _validate_unique_refs(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "visibility"))


class RuntimeFactScopeModel(ContractModel):
    kind: RuntimeFactScopeKind
    run_id: NonEmptyString
    participant_address: NonEmptyString | None = None
    episode_id: NonEmptyString | None = None
    workflow_address: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_scope_shape(self) -> RuntimeFactScopeModel:
        scoped_values = {
            "participant_address": self.participant_address,
            "episode_id": self.episode_id,
            "workflow_address": self.workflow_address,
        }
        present_fields = {name for name, value in scoped_values.items() if value is not None}
        expected_fields = {
            RuntimeFactScopeKind.RUN: set(),
            RuntimeFactScopeKind.PARTICIPANT: {"participant_address"},
            RuntimeFactScopeKind.EPISODE: {"participant_address", "episode_id"},
            RuntimeFactScopeKind.WORKFLOW: {"workflow_address"},
        }
        messages = {
            RuntimeFactScopeKind.RUN: "run-scoped facts cannot carry participant, episode, or workflow scope",
            RuntimeFactScopeKind.PARTICIPANT: "participant-scoped facts require only participant_address",
            RuntimeFactScopeKind.EPISODE: "episode-scoped facts require participant_address and episode_id",
            RuntimeFactScopeKind.WORKFLOW: "workflow-scoped facts require only workflow_address",
        }
        if present_fields != expected_fields[self.kind]:
            raise ValueError(messages[self.kind])
        return self


class RuntimeFactDeclarationModel(ContractModel):
    fact_id: NonEmptyString
    value_type: RuntimeFactValueType
    source_kind: RuntimeFactSourceKind
    sensitivity: RuntimeFactSensitivity
    visibility: RuntimeFactVisibilityModel
    authority_refs: list[NonEmptyString] = Field(min_length=1)

    @field_validator("authority_refs")
    @classmethod
    def _validate_authority_refs(cls, value: list[str]) -> list[str]:
        return _unique(value, "authority_refs")

    @model_validator(mode="after")
    def _validate_secret_source_posture(self) -> RuntimeFactDeclarationModel:
        secret_source = self.source_kind == RuntimeFactSourceKind.SECRET_REFERENCE
        secret_sensitivity = self.sensitivity == RuntimeFactSensitivity.SECRET
        if secret_source != secret_sensitivity:
            raise ValueError("secret_reference source kind and secret sensitivity must be declared together")
        return self


class RuntimeFactVersionModel(ContractModel):
    fact_id: NonEmptyString
    version_id: NonEmptyString
    sequence: int = Field(ge=1)
    value_type: RuntimeFactValueType
    source_kind: RuntimeFactSourceKind
    sensitivity: RuntimeFactSensitivity
    scope: RuntimeFactScopeModel
    observed_at: Rfc3339DateTimeString
    expires_at: Rfc3339DateTimeString | None = None
    value: RuntimeFactScalar | None = None
    secret_ref: NonEmptyString | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    provenance_refs: list[NonEmptyString] = Field(min_length=1)

    @field_validator("evidence_refs", "provenance_refs")
    @classmethod
    def _validate_unique_refs(cls, value: list[str], info: object) -> list[str]:
        return _unique(value, getattr(info, "field_name", "refs"))

    @model_validator(mode="after")
    def _validate_value_posture(self) -> RuntimeFactVersionModel:
        if self.sensitivity == RuntimeFactSensitivity.SECRET:
            if self.secret_ref is None or self.value is not None:
                raise ValueError("secret facts require secret_ref and cannot carry a portable value")
        elif self.value is None or self.secret_ref is not None:
            raise ValueError("non-secret facts require value and cannot carry secret_ref")
        if self.value is not None and not _value_matches_type(self.value, self.value_type):
            raise ValueError("fact value does not match value_type")
        return self


def _value_matches_type(value: RuntimeFactScalar, value_type: RuntimeFactValueType) -> bool:
    if value_type in {RuntimeFactValueType.STRING, RuntimeFactValueType.REFERENCE}:
        matches = isinstance(value, str)
    elif value_type == RuntimeFactValueType.BOOLEAN:
        matches = isinstance(value, bool)
    elif value_type == RuntimeFactValueType.INTEGER:
        matches = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == RuntimeFactValueType.NUMBER:
        matches = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        matches = False
    return matches


class RuntimeFactSinkModel(ContractModel):
    sink_id: NonEmptyString
    action_contract_address: NonEmptyString
    target_field: NonEmptyString
    value_type: RuntimeFactValueType
    allowed_source_kinds: list[RuntimeFactSourceKind] = Field(min_length=1)
    allowed_scope_kinds: list[RuntimeFactScopeKind] = Field(min_length=1)
    allowed_sensitivities: list[RuntimeFactSensitivity] = Field(min_length=1)
    max_age_seconds: int | None = Field(default=None, ge=0)
    authority_refs: list[NonEmptyString] = Field(min_length=1)
    audience: RuntimeFactAudience
    absence_disposition: RuntimeFactAbsenceDisposition

    @field_validator("action_contract_address")
    @classmethod
    def _validate_action_contract_address(cls, value: str) -> str:
        if not value.startswith("participant.action-contract."):
            raise ValueError("action_contract_address must be a compiled participant action-contract address")
        return value

    @field_validator("target_field")
    @classmethod
    def _validate_target_field(cls, value: str) -> str:
        if not value.startswith("input.") or len(value) == len("input."):
            raise ValueError("target_field must identify a run-local action input beneath 'input.'")
        return value

    @field_validator("allowed_source_kinds", "allowed_scope_kinds", "allowed_sensitivities", "authority_refs")
    @classmethod
    def _validate_unique_values(cls, value: list[object], info: object) -> list[object]:
        if len(value) != len(set(value)):
            raise ValueError(f"{getattr(info, 'field_name', 'values')} entries must be unique")
        return value


class RuntimeFactBindingSelectionModel(ContractModel):
    sink: RuntimeFactSinkModel
    candidate_fact_ids: list[NonEmptyString] = Field(default_factory=list)

    @field_validator("candidate_fact_ids")
    @classmethod
    def _validate_candidate_fact_ids(cls, value: list[str]) -> list[str]:
        return _unique(value, "candidate_fact_ids")


class RuntimeFactBindingRequestModel(ContractModel):
    run_id: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    workflow_address: NonEmptyString | None = None
    action_instance_id: NonEmptyString
    action_contract_address: NonEmptyString


class RuntimeFactBindingEventModel(ContractModel):
    event_id: NonEmptyString
    run_id: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    workflow_address: NonEmptyString | None = None
    action_instance_id: NonEmptyString
    action_contract_address: NonEmptyString
    sink_id: NonEmptyString
    target_field: NonEmptyString
    fact_id: NonEmptyString | None = None
    fact_version_id: NonEmptyString | None = None
    disposition: RuntimeFactBindingDisposition
    sensitivity: RuntimeFactSensitivity | None = None
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    provenance_refs: list[NonEmptyString] = Field(default_factory=list)
    authorization_refs: list[NonEmptyString] = Field(default_factory=list)
    redacted: bool = False
    reason_code: NonEmptyString | None = None


class RuntimeFactProjectionModel(ContractModel):
    fact_id: NonEmptyString
    fact_version_id: NonEmptyString
    value_type: RuntimeFactValueType
    source_kind: RuntimeFactSourceKind
    sensitivity: RuntimeFactSensitivity
    scope: RuntimeFactScopeModel
    observed_at: Rfc3339DateTimeString
    value: RuntimeFactScalar | None = None
    redacted: bool = False
    secret_reference_present: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    provenance_refs: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_projection_posture(self) -> RuntimeFactProjectionModel:
        if self.sensitivity == RuntimeFactSensitivity.SECRET:
            if self.value is not None or not self.redacted or not self.secret_reference_present:
                raise ValueError("secret fact projections must be redacted and value-free")
        elif self.value is None or self.redacted or self.secret_reference_present:
            raise ValueError("non-secret fact projections require an unredacted value")
        return self


class RuntimeFactBindingPlaneModel(ContractModel):
    schema_version: Literal[RUNTIME_FACT_BINDING_PLANE_V1_SCHEMA_VERSION] = RUNTIME_FACT_BINDING_PLANE_V1_SCHEMA_VERSION
    declarations: list[RuntimeFactDeclarationModel] = Field(default_factory=list)
    sinks: list[RuntimeFactSinkModel] = Field(default_factory=list)
    versions: list[RuntimeFactVersionModel] = Field(default_factory=list)
    events: list[RuntimeFactBindingEventModel] = Field(default_factory=list)
    projections: list[RuntimeFactProjectionModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_references(self) -> RuntimeFactBindingPlaneModel:
        declarations = _unique_index(self.declarations, "fact_id", "declaration")
        sinks = _unique_index(self.sinks, "sink_id", "sink")
        versions = _unique_index(self.versions, "version_id", "fact version")
        _unique_index(self.events, "event_id", "binding event")
        _validate_fact_versions(self.versions, declarations)
        _validate_binding_events(self.events, declarations, sinks, versions)
        _validate_projections(self.projections, versions)
        return self


def _validate_fact_versions(
    fact_versions: list[RuntimeFactVersionModel],
    declarations: dict[str, RuntimeFactDeclarationModel],
) -> None:
    sequences: dict[str, list[int]] = {}
    for version in fact_versions:
        declaration = declarations.get(version.fact_id)
        if declaration is None:
            raise ValueError(f"fact version fact_id {version.fact_id!r} must resolve to a declaration")
        version_posture = (version.value_type, version.source_kind, version.sensitivity)
        declaration_posture = (declaration.value_type, declaration.source_kind, declaration.sensitivity)
        if version_posture != declaration_posture:
            raise ValueError("fact version type, source, and sensitivity must match its declaration")
        sequences.setdefault(version.fact_id, []).append(version.sequence)
    for fact_id, fact_sequences in sequences.items():
        expected = list(range(1, len(fact_sequences) + 1))
        if sorted(fact_sequences) != expected:
            raise ValueError(f"fact version sequence for {fact_id!r} must be contiguous from 1")


def _validate_binding_events(
    events: list[RuntimeFactBindingEventModel],
    declarations: dict[str, RuntimeFactDeclarationModel],
    sinks: dict[str, RuntimeFactSinkModel],
    versions: dict[str, RuntimeFactVersionModel],
) -> None:
    for event in events:
        sink = sinks.get(event.sink_id)
        if sink is None:
            raise ValueError(f"binding event sink_id {event.sink_id!r} must resolve to a sink")
        if (event.target_field, event.action_contract_address) != (sink.target_field, sink.action_contract_address):
            raise ValueError("binding event target and action contract must match its sink")
        if event.disposition == RuntimeFactBindingDisposition.BOUND and (
            event.fact_id is None or event.fact_version_id is None
        ):
            raise ValueError("bound events require fact_id and fact_version_id")
        if event.fact_version_id is not None:
            _validate_event_fact_version(event, sink, declarations, versions)


def _validate_event_fact_version(
    event: RuntimeFactBindingEventModel,
    sink: RuntimeFactSinkModel,
    declarations: dict[str, RuntimeFactDeclarationModel],
    versions: dict[str, RuntimeFactVersionModel],
) -> None:
    version = versions.get(event.fact_version_id or "")
    if version is None:
        raise ValueError(f"binding event fact_version_id {event.fact_version_id!r} must resolve to a fact version")
    if event.fact_id != version.fact_id:
        raise ValueError("binding event fact_id must match its fact version")
    _validate_event_version_metadata(event, sink, version, declarations[version.fact_id])


def _validate_projections(
    projections: list[RuntimeFactProjectionModel],
    versions: dict[str, RuntimeFactVersionModel],
) -> None:
    for projection in projections:
        version = versions.get(projection.fact_version_id)
        if version is None:
            raise ValueError(
                f"projection fact_version_id {projection.fact_version_id!r} must resolve to a fact version"
            )
        if projection.fact_id != version.fact_id:
            raise ValueError("projection fact_id must match its fact version")
        _validate_projection_version_metadata(projection, version)


def _validate_event_version_metadata(
    event: RuntimeFactBindingEventModel,
    sink: RuntimeFactSinkModel,
    version: RuntimeFactVersionModel,
    declaration: RuntimeFactDeclarationModel,
) -> None:
    expected_redaction = version.sensitivity == RuntimeFactSensitivity.SECRET
    metadata_matches = all(
        (
            event.sensitivity == version.sensitivity,
            event.evidence_refs == version.evidence_refs,
            event.provenance_refs == version.provenance_refs,
            event.redacted == expected_redaction,
        )
    )
    if not metadata_matches:
        raise ValueError("binding event metadata must match its immutable fact version")
    if event.disposition == RuntimeFactBindingDisposition.BOUND:
        _validate_bound_event_policy(event, sink, version, declaration)


def _validate_bound_event_policy(
    event: RuntimeFactBindingEventModel,
    sink: RuntimeFactSinkModel,
    version: RuntimeFactVersionModel,
    declaration: RuntimeFactDeclarationModel,
) -> None:
    sink_policy_matches = all(
        (
            version.value_type == sink.value_type,
            version.source_kind in sink.allowed_source_kinds,
            version.scope.kind in sink.allowed_scope_kinds,
            version.sensitivity in sink.allowed_sensitivities,
            event.run_id == version.scope.run_id,
            version.scope.participant_address in {None, event.participant_address},
            version.scope.episode_id in {None, event.episode_id},
            version.scope.workflow_address in {None, event.workflow_address},
            (set(declaration.authority_refs) | set(sink.authority_refs)).issubset(event.authorization_refs),
        )
    )
    if not sink_policy_matches:
        raise ValueError("bound event fact version must satisfy its compiled sink policy")
    if not _bound_event_visible(event, sink, version, declaration):
        raise ValueError("bound event fact version must satisfy sink visibility and audience policy")


def _bound_event_visible(
    event: RuntimeFactBindingEventModel,
    sink: RuntimeFactSinkModel,
    version: RuntimeFactVersionModel,
    declaration: RuntimeFactDeclarationModel,
) -> bool:
    if sink.audience == RuntimeFactAudience.WORKFLOW:
        audience_visible = event.workflow_address in declaration.visibility.workflow_addresses
    else:
        audience_visible = event.participant_address in declaration.visibility.participant_addresses
    secret_visible = (
        version.sensitivity != RuntimeFactSensitivity.SECRET or sink.audience == RuntimeFactAudience.PROTECTED_SINK
    )
    return audience_visible and secret_visible


def _validate_projection_version_metadata(
    projection: RuntimeFactProjectionModel,
    version: RuntimeFactVersionModel,
) -> None:
    secret = version.sensitivity == RuntimeFactSensitivity.SECRET
    metadata_matches = all(
        (
            projection.value_type == version.value_type,
            projection.source_kind == version.source_kind,
            projection.sensitivity == version.sensitivity,
            projection.scope == version.scope,
            projection.observed_at == version.observed_at,
            projection.confidence == version.confidence,
            projection.evidence_refs == version.evidence_refs,
            projection.provenance_refs == version.provenance_refs,
            projection.value == (None if secret else version.value),
            projection.redacted == secret,
            projection.secret_reference_present == secret,
        )
    )
    if not metadata_matches:
        raise ValueError("projection metadata must match its immutable fact version")


def _unique_index[ModelT](items: list[ModelT], field_name: str, kind: str) -> dict[str, ModelT]:
    indexed: dict[str, ModelT] = {}
    for item in items:
        key = getattr(item, field_name)
        if key in indexed:
            raise ValueError(f"{kind} {field_name} {key!r} must be unique")
        indexed[key] = item
    return indexed


__all__ = (
    "RuntimeFactAbsenceDisposition",
    "RuntimeFactAudience",
    "RuntimeFactBindingDisposition",
    "RuntimeFactBindingEventModel",
    "RuntimeFactBindingPlaneModel",
    "RuntimeFactProjectionModel",
    "RuntimeFactBindingRequestModel",
    "RuntimeFactBindingSelectionModel",
    "RuntimeFactDeclarationModel",
    "RuntimeFactScopeKind",
    "RuntimeFactScopeModel",
    "RuntimeFactSensitivity",
    "RuntimeFactSinkModel",
    "RuntimeFactSourceKind",
    "RuntimeFactValueType",
    "RuntimeFactVersionModel",
    "RuntimeFactVisibilityModel",
)
