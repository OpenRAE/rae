"""Runner-owned execution and measurement for participant-policy probes.

This half of the probe family builds the real control plane on the target under
evaluation, instruments that target, drives the typed boundary, and measures
what happened. It exists separately from the judging half so it is structurally
obvious that no harness-supplied value reaches these measurements: the harness
contributes case inputs, and everything reported here is read back from the
runtime's own state.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace

from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget

from raes_conformance.conformance.diagnostics import sanitized_failure_message
from raes_conformance.conformance.participant_policy_types import (
    ParticipantPolicyOperation,
    ParticipantPolicyProbeCase,
    _declared_level,
)


@dataclass
class _CallCounter:
    """Counts real participant-runtime calls on the target under evaluation.

    Backend invocation was previously inferred from participant behavior
    history, which is invisible to a target call that has external side effects
    without writing history. Wrapping the runtime counts the calls directly.
    """

    inner: object
    calls: int = 0
    called_methods: list[str] = field(default_factory=list)

    def __getattr__(self, name: str) -> object:
        attribute = getattr(self.inner, name)
        if not callable(attribute):
            return attribute

        def _counted(*args: object, **kwargs: object) -> object:
            self.calls += 1
            self.called_methods.append(name)
            return attribute(*args, **kwargs)

        return _counted


@dataclass(frozen=True)
class _Ledger:
    """Runner-owned snapshot of the side effects a probe must not produce."""

    behavior_history: str
    crossing_records: tuple[str, ...]
    audit_events: int


def _ledger(plane: RuntimeControlPlane) -> _Ledger:
    snapshot = plane.snapshot
    records: list[str] = []
    for participant in sorted(snapshot.participant_crossing_history):
        records.extend(repr(entry) for entry in snapshot.participant_crossing_history[participant])
    return _Ledger(
        behavior_history=repr(snapshot.participant_behavior_history),
        crossing_records=tuple(records),
        audit_events=len(plane.audit_log()),
    )


@dataclass(frozen=True)
class _Outcome:
    """Everything the runner measured for one case."""

    released: bool
    refused: bool
    backend_calls: int
    appended_dispositions: tuple[str, ...]
    invalid_reason: str | None
    mutated_existing: bool
    audited: bool
    declared_support_level: str
    effective_support_level: str | None
    evidence_refs: tuple[str, ...]
    counterexample_ref: str | None


def _instrumented_target(target: RuntimeTarget) -> tuple[RuntimeTarget, _CallCounter | None]:
    """Wrap the target's participant runtime so its calls are counted directly."""

    if target.participant_runtime is None:
        return target, None
    counter = _CallCounter(inner=target.participant_runtime)
    return replace(target, participant_runtime=counter), counter


def _validate_records(plane: RuntimeControlPlane) -> tuple[tuple[str, ...], str | None]:
    """Semantically validate every crossing record the runtime has committed.

    An appended record is not evidence just because it exists; it must satisfy
    the published API-423 contract, or the report would carry a malformed
    decision as though the runtime had produced a governed one.
    """

    dispositions: list[str] = []
    for participant in sorted(plane.snapshot.participant_crossing_history):
        for entry in plane.snapshot.participant_crossing_history[participant]:
            try:
                # The published model covers the whole event record, not just
                # its nested occurrence, so validate the record as committed.
                record = ParticipantCrossingOccurrenceModel.model_validate(entry)
            except Exception as exc:
                return tuple(dispositions), sanitized_failure_message(exc)
            # ``occurrence`` is a union over crossing stages; only the decision
            # stage carries a disposition, and that is the stage an obligation's
            # expected outcome is compared against.
            disposition = getattr(record.occurrence, "disposition", None)
            if disposition is not None:
                dispositions.append(disposition.value)
    return tuple(dispositions), None


def _drive_ingress(case: ParticipantPolicyProbeCase, plane: RuntimeControlPlane) -> tuple[bool, bool]:
    receipt = plane.admit_participant_action(
        case.behavior,
        case.admission_request,
        identity=case.identity,
        crossing_evidence=case.crossing_evidence,
        idempotency_key=case.idempotency_key,
    )
    status = plane.get_operation(receipt.operation_id)
    allowed = status is not None and status.state is OperationState.SUCCEEDED
    return allowed, not allowed


def _drive_supervisory_control(case: ParticipantPolicyProbeCase, plane: RuntimeControlPlane) -> tuple[bool, bool]:
    receipt = plane.record_participant_control(
        case.participant_address,
        case.control_intent,
        identity=case.identity,
        crossing_evidence=case.crossing_evidence,
        idempotency_key=case.idempotency_key,
    )
    status = plane.get_operation(receipt.operation_id)
    allowed = status is not None and status.state is OperationState.SUCCEEDED
    return allowed, not allowed


