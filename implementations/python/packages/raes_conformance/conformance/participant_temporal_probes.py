"""Scenario-specific bounded temporal probes; no universal backend baseline."""

from collections.abc import Iterable

from raes_contracts.contracts import ExperimentStochasticControlModel
from raes_contracts.contracts.participant_temporal import ParticipantTemporalAssessmentModel
from raes_contracts.participant_temporal import require_participant_temporal_history
from raes_runtime.registry import RuntimeTarget, participant_temporal_probe_manager

from .diagnostics import _diagnostic, sanitized_failure_message
from .report import ConformanceCaseResult


def _stop_probe_clock_driver(manager: object | None) -> bool:
    if manager is None:
        return True
    try:
        return manager._stop_participant_clock_driver()  # type: ignore[attr-defined]
    except Exception:  # NOSONAR - shutdown must report failure without leaking exception payloads
        return False


def participant_temporal_scenario_case(
    target: RuntimeTarget,
    scenario: object,
    *,
    clock_advances: tuple[tuple[str, int], ...] = (),
    stochastic_controls: Iterable[ExperimentStochasticControlModel] = (),
) -> ConformanceCaseResult:
    """Execute a caller-selected finite fixture covering claimed guarantee digests.

    Only use an isolated, disposable target: apply and advances can cause native
    effects. The caller owns native cleanup; the probe stops its local clock
    driver. Generic registration probes cannot infer
    a scenario from opaque digest claims and do not replace this probe.
    """

    diagnostics = []
    assessments = []
    manager = None
    driver_stopped = True
    try:
        manager = participant_temporal_probe_manager(target, stochastic_controls=stochastic_controls)
        diagnostics, assessments = _run_temporal_probe(
            manager,
            scenario,
            clock_advances,
        )
    except (TypeError, ValueError) as exc:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-temporal-guarantee-failed",
                "participant.temporal",
                sanitized_failure_message(exc),
            )
        )
    finally:
        driver_stopped = _stop_probe_clock_driver(manager)
    if not driver_stopped:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-clock-driver-stop-failed",
                "participant.temporal",
                (
                    "Probe clock driver shutdown was not confirmed; wait for in-flight work to quiesce before "
                    "native cleanup."
                ),
            )
        )
    passed = not any(item.is_error for item in diagnostics)
    return ConformanceCaseResult(
        name="participant-shared-time-scenario",
        contract_name="runtime-snapshot-v1",
        valid=True,
        passed=passed,
        diagnostics=tuple(diagnostics),
        outcome="passed" if passed else "failed",
        cleanup_verified=None if driver_stopped else False,
        residual_state=() if driver_stopped else ("Probe-owned clock driver shutdown is unconfirmed.",),
        finite_scope="Only the supplied scenario, manifest and finite clock advances.",
        evidence_refs=tuple(
            sorted({ref for item in assessments for proof in item.evidence for ref in proof.evidence_refs})
        ),
        explicit_non_claims=(
            "native application fidelity",
            "continuous monitoring implementation",
            "unclaimed backend features",
        ),
        limitations=(
            (
                "Probe stops its local clock driver. Caller owns native target setup and cleanup; "
                "execution basis defaults to fixture-only."
            ),
        ),
    )


def _run_temporal_probe(
    manager: object,
    scenario: object,
    clock_advances: tuple[tuple[str, int], ...],
) -> tuple[list[object], list[ParticipantTemporalAssessmentModel]]:
    plan = manager.plan(scenario)
    required = _required_temporal_contract_digests(plan)
    if not required:
        raise ValueError("Temporal conformance requires a fixture with explicit shared-time bindings.")
    result = _apply_temporal_probe_plan(manager, plan, clock_advances)
    require_participant_temporal_history(result.snapshot)
    assessments = _temporal_assessments(result.snapshot)
    _require_admitted_guarantees(result.success, required, assessments)
    return list(result.diagnostics), assessments


def _required_temporal_contract_digests(plan: object) -> set[str]:
    return {
        binding.contract_digest
        for spec in plan.model.behavior_specifications.values()  # type: ignore[attr-defined]
        if spec.autonomous_execution is not None
        for binding in spec.autonomous_execution.temporal_bindings
    }


def _apply_temporal_probe_plan(
    manager: object,
    plan: object,
    clock_advances: tuple[tuple[str, int], ...],
) -> object:
    result = manager.apply(plan)  # type: ignore[attr-defined]
    for clock, ticks in clock_advances:
        if not result.success:
            break
        result = manager.advance_time(clock, ticks=ticks)  # type: ignore[attr-defined]
    return result


def _temporal_assessments(snapshot: object) -> list[ParticipantTemporalAssessmentModel]:
    return [
        ParticipantTemporalAssessmentModel.model_validate(item)
        for history in snapshot.participant_behavior_history.values()  # type: ignore[attr-defined]
        for event in history
        for item in event.get("temporal_assessments", ())
    ]


def _require_admitted_guarantees(
    success: bool,
    required: set[str],
    assessments: list[ParticipantTemporalAssessmentModel],
) -> None:
    observed = {item.context.binding.contract_digest for item in assessments}
    if not success or observed != required or any(item.status != "met" for item in assessments):
        raise ValueError("The fixture did not establish every admitted temporal guarantee.")
