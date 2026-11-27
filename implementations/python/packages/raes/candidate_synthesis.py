"""Pure source-neutral synthesis of ordinary SDL authoring candidates."""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ArtifactTransformationKind,
    ArtifactTransformationLossKind,
    ArtifactTransformationLossModel,
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
    CandidateSynthesisChoiceModel,
    CandidateSynthesisConstructTraceModel,
    CandidateSynthesisContributionModel,
    CandidateSynthesisDisposition,
    CandidateSynthesisInputModel,
    CandidateSynthesisProfileDefinitionModel,
    CandidateSynthesisReason,
    CandidateSynthesisRecordModel,
    ConceptSourceAssertionModel,
    OrderingSourceAssertionModel,
    ParameterizationSourceAssertionModel,
    PreservationOutcome,
    RelationshipSourceAssertionModel,
    SynthesisContributionKind,
    TransformationCheckOutcome,
)
from raes_contracts.digests import sha256_digest

from ._transformation_support import SDL_CONTRACT_PROFILE, check, diagnostic
from .canonical import canonical_sdl_digest
from .formatting import render_sdl_source
from .scenario import Scenario

SYNTHESIS_PROFILE_ID = "concept-nodes/v1"
SYNTHESIS_PROFILE_VERSION = "1"
_SYNTHESIS_PROFILE_CONTENT = {
    "schema_version": "sdl-candidate-synthesis-profile/v1",
    "profile_id": SYNTHESIS_PROFILE_ID,
    "profile_version": SYNTHESIS_PROFILE_VERSION,
    "source_profile": "sdl-candidate-synthesis-input/v1",
    "target_profile": "sdl-authoring-input/v1",
    "rendering_profile": "sdl-yaml/v1",
    "canonicalization_profile": "raes-sdl-canonical/v1",
    "supported_assertion_kinds": ["concept"],
    "supported_node_types": ["compute", "switch"],
    "rule_ids": ["concept-node-emission"],
    "default_ids": [],
    "refusal_reason_codes": [
        "ambiguous-ordering",
        "missing-native-semantics",
        "stale-input",
        "transformation-profile-unavailable",
        "unresolved-parameterization",
        "unsupported-relation",
    ],
    "all_or_none": True,
    "semantic_validation_required": True,
    "imports_allowed": False,
    "deterministic_order": "sorted-target-ref/v1",
    "limits": {
        "max_assertions": 4096,
        "max_assumptions": 1024,
        "max_decisions": 1024,
        "max_node_identifier_length": 35,
    },
}
SYNTHESIS_PROFILE = CandidateSynthesisProfileDefinitionModel(
    **_SYNTHESIS_PROFILE_CONTENT,
    profile_digest=canonical_json_digest(_SYNTHESIS_PROFILE_CONTENT),
)
SYNTHESIS_PROFILE_DIGEST = SYNTHESIS_PROFILE.profile_digest
SYNTHESIS_PRESERVATION_PROFILE = "source-neutral-candidate-provenance/v1"


@dataclass(frozen=True, slots=True)
class SDLCandidateSynthesisResult:
    """All-or-none candidate bytes, admitted SDL, and portable synthesis record."""

    candidate_content: str | None
    candidate: Scenario | None
    record: CandidateSynthesisRecordModel

    @property
    def succeeded(self) -> bool:
        return self.candidate is not None and self.record.disposition == CandidateSynthesisDisposition.SUCCESS


def _input_digest(value: CandidateSynthesisInputModel) -> str:
    return canonical_json_digest(value.model_dump(mode="json"))


def _derivation_digest(value: CandidateSynthesisInputModel, input_digest: str) -> str:
    return canonical_json_digest(
        {
            "input_digest": input_digest,
            "operation_profile": SYNTHESIS_PROFILE_ID,
            "policy_digest": value.policy_digest,
            "transformation_profile_digest": value.transformation_profile.digest,
        }
    )


def _choice(
    assertion_id: str,
    reason: CandidateSynthesisReason,
    *alternatives: str,
) -> CandidateSynthesisChoiceModel:
    return CandidateSynthesisChoiceModel(
        choice_id=f"{assertion_id}-{reason.value}",
        reason=reason,
        assertion_ids=(assertion_id,),
        alternatives=tuple(sorted(set(alternatives))),
    )


