"""Offline checks of observed calls, not a runtime or bisimulation oracle."""

from dataclasses import asdict, dataclass, field, replace

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingOccurrenceModel,
)
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_runtime.control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
)
from raes_runtime.participant_crossing_mediation import (
    ParticipantCrossingIntent,
    ParticipantCrossingValidationContext,
)
from raes_runtime.participant_crossing_state_cut import (
    expected_participant_history_heads,
)

from . import concrete
from .runtime_mapping_integrity import integrity as _integrity


@dataclass(frozen=True)
class Binding:
    participant: str
    episode: str
    audience: str
    controller: str
    principal: str
    target: str
    policy_cuts: tuple[str, str]
    run_scope: str = "run:default"


@dataclass(frozen=True)
class Event:
    label: str
    coordinates: dict[str, str] = field(default_factory=dict)
    facts: dict[str, object] = field(default_factory=dict)
    ordinal: int | None = None


@dataclass(frozen=True)
class Commit:
    snapshot: RuntimeSnapshot
    record: ControlPlaneOperationRecord
    audit: tuple[AuditEvent, ...]
    expected_snapshot: RuntimeSnapshot
    expected_record: ControlPlaneOperationRecord
    expected_audit: AuditEvent
    expected_revision: int
    revision: int
    records: dict[str, ControlPlaneOperationRecord]
    audit_before: tuple[AuditEvent, ...]


@dataclass(frozen=True)
class Observation:
    binding: Binding
    input_class: str
    events: tuple[Event, ...]
    intents: tuple[ParticipantCrossingIntent, ...]
    before: RuntimeSnapshot
    after: RuntimeSnapshot
    records_before: dict[str, ControlPlaneOperationRecord]
    records_after: dict[str, ControlPlaneOperationRecord]
    audit: tuple[AuditEvent, ...]
    commits: tuple[Commit, ...]
    context: ParticipantCrossingValidationContext
    result: object
    error_type: str | None
    backend_calls: int
    cut: str = "p0"
    timed: bool = False
    entry_point: str = "admit_participant_action"
    final_sink: bool = False
    configuration: dict[str, object] = field(default_factory=dict)
    before_revision: int = 0
    after_revision: int = 0
    before_policy_cut: str | None = None
    witness_count: int = 0
    audit_before: tuple[AuditEvent, ...] = ()


def _initial_state(observed: Observation) -> tuple[concrete.State | None, list[str]]:
    """Project pre-call facts; never reconstruct an unobserved transition path."""
    binding = observed.binding
    if observed.before_policy_cut not in binding.policy_cuts:
        return None, ["initial-cut-unmapped"]
    current_cut = "p0" if observed.before_policy_cut == binding.policy_cuts[0] else "p1"
    history = observed.before.participant_crossing_history.get(binding.participant, [])
    if not history:
        return replace(concrete.INITIAL, cut=current_cut), []
    if len(history) != 2 or [item["occurrence"]["stage"] for item in history] != [
        "requested",
        "decided",
    ]:
        return None, ["initial-state-unmapped"]
    request, decision = [
        ParticipantCrossingOccurrenceModel.model_validate(item) for item in history
    ]
    detail = decision.occurrence
    disposition = detail.disposition.value
    if (
        disposition not in {"deny", "unsupported"}
        or detail.policy.decision_cut_ref not in binding.policy_cuts
    ):
        # Missing delivery/observation evidence cannot establish a terminal permit.
        return None, ["initial-state-unmapped"]
    owner_ids = {
        event.operation_id
        for event in observed.audit_before
        if event.details.get("crossing_decision_id", event.details.get("decision_id"))
        == detail.decision_id
    }
    owners = [
        observed.records_before[key]
        for key in owner_ids
        if key in observed.records_before
    ]
    heads = expected_participant_history_heads(observed.before, binding.participant)
    if (
        len(owners) != 1
        or owners[0].status.state is not OperationState.FAILED
        or owners[0].result_history_heads != heads
    ):
        return None, ["initial-state-unmapped"]
    if (
        request.participant_address,
        request.episode_id,
        detail.audience_scope_ref,
        detail.controller_ref,
    ) != (
        binding.participant,
        binding.episode,
        binding.audience,
        binding.controller,
    ):
        return None, ["initial-state-unmapped"]
    recorded_cut = (
        "p0" if detail.policy.decision_cut_ref == binding.policy_cuts[0] else "p1"
    )
    values = detail.gates.model_dump(mode="json")
    backend = values.pop("backend_support")
    state = concrete.State(
        phase="terminal",
        cut=current_cut,
        intent=("request-0", observed.input_class, recorded_cut, "fresh"),
        gate="deny" if "deny" in values.values() else "permit",
        capability="supported" if backend == "permit" else "unsupported",
        decision=disposition,
        delivery="withheld",
        head="h1",
        last=("request-0", recorded_cut, disposition),
    )
    if state not in concrete.build().states:
        return None, ["initial-state-unmapped"]
    return state, []


