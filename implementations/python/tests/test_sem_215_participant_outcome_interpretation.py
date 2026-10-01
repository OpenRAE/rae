"""SEM-215 participant outcome interpretation semantics."""

from __future__ import annotations

import textwrap

import pytest
from raes._errors import SDLParseError, SDLValidationError
from raes.parser import parse_sdl
from raes.participant_behavior import (
    ParticipantEffectClass,
    ParticipantFailureClass,
    ParticipantPreconditionClass,
)
from raes.participant_outcome_semantics import (
    OutcomeInterpretationSourceLayer,
    OutcomeInterpretationTargetLayer,
)
from raes_contracts.contracts import ParticipantBehaviorHistoryEventModel
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    ParticipantActionEffectResult,
    ParticipantActionPreconditionResult,
    ParticipantActionPreconditionStatus,
    ParticipantActionResult,
    ParticipantActionResultStatus,
    ParticipantBehaviorHistoryEvent,
    ParticipantBehaviorHistoryEventType,
    ParticipantObservationStatus,
    ParticipantOutcomeInterpretationRecord,
    ParticipantOutcomeSourceRecord,
    ParticipantOutcomeTargetRecord,
    iter_participant_behavior_history_violations,
)

T0 = "2026-05-21T09:00:00Z"
PARTICIPANT_ADDRESS = "participant.behavior.red-agent"
OTHER_PARTICIPANT_ADDRESS = "participant.behavior.blue-agent"
ACTION_ADDRESS = "participant.action-contract.scan"
RULE_ADDRESS = "participant.outcome-interpretation-rule.scan-evidence-objective"
OBSERVATION_ADDRESS = "participant.observation-boundary.red-view"
ACTION_INSTANCE = "scan-0001"
EPISODE_ID = "episode-1"
OBSERVATION_POINT = "episode-step:scan-0001:terminal-observation"


