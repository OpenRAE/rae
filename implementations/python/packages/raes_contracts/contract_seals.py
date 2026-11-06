"""Fill derived contract fields from the rest of a document (issue #1929).

Some contract documents carry fields whose value is computed from the rest of the
same document: self-digests such as ``plan_digest`` and derived identifiers such as
``selection_id``. The owning models verify these fields. A document author must not
compute them by hand, so test fixtures leave them out and :func:`seal_payload` fills
each missing derived field with the value that the owning model would verify.

The engine walks the model's declared field types, so it seals nested models first.
It fills only fields that are absent; a present value stays, so a fixture can still
carry a deliberately wrong value to test the refusal.
"""

from __future__ import annotations

import copy
import types
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any

from pydantic import BaseModel, ValidationError

from ._domain_profile_contracts import (
    AdmittedDomainProfileDefinitionModel,
    DomainProfileDefinitionModel,
    DomainProfileSchemaModel,
    canonical_domain_profile_definition_digest,
)
from ._participant_opacity_model_check import (
    ParticipantOpacityModelCheckEvidenceModel,
    model_check_counterexample_digest,
)
from ._sealing import sealing
from .assigned_trial import TrialAssignmentModel
from .authoring_adapters import AuthoringAdapterVectorModel
from .canonical import canonical_contract_digest, canonical_json_digest
from .contracts.admitted_trial_plan import AdmittedTrialEntryModel, AdmittedTrialPlanModel
from .contracts.candidate_synthesis import (
    CandidateSynthesisInputModel,
    CandidateSynthesisRecordModel,
    assertion_set_digest,
)
from .contracts.candidate_synthesis_profiles import CandidateSynthesisProfileDefinitionModel
from .contracts.difficulty_adaptation import DifficultyPolicyModel, difficulty_policy_digest
from .contracts.experiment_bindings import ParticipantConfigurationResultModel
from .contracts.experiment_run import ExperimentRunModel
from .contracts.experiment_spec import ExperimentSpecModel
from .contracts.experiment_study_contract import ExperimentStudyModel
from .contracts.experiment_treatments import ExperimentScenarioSelectionDescriptorModel, scenario_selection_id
from .contracts.materialization_attestation import MaterializationArchiveRecord, materialization_artifact_uri
from .contracts.mixed_composition import MixedParticipantCompositionProfileModel, mixed_composition_profile_digest
from .contracts.semantic_projection import (
    SemanticProjectionPredicateProfileModel,
    SemanticProjectionReportModel,
    canonical_semantic_projection_frame_digest,
    canonical_semantic_projection_predicate_profile_digest,
    semantic_projection_adapter_digest,
    semantic_projection_qualified_fraction,
)
from .contracts.time_model import RealizedTimeModelProvenanceModel
from .digests import sha256_digest
from .participant_opacity import ParticipantOpacityAnalysisEvidenceModel, analysis_counterexample_digest
from .realization_envelope import (
    BackendRealizationEnvelopeModel,
    realization_envelope_digest,
    realizer_configuration_digest,
)
from .realization_profiles import PlanProfileAuthority
from .semantic_comparison import (
    ImpactScopeModel,
    SemanticComparisonRequestModel,
    SemanticComparisonResultModel,
    canonical_impact_scope_digest,
)

_DIGEST_PLACEHOLDER = "sha256:" + "0" * 64
_MISSING = object()

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class SealField:
    """One derived field of a model: where it lives and how its value is computed."""

    path: tuple[str, ...]
    compute: Callable[[Any], object]
    placeholder: object = _DIGEST_PLACEHOLDER


def _without(model: BaseModel, field: str) -> dict[str, Any]:
    data = model.model_dump(mode="json")
    data.pop(field, None)
    return data