def assess(observed: Observation) -> dict[str, object]:
    """Check witnessed edges exactly; never manufacture a hidden continuation."""
    issues = _integrity(observed)
    integrity = set(issues) - {"identity-context-mismatch"}
    if (
        observed.after.participant_control_history
        != observed.before.participant_control_history
    ):
        issues.append("control-change-outside-carrier")
    if len(set(observed.records_after) - set(observed.records_before)) > 1:
        issues.append("additional-operation-outside-carrier")
    if observed.timed:
        issues.append("timing-excluded")
    if observed.input_class not in {
        "plain",
        "transform",
        "declassify",
        "unsupported",
        "forbidden",
    }:
        issues.append("input-outside-carrier")
    if observed.cut not in {"p0", "p1"}:
        issues.append("cut-outside-carrier")
    state, initial_issues = _initial_state(observed)
    issues.extend(initial_issues)
    states = [asdict(state)] if state is not None else []
    if observed.witness_count != len(observed.events):
        issues.append("missing-witness")
    for ordinal, event in enumerate(observed.events):
        if state is None:
            break
        if type(event.ordinal) is not int or event.ordinal != ordinal:
            issues.append("missing-witness")
            break
        candidates = [
            target
            for label, target in concrete.successors(state)
            if label == event.label
            and (
                label != "crossing.request" or target.intent[1] == observed.input_class
            )
            and all(
                getattr(target, name, None) == value
                for name, value in event.coordinates.items()
            )
        ]
        if len(candidates) != 1:
            issues.append("transition-mismatch")
            break
        state = candidates[0]
        if event.label == "internal.atomic-commit" and (
            (
                state.decision in {"deny", "unsupported"}
                and event.facts.get("operation_state") != "failed"
            )
            or (
                state.decision not in {"deny", "unsupported"}
                and event.facts.get("operation_state") == "failed"
            )
        ):
            issues.append("final-outcome-mismatch")
        states.append(asdict(state))
    complete = state is not None and state.phase == "terminal"
    if observed.error_type is not None:
        # Exception existence remains visible even if its text is withheld.
        issues.append("unmodeled-error")
    if observed.backend_calls:
        issues.append("external-application-outside-crossing-model")
    if not complete:
        issues.append("incomplete-observation")
    gap_codes = {
        "missing-witness",
        "incomplete-observation",
        "initial-state-unmapped",
        "initial-cut-unmapped",
    }
    classification = (
        "invalid-evidence"
        if integrity
        else "observation-gap"
        if issues and set(issues) <= gap_codes
        else "incompatible"
        if issues
        else "match"
    )
    return {
        "classification": classification,
        "issues": sorted(set(issues)),
        "runtime_safety_issues": sorted(integrity),
        "observation_gaps": sorted(gap_codes & set(issues)),
        "unexercised": [
            "enabled-choice-completeness",
            "production-backend",
            "independent-reproduction",
        ],
        "input_class": observed.input_class,
        "cut": observed.cut,
        "entry_point": observed.entry_point,
        "runtime_binding": asdict(observed.binding),
        "final_sink_enforced": observed.final_sink,
        "configuration": observed.configuration,
        "snapshot_revisions": [observed.before_revision, observed.after_revision],
        "backend_calls": observed.backend_calls,
        "events": [asdict(event) for event in observed.events],
        "visible_events": [
            event.label
            for event in observed.events
            if not event.label.startswith("internal.")
        ],
        "states": states,
        "crossing_rows_added": len(
            observed.after.participant_crossing_history.get(
                observed.binding.participant, []
            )
        )
        - len(
            observed.before.participant_crossing_history.get(
                observed.binding.participant, []
            )
        ),
        "operation_records_added": len(
            set(observed.records_after) - set(observed.records_before)
        ),
        "operation_outcomes": sorted(
            record.status.state.value
            for key, record in observed.records_after.items()
            if observed.records_before.get(key) != record
        ),
        "observed_error": observed.error_type,
        "equivalence_result": "not-established",
        "runtime_realization": "not-established",
        "backend_conformance": "not-established",
    }
