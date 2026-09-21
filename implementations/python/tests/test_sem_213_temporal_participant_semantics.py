"""SEM-213 temporal participant semantics."""

from __future__ import annotations

import textwrap

import pytest
from raes._errors import SDLParseError
from raes.parser import parse_sdl
from raes.participant_behavior import ParticipantEffectClass, ParticipantPreconditionClass
from raes.participant_temporal_semantics import (
    ParticipantTemporalContractKind,
    ParticipantTemporalEventPoint,
    ParticipantTimeDomain,
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
    ParticipantTemporalRuntimeContext,
    ParticipantTemporalState,
    ParticipantTemporalStateTransition,
    iter_participant_behavior_history_violations,
    iter_participant_temporal_state_machine_violations,
)

T0 = "2026-05-21T04:00:00Z"
PARTICIPANT_ADDRESS = "participant.behavior.red-agent"
ACTION_ADDRESS = "participant.action-contract.scan"
OBSERVATION_ADDRESS = "participant.observation-boundary.red-view"
ACTION_INSTANCE = "scan-0001"
EPISODE_ID = "episode-1"


def _scenario_yaml() -> str:
    return textwrap.dedent(
        """
        name: sem-213
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
            fidelity_claim: records participant discovery timing without claiming portable wall-clock fidelity
            preconditions:
              - precondition_id: scheduled-window-open
                precondition_class: temporal
                description: scan may start only inside the scenario maintenance window
                support_refs: [windows.maintenance]
              - precondition_id: backend-can-realize-scan
                precondition_class: realization
                description: backend can realize the scan action contract
                support_refs: [backend.participant-runtime]
            effects:
              - effect_id: terminal-scan-observation
                effect_class: observation_effect
                description: terminal scan observation is emitted for the participant
                evidence_refs: [evidence.scan-output]
            failure_classes: [precondition_unsatisfied, timeout, backend_error, unknown]
            temporal_contracts:
              - temporal_id: scan-schedule
                temporal_kind: schedule
                time_domain: scenario_time
                clock_authority: scenario.author.clock
                event_points: [submit, start]
                description: scan is eligible only during the authored maintenance window
                window_ref: windows.maintenance
                ordering_basis: participant schedule relation, not raw timestamp causality
                backend_disclosure_refs: [timing.remote-pacing]
              - temporal_id: scan-cadence
                temporal_kind: cadence
                time_domain: episode_step
                clock_authority: processor.episode-sequence
                event_points: [submit]
                description: scan attempts are rate-limited per participant episode
                duration_ref: cadence.scan.per-episode
                reset_boundary: participant episode reset starts a new cadence segment
                replay_boundary: replay preserves the original cadence segment id
                randomization_basis: seeded participant episode sequence
                ordering_basis: participant episode sequence
                backend_disclosure_refs: [timing.remote-pacing]
              - temporal_id: scan-deadline
                temporal_kind: deadline
                time_domain: backend_time
                clock_authority: backend.adapter.clock
                event_points: [submit, deadline, end]
                description: backend must realize the scan before the participant timeout
                duration_ref: duration.scan.deadline
                reset_boundary: participant episode reset clears the deadline state
                replay_boundary: replay reports the original deadline state
                ordering_basis: backend event order relation
                backend_disclosure_refs: [timing.remote-pacing, timing.serialization]
              - temporal_id: scan-dwell
                temporal_kind: dwell
                time_domain: scenario_time
                clock_authority: scenario.author.clock
                event_points: [start, end]
                description: target service must remain in scope for the scan dwell window
                window_ref: windows.maintenance
                duration_ref: duration.scan.dwell
                reset_boundary: participant episode reset clears dwell accumulation
                replay_boundary: replay reports original dwell evidence
                ordering_basis: scenario window relation
                backend_disclosure_refs: [timing.serialization]
              - temporal_id: scan-latency
                temporal_kind: latency
                time_domain: backend_time
                clock_authority: backend.adapter.clock
                event_points: [submit, observed]
                description: terminal observation latency is measured from submit to observation delivery
                duration_ref: duration.scan.observation-latency
                reset_boundary: participant episode reset closes the latency segment
                replay_boundary: replay reports original latency evidence
                ordering_basis: backend delivery order relation
                backend_disclosure_refs: [timing.remote-pacing]
              - temporal_id: scan-window
                temporal_kind: time_window
                time_domain: wall_clock_time
                clock_authority: study.coordinator.clock
                event_points: [window_open, window_close]
                description: study-level collection window for participant attempts
                window_ref: study.collection-window
                reset_boundary: participant episode reset does not change the study window
                replay_boundary: replay reports the original study window
                randomization_basis: study coordinator seed and cohort assignment
                ordering_basis: study coordinator window relation
                backend_disclosure_refs: [timing.remote-pacing]
            backend_timing_disclosures:
              - disclosure_id: timing.remote-pacing
                disclosure_kind: pacing
                support_mode: disclosed_limitation
                description: remote backend pacing is best-effort and not portable semantic time
                affected_temporal_ids:
                  - scan-schedule
                  - scan-cadence
                  - scan-deadline
                  - scan-latency
                  - scan-window
                limitations: [wall-clock pacing may lag backend event time]
              - disclosure_id: timing.serialization
                disclosure_kind: serialization
                support_mode: disclosed_limitation
                description: backend serializes scan realization before emitting terminal observation
                affected_temporal_ids: [scan-deadline, scan-dwell]
                limitations: [serialized order is disclosed as realized order, not simultaneity]
        agents:
          red-agent:
            affiliations: [red-team]
            actions: [scan]
            observation_boundaries: [red-view]
        observation_boundaries:
          red-view:
            projection_basis: participant-local projection
            observable_refs: [nodes.web.services.http]
            hidden_refs: []
            evidence_refs: [evidence.scan-output]
            redaction_policy: no hidden refs in this SEM-213 fixture
            latency_profile: terminal observation emitted after backend realization
        """
    )


