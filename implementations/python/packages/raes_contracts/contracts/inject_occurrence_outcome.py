"""ADR-112 inject invocation, per-binding readback and participant correlation; an adopting runtime settles."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from ..canonical import canonical_json_digest
from ..operation_lifecycle import OperationState
from ..versions import INJECT_OCCURRENCE_CORRELATION_SCHEMA_VERSION, INJECT_OCCURRENCE_OUTCOME_SCHEMA_VERSION
from .backend_operation import BackendOperationRequestModel, OperationArtifactReferenceModel, OperationContractModel
from .backend_operation_response import (
    BackendOperationAcknowledgementModel,
    BackendOperationEffectsModel,
    BackendOperationOutcomeModel,
    BackendOperationResponseModel,
)
from .backend_operation_validation import validate_backend_operation_response
from .inject_occurrence import (
    InjectOccurrenceModel,
    InjectSchedulePlacementModel,
    InjectTargetBindingModel,
    inject_occurrence_digest,
)

InjectOccurrenceEffect = Literal["effect-applied", "effect-absent", "known-partial", "indeterminate"]
_BACKEND_EFFECT: dict[str, InjectOccurrenceEffect] = {
    "complete": "effect-applied",
    "absent": "effect-absent",
    "partial": "known-partial",
    "unknown": "indeterminate",
}


class InjectBindingOutcomeModel(OperationContractModel):
    """One selected binding's reported effect knowledge; a missing report is never absence."""

    binding: InjectTargetBindingModel
    effects: BackendOperationEffectsModel
    readback: OperationArtifactReferenceModel | None = None

    @model_validator(mode="after")
    def _readback_basis(self) -> Self:
        if self.effects.effect in {"complete", "partial"} and self.readback is None:
            raise ValueError("applied inject effects require their observation or readback basis")
        return self


def inject_occurrence_effect(bindings: tuple[InjectBindingOutcomeModel, ...]) -> InjectOccurrenceEffect:
    """Aggregate fan-out facts (EI-04); any unknown or unceased binding stays indeterminate."""

    if not bindings:
        raise ValueError("an inject effect aggregates at least one reported binding")
    if any(item.effects.effect == "unknown" or not item.effects.cessation_established for item in bindings):
        return "indeterminate"
    effects = {item.effects.effect for item in bindings}
    if effects == {"complete"}:
        return "effect-applied"
    return "effect-absent" if effects == {"absent"} else "known-partial"


def _backend_effect(effects: BackendOperationEffectsModel) -> InjectOccurrenceEffect:
    """Classify the backend's own report; effects without established cessation stay indeterminate."""

    return _BACKEND_EFFECT[effects.effect] if effects.cessation_established else "indeterminate"


def _is_start_refusal(message: object) -> bool:
    """A refused start proves the invocation never began; an admission refusal precedes dispatch (EI-03)."""

    return isinstance(message, BackendOperationAcknowledgementModel) and message.disposition == "refused"


class InjectOccurrenceOutcomeModel(OperationContractModel):
    """Per-binding readback for one claimed occurrence; not delivery, observation or a commit."""

    schema_version: Literal[INJECT_OCCURRENCE_OUTCOME_SCHEMA_VERSION] = INJECT_OCCURRENCE_OUTCOME_SCHEMA_VERSION
    occurrence: OperationArtifactReferenceModel
    response: BackendOperationResponseModel
    bindings: tuple[InjectBindingOutcomeModel, ...] = Field(min_length=1, max_length=256)
    effect: InjectOccurrenceEffect

    @model_validator(mode="after")
    def _settlement(self) -> Self:
        if self.occurrence.contract_id != "inject-occurrence-v1":
            raise ValueError("inject outcome must name a claimed inject occurrence")
        selected = [(item.binding.binding, item.binding.instance) for item in self.bindings]
        if len(selected) != len(set(selected)):
            raise ValueError("inject outcome reports each selected binding instance once")
        if self.effect != inject_occurrence_effect(self.bindings):
            raise ValueError("inject outcome effect must aggregate every binding's reported facts")
        message = self.response.message
        if isinstance(message, BackendOperationOutcomeModel):
            self._backend_outcome(message)
        elif not _is_start_refusal(message) or self.effect != "effect-absent":
            raise ValueError("only a start refusal with proven absence or a backend outcome settles an occurrence")
        return self

    def _backend_outcome(self, message: BackendOperationOutcomeModel) -> None:
        if _backend_effect(message.effects) != self.effect:
            raise ValueError("backend outcome effects disagree with the per-binding readback")
        if message.proposed_state == OperationState.SUCCEEDED and self.effect != "effect-applied":
            raise ValueError("success requires an applied world effect; no successful no-op settles an inject")


