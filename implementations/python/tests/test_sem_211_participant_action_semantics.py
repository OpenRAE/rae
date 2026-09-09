"""SEM-211 participant action precondition/effect/failure semantics."""

from __future__ import annotations

import textwrap

import pytest
from raes._errors import SDLParseError
from raes.parser import parse_sdl
from raes.participant_behavior import (
    ParticipantEffectClass,
    ParticipantFailureClass,
    ParticipantPreconditionClass,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    Diagnostic,
    ParticipantActionEffectResult,
    ParticipantActionPreconditionResult,
    ParticipantActionPreconditionStatus,
    ParticipantActionResult,
    ParticipantActionResultStatus,
    ParticipantBehaviorHistoryEvent,
    ParticipantBehaviorHistoryEventType,
    ParticipantHistoryAddressScope,
    ParticipantObservationStatus,
    RuntimeSnapshot,
    iter_participant_behavior_history_violations,
    map_backend_diagnostic_to_participant_failure,
)
from raes_runtime.control_plane_store import LocalControlPlaneStore

T0 = "2026-05-19T20:00:00Z"
PARTICIPANT_ADDRESS = "participant.behavior.red-agent"
ACTION_ADDRESS = "participant.action-contract.scan"
OBSERVATION_ADDRESS = "participant.observation-boundary.red-view"
ACTION_INSTANCE = "scan-0001"


def _scenario_yaml() -> str:
    return textwrap.dedent(
        """
        name: sem-211
        nodes:
          web:
            type: compute
            resources: {ram: 1 GiB, cpu: 1}
            services: [{port: 80, name: http}]
        entities:
          red-team:
            role: red
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
                support_refs: [agents.red-agent, nodes.web.services.http]
              - precondition_id: target-service-present
                precondition_class: target
                description: target service exists in the participant action scope
                support_refs: [nodes.web.services.http]
              - precondition_id: backend-can-realize-scan
                precondition_class: realization
                description: backend can realize the scan action contract
                support_refs: [backend.participant-runtime]
            effects:
              - effect_id: discover-http-service
                effect_class: intended_effect
                description: participant may discover the web HTTP service
                target_refs: [nodes.web.services.http]
              - effect_id: scan-shared-knowledge-update
                effect_class: side_effect
                description: participant-local service knowledge is updated
                target_refs: [nodes.web.services.http]
              - effect_id: terminal-scan-observation
                effect_class: observation_effect
                description: terminal scan observation is emitted for the participant
                evidence_refs: [evidence.scan-output]
              - effect_id: participant-view-discovers-service
                effect_class: visibility_effect
                description: participant view marks the web node discovered
                target_refs: [nodes.web]
              - effect_id: scan-evidence
                effect_class: evidence_effect
                description: scan tool output is retained as run evidence
                evidence_refs: [evidence.scan-output]
              - effect_id: no-hidden-truth-change
                effect_class: no_effect
                description: scan does not expose hidden adjudication material
            state_transition_effects: [participant knowledge expands]
            failure_classes:
              - precondition_unsatisfied
              - unsupported_action
              - target_unavailable
              - timeout
              - backend_error
              - unknown
            backend_failure_mappings:
              - backend_error_code: backend.timeout
                failure_class: timeout
                diagnostic: backend reported action timeout
              - backend_error_code: backend.not-supported
                failure_class: unsupported_action
                diagnostic: backend lacks the scan action implementation
            interactions:
              - interaction_class: shared_state_change
                target: nodes.web.services.http
                rationale: scan reads and updates participant-visible service knowledge
                shared_state_refs: [nodes.web.services.http]
        observation_boundaries:
          red-view:
            projection_basis: participant-local projection over observed services
            observable_refs: []
            hidden_refs: [nodes.web]
            evidence_refs: [evidence.scan-output]
            redaction_policy: hidden refs never project without explicit disclosure
            latency_profile: terminal observation emitted after state transition commit
            view_rules:
              - information_ref: nodes.web
                boundary_class: observable_resource
                disposition: hidden
                visibility_basis: service is not known before terminal scan output
              - information_ref: evidence.scan-output
                boundary_class: archival_evidence
                disposition: evidence_only
                visibility_basis: archival run evidence reference
                evidence_refs: [evidence.scan-output]
            view_transitions:
              - transition_id: discover-web-service
                transition_kind: discovery
                information_ref: nodes.web
                trigger: scan terminal observation
                effective_from: episode-step:scan-0001:terminal-observation
                effective_order: 30
                history_event_type: observation_emitted
                action_instance_id: scan-0001
                from_disposition: hidden
                to_disposition: discovered
                evidence_refs: [evidence.scan-output]
                certainty: high
                latency_profile: terminal observation latency
        agents:
          red-agent:
            entity: red-team
            actions: [scan]
            observation_boundaries: [red-view]
        """
    )