def _scenario_yaml() -> str:
    return textwrap.dedent(
        """
        name: sem-215
        nodes:
          web:
            type: compute
            resources: {ram: 1 GiB, cpu: 1}
            services: [{port: 80, name: http}]
        entities:
          red-team:
            role: red
        conditions:
          exfil-detected:
            proposition: exfil-detected
            command: "test -f /tmp/alert"
            interval: 10
        evidence_requirements:
          exfil-detection-evidence:
            description: Capture evidence used to decide the exfiltration detection proposition.
            source_class: participant_action
            scope_refs: [nodes.web.services.http]
            boundary_kind: assertion_evaluation
            channel: log
            artifact_role: proposition_truth_evidence
            sensitivity: plain
            redaction: redact_secrets
            integrity: checksum
            retention: study_lifetime
            loss_disclosure: required
        propositions:
          exfil-detected:
            description: Exfiltration was detected for the governed web service.
            subjects: [nodes.web.services.http]
            basis: observed_state
            predicate: {kind: boolean, property: exfil-detected, semantic_ref: urn:raes:observable:exfil-detected, operator: equals, expected: true}
            evidence_requirements: [exfil-detection-evidence]
        assertions:
          exfil-detected: {proposition: exfil-detected, role: postcondition, polarity: positive}
        objectives:
          exfil-objective:
            assigned_participant: red-agent
            actions: [scan]
            targets: [nodes.web.services.http]
            success:
              assertions: [exfil-detected]
        workflows:
          response-flow:
            start: verify
            steps:
              verify:
                type: objective
                objective: exfil-objective
                on_success: done
                on_failure: done
              done:
                type: end
        action_contracts:
          scan:
            semantic_version: 1.0.0
            lifecycle_state: active
            behavioral_granularity: atomic
            procedure_basis: nmap service discovery
            realization_profile: backend-declared
            fidelity_claim: records participant discovery intent and terminal observation
            preconditions:
              - precondition_id: authority-in-scope
                precondition_class: authority
                description: red participant is authorized to scan the web service
                support_refs: [agents.red-agent]
            effects:
              - effect_id: scan-evidence
                effect_class: evidence_effect
                description: scan emits evidence even when the action fails
                evidence_refs: [evidence.scan-output, evidence.alert]
              - effect_id: detection-alert
                effect_class: detection_effect
                description: scan may trigger a backend detection alert
                target_refs: [alerts.ids.scan]
                evidence_refs: [evidence.alert]
            failure_classes: [precondition_unsatisfied, timeout, backend_error, unknown]
        observation_boundaries:
          red-view:
            projection_basis: participant-local projection over observed services
            observable_refs: [nodes.web.services.http]
            hidden_refs: [content.private-answer-key]
            evidence_refs: [evidence.scan-output, evidence.alert]
            redaction_policy: hidden refs never project without explicit disclosure
            latency_profile: terminal observation emitted after state transition commit
            view_rules:
              - information_ref: nodes.web.services.http
                boundary_class: observable_resource
                disposition: observable
                visibility_basis: service is visible to the red participant
              - information_ref: content.private-answer-key
                boundary_class: private_answer_key
                disposition: hidden
                visibility_basis: adjudication-only hidden truth
              - information_ref: evidence.alert
                boundary_class: archival_evidence
                disposition: evidence_only
                visibility_basis: archival alert evidence reference
                evidence_refs: [evidence.alert]
        agents:
          red-agent:
            affiliations: [red-team]
            actions: [scan]
            observation_boundaries: [red-view]
        outcome_interpretation_rules:
          scan-evidence-objective:
            semantic_version: 1.0.0
            participant_scope: participant_local
            observation_point_basis: terminal participant observation event
            interpretation_basis: explicit SEM-215 mapping from local scan evidence to objective/evaluation meaning
            evidence_refs: [evidence.alert]
            limitations:
              - local scan result is not objective success by itself
              - reward remains a derived assessment signal
            source_bindings:
              - source_id: local-action
                source_layer: participant_action_outcome
                ref: scan
                interpretation_role: local action status input
                evidence_refs: [evidence.scan-output]
              - source_id: alert-evidence
                source_layer: evidence_claim
                ref: evidence.alert
                interpretation_role: alert evidence input
                evidence_refs: [evidence.alert]
              - source_id: scaffold
                source_layer: scaffold_variant
                ref: scaffold.standard
                interpretation_role: benchmark context input
                provenance_refs: [provenance.scaffold.standard]
            target_bindings:
              - target_id: objective-meaning
                target_layer: objective_result
                ref: exfil-objective
                relation: evidence supports objective interpretation
                evidence_refs: [evidence.alert]
                limitations: [objective success still requires evaluator confirmation]
              - target_id: evaluation-meaning
                target_layer: evaluation_result
                ref: exfil-eval
                relation: evidence is an input to evaluation meaning
                evidence_refs: [evidence.alert]
                limitations: [evaluation result is not inferred from action status]
              - target_id: workflow-meaning
                target_layer: workflow_result
                ref: response-flow
                relation: evidence may inform workflow result interpretation
                evidence_refs: [evidence.alert]
                limitations: [workflow completion is evaluated separately]
              - target_id: reward-meaning
                target_layer: reward_signal
                ref: reward.scan-learning
                relation: reward relevant only under governed assessment rule
                governance_ref: assessment.reward.scan-learning
                evidence_refs: [evidence.alert]
                limitations: [reward is derived, not the participant outcome]
        """
    )


def _preconditions() -> tuple[ParticipantActionPreconditionResult, ...]:
    return (
        ParticipantActionPreconditionResult(
            precondition_id="authority-in-scope",
            precondition_class=ParticipantPreconditionClass.AUTHORITY,
            status=ParticipantActionPreconditionStatus.SATISFIED,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id=EPISODE_ID,
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:attempt",
            support_refs=("agents.red-agent",),
        ),
    )


def _effects() -> tuple[ParticipantActionEffectResult, ...]:
    return (
        ParticipantActionEffectResult(
            effect_id="scan-evidence",
            effect_class=ParticipantEffectClass.EVIDENCE_EFFECT,
            description="scan emitted evidence",
            evidence_refs=("evidence.scan-output", "evidence.alert"),
        ),
        ParticipantActionEffectResult(
            effect_id="detection-alert",
            effect_class=ParticipantEffectClass.DETECTION_EFFECT,
            description="scan triggered a backend detection alert",
            target_refs=("alerts.ids.scan",),
            evidence_refs=("evidence.alert",),
        ),
    )