def _unresolved_choices(value: CandidateSynthesisInputModel) -> tuple[CandidateSynthesisChoiceModel, ...]:
    choices: list[CandidateSynthesisChoiceModel] = []
    decisions_by_assertion = {
        assertion_id: [decision for decision in value.decisions if assertion_id in decision.assertion_ids]
        for assertion_id in (item.assertion_id for item in value.assertions)
    }
    for assertion in value.assertions:
        if isinstance(assertion, ConceptSourceAssertionModel):
            if len(decisions_by_assertion[assertion.assertion_id]) != 1:
                choices.append(
                    _choice(
                        assertion.assertion_id,
                        CandidateSynthesisReason.MISSING_NATIVE_SEMANTICS,
                        "supply-one-explicit-native-construct-decision",
                    )
                )
        elif isinstance(assertion, OrderingSourceAssertionModel) and assertion.direction == "unspecified":
            choices.append(
                _choice(
                    assertion.assertion_id,
                    CandidateSynthesisReason.AMBIGUOUS_ORDERING,
                    "left-before-right",
                    "right-before-left",
                )
            )
        elif isinstance(assertion, RelationshipSourceAssertionModel):
            choices.append(
                _choice(
                    assertion.assertion_id,
                    CandidateSynthesisReason.UNSUPPORTED_RELATION,
                    "select-a-governed-profile-with-an-exact-native-relation",
                )
            )
        elif isinstance(assertion, ParameterizationSourceAssertionModel):
            choices.append(
                _choice(
                    assertion.assertion_id,
                    CandidateSynthesisReason.UNRESOLVED_PARAMETERIZATION,
                    *assertion.candidate_values,
                )
            )
        else:
            choices.append(
                _choice(
                    assertion.assertion_id,
                    CandidateSynthesisReason.MISSING_NATIVE_SEMANTICS,
                    "select-a-governed-profile-with-an-exact-native-rule",
                )
            )
    return tuple(sorted(choices, key=lambda item: item.choice_id))


def _refused(
    value: CandidateSynthesisInputModel,
    *,
    disposition: CandidateSynthesisDisposition,
    choices: tuple[CandidateSynthesisChoiceModel, ...],
    diagnostic_code: str,
) -> SDLCandidateSynthesisResult:
    input_digest = _input_digest(value)
    semantic_omissions = tuple(
        ArtifactTransformationLossModel(
            kind=ArtifactTransformationLossKind.SEMANTIC_OMISSION,
            affected_identity=assertion_id,
            diagnostic=diagnostic(
                "candidate-synthesis.semantic-omission",
                "The source assertion cannot be represented without omitting unsupported semantics.",
                address=f"/assertions/{assertion_id}",
            ),
        )
        for assertion_id in sorted(
            {
                assertion_id
                for choice in choices
                if choice.reason == CandidateSynthesisReason.UNSUPPORTED_RELATION
                for assertion_id in choice.assertion_ids
            }
        )
    )
    report = ArtifactTransformationReportModel(
        operation_profile=SYNTHESIS_PROFILE_ID,
        status=ArtifactTransformationStatus.REFUSED,
        artifact_kind=ArtifactTransformationKind.SDL_AUTHORING,
        source_profile=value.schema_version,
        target_profile=SDL_CONTRACT_PROFILE,
        canonicalization_profile="raes-sdl-canonical/v1",
        source_digest=input_digest,
        policy_digest=value.policy_digest,
        derivation_digest=_derivation_digest(value, input_digest),
        preconditions=(
            check("candidate-resolved", TransformationCheckOutcome.FAILED, diagnostic_code),
            check("source-admitted", TransformationCheckOutcome.PASSED),
        ),
        preservation=ArtifactTransformationPreservationModel(
            profile=SYNTHESIS_PRESERVATION_PROFILE,
            outcome=PreservationOutcome.NOT_APPLICABLE,
            limitations=("A refused synthesis emits no SDL candidate.",),
        ),
        losses=semantic_omissions,
        diagnostics=(
            diagnostic(
                diagnostic_code,
                "Candidate synthesis requires an exact governed choice or supported transformation profile.",
            ),
        ),
    )
    record = CandidateSynthesisRecordModel(
        record_id=f"{value.input_id}-record",
        input_id=value.input_id,
        input_digest=input_digest,
        disposition=disposition,
        input=value,
        profile=(SYNTHESIS_PROFILE if value.transformation_profile == SYNTHESIS_PROFILE.coordinate() else None),
        unresolved_choices=choices,
        transformation_report=report,
    )
    return SDLCandidateSynthesisResult(candidate_content=None, candidate=None, record=record)


def _construct_traces(value: CandidateSynthesisInputModel) -> tuple[CandidateSynthesisConstructTraceModel, ...]:
    traces: list[CandidateSynthesisConstructTraceModel] = []
    for decision in value.decisions:
        decision_kind = (
            SynthesisContributionKind.AUTHOR_DECISION
            if decision.actor_kind == "author"
            else SynthesisContributionKind.GOVERNED_POLICY_DECISION
        )
        contributions = [
            *(
                CandidateSynthesisContributionModel(
                    kind=SynthesisContributionKind.IMPORTED_ASSERTION,
                    ref_id=assertion_id,
                )
                for assertion_id in decision.assertion_ids
            ),
            *(
                CandidateSynthesisContributionModel(
                    kind=SynthesisContributionKind.TRANSFORMATION_ASSUMPTION,
                    ref_id=assumption.assumption_id,
                )
                for assumption in value.assumptions
                if set(assumption.assertion_ids) & set(decision.assertion_ids)
            ),
            CandidateSynthesisContributionModel(
                kind=SynthesisContributionKind.INFERRED_STRUCTURE,
                ref_id="concept-node-emission",
            ),
            CandidateSynthesisContributionModel(kind=decision_kind, ref_id=decision.decision_id),
        ]
        traces.append(
            CandidateSynthesisConstructTraceModel(
                target_ref=decision.target_ref,
                contributions=tuple(contributions),
            )
        )
    return tuple(sorted(traces, key=lambda item: item.target_ref))