class InjectOccurrenceCorrelationModel(OperationContractModel):
    """Exact applied occurrence, settled outcome and produced result a participant consumer joins."""

    schema_version: Literal[INJECT_OCCURRENCE_CORRELATION_SCHEMA_VERSION] = INJECT_OCCURRENCE_CORRELATION_SCHEMA_VERSION
    occurrence: OperationArtifactReferenceModel
    outcome: OperationArtifactReferenceModel
    result: OperationArtifactReferenceModel

    @model_validator(mode="after")
    def _join(self) -> Self:
        if (self.occurrence.contract_id, self.outcome.contract_id) != (
            "inject-occurrence-v1",
            "inject-occurrence-outcome-v1",
        ):
            raise ValueError("inject correlation joins an inject occurrence and its outcome")
        if self.occurrence.artifact_id != self.outcome.artifact_id:
            raise ValueError("inject correlation outcome must settle the same occurrence")
        return self


def inject_occurrence_reference(occurrence: InjectOccurrenceModel) -> OperationArtifactReferenceModel:
    """Return the content-bound command reference for one claimed occurrence."""

    return OperationArtifactReferenceModel(
        contract_id="inject-occurrence-v1",
        artifact_id=occurrence.request.occurrence_id,
        digest=inject_occurrence_digest(occurrence),
    )


def inject_occurrence_outcome_digest(outcome: InjectOccurrenceOutcomeModel) -> str:
    return canonical_json_digest(outcome.model_dump(mode="json"))


def require_inject_occurrence_invocation(
    occurrence: InjectOccurrenceModel, request: BackendOperationRequestModel
) -> None:
    """Bind one backend invocation to the exact claimed occurrence; this grants no dispatch."""

    if request.command != inject_occurrence_reference(occurrence):
        raise ValueError("backend invocation must command the exact claimed inject occurrence")
    binding = request.binding
    if binding.operation_id != occurrence.operation_id or binding.context != occurrence.admission:
        raise ValueError("backend invocation must retain the occurrence operation and admission context")
    if not set(occurrence.evidence_requirements) <= set(request.requirement_refs):
        raise ValueError("backend invocation must carry every evidence requirement of the occurrence")
    placement = occurrence.request.placement
    claims = {occurrence.request.request_key, occurrence.request.occurrence_id, occurrence.operation_id}
    if isinstance(placement, InjectSchedulePlacementModel):
        claims.add(placement.slot)
    if {binding.attempt_id, binding.invocation_id} & claims:
        raise ValueError("backend attempt and invocation identities must stay distinct from the claims")
    scope = binding.effect_scope
    if scope.kind == "resources" and not {item.binding for item in occurrence.request.bindings} <= set(scope.addresses):
        raise ValueError("backend effect scope must cover every selected inject binding")


def validate_inject_occurrence_outcome(
    occurrence: InjectOccurrenceModel, request: BackendOperationRequestModel, outcome: InjectOccurrenceOutcomeModel
) -> None:
    """Join readback to the exact occurrence and invocation; an adopting runtime still validates and commits."""

    require_inject_occurrence_invocation(occurrence, request)
    validate_backend_operation_response(request, outcome.response)
    if outcome.occurrence != request.command:
        raise ValueError("inject outcome names another occurrence")
    if tuple(item.binding for item in outcome.bindings) != occurrence.request.bindings:
        raise ValueError("inject outcome must report every selected binding in request order")
    scope = request.binding.effect_scope
    residual = {address for item in outcome.bindings for address in item.effects.residual_scope}
    if scope.kind == "resources" and not residual <= set(scope.addresses):
        raise ValueError("binding residual effects exceed the admitted resource scope")


def inject_occurrence_correlation(
    occurrence: InjectOccurrenceModel, request: BackendOperationRequestModel, outcome: InjectOccurrenceOutcomeModel
) -> InjectOccurrenceCorrelationModel:
    """Return the participant join; only a successful applied effect supplies a produced result."""

    validate_inject_occurrence_outcome(occurrence, request, outcome)
    message = outcome.response.message
    if (
        not isinstance(message, BackendOperationOutcomeModel)
        or message.proposed_state != OperationState.SUCCEEDED
        or message.result is None
    ):
        raise ValueError("only a successful applied world effect supplies a result for participant joins")
    return InjectOccurrenceCorrelationModel(
        occurrence=outcome.occurrence,
        outcome=OperationArtifactReferenceModel(
            contract_id="inject-occurrence-outcome-v1",
            artifact_id=occurrence.request.occurrence_id,
            digest=inject_occurrence_outcome_digest(outcome),
        ),
        result=message.result,
    )


def validate_inject_occurrence_correlation(
    occurrence: InjectOccurrenceModel,
    request: BackendOperationRequestModel,
    outcome: InjectOccurrenceOutcomeModel,
    correlation: InjectOccurrenceCorrelationModel,
) -> None:
    """Accept a received participant join only if it equals the join recomputed from its sources."""

    if correlation != inject_occurrence_correlation(occurrence, request, outcome):
        raise ValueError("inject correlation must equal the join recomputed from its validated sources")
