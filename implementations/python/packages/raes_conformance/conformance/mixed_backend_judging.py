"""Runner-owned verdicts for mixed-backend edge and handoff cases.

The drivers in ``mixed_backend_probes`` collect facts from the shared runtime;
the functions here compare those facts with the case catalog. A negative case
passes only when the correct rejection occurs. Expected time comparisons come
from the admitted time model, never from a backend answer.
"""

from __future__ import annotations

import secrets
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from raes_contracts.contracts.time_model import TimeRuntimeStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_runtime.control_plane_store import NewClaimRejected

from raes_conformance.conformance.diagnostics import _diagnostic
from raes_conformance.conformance.mixed_backend_cases import MixedBackendCase, cut_comparison
from raes_conformance.conformance.mixed_backend_execution import (
    EFFECT_METHODS,
    OperationRead,
    binding_digest,
    component_coordinates,
    configuration_digest,
    evidence_records,
    service_coordinates,
)
from raes_conformance.conformance.mixed_backend_types import (
    MixedBackendCaseBinding,
    MixedCompositionProbeConfiguration,
)

_ADMISSION_REFUSED = "runtime.control-plane.backend-admission-refused"
_GRANT = "coordinator.grant"
_BRIDGE_START = "bridge.start_operation"
_TRANSFER_START = "transfer.start_operation"


@dataclass(frozen=True)
class Verdict:
    """Everything the runner judged for one case."""

    outcome: str
    failures: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    binding: MixedBackendCaseBinding | None = None
    configuration_digest: str | None = None
    profile_digest: str | None = None
    target_binding: str | None = None
    expected_operations: tuple[str, ...] = ()
    accounted_operations: tuple[str, ...] = ()
    residual_state: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    cleanup_verified: bool | None = None


def outcome_of(failures: Sequence[str], unrealized: bool) -> str:
    """Rank an observed failure above an unrealized condition, and that above a pass."""

    if failures:
        return "failed"
    if unrealized:
        return "unsupported"
    return "passed"


def unsupported(code: str, address: str, message: str) -> Verdict:
    return Verdict("unsupported", diagnostics=(_diagnostic(code, address, message),))


def nonce() -> str:
    return secrets.token_hex(16)


@dataclass
class CompositionRun:
    """Facts and findings for one edge or handoff case."""

    case: MixedBackendCase
    configuration: MixedCompositionProbeConfiguration
    installation: object
    failures: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    expected: dict[str, int] = field(default_factory=dict)
    calls: Counter[str] = field(default_factory=Counter)
    read: OperationRead = field(default_factory=OperationRead)
    requested_cut: TimeRuntimeStateModel | None = None
    unrealized: str | None = None
    key: str | None = None
    cleanup: bool = True

    @property
    def declaration(self) -> object:
        return self.installation.binding

    @property
    def run_id(self) -> str:
        return self.configuration.binding.entry.run_id

    def check(self, condition: bool, failure: str) -> None:
        if not condition:
            self.failures.append(failure)

    def expect_calls(self, expected: Mapping[str, int], observed: Counter[str]) -> None:
        self.expected = dict(expected)
        for label, count in expected.items():
            self.check(observed.get(label, 0) == count, f"{label} ran {observed.get(label, 0)} times, not {count}")


@dataclass(frozen=True)
class EdgeFacts:
    """What the runtime retained for one edge submission and its exact replay."""

    read: OperationRead
    appended: Sequence[Mapping[str, object]]
    behavior_delta: int
    committed: TimeRuntimeStateModel | None
    order: Sequence[str]
    component_admits: int
    replay: OperationRead | None = None
    replay_calls: Counter[str] = field(default_factory=Counter)


def _kinds(events: Sequence[Mapping[str, object]], operation_id: str | None) -> list[str]:
    prefix = f"composition:{operation_id}:"
    return [str(event["event_kind"]) for event in events if str(event["event_id"]).startswith(prefix)]


def _first(order: Sequence[str], label: str) -> int:
    return order.index(label) if label in order else len(order)


