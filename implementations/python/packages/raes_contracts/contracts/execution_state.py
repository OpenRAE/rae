"""Workflow, evaluation, and proposition-truth execution-state contracts."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..versions import (
    EVALUATION_STATE_SCHEMA_VERSION,
    PROPOSITION_TRUTH_RESULT_SCHEMA_VERSION,
    SCENARIO_INSTANTIATION_REQUEST_SCHEMA_VERSION,
    WORKFLOW_CANCELLATION_REQUEST_SCHEMA_VERSION,
    WORKFLOW_STATE_SCHEMA_VERSION,
)
from .base import ContractModel, NonEmptyString


class InstantiationRequestModel(ContractModel):
    schema_version: Literal[SCENARIO_INSTANTIATION_REQUEST_SCHEMA_VERSION] = (
        SCENARIO_INSTANTIATION_REQUEST_SCHEMA_VERSION
    )
    profile: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowStepStateModel(ContractModel):
    lifecycle: str
    outcome: str | None = None
    attempts: int
    attempt_provenance: list[WorkflowStepAttemptProvenanceModel] = Field(default_factory=list)


class WorkflowStepAttemptProvenanceModel(ContractModel):
    step_name: NonEmptyString
    execution_mode: Literal["scripted", "objective", "scaffolded"]
    attempt_id: NonEmptyString
    objective_address: str = ""
    procedure_ref: str = ""
    exposed_scaffold_refs: list[NonEmptyString] = Field(default_factory=list)
    allowed_action_families: list[NonEmptyString] = Field(default_factory=list)
    selected_action_family: str = ""
    selected_tool_ref: str = ""
    selected_affordance_ref: str = ""
    fact_versions: list[NonEmptyString] = Field(default_factory=list)
    outcome: Literal["", "succeeded", "failed", "exhausted"] = ""
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    assertion_truth_refs: list[NonEmptyString] = Field(default_factory=list)
    participant_report: str = ""

    @model_validator(mode="after")
    def _validate_success_evidence(self) -> WorkflowStepAttemptProvenanceModel:
        if self.outcome == "succeeded" and not (self.evidence_refs and self.assertion_truth_refs):
            raise ValueError("successful workflow step provenance requires evidence-bearing assertion truth")
        return self


class WorkflowExecutionStateModel(ContractModel):
    state_schema_version: Literal[WORKFLOW_STATE_SCHEMA_VERSION] = WORKFLOW_STATE_SCHEMA_VERSION
    workflow_status: str
    run_id: str
    started_at: str
    updated_at: str
    terminal_reason: str | None = None
    compensation_status: str
    compensation_started_at: str | None = None
    compensation_updated_at: str | None = None
    compensation_failures: list[dict[str, Any]] = Field(default_factory=list)
    steps: dict[str, WorkflowStepStateModel] = Field(default_factory=dict)


class WorkflowHistoryEventModel(ContractModel):
    event_type: str
    timestamp: str
    step_name: str | None = None
    branch_name: str | None = None
    join_step: str | None = None
    outcome: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    invocation_id: NonEmptyString | None = None
    dispatch_id: NonEmptyString | None = None
    attempt: Annotated[int, Field(strict=True, ge=1)] | None = None
    origin: Literal["runtime", "backend"] | None = None

    @model_validator(mode="after")
    def _correlation(self) -> WorkflowHistoryEventModel:
        if self.dispatch_id is not None and (self.invocation_id is None or self.attempt is None):
            raise ValueError("dispatch history requires its invocation and attempt")
        if self.event_type == "step_reported" and (self.dispatch_id is None or self.origin != "backend"):
            raise ValueError("step report requires its backend dispatch correlation")
        return self


class WorkflowCancellationRequestModel(ContractModel):
    schema_version: Literal[WORKFLOW_CANCELLATION_REQUEST_SCHEMA_VERSION] = WORKFLOW_CANCELLATION_REQUEST_SCHEMA_VERSION
    run_id: str | None = None
    reason: str = "cancelled by operator"


class EvaluationResultStateModel(ContractModel):
    state_schema_version: Literal[EVALUATION_STATE_SCHEMA_VERSION] = EVALUATION_STATE_SCHEMA_VERSION
    resource_type: str
    run_id: str
    status: str
    observed_at: str
    updated_at: str
    passed: bool | None = None
    score: float | int | None = None
    max_score: int | None = None
    detail: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class EvaluationHistoryEventModel(ContractModel):
    event_type: str
    timestamp: str
    status: str
    passed: bool | None = None
    score: float | int | None = None
    max_score: int | None = None
    detail: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class PropositionTruthOutcome(str, Enum):
    """Portable proposition-evaluation outcome domain.

    ``unsupported`` is a realization disposition included in the portable
    envelope, not a logical truth value.
    """

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class PropositionEvaluationBasis(str, Enum):
    DECLARED_STATE = "declared_state"
    OBSERVED_STATE = "observed_state"


class PropositionAssertionPolarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class PropositionIndeterminacyReason(str, Enum):
    MISSING_EVIDENCE = "missing_evidence"
    STALE_EVIDENCE = "stale_evidence"
    PARTIAL_EVIDENCE = "partial_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    REDACTED_EVIDENCE = "redacted_evidence"
    LOSSY_EVIDENCE = "lossy_evidence"
    PROBE_FAILURE = "probe_failure"


class PropositionLossKind(str, Enum):
    MISSING = "missing"
    STALE = "stale"
    PARTIAL = "partial"
    CONFLICTING = "conflicting"
    REDACTED = "redacted"
    LOSSY = "lossy"
    PROBE_FAILURE = "probe_failure"


class PropositionProbeBindingModel(ContractModel):
    """Provenance for one capability-bound proposition realization."""

    binding_id: NonEmptyString
    implementation_id: NonEmptyString
    implementation_version: NonEmptyString
    artifact_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    backend_manifest_ref: NonEmptyString
    proposition_address: NonEmptyString
    capability_refs: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_capabilities(self) -> PropositionProbeBindingModel:
        if len(set(self.capability_refs)) != len(self.capability_refs):
            raise ValueError("probe binding capability_refs must be unique")
        return self


class PropositionTemporalContextModel(ContractModel):
    """Governed boundary and clock context used for one evaluation."""

    boundary_ref: NonEmptyString
    time_domain: NonEmptyString
    clock_authority: NonEmptyString


class PropositionLossDisclosureModel(ContractModel):
    kind: PropositionLossKind
    within_admissible_bound: bool


class PropositionTruthResultModel(ContractModel):
    """Evidence-bearing truth result separate from evaluator lifecycle state."""

    schema_version: Literal[PROPOSITION_TRUTH_RESULT_SCHEMA_VERSION] = PROPOSITION_TRUTH_RESULT_SCHEMA_VERSION
    result_id: NonEmptyString
    proposition_address: NonEmptyString
    assertion_address: NonEmptyString
    assertion_polarity: PropositionAssertionPolarity
    proposition_outcome: PropositionTruthOutcome
    assertion_outcome: PropositionTruthOutcome
    evaluation_basis: PropositionEvaluationBasis
    indeterminacy_reason: PropositionIndeterminacyReason | None = None
    probe_binding: PropositionProbeBindingModel | None = None
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)
    declared_artifact_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")] | None = None
    temporal_context: PropositionTemporalContextModel | None = None
    loss_disclosures: list[PropositionLossDisclosureModel] = Field(default_factory=list)
    unsupported_capability_refs: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_truth_result(self) -> PropositionTruthResultModel:
        self._validate_unique_refs()
        self._validate_polarity()
        self._validate_outcome_explanation()
        self._validate_basis_evidence()
        self._validate_loss_bounds()
        return self

    def _validate_unique_refs(self) -> None:
        for field_name in ("evidence_refs", "unsupported_capability_refs"):
            refs = getattr(self, field_name)
            if len(set(refs)) != len(refs):
                raise ValueError(f"{field_name} must be unique")

    def _validate_polarity(self) -> None:
        expected = self.proposition_outcome
        if self.assertion_polarity is PropositionAssertionPolarity.NEGATIVE:
            if expected is PropositionTruthOutcome.TRUE:
                expected = PropositionTruthOutcome.FALSE
            elif expected is PropositionTruthOutcome.FALSE:
                expected = PropositionTruthOutcome.TRUE
        if self.assertion_outcome is not expected:
            raise ValueError(
                f"{self.assertion_polarity.value} assertion outcome must preserve or invert the proposition outcome"
            )

    def _validate_outcome_explanation(self) -> None:
        if self.proposition_outcome is PropositionTruthOutcome.UNKNOWN:
            if self.indeterminacy_reason is None:
                raise ValueError("unknown proposition outcome requires indeterminacy_reason")
        elif self.indeterminacy_reason is not None:
            raise ValueError("indeterminacy_reason is valid only for unknown outcomes")
        if self.proposition_outcome is PropositionTruthOutcome.UNSUPPORTED:
            if not self.unsupported_capability_refs:
                raise ValueError("unsupported outcome requires unsupported_capability_refs")
        elif self.unsupported_capability_refs:
            raise ValueError("unsupported_capability_refs are valid only for unsupported outcomes")

    def _validate_basis_evidence(self) -> None:
        decided = self.proposition_outcome in {PropositionTruthOutcome.TRUE, PropositionTruthOutcome.FALSE}
        if decided and self.evaluation_basis is PropositionEvaluationBasis.OBSERVED_STATE:
            self._validate_observed_evidence()
        if self.probe_binding is not None and self.probe_binding.proposition_address != self.proposition_address:
            raise ValueError("probe_binding proposition_address must match proposition_address")
        if (
            decided
            and self.evaluation_basis is PropositionEvaluationBasis.DECLARED_STATE
            and self.declared_artifact_digest is None
        ):
            raise ValueError("declared-state decided truth requires declared_artifact_digest")

    def _validate_observed_evidence(self) -> None:
        if self.probe_binding is None:
            raise ValueError("observed-state decided truth requires probe_binding")
        if not self.evidence_refs:
            raise ValueError("observed-state decided truth requires evidence_refs")
        if self.temporal_context is None:
            raise ValueError("observed-state decided truth requires temporal_context")

    def _validate_loss_bounds(self) -> None:
        decided = self.proposition_outcome in {PropositionTruthOutcome.TRUE, PropositionTruthOutcome.FALSE}
        if decided and any(not disclosure.within_admissible_bound for disclosure in self.loss_disclosures):
            raise ValueError("lossy or partial evidence outside the admitted bound cannot decide truth")

    def semantic_claim(self) -> tuple[object, ...]:
        """Return the backend-independent portion used for equivalence checks."""

        return (
            self.proposition_address,
            self.assertion_address,
            self.assertion_polarity,
            self.proposition_outcome,
            self.assertion_outcome,
            self.evaluation_basis,
            self.indeterminacy_reason,
            self.temporal_context,
            tuple(self.loss_disclosures),
            tuple(self.unsupported_capability_refs),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        schema = handler.resolve_ref_schema(schema)
        decided = {"enum": ["true", "false"]}
        loss_items = deepcopy(schema["properties"]["loss_disclosures"]["items"])
        loss_items["properties"] = {"within_admissible_bound": {"const": True}}
        loss_items["required"] = ["within_admissible_bound"]
        schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {
                            "evaluation_basis": {"const": "observed_state"},
                            "proposition_outcome": decided,
                        },
                        "required": ["evaluation_basis", "proposition_outcome"],
                    },
                    "then": {
                        "properties": {
                            "probe_binding": {"not": {"type": "null"}},
                            "evidence_refs": {"minItems": 1},
                            "temporal_context": {"not": {"type": "null"}},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"proposition_outcome": {"const": "unknown"}},
                        "required": ["proposition_outcome"],
                    },
                    "then": {"properties": {"indeterminacy_reason": {"not": {"type": "null"}}}},
                    "else": {"properties": {"indeterminacy_reason": {"type": "null"}}},
                },
                {
                    "if": {
                        "properties": {"proposition_outcome": {"const": "unsupported"}},
                        "required": ["proposition_outcome"],
                    },
                    "then": {"properties": {"unsupported_capability_refs": {"minItems": 1}}},
                    "else": {"properties": {"unsupported_capability_refs": {"maxItems": 0}}},
                },
                {
                    "if": {
                        "properties": {"proposition_outcome": decided},
                        "required": ["proposition_outcome"],
                    },
                    "then": {"properties": {"loss_disclosures": {"items": loss_items}}},
                },
            ]
        )
        return schema
