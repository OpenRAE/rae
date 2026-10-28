"""Public runner for executable mixed-backend capability probes (issue #1017).

**The runner owns execution, expectations and the verdict.** A trusted
in-process harness realizes backend conditions and returns fresh configuration
for each case. The runner instruments that configuration, drives the shared
``RuntimeControlPlane`` and judges what the runtime retained. Every case uses
the ``hermetic-live`` basis: an in-process service is never concrete backend
realization, so the runner never sets ``native_conformance``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import replace

from raes_contracts.contracts import validate_mixed_backend_bindings

from raes_conformance.conformance.diagnostics import _diagnostic, sanitized_failure_message
from raes_conformance.conformance.mixed_backend_cases import (
    PROBE_REVISION,
    MixedBackendCase,
    binding_variant,
    cut_comparison,
    probe_digest,
    probe_set_digest,
    requested_time_state,
    select_cases,
)
from raes_conformance.conformance.mixed_backend_execution import (
    Instrumented,
    close_plane,
    composition_cut,
    composition_history,
    instrument,
    open_plane,
    probed_installation,
    submit,
    tool_digest,
)
from raes_conformance.conformance.mixed_backend_judging import (
    CompositionRun,
    EdgeFacts,
    HandoffAttempt,
    Verdict,
    composition_verdict,
    judge_edge,
    judge_handoff,
    nonce,
    unsupported,
)
from raes_conformance.conformance.mixed_backend_types import (
    MixedBackendCondition,
    MixedBackendProbeHarness,
    MixedBackendProbeRequest,
    MixedBackendSubject,
    MixedCompositionProbeConfiguration,
    require_environment_digest,
)
from raes_conformance.conformance.mixed_control_probes import run_combination_case, run_control_case
from raes_conformance.conformance.report import (
    BackendConformanceReport,
    ConformanceCaseResult,
    _bounded_conformance_claim,
    validate_backend_conformance_report,
)
from raes_conformance.realization import ExecutionBasis

MIXED_BACKEND_PROBE_FAMILY = "mixed-backend-execution"
_PROBE_KIND = "mixed-backend-executed-case"
_CONTRACTS = {
    MixedBackendSubject.EDGE: "mixed-backend-execution-binding-v1",
    MixedBackendSubject.HANDOFF: "mixed-backend-execution-binding-v1",
    MixedBackendSubject.CONTROL: "participant-control-occurrence-v2",
    MixedBackendSubject.COMBINATION: "mixed-backend-execution-binding-v1",
}
_STANDING_LIMITATIONS = (
    "Installed services ran in process under the shared runtime; this is not concrete backend realization.",
    "Native translation inside a pinned service is not observed independently of that service.",
)
_NON_CLAIMS = (
    "Does not establish backend-native realization or conformance.",
    "Does not establish exactly-once external effects, physical timing or backend equivalence.",
    "Does not establish behavior for unexecuted cuts, conditions or configurations.",
)
_UNAVAILABLE = "conformance.mixed-configuration-unavailable"
_NOMINAL = MixedBackendCondition.NOMINAL


def run_mixed_backend_conformance(
    harness: MixedBackendProbeHarness,
    *,
    cases: Iterable[str] | None = None,
) -> BackendConformanceReport:
    """Run the selected mixed-backend cases, or every catalog case, through the shared runtime.

    Each case requests fresh configuration, so every case runs independently.
    The report passes only when every selected case passes. An unsupported
    case never passes and is also listed in ``unsupported_capability_gaps``.
    """

    selected = select_cases(cases)
    environment = require_environment_digest(getattr(harness, "environment_digest", None))
    set_digest = probe_set_digest(selected)
    results = tuple(_run_case(harness, case, environment, set_digest) for case in selected)
    report = BackendConformanceReport(
        profile=MIXED_BACKEND_PROBE_FAMILY,
        passed=all(result.passed for result in results),
        claim=_bounded_conformance_claim(
            profile=MIXED_BACKEND_PROBE_FAMILY,
            cases=results,
            left_carrier_ref=f"mixed-backend-harness:{environment}",
            subject="Executable mixed-backend capability for the selected cases",
            right_carrier_ref=f"mixed-backend-probe-catalog:{PROBE_REVISION}",
            evidence_boundary=(
                f"The {len(results)} named mixed-backend cases recorded in this report, each executed once "
                "in the shared runtime; no unexecuted cut, condition or configuration is quantified."
            ),
        ),
        cases=results,
        unsupported_capability_gaps=tuple(result.name for result in results if result.outcome == "unsupported"),
        probe_set_digest=set_digest,
    )
    return validate_backend_conformance_report(report)


def _run_case(harness: object, case: MixedBackendCase, environment: str, set_digest: str) -> ConformanceCaseResult:
    try:
        if case.subject is MixedBackendSubject.CONTROL:
            verdict = run_control_case(harness, case)
        elif case.subject is MixedBackendSubject.COMBINATION:
            verdict = run_combination_case(harness, case)
        else:
            verdict = _composition_case(harness, case)
    except Exception as exc:
        failure = _diagnostic("conformance.mixed-case-error", case.case_id, sanitized_failure_message(exc))
        verdict = Verdict("failed", diagnostics=(failure,))
    return _case_result(case, verdict, environment, set_digest)


def _case_result(case: MixedBackendCase, verdict: Verdict, environment: str, set_digest: str) -> ConformanceCaseResult:
    diagnostics = list(verdict.diagnostics)
    if verdict.failures:
        diagnostics.append(_diagnostic("conformance.mixed-case-failed", case.case_id, "; ".join(verdict.failures)))
    executed = verdict.binding is not None
    return ConformanceCaseResult(
        name=case.case_id,
        contract_name=_CONTRACTS[case.subject],
        valid=True,
        passed=verdict.outcome == "passed",
        outcome=verdict.outcome,
        diagnostics=tuple(diagnostics),
        execution_basis=ExecutionBasis.HERMETIC_LIVE.value,
        probe_kind=_PROBE_KIND,
        probe_digest=probe_digest(case),
        probe_set_digest=set_digest,
        configuration_digest=verdict.configuration_digest,
        target_binding=verdict.target_binding,
        expected_operations=verdict.expected_operations,
        accounted_operations=verdict.accounted_operations,
        cleanup_verified=verdict.cleanup_verified,
        residual_state=verdict.residual_state,
        evidence_refs=verdict.evidence_refs,
        finite_scope=f"Case {case.case_id}: {case.claim} One execution of the configuration recorded in mixed_binding.",
        limitations=(*verdict.limitations, *_STANDING_LIMITATIONS),
        explicit_non_claims=_NON_CLAIMS,
        realization_owner="installed-service" if executed else None,
        evidence_origin="observed-execution" if executed else None,
        profile_digest=verdict.profile_digest,
        tool_digest=tool_digest(),
        environment_digest=environment,
        mixed_binding=verdict.binding,
    )


def _composition_case(harness: object, case: MixedBackendCase) -> Verdict:
    request = MixedBackendProbeRequest(case.case_id, case.subject, nonce())
    configuration = harness.composition(request)
    if configuration is None:
        return unsupported(_UNAVAILABLE, case.case_id, "The harness supplied no configuration.")
    installation = probed_installation(configuration.binding, case.subject.value, configuration.obligation_id)
    if installation is None:
        return unsupported(
            "conformance.mixed-portable-installation-missing",
            case.case_id,
            "No installed portable services bind the probed obligation; a declaration does not establish execution.",
        )
    missing = _missing_inputs(configuration, case.subject)
    if missing:
        return Verdict("failed", failures=tuple(missing))
    run = CompositionRun(case, configuration, installation)
    if case.binding_variant is not None:
        _binding_variant(harness, run, request)
        return composition_verdict(run)
    if case.time_variant != "nominal":
        requested = _requested_cut(harness, run, request)
        installation = (
            None
            if requested is None
            else probed_installation(requested.binding, case.subject.value, requested.obligation_id)
        )
        if installation is None:
            run.unrealized = "The harness did not supply the requested time cut."
            return composition_verdict(run)
        run.configuration, run.installation = requested, installation
    _execute(harness, run, request)
    return composition_verdict(run)


def _missing_inputs(configuration: MixedCompositionProbeConfiguration, subject: MixedBackendSubject) -> list[str]:
    """Refuse configuration whose baseline inputs could make a negative case pass for another reason."""

    required = ["target", "crossing_policy_resolver", "store", "identity", "obligation_id"]
    if subject is MixedBackendSubject.EDGE:
        required += ["participant_address", "episode_id", "behavior", "admission_request"]
    return [f"the configuration supplies no {name}" for name in required if getattr(configuration, name) is None]


def _requested_cut(
    harness: object,
    run: CompositionRun,
    request: MixedBackendProbeRequest,
) -> MixedCompositionProbeConfiguration | None:
    """Read the nominal committed cut, derive the requested cut and request it."""

    plane = open_plane(run.configuration, run.configuration.binding)
    try:
        nominal = plane.snapshot.time_model_state
    finally:
        run.cleanup = close_plane(plane, run.failures) and run.cleanup
    required = run.declaration.subject.time
    model = run.configuration.binding.context.time_models[required.time_model_ref]
    requested, discriminating = requested_time_state(run.case, required, model, nominal)
    if cut_comparison(required, model, requested) != "incomparable":
        raise ValueError("the derived cut is not incomparable under the admitted mapping")
    run.requested_cut = requested
    run.limitations.append(
        "The requested cut distinguishes the admitted mapping from identity."
        if discriminating
        else "The requested cut does not distinguish the admitted mapping from identity."
    )
    return harness.composition(replace(request, collection_id=nonce(), time_state=requested))


def _binding_variant(harness: object, run: CompositionRun, request: MixedBackendProbeRequest) -> None:
    """Require the binding owner to refuse a missing or contradictory installation before any call.

    The unmodified installation set passes the same rebuild first, so an
    unrelated defect fails the case instead of passing as the expected refusal.
    """

    binding, obligation = run.configuration.binding, run.configuration.obligation_id
    instrument(binding, obligation)
    key = run.declaration.binding_id
    installed = {item_key: item for item_key, item in binding.backend_installations.items() if item_key != key}
    mutated = binding_variant(run.case, run.declaration)
    if mutated is not None:
        installed[key] = replace(run.installation, binding=mutated)
    declarations = [item.binding for item in installed.values()]
    if declarations:
        run.check(_owner_refuses(binding, declarations), "the binding owner admitted the variant")
        try:
            instrument(binding, obligation, installations=installed)
        except ValueError as exc:
            run.limitations.append(f"The binding owner refused the variant ({sanitized_failure_message(exc)}).")
        else:
            run.failures.append("the runtime installed a missing or contradictory binding")
    else:
        _execute_unbound(harness, run, request, instrument(binding, obligation, installations=installed))
    run.expect_calls({"coordinator.grant": 0, "bridge.start_operation": 0}, run.calls)


def _owner_refuses(binding: object, declarations: list[object]) -> bool:
    try:
        validate_mixed_backend_bindings(binding.profile, binding.context, declarations)
    except ValueError:
        return True
    return False


def _execute_unbound(
    harness: object,
    run: CompositionRun,
    request: MixedBackendProbeRequest,
    instrumented: Instrumented,
) -> None:
    """Refuse dispatch for the only edge once its unmodified configuration is shown to execute."""

    if not _baseline_executes(harness, run, request):
        return
    plane = open_plane(run.configuration, instrumented.binding)
    try:
        before = len(composition_history(plane, run.run_id))
        _prepare_edge(run.configuration, plane)
        run.read = submit(lambda: _admit(run.configuration, plane, nonce()), plane, run.configuration.store)
        kinds = {event["event_kind"] for event in composition_history(plane, run.run_id)[before:]}
        refusal = run.read.refusal_type
        run.check(refusal is not None and issubclass(refusal, ValueError), "dispatch was not refused by validation")
        run.check(not kinds & {"attempt", "execution", "delivery", "observation"}, "an unbound edge was attempted")
        run.check(instrumented.component_calls("admit_action") == 0, "a component runtime was called directly")
        run.calls = Counter(instrumented.log.entries())
    finally:
        run.cleanup = close_plane(plane, run.failures) and run.cleanup


def _baseline_executes(harness: object, run: CompositionRun, request: MixedBackendProbeRequest) -> bool:
    configuration = harness.composition(replace(request, collection_id=nonce()))
    if configuration is None:
        run.unrealized = "The harness supplied no baseline configuration."
        return False
    instrumented = instrument(configuration.binding, configuration.obligation_id)
    plane = open_plane(configuration, instrumented.binding)
    try:
        _prepare_edge(configuration, plane)
        baseline = submit(lambda: _admit(configuration, plane, nonce()), plane, configuration.store)
    finally:
        run.cleanup = close_plane(plane, run.failures) and run.cleanup
    run.check(
        baseline.state == "succeeded", "the unmodified configuration did not execute; the refusal is unattributed"
    )
    if baseline.state == "succeeded":
        run.limitations.append("The unmodified configuration executed before the variant was refused.")
    return baseline.state == "succeeded"


def _execute(harness: object, run: CompositionRun, request: MixedBackendProbeRequest) -> None:
    realized: list[object] = []

    def after_grant() -> None:
        try:
            realized.append(run.configuration.apply_condition(run.case.condition))
        except Exception as exc:
            realized.append(exc)

    hook = after_grant if run.case.condition_point == "after-time-grant" else None
    instrumented = instrument(run.configuration.binding, run.configuration.obligation_id, after_grant=hook)
    plane = open_plane(run.configuration, instrumented.binding)
    try:
        if run.requested_cut is not None and plane.snapshot.time_model_state != run.requested_cut:
            run.failures.append("the harness did not realize the requested time cut")
        elif run.case.subject is MixedBackendSubject.HANDOFF:
            _drive_handoff(run, plane, instrumented)
        else:
            _drive_edge(run, plane, instrumented, realized)
    finally:
        run.cleanup = close_plane(plane, run.failures) and run.cleanup
    if run.case.case_id == "edge-restart-no-reissue" and not run.failures and run.unrealized is None:
        _restart(harness, run, request)


def _realize(run: CompositionRun, condition: MixedBackendCondition) -> bool:
    if run.configuration.apply_condition(condition) is True:
        return True
    run.unrealized = f"The harness cannot realize the {condition.value} condition."
    return False


def _prepare_edge(configuration: MixedCompositionProbeConfiguration, plane: object) -> None:
    plane.activate_mixed_composition(identity=configuration.identity, idempotency_key=f"{nonce()}:activate")
    if not plane.snapshot.participant_episode_history.get(configuration.participant_address):
        plane.initialize_participant_episode(
            configuration.participant_address, episode_id=configuration.episode_id, identity=configuration.identity
        )


def _admit(configuration: MixedCompositionProbeConfiguration, plane: object, key: str) -> object:
    return plane.admit_participant_action(
        configuration.behavior,
        configuration.admission_request,
        identity=configuration.identity,
        crossing_evidence=configuration.crossing_evidence,
        idempotency_key=key,
    )


def _drive_edge(run: CompositionRun, plane: object, instrumented: Instrumented, realized: list[object]) -> None:
    configuration, log = run.configuration, instrumented.log
    _prepare_edge(configuration, plane)
    if run.case.condition is not _NOMINAL and run.case.condition_point == "before-submission":
        if not _realize(run, run.case.condition):
            return
    history = len(composition_history(plane, run.run_id))
    participant = configuration.participant_address
    behavior = len(plane.snapshot.participant_behavior_history.get(participant, ()))
    committed, start, run.key = plane.snapshot.time_model_state, len(log), nonce()
    read = submit(lambda: _admit(configuration, plane, run.key), plane, configuration.store)
    if realized and isinstance(realized[0], Exception):
        run.failures.append(f"the harness failed to realize the condition ({sanitized_failure_message(realized[0])})")
        return
    if realized and realized[0] is not True:
        run.unrealized = f"The harness cannot realize the {run.case.condition.value} condition."
        return
    run.calls = Counter(log.entries(start))
    replay, replay_calls = None, Counter()
    if run.case.case_id in {"edge-executes", "edge-restart-no-reissue"}:
        mark = len(log)
        replay = submit(lambda: _admit(configuration, plane, run.key), plane, configuration.store)
        replay_calls = Counter(log.entries(mark))
    facts = EdgeFacts(
        read=read,
        appended=composition_history(plane, run.run_id)[history:],
        behavior_delta=len(plane.snapshot.participant_behavior_history.get(participant, ())) - behavior,
        committed=committed,
        order=log.entries(start),
        component_admits=instrumented.component_calls("admit_action"),
        replay=replay,
        replay_calls=replay_calls,
    )
    judge_edge(run, facts)


def _drive_handoff(run: CompositionRun, plane: object, instrumented: Instrumented) -> None:
    configuration, log = run.configuration, instrumented.log
    plane.activate_mixed_composition(identity=configuration.identity, idempotency_key=f"{nonce()}:activate")

    def attempt(key: str) -> HandoffAttempt:
        before, mark = composition_cut(plane, run.run_id), len(log)
        read = submit(
            lambda: plane.advance_mixed_composition(
                transition_id=configuration.obligation_id, identity=configuration.identity, idempotency_key=key
            ),
            plane,
            configuration.store,
        )
        return HandoffAttempt(read, before, composition_cut(plane, run.run_id), Counter(log.entries(mark)))

    if run.case.condition is not _NOMINAL and not _realize(run, run.case.condition):
        return
    keys = [nonce()]
    attempts = [attempt(keys[0])]
    if run.case.case_id == "handoff-repeated-transition":
        if not _realize(run, _NOMINAL):
            return
        keys.append(nonce())
        attempts += [attempt(keys[1]), attempt(nonce())]
    replay = attempt(keys[-1]) if run.case.expected_state == "succeeded" else None
    judge_handoff(run, attempts, replay)


def _restart(harness: object, run: CompositionRun, request: MixedBackendProbeRequest) -> None:
    """Reopen the selected durable store with fresh services and replay the original submission."""

    configuration = harness.composition(replace(request, collection_id=nonce(), restart_of=request.collection_id))
    if configuration is None:
        run.unrealized = "The harness cannot reopen its durable store."
        return
    instrumented = instrument(configuration.binding, configuration.obligation_id)
    plane = open_plane(configuration, instrumented.binding)
    try:
        replay = submit(lambda: _admit(configuration, plane, run.key), plane, configuration.store)
        original = run.read
        run.check(
            replay.operation_id == original.operation_id, "a reopened store did not return the original operation"
        )
        run.check(
            (replay.reports, replay.responses, replay.state) == (original.reports, original.responses, original.state),
            "a reopened store changed the retained stages, responses or state",
        )
        calls = sorted(set(instrumented.log.entries()))
        run.check(not calls, f"reopened services were called: {calls}")
    finally:
        run.cleanup = close_plane(plane, run.failures) and run.cleanup


__all__ = ["MIXED_BACKEND_PROBE_FAMILY", "run_mixed_backend_conformance"]
