"""Base contract model, primitive type aliases, and RFC3339/digest helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import Field, model_validator

from raes_contracts._base import ContractModel, NonEmptyString, PrefixedDigestString
from raes_contracts.runtime_vocabulary_scopes import SDL_IDENTITY_VOCABULARY_SCOPES

BehavioralRelationId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]


BehavioralTaxonomyRevision = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.-]*$")]

_ASSURANCE_AXIS_RULES: dict[str, tuple[str, frozenset[str]]] = {
    "definition": ("defined", frozenset({"structural"})),
    "checker": ("implemented", frozenset({"structural", "finite"})),
    "bounded-test": ("tested", frozenset({"finite"})),
    "model-check": ("model-checked", frozenset({"model-check"})),
    "proof": ("proved", frozenset({"proof"})),
    "runtime-enforcement": ("enforced", frozenset({"structural", "finite"})),
    "backend-declaration": ("declared", frozenset({"structural"})),
    "backend-realization": ("realized", frozenset({"structural", "finite"})),
    "backend-conformance": ("conformant", frozenset({"finite", "statistical"})),
}


class BehavioralClaimBindingModel(ContractModel):
    """A bounded claim tied to one revisioned behavioral-relation definition.

    This is deliberately a claim *binding*, not another relation registry. The
    catalog owns relation meaning; consumers supply the subject, carriers,
    quantifier/evidence boundary, assurance state, and explicit limitations.
    """

    taxonomy_id: NonEmptyString
    taxonomy_revision: BehavioralTaxonomyRevision
    relation_id: BehavioralRelationId
    subject: NonEmptyString
    left_carrier_ref: NonEmptyString | None = None
    right_carrier_ref: NonEmptyString | None = None
    observation_projection_ref: NonEmptyString | None = None
    observation_projection_revision: NonEmptyString | None = None
    relation_parameter_profile_ref: NonEmptyString | None = None
    relation_parameter_profile_revision: NonEmptyString | None = None
    quantifier_scope: Literal[
        "single-artifact",
        "finite-cases",
        "sampled-population",
        "all-admitted-inputs",
        "all-traces",
        "all-strategies",
    ]
    evidence_scope: Literal["structural", "finite", "statistical", "model-check", "proof"]
    assurance_axis: (
        Literal[
            "definition",
            "checker",
            "bounded-test",
            "model-check",
            "proof",
            "runtime-enforcement",
            "backend-declaration",
            "backend-realization",
            "backend-conformance",
        ]
        | None
    ) = None
    evidence_boundary: NonEmptyString
    assurance_status: Literal[
        "defined",
        "implemented",
        "tested",
        "model-checked",
        "proved",
        "deliberately-unproved",
        "future",
        "enforced",
        "declared",
        "realized",
        "conformant",
    ]
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    limitations: list[NonEmptyString] = Field(min_length=1)
    explicit_non_claims: list[NonEmptyString] = Field(min_length=1)

    def _validate_quantifier_evidence(self) -> None:
        universal_scopes = {"all-admitted-inputs", "all-traces", "all-strategies"}
        if self.quantifier_scope in universal_scopes and self.evidence_scope not in {"model-check", "proof"}:
            raise ValueError("universal quantification requires model-check or proof evidence")

    def _validate_explicit_assurance_axis(self) -> None:
        if self.assurance_axis is None:
            return
        expected_status, allowed_evidence = _ASSURANCE_AXIS_RULES[self.assurance_axis]
        negative_axis_state = self.assurance_status == "future" or (
            self.assurance_axis == "proof" and self.assurance_status == "deliberately-unproved"
        )
        if negative_axis_state:
            if self.evidence_scope != "structural":
                raise ValueError(
                    f"assurance axis {self.assurance_axis!r} with status {self.assurance_status!r} "
                    "requires structural evidence"
                )
            return
        if self.assurance_status != expected_status or self.evidence_scope not in allowed_evidence:
            raise ValueError(
                f"assurance axis {self.assurance_axis!r} requires status {expected_status!r} "
                f"and evidence scope in {sorted(allowed_evidence)!r}"
            )

    def _validate_unscoped_assurance(self) -> None:
        if self.assurance_axis is not None:
            return
        if self.assurance_status in {"enforced", "declared", "realized", "conformant"}:
            raise ValueError(f"assurance status {self.assurance_status!r} requires an explicit assurance axis")
        if self.assurance_status == "proved" and self.evidence_scope != "proof":
            raise ValueError("proved assurance requires proof evidence")
        if self.assurance_status == "model-checked" and self.evidence_scope != "model-check":
            raise ValueError("model-checked assurance requires model-check evidence")

    @staticmethod
    def _validate_coordinate_pair(ref: str | None, revision: str | None, label: str) -> None:
        if (ref is None) != (revision is None):
            raise ValueError(f"{label} ref and revision must be supplied together")

    @model_validator(mode="after")
    def _validate_claim_strength(self) -> BehavioralClaimBindingModel:
        self._validate_quantifier_evidence()
        self._validate_explicit_assurance_axis()
        self._validate_unscoped_assurance()
        self._validate_coordinate_pair(
            self.observation_projection_ref,
            self.observation_projection_revision,
            "observation projection",
        )
        self._validate_coordinate_pair(
            self.relation_parameter_profile_ref,
            self.relation_parameter_profile_revision,
            "relation parameter profile",
        )
        return self


Rfc3339DateTimeString = Annotated[
    str,
    Field(
        min_length=1,
        pattern=(
            r"^\d{4}-\d{2}-\d{2}[Tt](?:[01]\d|2[0-3]):[0-5]\d:(?:[0-5]\d|60)"
            r"(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
        ),
        json_schema_extra={"format": "date-time"},
    ),
]


CalendarDateString = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


HexDigestString = Annotated[str, Field(min_length=1, pattern=r"^[A-Fa-f0-9]+$")]


NonNegativeInteger = Annotated[int, Field(ge=0)]


PositiveInteger = Annotated[int, Field(ge=1)]


UnitIntervalFloat = Annotated[float, Field(gt=0, le=1)]


ClosedUnitIntervalFloat = Annotated[float, Field(ge=0, le=1)]


SemanticProfileId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9]+$")]


SemanticAssumptionId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


ReferenceModelId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")]


JsonPointerString = Annotated[str, Field(pattern=r"^#(?:/[A-Za-z0-9_.$~-]+)+$")]


JsonInstancePathString = Annotated[str, Field(pattern=r"^#(?:/[A-Za-z0-9_.$~-]+)*$")]


InstancePath = Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.(?:[a-z_][a-z0-9_]*|\*))*$")]


ControlledVocabularyTermId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")]


_BACKEND_CONCEPT_BINDING_SCOPES = frozenset(
    {
        "capabilities.provisioner.supported_node_types",
        "capabilities.provisioner.supported_os_families",
        "capabilities.provisioner.operating_systems.distribution",
        "capabilities.provisioner.supported_node_architectures",
        "capabilities.provisioner.supported_content_types",
        "capabilities.provisioner.supported_account_features",
        "capabilities.provisioner.supported_domain_profiles",
        "capabilities.provisioner.supported_service_materialization_profiles",
        "capabilities.orchestrator.supported_sections",
        "capabilities.evaluator.supported_sections",
        "capabilities.observation.supported_capture_kinds",
        "capabilities.observation.supported_channel_kinds",
        "capabilities.observation.supported_sealing_modes",
        "capabilities.participant_runtime.supported_participant_roles",
        "capabilities.participant_runtime.supported_behavior_features",
        "capabilities.participant_runtime.supported_interaction_features",
        "capabilities.time.supported_domain_kinds",
        "capabilities.time.supported_authority_kinds",
        "capabilities.time.supported_advancement_modes",
        "capabilities.time.supported_synchronization_modes",
        "capabilities.time.supported_constraint_kinds",
    }
)


_PROCESSOR_CONCEPT_BINDING_SCOPES = frozenset(
    {
        "capabilities.supported_sdl_versions",
        "capabilities.supported_features",
    }
)


_PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES = frozenset(
    {
        "implementation_kind",
        "capabilities.supported_participant_contracts",
        "capabilities.supported_decision_surface_modes",
        "capabilities.tool_affordance_expectations",
        "capabilities.exposure_policy_kinds",
    }
)


_CONTROLLED_VOCABULARY_GOVERNED_SCOPES = frozenset(
    {
        *SDL_IDENTITY_VOCABULARY_SCOPES,
        "behavior_specifications.behavior_mode",
        "agents.interactive_access.channel",
        "sdl.accounts.auth_method",
        "sdl.accounts.credential_bindings.auth_method",
        "sdl.accounts.credential_bindings.purpose",
        "capabilities.supported_features",
        "implementation_kind",
        "capabilities.supported_participant_contracts",
        "capabilities.supported_decision_surface_modes",
        "capabilities.tool_affordance_expectations",
        "capabilities.exposure_policy_kinds",
        "capabilities.orchestrator.supported_workflow_features",
        "capabilities.orchestrator.supported_workflow_state_predicates",
        "workflows.steps.fact_binding_refs",
        "random_streams.draw_purpose",
        "participant-crossing-occurrence.direction",
        "participant-crossing-occurrence.interaction_kind",
        "participant-crossing-occurrence.subject.subject_kind",
        "participant-crossing-occurrence.operation",
        "participant-crossing-occurrence.gates",
        "participant-crossing-occurrence.decision.disposition",
        "participant-crossing-occurrence.backend_posture",
        "participant-crossing-occurrence.losses.kind",
        "participant-crossing-occurrence.stage",
        "participant-flow-control-relation.labels.resolution_status",
        "participant-flow-control-relation.labels.subject.subject_kind",
        "participant-flow-control-relation.releases.kind",
        "participant-flow-control-relation.sink_decisions.coordinate_result",
        "participant-flow-control-relation.sink_decisions.final_disposition",
        "participant-flow-control-relation.sink_decisions.sink.sink_kind",
        "participant-flow-control-relation.bindings.kind",
        "participant-flow-control-relation.bindings.relation_target.target_kind",
        "external_concept_bindings.bindings.*.assertion.relationship_kind",
        "external_concept_bindings.bindings.*.assertion.semantic_effect",
        "external_concept_bindings.bindings.*.confidence.posture",
        "external_concept_bindings.bindings.*.approximation.posture",
        "external_concept_bindings.bindings.*.review.status",
        "external_concept_bindings.bindings.*.perspective.participant_availability.kind",
        "scenario.realization.constraints.compute-substrate",
        "nodes.os_distribution",
        "runtime.snapshot.realization_observations.operating-system.distribution",
        "runtime.snapshot.realization_observations.compute-substrate",
        *_BACKEND_CONCEPT_BINDING_SCOPES,
        *_PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES,
    }
)


_CHECKSUM_VALUE_PATTERNS = {
    "sha256": r"^[A-Fa-f0-9]{64}$",
    "sha384": r"^[A-Fa-f0-9]{96}$",
    "sha512": r"^[A-Fa-f0-9]{128}$",
    "blake3": r"^[A-Fa-f0-9]{64}$",
}


_RFC3339_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt](?:[01]\d|2[0-3]):[0-5]\d:(?P<second>[0-5]\d|60)"
    r"(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


_VALID_UTC_LEAP_SECOND_DATES = frozenset(
    {
        (1972, 6, 30),
        (1972, 12, 31),
        (1973, 12, 31),
        (1974, 12, 31),
        (1975, 12, 31),
        (1976, 12, 31),
        (1977, 12, 31),
        (1978, 12, 31),
        (1979, 12, 31),
        (1981, 6, 30),
        (1982, 6, 30),
        (1983, 6, 30),
        (1985, 6, 30),
        (1987, 12, 31),
        (1989, 12, 31),
        (1990, 12, 31),
        (1992, 6, 30),
        (1993, 6, 30),
        (1994, 6, 30),
        (1995, 12, 31),
        (1997, 6, 30),
        (1998, 12, 31),
        (2005, 12, 31),
        (2008, 12, 31),
        (2012, 6, 30),
        (2015, 6, 30),
        (2016, 12, 31),
    }
)


_RAES_SEMANTIC_INVARIANT_PROFILE_URI = "https://openrae.github.io/rae/schemas/semantic-invariants/v1"


def _canonical_digest(digest: str | None) -> str | None:
    return digest.casefold() if digest is not None else None


def _parse_rfc3339_datetime(field_name: str, value: str) -> datetime:
    match = _RFC3339_DATETIME_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"{field_name} must be a valid RFC 3339 date-time")
    normalized_value = f"{value[:-1]}+00:00" if value.endswith(("Z", "z")) else value
    if match.group("second") == "60":
        normalized_value = f"{normalized_value[:17]}59{normalized_value[19:]}"
    try:
        parsed = datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid RFC 3339 date-time") from exc
    if match.group("second") == "60":
        utc_leap_second = parsed.astimezone(UTC)
        if (
            (utc_leap_second.year, utc_leap_second.month, utc_leap_second.day) not in _VALID_UTC_LEAP_SECOND_DATES
            or utc_leap_second.hour != 23
            or utc_leap_second.minute != 59
            or utc_leap_second.second != 59
        ):
            raise ValueError(f"{field_name} must use a valid RFC 3339 leap-second instant")
        parsed += timedelta(seconds=1)
    return parsed


def _payload_get(payload: object, field_name: str) -> object:
    if isinstance(payload, Mapping):
        return payload.get(field_name)
    return getattr(payload, field_name, None)


def _validate_rfc3339_payload_field(payload: object, field_name: str) -> None:
    value = _payload_get(payload, field_name)
    if value is not None:
        _parse_rfc3339_datetime(field_name, value)


def _validate_artifact_collection_created_at(field_name: str, artifacts: object) -> None:
    for index, artifact in enumerate(artifacts or []):
        created_at = _payload_get(artifact, "created_at")
        if created_at is not None:
            _parse_rfc3339_datetime(f"{field_name}/{index}/created_at", created_at)


__all__ = [
    "BehavioralClaimBindingModel",
    "BehavioralRelationId",
    "BehavioralTaxonomyRevision",
    "CalendarDateString",
    "ClosedUnitIntervalFloat",
    "ContractModel",
    "ControlledVocabularyTermId",
    "HexDigestString",
    "InstancePath",
    "JsonInstancePathString",
    "JsonPointerString",
    "NonEmptyString",
    "NonNegativeInteger",
    "PositiveInteger",
    "PrefixedDigestString",
    "ReferenceModelId",
    "Rfc3339DateTimeString",
    "SemanticAssumptionId",
    "SemanticProfileId",
    "UnitIntervalFloat",
]