@cache
def _registry() -> dict[type[BaseModel], tuple[SealField, ...]]:
    def input_digest(record: CandidateSynthesisRecordModel) -> str:
        return canonical_json_digest(record.input.model_dump(mode="json"))

    def frame_digest(report: SemanticProjectionReportModel) -> str:
        return canonical_semantic_projection_frame_digest(report.frame)

    return {
        AdmittedTrialEntryModel: (
            SealField(("entry_digest",), lambda m: canonical_json_digest(_without(m, "entry_digest"))),
        ),
        AdmittedTrialPlanModel: (
            SealField(("plan_digest",), lambda m: canonical_json_digest(_without(m, "plan_digest"))),
        ),
        AuthoringAdapterVectorModel: (
            SealField(("input_digest",), lambda m: sha256_digest(m.input_source.encode("utf-8"))),
            SealField(("operation_digest",), lambda m: canonical_json_digest(m.operation.model_dump(mode="json"))),
        ),
        DomainProfileSchemaModel: (SealField(("schema_digest",), lambda m: canonical_json_digest(m.schema_document)),),
        DomainProfileDefinitionModel: (
            SealField(("coordinate", "definition_digest"), canonical_domain_profile_definition_digest),
        ),
        AdmittedDomainProfileDefinitionModel: (
            SealField(("provenance", "source_digest"), lambda m: m.definition.coordinate.definition_digest),
        ),
        BackendRealizationEnvelopeModel: (
            SealField(
                ("configuration", "configuration_digest"), lambda m: realizer_configuration_digest(m.configuration)
            ),
            SealField(("digest",), realization_envelope_digest),
        ),
        ParticipantOpacityModelCheckEvidenceModel: (
            SealField(("assumptions_digest",), lambda m: m.assumptions.canonical_digest),
            SealField(("checker_configuration_digest",), lambda m: m.checker_configuration.canonical_digest),
            SealField(("counterexample", "counterexample_digest"), model_check_counterexample_digest),
        ),
        ParticipantOpacityAnalysisEvidenceModel: (
            SealField(("checker_configuration_digest",), lambda m: m.checker_configuration.canonical_digest),
            SealField(("counterexample", "counterexample_digest"), analysis_counterexample_digest),
        ),
        CandidateSynthesisInputModel: (
            SealField(("source", "assertion_set_digest"), lambda m: assertion_set_digest(m.assertions)),
        ),
        MaterializationArchiveRecord: (
            SealField(
                ("artifact", "uri"),
                lambda m: materialization_artifact_uri(m.artifact.checksum.value),
                placeholder="urn:sha256:" + "0" * 64,
            ),
        ),
        ImpactScopeModel: (SealField(("scope_digest",), canonical_impact_scope_digest),),
        SemanticComparisonResultModel: (SealField(("impact_scope_digest",), lambda m: m.impact_scope.scope_digest),),
        DifficultyPolicyModel: (SealField(("policy_digest",), difficulty_policy_digest),),
        ParticipantConfigurationResultModel: (
            SealField(("configuration_digest",), lambda m: canonical_contract_digest(m.configuration)),
        ),
        SemanticProjectionPredicateProfileModel: (
            SealField(("adapter_digest",), semantic_projection_adapter_digest),
            SealField(("profile_digest",), canonical_semantic_projection_predicate_profile_digest),
        ),
        SemanticProjectionReportModel: (
            SealField(("frame_digest",), frame_digest),
            SealField(("summary", "frame_digest"), frame_digest),
            SealField(("summary", "predicate_profile_digest"), lambda m: m.frame.predicate_profile.profile_digest),
            SealField(("summary", "qualified_fraction"), semantic_projection_qualified_fraction, placeholder="pending"),
        ),
        CandidateSynthesisProfileDefinitionModel: (
            SealField(
                ("profile_digest",),
                lambda m: canonical_json_digest(m.model_dump(mode="json", exclude={"profile_digest"})),
            ),
        ),
        CandidateSynthesisRecordModel: (
            SealField(("input_digest",), input_digest),
            SealField(("transformation_report", "source_digest"), input_digest),
        ),
        RealizedTimeModelProvenanceModel: (
            SealField(("declaration_digest",), lambda m: m.declared_model.canonical_digest()),
        ),
        MixedParticipantCompositionProfileModel: (SealField(("profile_digest",), mixed_composition_profile_digest),),
        ExperimentScenarioSelectionDescriptorModel: (
            SealField(("selection_id",), scenario_selection_id, placeholder="selection-" + "0" * 64),
        ),
    }


def sealed_models() -> tuple[type[BaseModel], ...]:
    """Return the models that own derived fields."""
    return tuple(_registry())


# --- typed walk -------------------------------------------------------------------------------------------------