def test_temporal_action_contract_declares_sem_213_and_compiles_it() -> None:
    scenario = parse_sdl(_scenario_yaml())

    contract = scenario.action_contracts["scan"]
    assert [item.temporal_kind for item in contract.temporal_contracts] == [
        ParticipantTemporalContractKind.SCHEDULE,
        ParticipantTemporalContractKind.CADENCE,
        ParticipantTemporalContractKind.DEADLINE,
        ParticipantTemporalContractKind.DWELL,
        ParticipantTemporalContractKind.LATENCY,
        ParticipantTemporalContractKind.TIME_WINDOW,
    ]
    assert contract.temporal_contracts[0].time_domain == ParticipantTimeDomain.SCENARIO_TIME
    assert contract.temporal_contracts[2].clock_authority == "backend.adapter.clock"

    model = compile_runtime_model(scenario)
    compiled = model.action_contracts[ACTION_ADDRESS]

    assert compiled.temporal_contract_ids == (
        "scan-schedule",
        "scan-cadence",
        "scan-deadline",
        "scan-dwell",
        "scan-latency",
        "scan-window",
    )
    assert compiled.temporal_kinds == (
        "schedule",
        "cadence",
        "deadline",
        "dwell",
        "latency",
        "time_window",
    )
    assert compiled.time_domains == ("scenario_time", "episode_step", "backend_time", "wall_clock_time")
    assert compiled.clock_authorities == (
        "scenario.author.clock",
        "processor.episode-sequence",
        "backend.adapter.clock",
        "study.coordinator.clock",
    )
    assert compiled.backend_timing_disclosures[0]["disclosure_id"] == "timing.remote-pacing"
    assert compiled.backend_timing_disclosures[0]["disclosure_kind"] == "pacing"