def _action_result(status: ParticipantActionResultStatus) -> ParticipantActionResult:
    return ParticipantActionResult(
        status=status,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EPISODE_ID,
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point=OBSERVATION_POINT,
        preconditions=_preconditions(),
        effects=_effects(),
        failure_class=(
            ParticipantFailureClass.BACKEND_ERROR
            if status in {ParticipantActionResultStatus.FAILED, ParticipantActionResultStatus.UNKNOWN}
            else None
        ),
        observations=("alerts.ids.scan",),
        evidence_refs=("evidence.scan-output", "evidence.alert"),
    )


def _outcome_record(
    *,
    participant_address: str = PARTICIPANT_ADDRESS,
    evidence_refs: tuple[str, ...] = ("evidence.alert",),
) -> ParticipantOutcomeInterpretationRecord:
    return ParticipantOutcomeInterpretationRecord(
        interpretation_id="interpretation.scan-0001",
        rule_address=RULE_ADDRESS,
        participant_address=participant_address,
        episode_id=EPISODE_ID,
        observation_point=OBSERVATION_POINT,
        source_bindings=(
            ParticipantOutcomeSourceRecord(
                source_id="local-action",
                source_layer=OutcomeInterpretationSourceLayer.PARTICIPANT_ACTION_OUTCOME,
                ref=ACTION_ADDRESS,
                observed_value="failed",
                evidence_refs=("evidence.scan-output",),
            ),
            ParticipantOutcomeSourceRecord(
                source_id="alert-evidence",
                source_layer=OutcomeInterpretationSourceLayer.EVIDENCE_CLAIM,
                ref="evidence.alert",
                observed_value="present",
                evidence_refs=("evidence.alert",),
            ),
            ParticipantOutcomeSourceRecord(
                source_id="scaffold",
                source_layer=OutcomeInterpretationSourceLayer.SCAFFOLD_VARIANT,
                ref="scaffold.standard",
                observed_value="active",
                provenance_refs=("provenance.scaffold.standard",),
            ),
        ),
        target_bindings=(
            ParticipantOutcomeTargetRecord(
                target_id="objective-meaning",
                target_layer=OutcomeInterpretationTargetLayer.OBJECTIVE_RESULT,
                ref="evaluation.objective.exfil-objective",
                interpreted_value="evidence_supported",
                evidence_refs=("evidence.alert",),
                limitations=("objective success still requires evaluator confirmation",),
            ),
        ),
        evidence_refs=evidence_refs,
        limitations=("local action failure still emitted evidence",),
    )


def _history_payloads(
    *,
    status: ParticipantActionResultStatus,
    outcome_record: ParticipantOutcomeInterpretationRecord | None = None,
) -> list[dict[str, object]]:
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EPISODE_ID,
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=_action_result(status),
        outcome_interpretations=((outcome_record or _outcome_record()),),
        details={"evidence_refs": ["evidence.alert"], "visible_refs": ["nodes.web.services.http"]},
    )
    return [
        {
            "event_type": "action_attempted",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": EPISODE_ID,
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "actor_provenance": "participant:red-agent",
            "details": {},
        },
        {
            "event_type": "state_transition_recorded",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": EPISODE_ID,
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "state_transition_kind": "participant_scan_realized",
            "post_state_digest": "sha256:scan",
            "details": {},
        },
        observation.to_payload(),
    ]


def _episode_status_scenario_yaml() -> str:
    return _scenario_yaml().replace(
        "      - source_id: scaffold\n"
        "        source_layer: scaffold_variant\n"
        "        ref: scaffold.standard\n"
        "        interpretation_role: benchmark context input\n"
        "        provenance_refs: [provenance.scaffold.standard]",
        "      - source_id: episode-terminal\n"
        "        source_layer: participant_episode_status\n"
        "        ref: episode.terminal\n"
        "        interpretation_role: participant episode terminal status input\n"
        "        provenance_refs: [runtime.participant-episode-history.episode-1]",
        1,
    )


def _replace_scaffold_source_with_episode_status(
    payloads: list[dict[str, object]],
    *,
    observed_value: str = "completed",
) -> None:
    payloads[2]["outcome_interpretations"][0]["source_bindings"][2].update(
        {
            "source_id": "episode-terminal",
            "source_layer": "participant_episode_status",
            "ref": "episode.terminal",
            "observed_value": observed_value,
            "provenance_refs": ["runtime.participant-episode-history.episode-1"],
        }
    )