def _satisfied_preconditions(
    *,
    participant_address: str = PARTICIPANT_ADDRESS,
) -> tuple[ParticipantActionPreconditionResult, ...]:
    return (
        ParticipantActionPreconditionResult(
            precondition_id="authority-in-scope",
            precondition_class=ParticipantPreconditionClass.AUTHORITY,
            status=ParticipantActionPreconditionStatus.SATISFIED,
            participant_address=participant_address,
            episode_id="episode-1",
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:attempt",
            support_refs=("agents.red-agent",),
        ),
        ParticipantActionPreconditionResult(
            precondition_id="target-service-present",
            precondition_class=ParticipantPreconditionClass.TARGET,
            status=ParticipantActionPreconditionStatus.SATISFIED,
            participant_address=participant_address,
            episode_id="episode-1",
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:attempt",
            support_refs=("nodes.web.services.http",),
        ),
        ParticipantActionPreconditionResult(
            precondition_id="backend-can-realize-scan",
            precondition_class=ParticipantPreconditionClass.REALIZATION,
            status=ParticipantActionPreconditionStatus.SATISFIED,
            participant_address=participant_address,
            episode_id="episode-1",
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:attempt",
            support_refs=("backend.participant-runtime",),
        ),
    )


def _declared_effects() -> tuple[ParticipantActionEffectResult, ...]:
    return (
        ParticipantActionEffectResult(
            effect_id="discover-http-service",
            effect_class=ParticipantEffectClass.INTENDED_EFFECT,
            description="participant discovered the web HTTP service",
            target_refs=("nodes.web.services.http",),
        ),
        ParticipantActionEffectResult(
            effect_id="terminal-scan-observation",
            effect_class=ParticipantEffectClass.OBSERVATION_EFFECT,
            description="terminal scan observation emitted",
            evidence_refs=("evidence.scan-output",),
        ),
    )


def _history_payloads_for_action_result(result: ParticipantActionResult) -> list[dict[str, object]]:
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=result,
    )
    return [
        {
            "event_type": "action_attempted",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": "episode-1",
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "actor_provenance": "participant:red-agent",
            "details": {},
        },
        {
            "event_type": "state_transition_recorded",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": "episode-1",
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "state_transition_kind": "participant_knowledge_expanded",
            "post_state_digest": "sha256:scan",
            "details": {},
        },
        observation.to_payload(),
    ]


def _scenario_with_hidden_action_result_ref() -> str:
    scenario = _scenario_yaml().replace(
        "hidden_refs: [nodes.web]",
        "hidden_refs: [nodes.web, content.private-answer-key]",
    )
    return scenario.replace(
        "              - information_ref: evidence.scan-output\n"
        "                boundary_class: archival_evidence\n"
        "                disposition: evidence_only\n"
        "                visibility_basis: archival run evidence reference\n"
        "                evidence_refs: [evidence.scan-output]",
        "              - information_ref: content.private-answer-key\n"
        "                boundary_class: private_answer_key\n"
        "                disposition: hidden\n"
        "                visibility_basis: adjudication-only hidden truth\n"
        "              - information_ref: evidence.scan-output\n"
        "                boundary_class: archival_evidence\n"
        "                disposition: evidence_only\n"
        "                visibility_basis: archival run evidence reference\n"
        "                evidence_refs: [evidence.scan-output]",
    )