def _candidates(annotation: object) -> Iterator[object]:
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        yield from _candidates(typing.get_args(annotation)[0])
    elif origin in (typing.Union, types.UnionType):
        for member in typing.get_args(annotation):
            yield from _candidates(member)
    else:
        yield annotation


def _literal_keys(model: type[BaseModel]) -> dict[str, tuple[object, ...]]:
    return {
        field.alias or name: typing.get_args(field.annotation)
        for name, field in model.model_fields.items()
        if typing.get_origin(field.annotation) is typing.Literal
    }


def _discriminated(model: type[BaseModel], value: Mapping[str, Any]) -> bool:
    literals = {key: allowed for key, allowed in _literal_keys(model).items() if key in value}
    return bool(literals) and all(value[key] in allowed for key, allowed in literals.items())


def _validates(model: type[BaseModel], value: Mapping[str, Any]) -> bool:
    try:
        with sealing():
            model.model_validate(value)
    except ValidationError:
        return False
    return True


def _model_for(annotation: object, value: Mapping[str, Any]) -> type[BaseModel] | None:
    models = [item for item in _candidates(annotation) if isinstance(item, type) and issubclass(item, BaseModel)]
    if len(models) > 1:
        # A discriminating literal field picks a union member; otherwise the first member that validates.
        models = [model for model in models if _discriminated(model, value)] or [
            model for model in models if _validates(model, value)
        ]
    return models[0] if models else None


def _item_annotation(origin: object, args: tuple[object, ...], index: int) -> object:
    if origin is tuple and args[-1] is not Ellipsis and len(args) > 1:
        return args[index]
    return args[0]


def _walk_container(annotation: object, value: object, visit: Callable[[type[BaseModel], JsonObject], None]) -> bool:
    """Walk the items of a mapping or sequence value; return whether *annotation* described a container."""
    for candidate in _candidates(annotation):
        origin, args = typing.get_origin(candidate), typing.get_args(candidate)
        if isinstance(value, dict) and origin in (dict, Mapping, typing.Mapping) and len(args) == 2:
            for item in value.values():
                _walk_value(args[1], item, visit)
            return True
        if isinstance(value, list) and origin in (list, tuple, set, frozenset, Sequence) and args:
            for index, item in enumerate(value):
                _walk_value(_item_annotation(origin, args, index), item, visit)
            return True
    return False


def _walk_value(annotation: object, value: object, visit: Callable[[type[BaseModel], JsonObject], None]) -> None:
    if _walk_container(annotation, value, visit) or not isinstance(value, dict):
        return
    model = _model_for(annotation, value)
    if model is not None:
        _walk_model(model, value, visit)


def _walk_model(
    model: type[BaseModel], payload: JsonObject, visit: Callable[[type[BaseModel], JsonObject], None]
) -> None:
    for name, field in model.model_fields.items():
        key = field.alias or name
        if key in payload:
            _walk_value(field.annotation, payload[key], visit)
    visit(model, payload)


def _get(payload: JsonObject, path: tuple[str, ...]) -> tuple[JsonObject | None, object]:
    current: object = payload
    for key in path[:-1]:
        if not isinstance(current, dict) or key not in current:
            return None, None
        current = current[key]
    if not isinstance(current, dict):
        return None, None
    return current, current.get(path[-1], _MISSING)


def _validated(model: type[BaseModel], payload: JsonObject) -> BaseModel | None:
    try:
        with sealing():
            return model.model_validate(payload)
    except ValidationError:
        return None


def seal_payload(model: type[BaseModel], payload: JsonObject) -> JsonObject:
    """Return a copy of *payload* with every absent derived field filled, nested models first."""

    result = copy.deepcopy(payload)

    def fill(owner: type[BaseModel], node: JsonObject) -> None:
        pending = []
        for item in _registry().get(owner, ()):
            parent, current = _get(node, item.path)
            if parent is not None and current is _MISSING:
                parent[item.path[-1]] = item.placeholder
                pending.append((parent, item))
        # Compute one field at a time: a later derived value can cover an earlier one.
        for parent, item in pending:
            instance = _validated(owner, node)
            if instance is None:
                for other_parent, other in pending:
                    other_parent.pop(other.path[-1], None)
                return
            parent[item.path[-1]] = item.compute(instance)

    _walk_model(model, result, fill)
    return result