def _episode_history_payloads(
    *,
    event_type: str = "episode_completed",
    terminal_reason: str = "completed",
) -> list[dict[str, object]]:
    return [
        {
            "event_type": "episode_initialized",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": EPISODE_ID,
            "sequence_number": 0,
            "control_action": "initialize",
            "details": {},
        },
        {
            "event_type": event_type,
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": EPISODE_ID,
            "sequence_number": 0,
            "terminal_reason": terminal_reason,
            "details": {},
        },
    ]


def test_outcome_interpretation_rule_parses_and_compiles_explicit_layers() -> None:
    scenario = parse_sdl(_scenario_yaml())

    rule = scenario.outcome_interpretation_rules["scan-evidence-objective"]
    assert [source.source_layer for source in rule.source_bindings] == [
        OutcomeInterpretationSourceLayer.PARTICIPANT_ACTION_OUTCOME,
        OutcomeInterpretationSourceLayer.EVIDENCE_CLAIM,
        OutcomeInterpretationSourceLayer.SCAFFOLD_VARIANT,
    ]
    assert [target.target_layer for target in rule.target_bindings] == [
        OutcomeInterpretationTargetLayer.OBJECTIVE_RESULT,
        OutcomeInterpretationTargetLayer.EVALUATION_RESULT,
        OutcomeInterpretationTargetLayer.WORKFLOW_RESULT,
        OutcomeInterpretationTargetLayer.REWARD_SIGNAL,
    ]

    model = compile_runtime_model(scenario)
    compiled = model.outcome_interpretation_rules[RULE_ADDRESS]

    assert compiled.source_refs == (
        ACTION_ADDRESS,
        "evidence.alert",
        "scaffold.standard",
    )
    assert compiled.target_refs == (
        "evaluation.objective.exfil-objective",
        "evaluation.evaluation.exfil-eval",
        "orchestration.workflow.response-flow",
        "reward.scan-learning",
    )
    assert compiled.target_layers == (
        "objective_result",
        "evaluation_result",
        "workflow_result",
        "reward_signal",
    )


def test_local_action_success_does_not_imply_objective_success_without_rule_record() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    observation_without_interpretation = _history_payloads(status=ParticipantActionResultStatus.SUCCEEDED)
    observation_without_interpretation[2]["outcome_interpretations"] = []

    violations = list(
        iter_participant_behavior_history_violations(
            observation_without_interpretation,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == []


def test_failed_local_action_can_emit_evidence_interpretation_under_explicit_rule() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))

    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads(status=ParticipantActionResultStatus.FAILED),
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == []


def test_outcome_interpretation_record_round_trips_on_participant_observation() -> None:
    record = _outcome_record()
    event = ParticipantBehaviorHistoryEvent.from_payload(
        _history_payloads(status=ParticipantActionResultStatus.FAILED, outcome_record=record)[2]
    )

    payload = event.to_payload()

    assert payload["outcome_interpretations"][0]["rule_address"] == RULE_ADDRESS
    assert ParticipantBehaviorHistoryEvent.from_payload(payload) == event


def test_outcome_interpretation_scope_must_match_observation_event() -> None:
    with pytest.raises(ValueError, match="outcome interpretation participant_address must match event"):
        ParticipantBehaviorHistoryEvent(
            event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
            timestamp=T0,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id=EPISODE_ID,
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            observation_boundary_address=OBSERVATION_ADDRESS,
            observation_status=ParticipantObservationStatus.TERMINAL,
            post_state_digest="sha256:scan",
            action_result=_action_result(ParticipantActionResultStatus.FAILED),
            outcome_interpretations=(_outcome_record(participant_address=OTHER_PARTICIPANT_ADDRESS),),
        )


def test_outcome_interpretation_evidence_refs_must_be_authorized_by_participant_boundary() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    hidden_record = _outcome_record(evidence_refs=("content.private-answer-key",))

    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads(status=ParticipantActionResultStatus.FAILED, outcome_record=hidden_record),
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert any(
        "outcome interpretation 'interpretation.scan-0001' evidence_ref 'content.private-answer-key'" in message
        for _, message in violations
    )