def judge_edge(run: CompositionRun, facts: EdgeFacts) -> None:
    """Judge one edge case from retained facts."""

    run.read = read = facts.read
    case = run.case
    kinds = _kinds(facts.appended, read.operation_id)
    run.check(facts.component_admits == 0, "the runtime called a component runtime outside the pinned bridge")
    if case.expected_state is not None:
        run.check(read.state == case.expected_state, f"operation state {read.state}, not {case.expected_state}")
    grant = read.stage("time-grant")
    if case.case_id == "edge-refused-before-claim":
        run.check(read.accepted is False, "a withdrawn backend did not refuse admission")
        run.check(_ADMISSION_REFUSED in read.diagnostic_codes, "the refusal is not the backend admission refusal")
        run.check(run.calls.get("bridge.check_operation", 0) >= 1, "the bridge was not asked for admission")
        run.expect_calls({_GRANT: 0, _BRIDGE_START: 0}, run.calls)
        run.check(not kinds, "an audit-only refusal appended composition facts")
        return
    run.check(read.accepted is True, "the operation was not accepted")
    if case.time_variant != "nominal":
        run.check(read.stages() == ("time-grant",), f"retained stages {read.stages()}, not the grant alone")
        run.check(grant is not None and grant.comparison == "incomparable", "the coordinator did not refuse the order")
        run.expect_calls({_GRANT: 1, _BRIDGE_START: 0}, run.calls)
    elif case.case_id == "edge-refused-after-time-grant":
        run.check(read.stages() == ("time-grant",), f"retained stages {read.stages()}, not the grant alone")
        run.check(run.calls.get("bridge.check_operation", 0) >= 2, "willingness was not checked again after the grant")
        run.check(read.reserved is False, "a cancelled pre-dispatch operation kept its reservation")
        run.expect_calls({_GRANT: 1, _BRIDGE_START: 0}, run.calls)
    elif case.case_id == "edge-start-refused":
        run.check(read.stages() == ("time-grant",), f"retained stages {read.stages()}, not the grant alone")
        run.check("acknowledgement:refused" in read.responses, "no refused acknowledgement was retained")
        run.check(read.reserved is True, "a consumed grant released its reservation without evidence")
        run.expect_calls({_GRANT: 1, _BRIDGE_START: 1}, run.calls)
    elif case.case_id == "edge-partial-execution":
        execution = read.stage("execution")
        run.check(execution is not None and execution.status in {"partial", "unknown"}, "partial execution was hidden")
        run.check(read.residual, "partial execution retained no residual state")
        run.check(read.reserved is True, "partial execution released its reservation")
        run.expect_calls({_GRANT: 1, _BRIDGE_START: 1}, run.calls)
    elif case.case_id == "edge-missing-delivery":
        execution = read.stage("execution")
        run.check(read.stages() == ("time-grant", "execution"), f"retained stages {read.stages()}")
        run.check(execution is not None and execution.status == "succeeded", "execution was not retained")
        run.check(read.reserved is True, "unresolved delivery released its reservation")
        run.expect_calls({_GRANT: 1, _BRIDGE_START: 1}, run.calls)
    else:
        _judge_execution(run, facts, kinds)
    if case.expected_state != "succeeded" and case.case_id != "edge-partial-execution":
        run.check(
            not set(kinds) & {"delivery", "observation"}, "delivery or observation was published without its evidence"
        )


def _judge_execution(run: CompositionRun, facts: EdgeFacts, kinds: list[str]) -> None:
    read, subject = facts.read, run.declaration.subject
    readers = ("delivery",) + (("observation",) if subject.observation_reader is not None else ())
    if subject.observation_reader is None:
        run.limitations.append("The binding declares no observation reader; no observation is claimed.")
    run.check(read.stages() == ("time-grant", "execution", *readers), f"retained stages {read.stages()}")
    grant, execution = read.stage("time-grant"), read.stage("execution")
    model = run.configuration.binding.context.time_models[subject.time.time_model_ref]
    expected = None if facts.committed is None else cut_comparison(subject.time, model, facts.committed)
    run.check(expected == "ordered", "the nominal cut is not ordered under the admitted mapping")
    run.check(grant is not None and grant.comparison == expected, "the grant differs from the admitted mapping")
    run.check(execution is not None and execution.status == "succeeded", "execution did not succeed")
    delivery = read.stage("delivery")
    run.check(
        delivery is not None and delivery.destination_component_id == subject.owner_component_id,
        "delivery was not read back at the destination provider",
    )
    _judge_request(run, read, subject)
    _judge_allocation(run, facts, kinds)
    _judge_chain(run, facts, subject)
    run.check(facts.behavior_delta >= 1, "the native result reached no participant history")
    run.check(facts.replay is not None and facts.replay.operation_id == read.operation_id, "replay was not exact")
    run.check(_effect_calls(facts.replay_calls) == 0, "an exact replay called an installed service again")


def _judge_request(run: CompositionRun, read: OperationRead, subject: object) -> None:
    run.check(read.post_time, "no post-invocation time readback was retained")
    run.check(read.reserved is False, "a settled operation kept its reservation")
    run.check(read.request_backend == subject.bridge.service_ref, "the request did not name the pinned bridge")
    run.check(read.request_command == binding_digest(run.declaration), "the request did not commit to the binding")


def _judge_chain(run: CompositionRun, facts: EdgeFacts, subject: object) -> None:
    order = facts.order
    labels = (_GRANT, _BRIDGE_START, "bridge.stage_reports", "delivery-reader.read_stage")
    positions = [_first(order, label) for label in labels]
    run.check(positions == sorted(positions) and positions[-1] < len(order), "stages ran out of chain order")
    expected_calls = dict.fromkeys(labels, 1)
    if subject.observation_reader is not None:
        expected_calls["observation-reader.read_stage"] = 1
    run.expect_calls(expected_calls, run.calls)


