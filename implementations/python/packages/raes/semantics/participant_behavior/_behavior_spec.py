"""Behavior-specification reference, vocabulary, feature, and evidence-contract checks."""

from __future__ import annotations

from collections.abc import Callable

from ._types import (
    ParticipantBehaviorIssue,
    _BehaviorSpecificationReferenceContext,
)


def _behavior_mode_issue(*, spec_name: str, behavior_mode: object) -> ParticipantBehaviorIssue | None:
    if not behavior_mode:
        return None
    try:
        from raes_contracts.controlled_vocabularies import validate_controlled_vocabulary_scope_values

        validate_controlled_vocabulary_scope_values("behavior_specifications.behavior_mode", [str(behavior_mode)])
    except ValueError as exc:
        return ParticipantBehaviorIssue(
            code="participant.behavior-spec-mode-ungoverned",
            participant_name="",
            spec_name=spec_name,
            ref=str(behavior_mode),
            message=str(exc),
        )
    return None


def _backend_feature_support_issue(*, spec_name: str, feature_ref: object) -> ParticipantBehaviorIssue | None:
    try:
        from raes_contracts.controlled_vocabularies import validate_controlled_vocabulary_value

        validation_errors: list[str] = []
        for vocabulary_id in (
            "participant-runtime-behavior-features",
            "participant-runtime-interaction-features",
        ):
            try:
                validate_controlled_vocabulary_value(vocabulary_id, str(feature_ref))
                return None
            except ValueError as exc:
                validation_errors.append(str(exc))
    except ValueError as exc:
        validation_errors = [str(exc)]
    return ParticipantBehaviorIssue(
        code="participant.behavior-spec-feature-ungoverned",
        participant_name="",
        spec_name=spec_name,
        ref=str(feature_ref),
        message="; ".join(validation_errors),
    )


def _evidence_contract_issue(*, spec_name: str, evidence_contract_ref: object) -> ParticipantBehaviorIssue | None:
    from raes_contracts.manifest_authority import (
        BACKEND_SUPPORTED_CONTRACT_IDS,
        PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS,
        PROCESSOR_SUPPORTED_CONTRACT_IDS,
    )

    allowed_contract_ids = frozenset(
        [
            *BACKEND_SUPPORTED_CONTRACT_IDS,
            *PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS,
            *PROCESSOR_SUPPORTED_CONTRACT_IDS,
        ]
    )
    if str(evidence_contract_ref) in allowed_contract_ids:
        return None
    return ParticipantBehaviorIssue(
        code="participant.behavior-spec-evidence-contract-unbound",
        participant_name="",
        spec_name=spec_name,
        ref=str(evidence_contract_ref),
        message="evidence_contract_refs must reference published processor, backend, or participant contracts",
    )


def _behavior_specification_named_ref_issues(
    *,
    spec_name: str,
    refs: list[object],
    known_names: set[str],
    code: str,
    is_unresolved: Callable[[object], bool],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    for ref in refs:
        if is_unresolved(ref):
            continue
        if str(ref) not in known_names:
            issues.append(
                ParticipantBehaviorIssue(
                    code=code,
                    participant_name="",
                    spec_name=spec_name,
                    ref=str(ref),
                )
            )
    return issues


def _behavior_specification_reference_issues(
    *,
    spec_name: str,
    behavior_spec: object,
    reference_context: _BehaviorSpecificationReferenceContext,
    is_unresolved: Callable[[object], bool],
) -> list[ParticipantBehaviorIssue]:
    reference_sets = (
        (
            list(getattr(behavior_spec, "participant_refs", []) or []),
            reference_context.participant_names,
            "participant.behavior-spec-participant-unbound",
        ),
        (
            list(getattr(behavior_spec, "participant_role_refs", []) or []),
            reference_context.participant_roles,
            "participant.behavior-spec-role-unbound",
        ),
        (
            list(getattr(behavior_spec, "action_contract_refs", []) or []),
            reference_context.action_names,
            "participant.behavior-spec-action-unbound",
        ),
        (
            list(getattr(behavior_spec, "observation_boundary_refs", []) or []),
            reference_context.observation_boundary_names,
            "participant.behavior-spec-observation-boundary-unbound",
        ),
        (
            list(getattr(behavior_spec, "outcome_interpretation_rule_refs", []) or []),
            reference_context.outcome_rule_names,
            "participant.behavior-spec-outcome-rule-unbound",
        ),
    )
    issues: list[ParticipantBehaviorIssue] = []
    for refs, known_names, code in reference_sets:
        issues.extend(
            _behavior_specification_named_ref_issues(
                spec_name=spec_name,
                refs=refs,
                known_names=known_names,
                code=code,
                is_unresolved=is_unresolved,
            )
        )
    return issues


def _behavior_specification_feature_issues(
    *,
    spec_name: str,
    behavior_spec: object,
    is_unresolved: Callable[[object], bool],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    for feature_ref in getattr(behavior_spec, "backend_feature_support_refs", []) or []:
        if is_unresolved(feature_ref):
            continue
        feature_issue = _backend_feature_support_issue(spec_name=spec_name, feature_ref=feature_ref)
        if feature_issue is not None:
            issues.append(feature_issue)
    return issues


def _behavior_specification_evidence_contract_issues(
    *,
    spec_name: str,
    behavior_spec: object,
    is_unresolved: Callable[[object], bool],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    for evidence_contract_ref in getattr(behavior_spec, "evidence_contract_refs", []) or []:
        if is_unresolved(evidence_contract_ref):
            continue
        evidence_issue = _evidence_contract_issue(
            spec_name=spec_name,
            evidence_contract_ref=evidence_contract_ref,
        )
        if evidence_issue is not None:
            issues.append(evidence_issue)
    return issues


def _behavior_specification_vocabulary_issues(
    *,
    spec_name: str,
    behavior_spec: object,
    is_unresolved: Callable[[object], bool],
) -> list[ParticipantBehaviorIssue]:
    issues: list[ParticipantBehaviorIssue] = []
    mode_issue = _behavior_mode_issue(
        spec_name=spec_name,
        behavior_mode=getattr(behavior_spec, "behavior_mode", None),
    )
    if mode_issue is not None:
        issues.append(mode_issue)
    issues.extend(
        _behavior_specification_feature_issues(
            spec_name=spec_name,
            behavior_spec=behavior_spec,
            is_unresolved=is_unresolved,
        )
    )
    issues.extend(
        _behavior_specification_evidence_contract_issues(
            spec_name=spec_name,
            behavior_spec=behavior_spec,
            is_unresolved=is_unresolved,
        )
    )
    return issues