def test_action_contract_declares_sem_211_classes_and_compiles_them():
    scenario = parse_sdl(_scenario_yaml())

    contract = scenario.action_contracts["scan"]
    assert [item.precondition_class.value for item in contract.preconditions] == [
        "authority",
        "target",
        "realization",
    ]
    assert [item.effect_class.value for item in contract.effects] == [
        "intended_effect",
        "side_effect",
        "observation_effect",
        "visibility_effect",
        "evidence_effect",
        "no_effect",
    ]
    assert [item.value for item in contract.failure_classes] == [
        "precondition_unsatisfied",
        "unsupported_action",
        "target_unavailable",
        "timeout",
        "backend_error",
        "unknown",
    ]

    model = compile_runtime_model(scenario)
    compiled = model.action_contracts[ACTION_ADDRESS]
    assert compiled.precondition_classes == ("authority", "target", "realization")
    assert compiled.effect_classes == (
        "intended_effect",
        "side_effect",
        "observation_effect",
        "visibility_effect",
        "evidence_effect",
        "no_effect",
    )
    assert compiled.failure_classes == (
        "precondition_unsatisfied",
        "unsupported_action",
        "target_unavailable",
        "timeout",
        "backend_error",
        "unknown",
    )
    assert compiled.backend_failure_mappings == (
        {
            "backend_error_code": "backend.timeout",
            "failure_class": "timeout",
            "diagnostic": "backend reported action timeout",
        },
        {
            "backend_error_code": "backend.not-supported",
            "failure_class": "unsupported_action",
            "diagnostic": "backend lacks the scan action implementation",
        },
    )


def test_legacy_string_preconditions_are_not_sem_211_contracts():
    scenario = _scenario_yaml().replace("precondition_class: authority", "precondition_class: legacy_string")

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(scenario)

    assert "preconditions" in str(excinfo.value)


def test_action_result_rejects_success_when_preconditions_are_unresolved():
    unresolved = ParticipantActionPreconditionResult(
        precondition_id="backend-can-realize-scan",
        precondition_class=ParticipantPreconditionClass.REALIZATION,
        status=ParticipantActionPreconditionStatus.UNRESOLVED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:attempt",
        diagnostics=("backend runtime did not declare realization support",),
    )

    with pytest.raises(ValueError, match="unsatisfied or unresolved preconditions fail closed"):
        ParticipantActionResult(
            status=ParticipantActionResultStatus.SUCCEEDED,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:terminal-observation",
            preconditions=(unresolved,),
            effects=_declared_effects(),
        )


def test_successful_action_result_requires_declared_effects():
    with pytest.raises(ValueError, match="succeeded action results require declared effects"):
        ParticipantActionResult(
            status=ParticipantActionResultStatus.SUCCEEDED,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:terminal-observation",
            preconditions=_satisfied_preconditions(),
            effects=(),
        )


def test_partial_success_action_result_requires_declared_effects():
    with pytest.raises(ValueError, match="partial_success action results require declared effects"):
        ParticipantActionResult(
            status=ParticipantActionResultStatus.PARTIAL_SUCCESS,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:terminal-observation",
            preconditions=_satisfied_preconditions(),
            effects=(),
            failure_class=ParticipantFailureClass.PARTIAL_SUCCESS,
        )


def test_side_effect_results_require_target_or_evidence_refs():
    with pytest.raises(ValueError, match="side_effect effects require target_refs or evidence_refs"):
        ParticipantActionEffectResult(
            effect_id="scan-shared-knowledge-update",
            effect_class=ParticipantEffectClass.SIDE_EFFECT,
            description="participant-local service knowledge is updated",
        )


def test_rejected_action_result_round_trips_with_portable_failure_class():
    unresolved = ParticipantActionPreconditionResult(
        precondition_id="backend-can-realize-scan",
        precondition_class=ParticipantPreconditionClass.REALIZATION,
        status=ParticipantActionPreconditionStatus.UNRESOLVED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:attempt",
        diagnostics=("backend runtime did not declare realization support",),
    )
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.REJECTED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:attempt",
        preconditions=(unresolved,),
        effects=(),
        failure_class=ParticipantFailureClass.PRECONDITION_UNSATISFIED,
        diagnostics=("action withheld because realization support is unresolved",),
    )

    assert ParticipantActionResult.from_payload(result.to_payload()) == result