def _drive_egress(case: ParticipantPolicyProbeCase, plane: RuntimeControlPlane) -> tuple[bool, bool]:
    """Project the participant view, then optionally deliver it.

    Projection and participant-directed delivery are separate governed
    transition facts, so a delivery case performs both crossings in order.
    """

    view = plane.get_participant_status_view(
        case.participant_address,
        identity=case.identity,
        crossing_evidence=case.crossing_evidence,
        idempotency_key=case.idempotency_key,
    )
    if case.operation is ParticipantPolicyOperation.STATUS_PROJECTION:
        return view is not None, view is None
    delivered = plane.deliver_participant_directed_view(
        case.participant_address,
        view,
        identity=case.identity,
        crossing_evidence=case.crossing_evidence,
        idempotency_key=f"{case.idempotency_key}-delivery",
    )
    return delivered is not None, delivered is None


_DRIVERS = {
    ParticipantPolicyOperation.ACTION_INGRESS: _drive_ingress,
    ParticipantPolicyOperation.SUPERVISORY_CONTROL: _drive_supervisory_control,
    ParticipantPolicyOperation.STATUS_PROJECTION: _drive_egress,
    ParticipantPolicyOperation.INJECT_DELIVERY: _drive_egress,
}


def _drive(case: ParticipantPolicyProbeCase, plane: RuntimeControlPlane) -> tuple[bool, bool]:
    """Invoke the typed boundary and return ``(released, refused)`` from its raw result."""

    return _DRIVERS[case.operation](case, plane)


def _iter_occurrences(plane: RuntimeControlPlane) -> Iterator[Mapping[str, object]]:
    """Yield every committed crossing occurrence in deterministic order."""

    for participant in sorted(plane.snapshot.participant_crossing_history):
        for entry in plane.snapshot.participant_crossing_history[participant]:
            yield entry.get("occurrence") or {}


def _committed_facts(plane: RuntimeControlPlane) -> tuple[tuple[str, ...], str | None]:
    """Read evidence refs and the last recorded backend posture off the records."""

    evidence_refs: list[str] = []
    effective: str | None = None
    for occurrence in _iter_occurrences(plane):
        posture = occurrence.get("backend_posture")
        if isinstance(posture, str):
            effective = posture
        refs = occurrence.get("required_evidence_refs") or ()
        evidence_refs.extend(ref for ref in refs if isinstance(ref, str) and ref not in evidence_refs)
    return tuple(evidence_refs), effective


def _prepared_plane(
    case: ParticipantPolicyProbeCase,
    target: RuntimeTarget,
) -> tuple[RuntimeControlPlane, _CallCounter | None]:
    """Build the plane on the target under evaluation and run the case's setup."""

    instrumented, counter = _instrumented_target(target)
    # Conformance cases exercise API-423 crossing realization with legacy
    # resolvers that predate the SEM-233 final-sink permit hook, so final-sink
    # flow-control enforcement is explicitly opted out here.
    plane = RuntimeControlPlane(
        instrumented,
        crossing_policy_resolver=case.resolver,
        behavior_specifications=case.behavior_specifications,
        enforce_final_sink_flow_control=False,
    )
    plane.initialize_participant_episode(case.participant_address, episode_id=case.episode_id)
    for request, key in case.setup_requests:
        plane.admit_participant_action(
            case.behavior,
            request,
            identity=case.identity,
            crossing_evidence=case.crossing_evidence,
            idempotency_key=key,
        )
    if counter is not None:
        # Setup admissions are not the obligation, so they must not count as
        # the case's own backend invocations.
        counter.calls = 0
        counter.called_methods.clear()
    return plane, counter


def _run_case(case: ParticipantPolicyProbeCase, target: RuntimeTarget) -> _Outcome:
    """Build the plane on the target, drive the boundary, and measure the result."""

    declared = _declared_level(target, case.feature)
    if declared is None:
        raise ValueError("participant-policy probe names a feature the target does not declare")

    plane, counter = _prepared_plane(case, target)
    before = _ledger(plane)
    try:
        released, refused = _drive(case, plane)
    except (PermissionError, ValueError):
        # Both are the runtime's fail-closed signals: PermissionError for an
        # identity/audience refusal, ValueError for a structural one such as a
        # replay after the state cut advanced. Either way nothing was released,
        # and the side-effect boundary below still has to hold.
        released, refused = False, True
    after = _ledger(plane)

    appended_count = len(after.crossing_records) - len(before.crossing_records)
    dispositions, invalid_reason = _validate_records(plane)
    evidence_refs, effective = _committed_facts(plane)
    return _Outcome(
        released=released,
        refused=refused,
        backend_calls=counter.calls if counter is not None else 0,
        appended_dispositions=dispositions[-appended_count:] if appended_count > 0 else (),
        invalid_reason=invalid_reason,
        mutated_existing=after.crossing_records[: len(before.crossing_records)] != before.crossing_records,
        audited=after.audit_events > before.audit_events,
        declared_support_level=declared,
        effective_support_level=effective if effective is not None else declared,
        evidence_refs=evidence_refs,
        counterexample_ref=f"crossing-disposition:{dispositions[-1]}" if dispositions else None,
    )


__all__ = ("_Outcome", "_run_case")