def test_outcome_interpretation_targets_require_declared_rule_and_binding() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    payloads[2]["outcome_interpretations"][0]["target_bindings"][0]["target_id"] = "undeclared-target"

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' target 'undeclared-target' is not declared by participant.outcome-interpretation-rule.scan-evidence-objective",
        )
    ]


def test_outcome_interpretation_records_must_match_declared_binding_refs() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    payloads[2]["outcome_interpretations"][0]["source_bindings"][0]["ref"] = "participant.action-contract.other"
    payloads[2]["outcome_interpretations"][0]["target_bindings"][0]["ref"] = "evaluation.objective.other"

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' source 'local-action' ref 'participant.action-contract.other' does not match action_result action_contract_address 'participant.action-contract.scan'",
        ),
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' source 'local-action' ref 'participant.action-contract.other' does not match declared ref 'participant.action-contract.scan'",
        ),
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' target 'objective-meaning' ref 'evaluation.objective.other' does not match declared ref 'evaluation.objective.exfil-objective'",
        ),
    ]


def test_outcome_interpretation_validation_is_independent_of_action_status() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.SUCCEEDED)
    payloads[2]["outcome_interpretations"][0]["source_bindings"][0]["observed_value"] = "succeeded"
    payloads[2]["outcome_interpretations"][0]["target_bindings"][0]["target_id"] = "undeclared-target"

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' target 'undeclared-target' is not declared by participant.outcome-interpretation-rule.scan-evidence-objective",
        )
    ]


def test_participant_action_outcome_source_must_match_event_action_status() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    payloads[2]["outcome_interpretations"][0]["source_bindings"][0]["observed_value"] = "succeeded"

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' source 'local-action' observed_value 'succeeded' does not match action_result status 'failed'",
        )
    ]


def test_outcome_evidence_refs_must_be_grounded_in_event_payload() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    payloads[2]["details"] = {"visible_refs": ["nodes.web.services.http"]}
    payloads[2]["action_result"]["evidence_refs"] = ["evidence.scan-output"]
    payloads[2]["action_result"]["effects"][0]["evidence_refs"] = ["evidence.scan-output"]
    payloads[2]["action_result"]["effects"][1]["evidence_refs"] = []

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' evidence_ref 'evidence.alert' is not grounded in event evidence",
        ),
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' evidence_claim source 'alert-evidence' ref 'evidence.alert' is not grounded in event evidence",
        ),
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' source 'alert-evidence' evidence_ref 'evidence.alert' is not grounded in event evidence",
        ),
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' target 'objective-meaning' evidence_ref 'evidence.alert' is not grounded in event evidence",
        ),
    ]


def test_reward_interpretation_requires_governed_assessment_rule() -> None:
    missing_governance = _scenario_yaml().replace(
        "        governance_ref: assessment.reward.scan-learning\n",
        "",
        1,
    )

    with pytest.raises(SDLParseError, match="reward_signal targets require governance_ref"):
        parse_sdl(missing_governance)


def test_outcome_interpretation_scope_is_participant_local_only() -> None:
    global_scope = _scenario_yaml().replace(
        "    participant_scope: participant_local\n",
        "    participant_scope: cohort_global\n",
        1,
    )

    with pytest.raises(SDLParseError, match="participant_scope must be one of: participant_local"):
        parse_sdl(global_scope)


def test_reward_interpretation_records_must_match_declared_governance_ref() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    target_binding = payloads[2]["outcome_interpretations"][0]["target_bindings"][0]
    target_binding.update(
        {
            "target_id": "reward-meaning",
            "target_layer": "reward_signal",
            "ref": "reward.scan-learning",
            "interpreted_value": "candidate_reward_signal",
            "governance_ref": "assessment.reward.unapproved",
            "limitations": ["reward is derived", "not the participant outcome"],
        }
    )

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' target 'reward-meaning' governance_ref 'assessment.reward.unapproved' does not match declared governance_ref 'assessment.reward.scan-learning'",
        )
    ]


def test_benchmark_outcome_inputs_require_explicit_provenance() -> None:
    missing_provenance = _scenario_yaml().replace(
        "        provenance_refs: [provenance.scaffold.standard]\n",
        "",
        1,
    )

    with pytest.raises(SDLParseError, match="scaffold_variant source bindings require provenance_refs"):
        parse_sdl(missing_provenance)