def test_terminal_observation_action_result_must_match_behavior_event_scope():
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address="participant.behavior.blue-agent",
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(participant_address="participant.behavior.blue-agent"),
        effects=_declared_effects(),
        evidence_refs=("evidence.scan-output",),
    )

    with pytest.raises(ValueError, match="action_result participant_address must match event participant_address"):
        ParticipantBehaviorHistoryEvent(
            event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
            timestamp=T0,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            observation_boundary_address=OBSERVATION_ADDRESS,
            observation_status=ParticipantObservationStatus.TERMINAL,
            post_state_digest="sha256:scan",
            action_result=result,
        )


def test_action_result_requires_concrete_action_contract_address():
    with pytest.raises(
        ValueError, match="action_contract_address must be a compiled participant action contract address"
    ):
        ParticipantActionPreconditionResult(
            precondition_id="authority-in-scope",
            precondition_class=ParticipantPreconditionClass.AUTHORITY,
            status=ParticipantActionPreconditionStatus.SATISFIED,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_contract_address=None,
            observation_point="episode-step:scan-0001:attempt",
            support_refs=("agents.red-agent",),
        )

    with pytest.raises(
        ValueError, match="action_contract_address must be a compiled participant action contract address"
    ):
        ParticipantActionResult(
            status=ParticipantActionResultStatus.ACCEPTED,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=None,
            observation_point="episode-step:scan-0001:attempt",
            preconditions=_satisfied_preconditions(),
            effects=(),
        )


def test_action_result_observation_points_must_anchor_to_action_instance():
    with pytest.raises(ValueError, match="action result observation_point must be anchored to action_instance_id"):
        ParticipantActionResult(
            status=ParticipantActionResultStatus.ACCEPTED,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-9999:attempt",
            preconditions=_satisfied_preconditions(),
            effects=(),
        )

    stale_precondition = ParticipantActionPreconditionResult(
        precondition_id="authority-in-scope",
        precondition_class=ParticipantPreconditionClass.AUTHORITY,
        status=ParticipantActionPreconditionStatus.SATISFIED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-9999:attempt",
        support_refs=("agents.red-agent",),
    )
    with pytest.raises(ValueError, match="precondition observation_point must be anchored"):
        ParticipantActionResult(
            status=ParticipantActionResultStatus.ACCEPTED,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            observation_point="episode-step:scan-0001:attempt",
            preconditions=(
                stale_precondition,
                *_satisfied_preconditions()[1:],
            ),
            effects=(),
        )


def test_terminal_observation_rejects_nonterminal_accepted_action_result():
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.ACCEPTED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:attempt-accepted",
        preconditions=_satisfied_preconditions(),
        effects=(),
    )

    with pytest.raises(ValueError, match="terminal observation action_result must report a terminal status"):
        ParticipantBehaviorHistoryEvent(
            event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
            timestamp=T0,
            participant_address=PARTICIPANT_ADDRESS,
            episode_id="episode-1",
            action_instance_id=ACTION_INSTANCE,
            action_contract_address=ACTION_ADDRESS,
            observation_boundary_address=OBSERVATION_ADDRESS,
            observation_status=ParticipantObservationStatus.TERMINAL,
            post_state_digest="sha256:scan",
            action_result=result,
        )


def test_terminal_observation_requires_sem_211_action_result_when_contract_available():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    events = [
        {
            "event_type": "action_attempted",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": "episode-1",
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "actor_provenance": "participant:red-agent",
            "details": {},
        },
        {
            "event_type": "state_transition_recorded",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": "episode-1",
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "state_transition_kind": "participant_knowledge_expanded",
            "post_state_digest": "sha256:scan",
            "details": {},
        },
        {
            "event_type": "observation_emitted",
            "timestamp": T0,
            "participant_address": PARTICIPANT_ADDRESS,
            "episode_id": "episode-1",
            "action_instance_id": ACTION_INSTANCE,
            "action_contract_address": ACTION_ADDRESS,
            "observation_boundary_address": OBSERVATION_ADDRESS,
            "observation_status": "terminal",
            "post_state_digest": "sha256:scan",
            "details": {},
        },
    ]

    violations = list(
        iter_participant_behavior_history_violations(
            events,
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            action_contracts=model.action_contracts,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            f"terminal observation must carry SEM-211 action_result for {ACTION_ADDRESS}",
        )
    ]