def test_temporal_claims_require_time_domain_and_clock_authority() -> None:
    missing_clock_authority = _scenario_yaml().replace(
        "        clock_authority: scenario.author.clock\n",
        "",
        1,
    )

    with pytest.raises(SDLParseError, match="clock_authority"):
        parse_sdl(missing_clock_authority)


def test_temporal_backend_disclosure_refs_fail_closed() -> None:
    unknown_backend_disclosure = _scenario_yaml().replace(
        "backend_disclosure_refs: [timing.remote-pacing]",
        "backend_disclosure_refs: [timing.unknown]",
        1,
    )

    with pytest.raises(SDLParseError, match="unknown backend_timing_disclosures"):
        parse_sdl(unknown_backend_disclosure)


def test_temporal_contract_shapes_fail_closed() -> None:
    deadline_without_deadline_point = _scenario_yaml().replace(
        "event_points: [submit, deadline, end]",
        "event_points: [submit, end]",
        1,
    )
    dwell_without_sustained_window = _scenario_yaml().replace(
        "event_points: [start, end]",
        "event_points: [start]",
        1,
    )
    window_without_seed_basis = _scenario_yaml().replace(
        "        randomization_basis: study coordinator seed and cohort assignment\n",
        "",
        1,
    )
    temporal_claim_without_disclosure = _scenario_yaml().replace(
        "backend_disclosure_refs: [timing.remote-pacing]",
        "backend_disclosure_refs: []",
        1,
    )
    bounded_disclosure_without_bound = (
        _scenario_yaml()
        .replace(
            "support_mode: disclosed_limitation",
            "support_mode: bounded",
            1,
        )
        .replace(
            "        limitations: [wall-clock pacing may lag backend event time]\n",
            "",
            1,
        )
    )

    invalid_payloads = [
        (deadline_without_deadline_point, "deadline temporal contracts require a deadline event_point"),
        (dwell_without_sustained_window, "dwell temporal contracts require at least two event_points"),
        (window_without_seed_basis, "time_window temporal contracts require randomization_basis"),
        (temporal_claim_without_disclosure, "schedule temporal contracts require backend_disclosure_refs"),
        (bounded_disclosure_without_bound, "bounded timing disclosures require limitations"),
    ]

    for payload, message in invalid_payloads:
        with pytest.raises(SDLParseError, match=message):
            parse_sdl(payload)


def _history_payloads(*, temporal_context: ParticipantTemporalRuntimeContext) -> list[dict[str, object]]:
    action_result = ParticipantActionResult(
        status=ParticipantActionResultStatus.SUCCEEDED,
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EPISODE_ID,
        action_instance_id=ACTION_INSTANCE,
        action_contract_address=ACTION_ADDRESS,
        observation_point="episode-step:scan-0001:terminal-observation",
        preconditions=(
            ParticipantActionPreconditionResult(
                precondition_id="scheduled-window-open",
                precondition_class=ParticipantPreconditionClass.TEMPORAL,
                status=ParticipantActionPreconditionStatus.SATISFIED,
                participant_address=PARTICIPANT_ADDRESS,
                episode_id=EPISODE_ID,
                action_contract_address=ACTION_ADDRESS,
                observation_point="episode-step:scan-0001:attempt",
                support_refs=("windows.maintenance",),
            ),
            ParticipantActionPreconditionResult(
                precondition_id="backend-can-realize-scan",
                precondition_class=ParticipantPreconditionClass.REALIZATION,
                status=ParticipantActionPreconditionStatus.SATISFIED,
                participant_address=PARTICIPANT_ADDRESS,
                episode_id=EPISODE_ID,
                action_contract_address=ACTION_ADDRESS,
                observation_point="episode-step:scan-0001:attempt",
                support_refs=("backend.participant-runtime",),
            ),
        ),
        effects=(
            ParticipantActionEffectResult(
                effect_id="terminal-scan-observation",
                effect_class=ParticipantEffectClass.OBSERVATION_EFFECT,
                description="terminal scan observation emitted",
                evidence_refs=("evidence.scan-output",),
            ),
        ),
        evidence_refs=("evidence.scan-output",),
    )
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
        action_result=action_result,
        temporal_contexts=(temporal_context,),
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