def _strip(model: type[BaseModel], payload: JsonObject, removed: list[str]) -> JsonObject:
    result = copy.deepcopy(payload)
    nodes: list[tuple[type[BaseModel], JsonObject]] = []
    _walk_model(model, result, lambda owner, node: nodes.append((owner, node)))
    # Strip outermost first: an outer digest is computed over the inner derived values.
    for owner, node in reversed(nodes):
        instance = _validated(owner, node)
        if instance is None:
            continue
        for item in _registry().get(owner, ()):
            parent, current = _get(node, item.path)
            if parent is not None and current is not _MISSING and current == item.compute(instance):
                del parent[item.path[-1]]
                removed.append(f"{owner.__name__}:{'/'.join(item.path)}")
    return result


def derivable_seal_paths(model: type[BaseModel], payload: JsonObject) -> list[str]:
    """Return the stored derived values that :func:`seal_payload` would reproduce, so need not be stored."""

    removed: list[str] = []
    _strip(model, payload, removed)
    return removed


def strip_derivable_seals(model: type[BaseModel], payload: JsonObject) -> JsonObject:
    """Return a copy of *payload* without stored derived values that :func:`seal_payload` reproduces."""

    return _strip(model, payload, [])


# Contracts whose documents contain derived fields, by contract id. A fixture reader seals these before validation.
_CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "admitted-trial-plan-v1": AdmittedTrialPlanModel,
    "assigned-trial-v1": TrialAssignmentModel,
    "authoring-adapter-vector-v1": AuthoringAdapterVectorModel,
    "domain-profile-definition-v1": DomainProfileDefinitionModel,
    "experiment-authoring-input-v1": ExperimentSpecModel,
    "experiment-run-v1": ExperimentRunModel,
    "experiment-study-v1": ExperimentStudyModel,
    "materialization-archive-record-v1": MaterializationArchiveRecord,
    "mixed-participant-composition-profile-v1": MixedParticipantCompositionProfileModel,
    "participant-configuration-result-v1": ParticipantConfigurationResultModel,
    "participant-opacity-analysis-evidence-v1": ParticipantOpacityAnalysisEvidenceModel,
    "participant-opacity-model-check-evidence-v1": ParticipantOpacityModelCheckEvidenceModel,
    "plan-realization-profiles-v1": PlanProfileAuthority,
    "realization-envelope-v1": BackendRealizationEnvelopeModel,
    "realized-time-model-v1": RealizedTimeModelProvenanceModel,
    "sdl-candidate-synthesis-input-v1": CandidateSynthesisInputModel,
    "sdl-candidate-synthesis-record-v1": CandidateSynthesisRecordModel,
    "semantic-comparison-request-v1": SemanticComparisonRequestModel,
    "semantic-comparison-result-v1": SemanticComparisonResultModel,
    "semantic-projection-report-v1": SemanticProjectionReportModel,
}

# Fixture kinds that must be internally consistent. ``invalid`` fixtures stay as written: one can test an absent field.
SEALED_FIXTURE_KINDS = frozenset({"valid", "context-invalid"})


def sealed_contract_ids() -> frozenset[str]:
    """Return the contract ids whose documents contain derived fields."""
    return frozenset(_CONTRACT_MODELS)


def contract_seal_model(contract_id: str) -> type[BaseModel] | None:
    """Return the model that owns the derived fields of *contract_id*, or ``None``."""
    return _CONTRACT_MODELS.get(contract_id)


def seal_contract_fixture(contract_id: str, payload: object, *, kind: str = "valid") -> object:
    """Return *payload* with its derived fields filled when *contract_id* has any and *kind* is sealed."""
    model = contract_seal_model(contract_id)
    if model is None or kind not in SEALED_FIXTURE_KINDS or not isinstance(payload, dict):
        return payload
    return seal_payload(model, payload)


__all__ = [
    "SEALED_FIXTURE_KINDS",
    "contract_seal_model",
    "seal_contract_fixture",
    "sealed_contract_ids",
    "SealField",
    "derivable_seal_paths",
    "seal_payload",
    "sealed_models",
    "strip_derivable_seals",
]