def test_action_result_must_report_every_declared_precondition():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions()[:2],
        effects=_declared_effects(),
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=result,
    )

    violations = list(
        iter_participant_behavior_history_violations(
            [
                {
                    "event_type": "action_attempted",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "actor_provenance": "participant:red-agent",
                    "details": {},
                },
                {
                    "event_type": "state_transition_recorded",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "state_transition_kind": "participant_knowledge_expanded",
                    "post_state_digest": "sha256:scan",
                    "details": {},
                },
                observation.to_payload(),
            ],
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            action_contracts=model.action_contracts,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            f"action_result is missing declared precondition 'backend-can-realize-scan'/'realization' for {ACTION_ADDRESS}",
        )
    ]


def test_action_result_precondition_refs_must_be_declared_by_contract():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    hidden_authority = ParticipantActionPreconditionResult(
        precondition_id="authority-in-scope",
        precondition_class=ParticipantPreconditionClass.AUTHORITY,
        status=ParticipantActionPreconditionStatus.SATISFIED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:attempt",
        support_refs=("content.private-answer-key",),
        evidence_refs=("content.private-answer-key",),
    )
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=(
            hidden_authority,
            *_satisfied_preconditions()[1:],
        ),
        effects=_declared_effects(),
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=result,
    )

    violations = list(
        iter_participant_behavior_history_violations(
            [
                {
                    "event_type": "action_attempted",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "actor_provenance": "participant:red-agent",
                    "details": {},
                },
                {
                    "event_type": "state_transition_recorded",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "state_transition_kind": "participant_knowledge_expanded",
                    "post_state_digest": "sha256:scan",
                    "details": {},
                },
                observation.to_payload(),
            ],
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            action_contracts=model.action_contracts,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result precondition 'authority-in-scope' reports undeclared support_ref "
            "'content.private-answer-key'",
        ),
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result precondition 'authority-in-scope' reports undeclared evidence_ref "
            "'content.private-answer-key'",
        ),
    ]


def test_action_result_effects_must_be_declared_by_compiled_contract():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(),
        effects=(
            *_declared_effects(),
            ParticipantActionEffectResult(
                effect_id="undeclared-detection-change",
                effect_class=ParticipantEffectClass.DETECTION_EFFECT,
                description="scan changed the backend detection surface",
                target_refs=("telemetry.ids-alerts",),
            ),
        ),
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=result,
    )

    violations = list(
        iter_participant_behavior_history_violations(
            [
                {
                    "event_type": "action_attempted",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "actor_provenance": "participant:red-agent",
                    "details": {},
                },
                {
                    "event_type": "state_transition_recorded",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "state_transition_kind": "participant_knowledge_expanded",
                    "post_state_digest": "sha256:scan",
                    "details": {},
                },
                observation.to_payload(),
            ],
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            action_contracts=model.action_contracts,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result effect 'undeclared-detection-change' uses undeclared effect_class 'detection_effect'",
        ),
        (
            "runtime.snapshot.participant-behavior-history[2]",
            f"action_result effect 'undeclared-detection-change'/'detection_effect' is not declared by {ACTION_ADDRESS}",
        ),
    ]


def test_action_result_effect_refs_must_be_declared_by_contract():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(),
        effects=(
            ParticipantActionEffectResult(
                effect_id="scan-shared-knowledge-update",
                effect_class=ParticipantEffectClass.SIDE_EFFECT,
                description="participant-local service knowledge is updated",
                target_refs=("content.private-answer-key",),
                evidence_refs=("content.private-answer-key",),
            ),
        ),
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=result,
    )

    violations = list(
        iter_participant_behavior_history_violations(
            [
                {
                    "event_type": "action_attempted",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "actor_provenance": "participant:red-agent",
                    "details": {},
                },
                {
                    "event_type": "state_transition_recorded",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "state_transition_kind": "participant_knowledge_expanded",
                    "post_state_digest": "sha256:scan",
                    "details": {},
                },
                observation.to_payload(),
            ],
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            action_contracts=model.action_contracts,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result effect 'scan-shared-knowledge-update' reports undeclared target_ref "
            "'content.private-answer-key'",
        ),
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result effect 'scan-shared-knowledge-update' reports undeclared evidence_ref "
            "'content.private-answer-key'",
        ),
    ]