def test_episode_status_outcome_inputs_require_explicit_provenance() -> None:
    missing_provenance = _scenario_yaml().replace(
        "      - source_id: scaffold\n"
        "        source_layer: scaffold_variant\n"
        "        ref: scaffold.standard\n"
        "        interpretation_role: benchmark context input\n"
        "        provenance_refs: [provenance.scaffold.standard]",
        "      - source_id: episode-terminal\n"
        "        source_layer: participant_episode_status\n"
        "        ref: episode.terminal\n"
        "        interpretation_role: participant episode terminal status input",
        1,
    )

    with pytest.raises(SDLParseError, match="participant_episode_status source bindings require provenance_refs"):
        parse_sdl(missing_provenance)


def test_episode_status_outcome_sources_must_be_grounded_in_episode_history() -> None:
    model = compile_runtime_model(parse_sdl(_episode_status_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    _replace_scaffold_source_with_episode_status(payloads)

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
            participant_episode_history=[],
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' source 'episode-terminal' participant_episode_status is not grounded by a terminal participant_episode_history event",
        )
    ]


def test_episode_status_outcome_source_must_match_episode_history_terminal_status() -> None:
    model = compile_runtime_model(parse_sdl(_episode_status_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    _replace_scaffold_source_with_episode_status(payloads, observed_value="completed")

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
            participant_episode_history=_episode_history_payloads(
                event_type="episode_interrupted",
                terminal_reason="interrupted",
            ),
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' source 'episode-terminal' observed_value 'completed' does not match participant_episode_history terminal status 'interrupted'",
        )
    ]


def test_episode_status_outcome_source_accepts_matching_terminal_episode_history() -> None:
    model = compile_runtime_model(parse_sdl(_episode_status_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    _replace_scaffold_source_with_episode_status(payloads, observed_value="completed")

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
            participant_episode_history=_episode_history_payloads(),
        )
    )

    assert violations == []


def test_provenance_required_outcome_sources_must_be_reported_at_runtime() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    payloads[2]["outcome_interpretations"][0]["source_bindings"] = payloads[2]["outcome_interpretations"][0][
        "source_bindings"
    ][:2]

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' source 'scaffold' with provenance-required layer 'scaffold_variant' is not reported",
        )
    ]


def test_declared_outcome_source_provenance_must_be_preserved_at_runtime() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    payloads[2]["outcome_interpretations"][0]["source_bindings"][2]["provenance_refs"] = []

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' source 'scaffold' omits declared provenance_ref 'provenance.scaffold.standard'",
        )
    ]


def test_outcome_source_provenance_cannot_expose_hidden_boundary_refs() -> None:
    hidden_provenance_yaml = _scenario_yaml().replace(
        "        provenance_refs: [provenance.scaffold.standard]\n",
        "        provenance_refs: [content.private-answer-key]\n",
        1,
    )
    model = compile_runtime_model(parse_sdl(hidden_provenance_yaml))
    payloads = _history_payloads(status=ParticipantActionResultStatus.FAILED)
    payloads[2]["outcome_interpretations"][0]["source_bindings"][2]["provenance_refs"] = ["content.private-answer-key"]

    violations = list(
        iter_participant_behavior_history_violations(
            payloads,
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
            outcome_interpretation_rules=model.outcome_interpretation_rules,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "outcome interpretation 'interpretation.scan-0001' provenance_ref 'content.private-answer-key' exposes a hidden participant-boundary ref at effective_order -1: disposition 'hidden'",
        ),
    ]


def test_outcome_interpretation_rule_refs_fail_closed() -> None:
    missing_objective = _scenario_yaml().replace(
        "        ref: exfil-objective\n", "        ref: missing-objective\n", 1
    )

    with pytest.raises(SDLValidationError, match="target 'missing-objective' references undefined objective"):
        parse_sdl(missing_objective)


def test_contract_schema_publishes_outcome_interpretation_payload() -> None:
    schema = ParticipantBehaviorHistoryEventModel.model_json_schema()

    assert "outcome_interpretations" in schema["properties"]
    interpretation_ref = schema["properties"]["outcome_interpretations"]["items"]["$ref"]
    assert interpretation_ref.endswith("/ParticipantOutcomeInterpretationRecordModel")