def _effect_calls(calls: Counter[str]) -> int:
    return sum(count for label, count in calls.items() if label.rsplit(".", 1)[-1] in EFFECT_METHODS)


def _judge_allocation(run: CompositionRun, facts: EdgeFacts, kinds: list[str]) -> None:
    subject = run.declaration.subject
    profile = run.configuration.binding.profile
    allocation = profile.allocations.get(subject.owner_allocation_id)
    run.check(
        allocation is not None and allocation.provider_component_id == subject.owner_component_id,
        "the binding owner is not the admitted action allocation's provider",
    )
    prefix = f"composition:{facts.read.operation_id}:"
    attempts = [e for e in facts.appended if e["event_id"] == f"{prefix}attempt"]
    run.check(len(attempts) == 1, "no single committed attempt was retained")
    if attempts:
        attempt = attempts[0]
        observed = (
            attempt.get("component_id"),
            attempt.get("allocation_id"),
            attempt.get("edge_id"),
            attempt.get("mapping_ref"),
            tuple(attempt.get("mapping_loss_refs") or ()),
        )
        admitted = (
            subject.owner_component_id,
            subject.owner_allocation_id,
            subject.edge_id,
            subject.time.mapping_ref,
            (subject.mapping_loss.limitation_ref,),
        )
        run.check(observed == admitted, "the attempt differs from the admitted allocation, mapping or loss")
    run.limitations.append(f"Declared mapping loss: {subject.mapping_loss.limitation_ref}.")
    for kind in ("delivery", "observation") if subject.observation_reader is not None else ("delivery",):
        run.check(kind in kinds, f"no {kind} fact was published")


@dataclass(frozen=True)
class HandoffAttempt:
    """One transfer attempt, the cut before it and the role calls it caused."""

    read: OperationRead
    before: Mapping[str, object]
    after: Mapping[str, object]
    calls: Counter[str]


def judge_handoff(run: CompositionRun, attempts: Sequence[HandoffAttempt], replay: HandoffAttempt | None) -> None:
    """Judge a handoff case from its attempts and the exact replay of the committed one."""

    subject = run.declaration.subject
    for index, attempt in enumerate(attempts):
        run.calls.update(attempt.calls)
        expected = _handoff_expectation(run.case.case_id, index)
        _judge_transfer(run, attempt, expected, subject)
    if run.case.case_id == "handoff-repeated-transition" and len(attempts) == 3:
        _judge_repeated(run, *attempts)
    if replay is not None:
        committed = next((a for a in attempts if a.read.state == "succeeded"), None)
        run.check(
            committed is not None and replay.read.operation_id == committed.read.operation_id, "replay was not exact"
        )
        run.check(_effect_calls(replay.calls) == 0, "an exact replay called an installed service again")
    run.read = next((a.read for a in attempts if a.read.state == run.case.expected_state), attempts[-1].read)
    starts = 2 if len(attempts) == 3 else 1
    run.expected = {_GRANT: starts, _TRANSFER_START: starts}


def _judge_repeated(run: CompositionRun, first: HandoffAttempt, second: HandoffAttempt, third: HandoffAttempt) -> None:
    """Require a fresh invocation per attempt and a claim refusal once the phase has moved."""

    run.check(second.read.invocation_id != first.read.invocation_id, "a repeated attempt reused an invocation")
    effects = sum(third.calls.get(label, 0) for label in (_GRANT, _TRANSFER_START))
    run.check(effects == 0, "an attempt from a moved phase granted or transferred again")
    transition = run.configuration.binding.profile.transitions[run.configuration.obligation_id]
    run.check(third.before.get("phase_id") == transition.target_phase_id, "the phase did not move before")
    run.check(
        third.read.refusal_type is not None and issubclass(third.read.refusal_type, NewClaimRejected),
        "an attempt from a moved phase was not refused by the current-state claim boundary",
    )
    run.check(third.after == third.before, "an attempt from a moved phase changed the cut")


def _handoff_expectation(case_id: str, index: int) -> str | None:
    if case_id == "handoff-repeated-transition":
        return ("failed", "succeeded", None)[index]
    return "failed" if case_id == "handoff-stale-transfer" else "succeeded"