def test_action_result_summary_evidence_refs_must_be_declared_by_contract():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(),
        effects=_declared_effects(),
        evidence_refs=("content.private-answer-key",),
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=result,
    )

    violations = list(
        iter_participant_behavior_history_violations(
            [
                {
                    "event_type": "action_attempted",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "actor_provenance": "participant:red-agent",
                    "details": {},
                },
                {
                    "event_type": "state_transition_recorded",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "state_transition_kind": "participant_knowledge_expanded",
                    "post_state_digest": "sha256:scan",
                    "details": {},
                },
                observation.to_payload(),
            ],
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            action_contracts=model.action_contracts,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result reports undeclared evidence_ref 'content.private-answer-key'",
        )
    ]


def test_action_result_summary_evidence_refs_must_be_grounded_in_reported_results():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(),
        effects=(
            ParticipantActionEffectResult(
                effect_id="discover-http-service",
                effect_class=ParticipantEffectClass.INTENDED_EFFECT,
                description="participant discovered the web HTTP service",
                target_refs=("nodes.web.services.http",),
            ),
        ),
        evidence_refs=("evidence.scan-output",),
    )

    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads_for_action_result(result),
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            action_contracts=model.action_contracts,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result evidence_ref 'evidence.scan-output' is not grounded in reported precondition or "
            "effect evidence_refs",
        )
    ]


def test_action_result_refs_must_be_authorized_by_observation_boundary():
    scenario = _scenario_with_hidden_action_result_ref().replace(
        "support_refs: [agents.red-agent, nodes.web.services.http]",
        "support_refs: [agents.red-agent, nodes.web.services.http, content.private-answer-key]",
    )
    model = compile_runtime_model(parse_sdl(scenario))
    hidden_authority = ParticipantActionPreconditionResult(
        precondition_id="authority-in-scope",
        precondition_class=ParticipantPreconditionClass.AUTHORITY,
        status=ParticipantActionPreconditionStatus.SATISFIED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:attempt",
        support_refs=("content.private-answer-key",),
    )
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=(
            hidden_authority,
            *_satisfied_preconditions()[1:],
        ),
        effects=_declared_effects(),
    )

    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads_for_action_result(result),
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses=None,
            ),
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result precondition 'authority-in-scope' support_ref 'content.private-answer-key' is not "
            "participant-visible at effective_order 30: disposition 'hidden'",
        )
    ]


def test_action_result_effect_targets_must_be_authorized_by_observation_boundary():
    scenario = _scenario_with_hidden_action_result_ref().replace(
        "        target_refs: [nodes.web.services.http]\n      - effect_id: terminal-scan-observation",
        "        target_refs: [nodes.web.services.http, content.private-answer-key]\n"
        "      - effect_id: terminal-scan-observation",
    )
    model = compile_runtime_model(parse_sdl(scenario))
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(),
        effects=(
            ParticipantActionEffectResult(
                effect_id="scan-shared-knowledge-update",
                effect_class=ParticipantEffectClass.SIDE_EFFECT,
                description="participant-local service knowledge is updated",
                target_refs=("content.private-answer-key",),
            ),
        ),
    )

    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads_for_action_result(result),
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses=None,
            ),
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result effect 'scan-shared-knowledge-update' target_ref 'content.private-answer-key' is not "
            "participant-visible at effective_order 30: disposition 'hidden'",
        )
    ]