def synthesize_sdl_candidate(value: CandidateSynthesisInputModel) -> SDLCandidateSynthesisResult:
    """Synthesize one complete candidate or a typed all-or-none refusal."""

    if not isinstance(value, CandidateSynthesisInputModel):
        raise TypeError("candidate synthesis requires an admitted CandidateSynthesisInputModel")
    profile = value.transformation_profile
    if (
        profile.profile_id != SYNTHESIS_PROFILE_ID
        or profile.version != SYNTHESIS_PROFILE_VERSION
        or profile.digest != SYNTHESIS_PROFILE_DIGEST
    ):
        choice = _choice(
            value.assertions[0].assertion_id,
            CandidateSynthesisReason.TRANSFORMATION_PROFILE_UNAVAILABLE,
            SYNTHESIS_PROFILE_ID,
        )
        return _refused(
            value,
            disposition=CandidateSynthesisDisposition.NON_REPRODUCIBLE,
            choices=(choice,),
            diagnostic_code="candidate-synthesis.transformation-profile-unavailable",
        )

    choices = _unresolved_choices(value)
    if choices:
        disposition = (
            CandidateSynthesisDisposition.UNSUPPORTED
            if any(item.reason == CandidateSynthesisReason.UNSUPPORTED_RELATION for item in choices)
            else CandidateSynthesisDisposition.REQUIRES_DECISION
        )
        return _refused(
            value,
            disposition=disposition,
            choices=choices,
            diagnostic_code="candidate-synthesis.unresolved-semantics",
        )

    nodes = {decision.target_ref.removeprefix("nodes."): {"type": decision.node_type} for decision in value.decisions}
    provisional = Scenario.model_validate(
        {
            "name": value.target.scenario_id,
            "version": value.target.scenario_version,
            "nodes": nodes,
        }
    )
    rendered = render_sdl_source(provisional)
    canonical_digest = canonical_sdl_digest(rendered.scenario)
    exact_digest = sha256_digest(rendered.content.encode("utf-8"))
    input_digest = _input_digest(value)
    report = ArtifactTransformationReportModel(
        operation_profile=SYNTHESIS_PROFILE_ID,
        status=ArtifactTransformationStatus.SUCCESS,
        artifact_kind=ArtifactTransformationKind.SDL_AUTHORING,
        source_profile=value.schema_version,
        target_profile=SDL_CONTRACT_PROFILE,
        canonicalization_profile=canonical_digest.profile,
        source_digest=input_digest,
        target_digest=canonical_digest.value,
        policy_digest=value.policy_digest,
        derivation_digest=_derivation_digest(value, input_digest),
        preconditions=tuple(
            check(name, TransformationCheckOutcome.PASSED)
            for name in (
                "assertions-current",
                "decisions-complete",
                "source-admitted",
                "transformation-profile-supported",
            )
        ),
        postconditions=tuple(
            check(name, TransformationCheckOutcome.PASSED)
            for name in ("candidate-reparsed", "candidate-semantic-valid")
        ),
        affected_identities=tuple(decision.target_ref for decision in value.decisions),
        preservation=ArtifactTransformationPreservationModel(
            profile=SYNTHESIS_PRESERVATION_PROFILE,
            outcome=PreservationOutcome.VERIFIED,
            evidence_digests=tuple(sorted({input_digest, canonical_digest.value, exact_digest})),
            limitations=(
                "Synthesis admission does not establish source equivalence, instantiation, compilation, or execution.",
            ),
        ),
    )
    record = CandidateSynthesisRecordModel(
        record_id=f"{value.input_id}-record",
        input_id=value.input_id,
        input_digest=input_digest,
        disposition=CandidateSynthesisDisposition.SUCCESS,
        input=value,
        profile=SYNTHESIS_PROFILE,
        construct_traces=_construct_traces(value),
        candidate_exact_digest=exact_digest,
        candidate_canonical_digest=canonical_digest.value,
        transformation_report=report,
    )
    return SDLCandidateSynthesisResult(
        candidate_content=rendered.content,
        candidate=rendered.scenario,
        record=record,
    )


__all__ = [
    "SDLCandidateSynthesisResult",
    "SYNTHESIS_PROFILE",
    "SYNTHESIS_PROFILE_DIGEST",
    "SYNTHESIS_PROFILE_ID",
    "SYNTHESIS_PROFILE_VERSION",
    "synthesize_sdl_candidate",
]