def test_runtime_temporal_context_must_match_compiled_contract() -> None:
    model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    context = ParticipantTemporalRuntimeContext(
        temporal_contract_id="scan-latency",
        time_domain=ParticipantTimeDomain.BACKEND_TIME,
        clock_authority="backend.adapter.clock",
        event_points=(ParticipantTemporalEventPoint.SUBMIT, ParticipantTemporalEventPoint.OBSERVED),
        observation_point="episode-step:scan-0001:terminal-observation",
        backend_disclosure_refs=("timing.remote-pacing",),
        reset_boundary="participant episode reset closes the latency segment",
        replay_boundary="replay reports original latency evidence",
    )

    assert (
        list(
            iter_participant_behavior_history_violations(
                _history_payloads(temporal_context=context),
                action_contracts=model.action_contracts,
            )
        )
        == []
    )

    mismatched = ParticipantTemporalRuntimeContext(
        temporal_contract_id="scan-latency",
        time_domain=ParticipantTimeDomain.WALL_CLOCK_TIME,
        clock_authority="backend.adapter.clock",
        event_points=(ParticipantTemporalEventPoint.SUBMIT, ParticipantTemporalEventPoint.OBSERVED),
        observation_point="episode-step:scan-0001:terminal-observation",
        backend_disclosure_refs=("timing.remote-pacing",),
        reset_boundary="participant episode reset closes the latency segment",
        replay_boundary="replay reports original latency evidence",
    )

    violations = list(
        iter_participant_behavior_history_violations(
            _history_payloads(temporal_context=mismatched),
            action_contracts=model.action_contracts,
        )
    )

    assert any(
        "temporal context 'scan-latency' time_domain 'wall_clock_time' does not match compiled contract "
        "'backend_time'" in message
        for _, message in violations
    )


