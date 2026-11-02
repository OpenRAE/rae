"""Participant context-view contracts and comparability semantics."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString
from .schema_invariants import _add_raes_invariant

ParticipantContextAudienceScope = Literal[
    "participant_visible",
    "operator_visible",
    "evaluator_visible",
    "auditor_visible",
]


ParticipantContextParticipantScope = Literal["participant_local"]


ParticipantContextSourceLayer = Literal[
    "source_snapshot",
    "participant_observation",
    "participant_information_state",
    "participant_behavior_history",
    "participant_episode_state",
    "participant_status_view",
    "participant_history_view",
    "evidence_record",
    "derived_measure",
    "control_plane_operation",
    "participant_control_context_asset",
]


ParticipantContextTemporalRelation = Literal[
    "same_observation_point",
    "bounded_staleness",
    "historical_replay",
]


ParticipantContextComparabilityClass = Literal[
    "portable_equivalent",
    "portable_with_disclosed_weakening",
    "backend_specific_non_comparable",
]


class ParticipantContextSourceLayerModel(ContractModel):
    """One governed source layer consumed by a SEM-214 context view."""

    source_id: NonEmptyString
    source_layer: ParticipantContextSourceLayer
    ref: NonEmptyString
    temporal_relation: ParticipantContextTemporalRelation
    observation_point: NonEmptyString | None = None
    freshness_basis_ref: NonEmptyString | None = None
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    provenance_refs: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_temporal_basis(self) -> ParticipantContextSourceLayerModel:
        if self.temporal_relation == "bounded_staleness" and self.freshness_basis_ref is None:
            raise ValueError("freshness_basis_ref is required for bounded_staleness source layers")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"temporal_relation": {"const": "bounded_staleness"}},
                    "required": ["temporal_relation"],
                },
                "then": {
                    "required": ["freshness_basis_ref"],
                    "properties": {"freshness_basis_ref": {"type": "string", "minLength": 1}},
                },
            }
        )
        return json_schema


class ParticipantContextTransformationModel(ContractModel):
    """Governed transformation relation for a SEM-214 context view."""

    transformation_rule_ref: NonEmptyString
    description: NonEmptyString
    input_source_ids: list[NonEmptyString] = Field(min_length=1)
    output_semantics_ref: NonEmptyString | None = None


class ParticipantContextComparabilityModel(ContractModel):
    """Explicit comparability claim for a SEM-214 context view."""

    comparability_class: ParticipantContextComparabilityClass
    comparison_basis_ref: NonEmptyString
    backend_disclosure_refs: list[NonEmptyString] = Field(default_factory=list)
    limitations: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_disclosed_weakening(self) -> ParticipantContextComparabilityModel:
        if (
            self.comparability_class in {"portable_with_disclosed_weakening", "backend_specific_non_comparable"}
            and not self.backend_disclosure_refs
        ):
            raise ValueError("backend_disclosure_refs are required when comparability is weakened or backend-specific")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {
                        "comparability_class": {
                            "enum": [
                                "portable_with_disclosed_weakening",
                                "backend_specific_non_comparable",
                            ]
                        }
                    },
                    "required": ["comparability_class"],
                },
                "then": {
                    "required": ["backend_disclosure_refs"],
                    "properties": {"backend_disclosure_refs": {"minItems": 1}},
                },
            }
        )
        return json_schema


class ParticipantContextViewModel(ContractModel):
    """API-408 derived operational context view with SEM-214 semantics."""

    view_id: NonEmptyString
    participant_address: NonEmptyString
    episode_id: NonEmptyString | None = None
    generated_at: Rfc3339DateTimeString
    source_snapshot_ref: NonEmptyString
    view_ref: NonEmptyString
    meaning_ref: NonEmptyString
    participant_scope: ParticipantContextParticipantScope
    audience_scope: ParticipantContextAudienceScope
    observation_point: NonEmptyString
    derived_from_refs: list[NonEmptyString] = Field(min_length=1)
    source_layers: list[ParticipantContextSourceLayerModel] = Field(min_length=1)
    transformation: ParticipantContextTransformationModel
    comparability: ParticipantContextComparabilityModel
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    provenance_refs: list[NonEmptyString] = Field(min_length=1)
    semantic_limitations: list[NonEmptyString] = Field(min_length=1)
    derivation_basis_ref: NonEmptyString | None = None
    payload_ref: NonEmptyString | None = None
    visibility_projection_ref: NonEmptyString
    marking_definition_refs: list[NonEmptyString] = Field(default_factory=list)
    redaction_policy_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_sem214_source_binding(self) -> ParticipantContextViewModel:
        source_ids = [source.source_id for source in self.source_layers]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("context view source_layers source_id values must be unique")
        unknown_inputs = sorted(set(self.transformation.input_source_ids) - set(source_ids))
        if unknown_inputs:
            raise ValueError(
                "context view transformation input_source_ids must reference source_layers: "
                + ", ".join(unknown_inputs)
            )
        available_refs = set(self.derived_from_refs) | {self.source_snapshot_ref}
        missing_refs = sorted(source.ref for source in self.source_layers if source.ref not in available_refs)
        if missing_refs:
            raise ValueError(
                "context view source layer refs must be listed in derived_from_refs or source_snapshot_ref: "
                + ", ".join(missing_refs)
            )
        return self

    @model_validator(mode="after")
    def _validate_sem216_audience_boundary(self) -> ParticipantContextViewModel:
        # SEM-216 B1/B2: archived evidence and derived evaluation/adjudication outputs are
        # distinct strata from an audience-specific view. A participant-visible view may only
        # draw on an evidence_record or derived_measure source layer through a governed view
        # rule (derivation_basis_ref), under a redaction policy (redaction_policy_ref); the
        # archival source must be consumed by the transformation rather than passed through raw;
        # and the disclosed payload must be the transformed output, never the raw archival ref.
        #
        # The required-ref clauses are also published as a schema allOf so schema-only consumers
        # enforce them; the relational mediation and payload-aliasing clauses cannot be expressed
        # in JSON Schema and are published as x-raes-invariants (see __get_pydantic_json_schema__).
        if self.audience_scope != "participant_visible":
            return self
        archival_layers = [
            source for source in self.source_layers if source.source_layer in {"evidence_record", "derived_measure"}
        ]
        if not archival_layers:
            return self
        if self.derivation_basis_ref is None:
            raise ValueError(
                "participant-visible context views that draw on archival evidence_record or derived_measure "
                "source layers must declare a derivation_basis_ref governed view rule"
            )
        if self.redaction_policy_ref is None:
            raise ValueError(
                "participant-visible context views that draw on archival evidence_record or derived_measure "
                "source layers must declare a redaction_policy_ref"
            )
        mediated = set(self.transformation.input_source_ids)
        unmediated = sorted(source.source_id for source in archival_layers if source.source_id not in mediated)
        if unmediated:
            raise ValueError(
                "participant-visible archival source layers must be mediated by the transformation view rule; "
                "unmediated source ids: " + ", ".join(unmediated)
            )
        if self.payload_ref is not None:
            raw_archival_refs = {source.ref for source in archival_layers}
            raw_archival_refs.update(ref for source in archival_layers for ref in source.evidence_refs)
            if self.payload_ref in raw_archival_refs:
                raise ValueError(
                    "participant-visible context views must not set payload_ref to a raw archival "
                    "evidence_record/derived_measure source ref; payload_ref must identify the transformed, "
                    "redacted view output produced under the governed view rule"
                )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {
                        "audience_scope": {"const": "participant_visible"},
                        "source_layers": {
                            "contains": {
                                "properties": {"source_layer": {"enum": ["evidence_record", "derived_measure"]}},
                                "required": ["source_layer"],
                            }
                        },
                    },
                    "required": ["audience_scope", "source_layers"],
                },
                "then": {
                    "required": ["derivation_basis_ref", "redaction_policy_ref"],
                    "properties": {
                        "derivation_basis_ref": {"type": "string", "minLength": 1},
                        "redaction_policy_ref": {"type": "string", "minLength": 1},
                    },
                },
            }
        )
        # SEM-216 relational obligations that standard JSON Schema cannot express are published
        # as RAES semantic invariants so schema-only consumers see the full portable contract and
        # the validator that enforces it (mirrors the experiment-core x-raes-invariants pattern).
        _add_raes_invariant(
            json_schema,
            "context-view-sem216-archival-source-mediated",
            "Participant-visible context views drawing on an archival evidence_record or derived_measure "
            "source layer must mediate that source through transformation.input_source_ids.",
            inputs=[{"contract_id": "participant-context-view-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "context-view-sem216-payload-not-raw-archival",
            "Participant-visible context views must not set payload_ref to a raw archival evidence_record or "
            "derived_measure source ref; payload_ref must identify the transformed, redacted view output.",
            inputs=[{"contract_id": "participant-context-view-v1", "instance_path": "#/payload_ref"}],
        )
        return json_schema