def _judge_transfer(run: CompositionRun, attempt: HandoffAttempt, expected: str | None, subject: object) -> None:
    if expected is None:
        return
    read, revision = attempt.read, attempt.before.get("phase_revision")
    if not isinstance(revision, int):
        run.failures.append("no committed composition cut preceded the transfer")
        return
    run.check(read.state == expected, f"transfer state {read.state}, not {expected}")
    run.check(read.stages() == ("time-grant", "handoff", "owner-readback"), f"retained stages {read.stages()}")
    transfer, owner = read.stage("handoff"), read.stage("owner-readback")
    run.check(
        transfer is not None
        and (transfer.predecessor_history_head, transfer.phase_revision)
        == (attempt.before.get("history_head"), revision),
        "the transfer did not fence on the committed head and revision",
    )
    committed = expected == "succeeded"
    owner_coordinates = (
        (subject.destination_component_id, subject.destination_owner_ref, revision + 1)
        if committed
        else (subject.source_component_id, subject.source_owner_ref, revision)
    )
    run.check(
        owner is not None and (owner.owner_component_id, owner.owner_ref, owner.phase_revision) == owner_coordinates,
        "the owner readback does not confirm the settled responsibility",
    )
    run.check(attempt.after.get("phase_revision") == (revision + 1 if committed else revision), "the phase is wrong")
    run.check(read.post_time, "no post-invocation time readback was retained")
    status = None if transfer is None else transfer.status
    run.check(
        (status == "committed") if committed else (status in {"stale", "failed"}),
        "the transfer status does not match the settled responsibility",
    )
    run.check(attempt.calls.get(_TRANSFER_START, 0) == 1, "the transfer did not start exactly once")
    run.check(attempt.calls.get("owner-reader.read_stage", 0) == 1, "the owner was not read back exactly once")


def accounting(expected: Mapping[str, int], calls: Counter[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Render expected and observed counts of the effect-bearing role calls."""

    labels = sorted({*expected, *(label for label in calls if label.rsplit(".", 1)[-1] in EFFECT_METHODS)})
    return (
        tuple(f"{label}={expected.get(label, 0)}" for label in labels),
        tuple(f"{label}={calls.get(label, 0)}" for label in labels),
    )


def composition_verdict(run: CompositionRun) -> Verdict:
    """Assemble the verdict and resolvable coordinates of one composition case."""

    run.check(run.cleanup, "cleanup: a probe runtime did not close")
    # Observed failures and cleanup take precedence: an unrealized condition
    # never hides what an opened runtime already showed.
    outcome = outcome_of(run.failures, run.unrealized is not None)
    diagnostics = ()
    if run.unrealized is not None:
        diagnostics = (_diagnostic("conformance.mixed-condition-unrealized", run.case.case_id, run.unrealized),)
    binding, declaration = run.configuration.binding, run.declaration
    subject, time = declaration.subject, declaration.subject.time
    expected_ops, accounted_ops = accounting(run.expected, run.calls)
    records = evidence_records(run.read)
    case_binding = MixedBackendCaseBinding(
        subject=run.case.subject.value,
        condition=run.case.condition.value,
        obligation_ref=run.configuration.obligation_id,
        profile_id=binding.profile.profile_id,
        profile_revision=binding.profile.profile_revision,
        profile_digest=binding.profile.profile_digest,
        plan_id=binding.plan.plan_id,
        plan_entry_id=binding.plan_entry_id,
        run_id=run.run_id,
        binding_id=declaration.binding_id,
        binding_digest=binding_digest(declaration),
        time_model_ref=time.time_model_ref,
        time_model_digest=time.time_model_digest,
        source_clock=time.source_clock_address,
        destination_clock=time.destination_clock_address,
        mapping_ref=time.mapping_ref,
        ordering_basis=time.ordering_basis,
        temporal_coupling=getattr(time, "temporal_coupling", None),
        mapping_loss_ref=subject.mapping_loss.limitation_ref if subject.kind == "edge" else None,
        expected_state=run.case.expected_state,
        observed_state=run.read.state,
        components=component_coordinates(binding),
        services=service_coordinates(declaration),
        evidence=records,
    )
    return Verdict(
        outcome=outcome,
        failures=tuple(run.failures),
        diagnostics=diagnostics,
        binding=case_binding,
        configuration_digest=configuration_digest(binding, declaration, run.configuration.supervision),
        profile_digest=binding.profile.profile_digest,
        target_binding=f"mixed-composition:{binding.plan.plan_id}:{binding.plan_entry_id}",
        expected_operations=expected_ops,
        accounted_operations=accounted_ops,
        residual_state=(f"operation:{run.read.operation_id}:reserved",) if run.read.reserved else (),
        evidence_refs=tuple(dict.fromkeys(ref for record in records for ref in record.evidence_refs)),
        limitations=tuple(dict.fromkeys(run.limitations)),
        cleanup_verified=run.cleanup,
    )


__all__ = [
    "CompositionRun",
    "EdgeFacts",
    "HandoffAttempt",
    "Verdict",
    "accounting",
    "composition_verdict",
    "judge_edge",
    "judge_handoff",
    "nonce",
    "outcome_of",
    "unsupported",
]