def test_temporal_state_machine_rejects_invalid_deadline_dwell_timeout_sequences() -> None:
    valid_cadence_sequence = [
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-cadence",
            from_state=ParticipantTemporalState.CADENCE_READY,
            to_state=ParticipantTemporalState.CADENCE_WAITING,
            event_point=ParticipantTemporalEventPoint.SUBMIT,
            time_domain=ParticipantTimeDomain.EPISODE_STEP,
            clock_authority="processor.episode-sequence",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-attempt-1",),
        ),
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-cadence",
            from_state=ParticipantTemporalState.CADENCE_WAITING,
            to_state=ParticipantTemporalState.CADENCE_READY,
            event_point=ParticipantTemporalEventPoint.END,
            time_domain=ParticipantTimeDomain.EPISODE_STEP,
            clock_authority="processor.episode-sequence",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-cadence-elapsed",),
        ),
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-cadence",
            from_state=ParticipantTemporalState.CADENCE_READY,
            to_state=ParticipantTemporalState.CADENCE_WAITING,
            event_point=ParticipantTemporalEventPoint.SUBMIT,
            time_domain=ParticipantTimeDomain.EPISODE_STEP,
            clock_authority="processor.episode-sequence",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-attempt-2",),
        ),
    ]
    valid_reset_boundary_sequence = [
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-cadence",
            from_state=ParticipantTemporalState.CADENCE_READY,
            to_state=ParticipantTemporalState.CADENCE_WAITING,
            event_point=ParticipantTemporalEventPoint.SUBMIT,
            time_domain=ParticipantTimeDomain.EPISODE_STEP,
            clock_authority="processor.episode-sequence",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-attempt-1",),
        ),
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-cadence",
            from_state=ParticipantTemporalState.CADENCE_WAITING,
            to_state=ParticipantTemporalState.RESET,
            event_point=ParticipantTemporalEventPoint.RESET,
            time_domain=ParticipantTimeDomain.EPISODE_STEP,
            clock_authority="processor.episode-sequence",
            boundary_ref="episode:episode-2",
            evidence_refs=("evidence.episode-reset",),
        ),
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-cadence",
            from_state=ParticipantTemporalState.CADENCE_READY,
            to_state=ParticipantTemporalState.CADENCE_WAITING,
            event_point=ParticipantTemporalEventPoint.SUBMIT,
            time_domain=ParticipantTimeDomain.EPISODE_STEP,
            clock_authority="processor.episode-sequence",
            boundary_ref="episode:episode-2",
            evidence_refs=("evidence.scan-attempt-after-reset",),
        ),
    ]
    repeated_cadence_without_release = [
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-cadence",
            from_state=ParticipantTemporalState.CADENCE_READY,
            to_state=ParticipantTemporalState.CADENCE_WAITING,
            event_point=ParticipantTemporalEventPoint.SUBMIT,
            time_domain=ParticipantTimeDomain.EPISODE_STEP,
            clock_authority="processor.episode-sequence",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-attempt-1",),
        ),
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-cadence",
            from_state=ParticipantTemporalState.CADENCE_WAITING,
            to_state=ParticipantTemporalState.CADENCE_WAITING,
            event_point=ParticipantTemporalEventPoint.SUBMIT,
            time_domain=ParticipantTimeDomain.EPISODE_STEP,
            clock_authority="processor.episode-sequence",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-repeat-too-soon",),
        ),
    ]
    dwell_without_active = [
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-dwell",
            from_state=ParticipantTemporalState.ELIGIBLE,
            to_state=ParticipantTemporalState.DWELL_SATISFIED,
            event_point=ParticipantTemporalEventPoint.END,
            time_domain=ParticipantTimeDomain.SCENARIO_TIME,
            clock_authority="scenario.author.clock",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-output",),
        )
    ]
    deadline_reuse_without_boundary = [
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-deadline",
            from_state=ParticipantTemporalState.ELIGIBLE,
            to_state=ParticipantTemporalState.DEADLINE_MISSED,
            event_point=ParticipantTemporalEventPoint.END,
            time_domain=ParticipantTimeDomain.BACKEND_TIME,
            clock_authority="backend.adapter.clock",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-timeout",),
        ),
        ParticipantTemporalStateTransition(
            temporal_contract_id="scan-deadline",
            from_state=ParticipantTemporalState.DEADLINE_MISSED,
            to_state=ParticipantTemporalState.ELIGIBLE,
            event_point=ParticipantTemporalEventPoint.START,
            time_domain=ParticipantTimeDomain.BACKEND_TIME,
            clock_authority="backend.adapter.clock",
            boundary_ref="episode:episode-1",
            evidence_refs=("evidence.scan-retry",),
        ),
    ]

    assert list(iter_participant_temporal_state_machine_violations(valid_cadence_sequence)) == []
    assert list(iter_participant_temporal_state_machine_violations(valid_reset_boundary_sequence)) == []

    violations = [
        *iter_participant_temporal_state_machine_violations(repeated_cadence_without_release),
        *iter_participant_temporal_state_machine_violations(dwell_without_active),
        *iter_participant_temporal_state_machine_violations(deadline_reuse_without_boundary),
    ]

    assert any("cadence repeated event requires cadence_ready" in message for _, message in violations)
    assert any("dwell_satisfied requires prior dwell_active" in message for _, message in violations)
    assert any("terminal temporal state requires reset or replay boundary" in message for _, message in violations)


def test_contract_schema_publishes_temporal_context_payload() -> None:
    schema = ParticipantBehaviorHistoryEventModel.model_json_schema()

    assert "temporal_contexts" in schema["properties"]
    temporal_ref = schema["properties"]["temporal_contexts"]["items"]["$ref"]
    assert temporal_ref.endswith("/ParticipantTemporalRuntimeContextModel")