def test_action_result_evidence_refs_must_be_authorized_by_observation_boundary():
    scenario = _scenario_with_hidden_action_result_ref().replace(
        "evidence_refs: [evidence.scan-output]",
        "evidence_refs: [evidence.scan-output, content.private-answer-key]",
        1,
    )
    model = compile_runtime_model(parse_sdl(scenario))
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(),
        effects=(
            ParticipantActionEffectResult(
                effect_id="terminal-scan-observation",
                effect_class=ParticipantEffectClass.OBSERVATION_EFFECT,
                description="terminal scan observation emitted",
                evidence_refs=("content.private-answer-key",),
            ),
        ),
    )

    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads_for_action_result(result),
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses=None,
            ),
            action_contracts=model.action_contracts,
            observation_boundaries=model.observation_boundaries,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[2]",
            "action_result effect 'terminal-scan-observation' evidence_ref 'content.private-answer-key' is not "
            "authorized evidence at effective_order 30: disposition 'hidden'",
        )
    ]


def test_action_result_failure_class_must_be_declared_by_compiled_contract():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    unresolved = ParticipantActionPreconditionResult(
        precondition_id="backend-can-realize-scan",
        precondition_class=ParticipantPreconditionClass.REALIZATION,
        status=ParticipantActionPreconditionStatus.UNRESOLVED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:attempt",
        diagnostics=("backend runtime did not declare realization support",),
    )
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.REJECTED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:attempt",
        preconditions=(*_satisfied_preconditions()[:2], unresolved),
        effects=(),
        failure_class=ParticipantFailureClass.AUTHORITY_DENIED,
        diagnostics=("backend rejected action outside portable contract",),
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.ORPHANED_ACTION,
        action_result=result,
    )

    violations = list(
        iter_participant_behavior_history_violations(
            [
                {
                    "event_type": "action_attempted",
                    "timestamp": T0,
                    "participant_address": PARTICIPANT_ADDRESS,
                    "episode_id": "episode-1",
                    "action_instance_id": ACTION_INSTANCE,
                    "action_contract_address": ACTION_ADDRESS,
                    "actor_provenance": "participant:red-agent",
                    "details": {},
                },
                observation.to_payload(),
            ],
            address_scope=ParticipantHistoryAddressScope(
                action_contract_addresses=set(model.action_contracts),
                observation_boundary_addresses={OBSERVATION_ADDRESS},
            ),
            action_contracts=model.action_contracts,
        )
    )

    assert violations == [
        (
            "runtime.snapshot.participant-behavior-history[1]",
            f"action_result failure_class 'authority_denied' is not declared by {ACTION_ADDRESS}",
        )
    ]


def test_backend_diagnostic_mapping_returns_portable_failure_class():
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    contract = model.action_contracts[ACTION_ADDRESS]

    assert (
        map_backend_diagnostic_to_participant_failure(
            Diagnostic(
                code="backend.timeout",
                domain="participant",
                address=ACTION_ADDRESS,
                message="operation timed out",
            ),
            contract,
        )
        == ParticipantFailureClass.TIMEOUT
    )
    assert (
        map_backend_diagnostic_to_participant_failure(
            Diagnostic(
                code="backend.unmapped",
                domain="participant",
                address=ACTION_ADDRESS,
                message="backend reported an unmapped failure",
            ),
            contract,
        )
        == ParticipantFailureClass.BACKEND_ERROR
    )


def test_local_control_plane_store_preserves_participant_behavior_history(tmp_path):
    result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=_satisfied_preconditions(),
        effects=_declared_effects(),
        evidence_refs=("evidence.scan-output",),
    )
    observation = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
        timestamp=T0,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id="episode-1",
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_boundary_address=OBSERVATION_ADDRESS,
        observation_status=ParticipantObservationStatus.TERMINAL,
        post_state_digest="sha256:scan",
        action_result=result,
    )
    snapshot = RuntimeSnapshot(
        participant_behavior_history={
            PARTICIPANT_ADDRESS: [
                observation.to_payload(),
            ]
        }
    )
    store = LocalControlPlaneStore(tmp_path / "control-plane")

    store.save_snapshot(snapshot, expected_revision=store.load_snapshot_state().revision)
    loaded = store.load_snapshot()

    assert loaded.participant_behavior_history == snapshot.participant_behavior_history
