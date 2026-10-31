"""Reusable-control and combination probes for mixed-backend capability (issue #1017).

Control cases drive repeated control cycles and a governed action through one
target's supported reusable-control path. Combination cases attempt the joint
configurations that the runtime does not support and report them as
``unsupported``; separate passes never establish a joint capability.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic_core import to_jsonable_python
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_contracts.canonical import canonical_json_digest, jsonable_fallback
from raes_contracts.errors import RaesError
from raes_runtime.control_plane import RuntimeControlPlane

from raes_conformance.conformance.diagnostics import _diagnostic, sanitized_failure_message
from raes_conformance.conformance.mixed_backend_cases import MixedBackendCase
from raes_conformance.conformance.mixed_backend_execution import close_plane
from raes_conformance.conformance.mixed_backend_judging import Verdict, nonce, outcome_of, unsupported
from raes_conformance.conformance.mixed_backend_types import (
    MixedBackendCaseBinding,
    MixedBackendCondition,
    MixedBackendProbeRequest,
    MixedBackendSubject,
    MixedComponentCoordinate,
    MixedControlProbeConfiguration,
    MixedEvidenceRecord,
)
from raes_conformance.conformance.participant_opacity_execution import _qualified_name_of, _raes_version
from raes_conformance.conformance.participant_policy_execution import _instrumented_target

_UNAVAILABLE = "conformance.mixed-configuration-unavailable"
_COMBINATION = "conformance.mixed-combination-unsupported"
_UNREALIZED = "conformance.mixed-condition-unrealized"
_PRODUCER = "runtime:participant-control"


def run_control_case(harness: object, case: MixedBackendCase) -> Verdict:
    """Drive repeated control cycles, then one governed action at the dispatch boundary."""

    configuration = harness.control(MixedBackendProbeRequest(case.case_id, case.subject, nonce()))
    if configuration is None:
        return unsupported(_UNAVAILABLE, case.case_id, "The harness supplied no reusable-control configuration.")
    target, counter = _instrumented_target(configuration.target)
    options: dict[str, object] = {
        "store": configuration.store,
        "behavior_specifications": configuration.behavior_specifications,
        "mixed_control": configuration.mixed_control,
    }
    if configuration.crossing_policy_resolver is not None:
        options["crossing_policy_resolver"] = configuration.crossing_policy_resolver
    failures: list[str] = []
    unrealized: list[str] = []
    plane = RuntimeControlPlane(target, **options)
    try:
        events = _drive_control(case, configuration, plane, counter, failures, unrealized)
    finally:
        cleanup = close_plane(plane, failures)
    if not cleanup:
        failures.append("cleanup: a probe runtime did not close")
    dispatches = counter.called_methods.count("admit_action")
    return _control_verdict(case, configuration, events, failures, cleanup, dispatches, unrealized)


def _drive_control(
    case: MixedBackendCase,
    configuration: MixedControlProbeConfiguration,
    plane: object,
    counter: object,
    failures: list[str],
    unrealized: list[str],
) -> tuple[Mapping[str, object], ...]:
    participant = configuration.participant_address
    plane.initialize_participant_episode(
        participant, episode_id=configuration.episode_id, identity=configuration.identity
    )
    cycles = 4 if case.case_id == "control-repeated-cycles" else 2
    transitions = (configuration.take_transition, configuration.return_transition) * (cycles // 2)
    last: tuple[object, str] | None = None
    for revision, transition in enumerate(transitions):
        key = nonce()
        intent = configuration.control_intent(transition, revision=revision, head=revision, order=revision + 1, key=key)
        state, occurrence = _control(plane, configuration, intent, key)
        _require(failures, state == "succeeded", f"control cycle {revision + 1} ended {state}")
        _require(
            failures,
            occurrence.get("disposition") == "accepted" and occurrence.get("resulting_state_revision") == revision + 1,
            f"control cycle {revision + 1} did not advance exactly one revision",
        )
        last = (intent, key)
    if case.case_id == "control-repeated-cycles" and last is not None:
        _retry_and_stale(configuration, plane, last, cycles, failures)
    history = _history(plane, participant)
    admits = counter.called_methods.count("admit_action")
    behavior = len(plane.snapshot.participant_behavior_history.get(participant, ()))
    if (
        case.condition is not MixedBackendCondition.NOMINAL
        and configuration.apply_condition(case.condition) is not True
    ):
        unrealized.append(f"The harness cannot realize the {case.condition.value} condition.")
        return history
    receipt = plane.admit_participant_action(
        configuration.behavior,
        configuration.admission_request,
        identity=configuration.actor_identity,
        crossing_evidence=configuration.crossing_evidence,
        idempotency_key=nonce(),
    )
    status = plane.get_operation(receipt.operation_id)
    codes = [item.code for item in status.diagnostics]
    behavior_delta = len(plane.snapshot.participant_behavior_history.get(participant, ())) - behavior
    _require(failures, counter.called_methods.count("admit_action") - admits == 1, "the action did not dispatch once")
    _require(failures, len(_history(plane, participant)) == len(history), "the action changed the control history")
    if case.condition is MixedBackendCondition.DISPATCH_REFUSED:
        _require(failures, status.state.value == "failed", f"a refused dispatch ended {status.state.value}")
        _require(failures, any(not code.startswith("runtime.control-plane.") for code in codes), "no backend refusal")
        _require(failures, behavior_delta == 0, "a refused dispatch reached participant history")
    else:
        _require(failures, status.state.value == "succeeded", f"the action after the cycles ended {status.state.value}")
        _require(failures, behavior_delta >= 1, "the accepted action reached no participant history")
    return _history(plane, participant)


def _retry_and_stale(
    configuration: MixedControlProbeConfiguration,
    plane: object,
    last: tuple[object, str],
    cycles: int,
    failures: list[str],
) -> None:
    participant = configuration.participant_address
    before = len(_history(plane, participant))
    intent, key = last
    _control(plane, configuration, intent, key)
    _require(failures, len(_history(plane, participant)) == before, "an exact control retry appended a new fact")
    stale_key = nonce()
    stale = configuration.control_intent(
        configuration.take_transition, revision=0, head=0, order=cycles + 1, key=stale_key
    )
    state, occurrence = _control(plane, configuration, stale, stale_key)
    _require(failures, state != "succeeded", "a stale control proposal succeeded")
    _require(
        failures,
        occurrence.get("disposition") == "rejected"
        and occurrence.get("attempted", {}).get("expected_state_revision") == 0
        and occurrence.get("observed", {}).get("state_revision") == cycles,
        "a stale control proposal was not rejected at its attempted and observed coordinates",
    )


def _control(
    plane: object,
    configuration: MixedControlProbeConfiguration,
    intent: object,
    key: str,
) -> tuple[str, Mapping[str, object]]:
    options = {} if configuration.crossing_evidence is None else {"crossing_evidence": configuration.crossing_evidence}
    receipt = plane.record_participant_control(
        configuration.participant_address, intent, identity=configuration.identity, idempotency_key=key, **options
    )
    history = _history(plane, configuration.participant_address)
    occurrence = history[-1].get("occurrence", {}) if history else {}
    return plane.get_operation(receipt.operation_id).state.value, occurrence


def _history(plane: object, participant: str) -> tuple[Mapping[str, object], ...]:
    return tuple(plane.snapshot.participant_control_history.get(participant, ()))


def _require(failures: list[str], condition: bool, failure: str) -> None:
    if not condition:
        failures.append(failure)


def _control_verdict(
    case: MixedBackendCase,
    configuration: MixedControlProbeConfiguration,
    events: tuple[Mapping[str, object], ...],
    failures: list[str],
    cleanup: bool,
    dispatches: int,
    unrealized: list[str],
) -> Verdict:
    target = configuration.target
    payload = backend_manifest_payload(target.manifest)
    component = MixedComponentCoordinate(
        component_id=target.name,
        target_name=target.name,
        backend_name=payload["identity"]["name"],
        backend_version=payload["identity"]["version"],
        manifest_digest=canonical_json_digest(payload),
    )
    records = tuple(
        MixedEvidenceRecord(
            position=index,
            kind="control-occurrence",
            producer_ref=_PRODUCER,
            digest=canonical_json_digest(event),
            status=str(event.get("occurrence", {}).get("disposition")),
        )
        for index, event in enumerate(events)
    )
    binding = MixedBackendCaseBinding(
        subject=case.subject.value,
        condition=case.condition.value,
        obligation_ref=f"{configuration.take_transition}/{configuration.return_transition}",
        expected_state=case.expected_state,
        control_policies=_control_policies(configuration),
        components=(component,),
        evidence=records,
    )
    # Observed failures and cleanup take precedence over an unrealized condition.
    outcome = outcome_of(failures, bool(unrealized))
    return Verdict(
        outcome=outcome,
        failures=tuple(failures),
        diagnostics=tuple(_diagnostic(_UNREALIZED, case.case_id, reason) for reason in unrealized),
        binding=binding,
        configuration_digest=control_configuration_digest(configuration),
        target_binding=f"backend-target:{target.name}",
        expected_operations=("participant-runtime.admit_action=1",),
        accounted_operations=(f"participant-runtime.admit_action={dispatches}",),
        limitations=(
            "Reusable control ran on one target; the joint mixed-runtime path is a separate unsupported case.",
        ),
        cleanup_verified=cleanup,
    )


def _control_policies(configuration: MixedControlProbeConfiguration) -> tuple[str, ...]:
    policies = (getattr(spec, "mixed_control_policy", None) for spec in configuration.behavior_specifications.values())
    return tuple(sorted({f"{policy.address}@{policy.policy_revision}" for policy in policies if policy is not None}))


def control_configuration_digest(configuration: MixedControlProbeConfiguration) -> str:
    """Digest the runtime, backend and compiled specification and policy contents that executed."""

    target = configuration.target
    return canonical_json_digest(
        {
            "runtime": {"implementation": _qualified_name_of(RuntimeControlPlane), "raes_version": _raes_version()},
            "manifest_digest": canonical_json_digest(backend_manifest_payload(target.manifest)),
            "participant_runtime": _qualified_name_of(type(target.participant_runtime)),
            "behavior_specifications": {
                address: canonical_json_digest(to_jsonable_python(specification, fallback=jsonable_fallback))
                for address, specification in sorted(configuration.behavior_specifications.items())
            },
            "transitions": [configuration.take_transition, configuration.return_transition],
        }
    )


def run_combination_case(harness: object, case: MixedBackendCase) -> Verdict:
    """Attempt a joint configuration; any result stays unsupported."""

    prepared = _combination_inputs(harness, case)
    if isinstance(prepared, Verdict):
        return prepared
    return _attempt_combination(case, *prepared)


def _combination_inputs(harness: object, case: MixedBackendCase) -> tuple[object, dict[str, object]] | Verdict:
    composition = harness.composition(MixedBackendProbeRequest(case.case_id, MixedBackendSubject.EDGE, nonce()))
    control = None
    reason: tuple[str, str] | None = None
    if composition is None:
        reason = (_UNAVAILABLE, "The harness supplied no composition configuration.")
    elif case.case_id == "combination-reusable-control-with-mixed-runtime":
        control = harness.control(MixedBackendProbeRequest(case.case_id, MixedBackendSubject.CONTROL, nonce()))
        if control is None:
            reason = (_UNAVAILABLE, "The harness supplied no reusable-control configuration.")
    elif composition.distributed_execution is None:
        reason = (_COMBINATION, "No distributed dispatcher is configured; portable services run only locally.")
    if reason is not None:
        return unsupported(reason[0], case.case_id, reason[1])
    options: dict[str, object] = {
        "mixed_runtime": composition.binding,
        "crossing_policy_resolver": composition.crossing_policy_resolver,
        "run_scope": f"run:{composition.binding.entry.run_id}",
        "store": composition.store,
    }
    if control is None:
        options["distributed_execution"] = composition.distributed_execution
        return composition.target, options
    options.update(behavior_specifications=control.behavior_specifications, mixed_control=control.mixed_control)
    return control.target, options


def _attempt_combination(case: MixedBackendCase, target: object, options: dict[str, object]) -> Verdict:
    try:
        plane = RuntimeControlPlane(target, **options)
    except (ValueError, RaesError) as exc:
        # The runtime configuration validator refuses an unsupported combination with ValueError (rule E3).
        # Any other failure reaches the isolation handler of the case runner.
        message = f"The runtime refused the combination ({sanitized_failure_message(exc)})."
        return unsupported(_COMBINATION, case.case_id, message)
    failures: list[str] = []
    cleanup = close_plane(plane, failures)
    accepted = _diagnostic(
        _COMBINATION, case.case_id, "The runtime accepted the combination, but no joint probe exists."
    )
    return Verdict(
        outcome_of(failures, True), failures=tuple(failures), diagnostics=(accepted,), cleanup_verified=cleanup
    )


__all__ = ["control_configuration_digest", "run_combination_case", "run_control_case"]
