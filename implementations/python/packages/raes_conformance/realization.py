"""Backend-neutral realization-honesty cases for the conformance report family."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError
from raes.realization_envelope import (
    NegativeProbe,
    PositiveProbe,
    generate_negative_probes,
    generate_positive_probes,
)
from raes.scenario import Scenario
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import InvalidInputError
from raes_contracts.json_serialization import sorted_json_digest
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_processor.reference import run_reference_processor
from raes_runtime.registry import RuntimeTarget

from ._materialization_scope import materialization_probe_scope
from ._realization_models import (
    ExecutionBasis,
    ExpectedRealizationObservation,
    ProbeOutcome,
    RealizationConformanceHarness,
    RealizationConformanceRun,
    RealizationProbeCase,
    RealizationProbeEvidence,
    RealizationProbeRequest,
    RealizationTransformation,
)
from ._realization_validation import (
    diagnostic as _diagnostic,
)
from ._realization_validation import (
    observation_diagnostics as _observation_diagnostics,
)
from ._realization_validation import (
    operation_inventory_diagnostics as _operation_inventory_diagnostics,
)
from ._realization_validation import (
    required_strengths as _required_strengths,
)
from ._realization_validation import (
    transformation_diagnostics as _transformation_diagnostics,
)

_CLEANUP_ADDRESS = "runtime.cleanup"


@dataclass(frozen=True)
class _CaseContext:
    target: RuntimeTarget
    envelope: BackendRealizationEnvelopeModel
    harness: RealizationConformanceHarness | None
    basis: ExecutionBasis
    observer_version: str
    probe_set_digest: str
    target_binding: str


def _probe_set_digest(positives: tuple[PositiveProbe, ...], negatives: tuple[NegativeProbe, ...]) -> str:
    material = [probe.digest for probe in positives] + [sorted_json_digest(probe.payload) for probe in negatives]
    return sorted_json_digest({"probe_digests": material})


def _execute(context: _CaseContext, request: RealizationProbeRequest) -> RealizationProbeEvidence:
    if context.harness is None:
        raise ValueError("realization conformance harness is required")
    return context.harness.execute(request)


def _target_binding(target: RuntimeTarget, envelope: BackendRealizationEnvelopeModel) -> str:
    return (
        f"backend-target:{target.manifest.name}@{target.manifest.version};"
        f"mode={envelope.configuration.mode};envelope={envelope.digest};"
        f"configuration={envelope.configuration.configuration_digest}"
    )


def _base_case(
    *,
    name: str,
    outcome: ProbeOutcome,
    passed: bool,
    diagnostics: tuple[Diagnostic, ...],
    context: _CaseContext,
) -> RealizationProbeCase:
    return RealizationProbeCase(
        name=name,
        contract_name="realization-envelope-v1",
        valid=True,
        passed=passed,
        diagnostics=diagnostics,
        execution_basis=context.basis.value,
        outcome=outcome.value,
        probe_set_digest=context.probe_set_digest,
        envelope_digest=context.envelope.digest,
        configuration_digest=context.envelope.configuration.configuration_digest,
        target_binding=context.target_binding,
    )


def _mismatch_run(
    target: RuntimeTarget,
    offered: BackendRealizationEnvelopeModel,
    selected: BackendRealizationEnvelopeModel,
    basis: ExecutionBasis,
) -> RealizationConformanceRun:
    binding = _target_binding(target, offered)
    context = _CaseContext(
        target=target,
        envelope=selected,
        harness=None,
        basis=basis,
        observer_version="",
        probe_set_digest="",
        target_binding=binding,
    )
    case = _base_case(
        name="realization-envelope-binding",
        outcome=ProbeOutcome.FAILED,
        passed=False,
        diagnostics=(
            _diagnostic(
                "conformance.realization-envelope-mismatch",
                "runtime.target.realization-envelope",
                "Selected realization envelope does not match the target configuration identity.",
            ),
        ),
        context=context,
    )
    return RealizationConformanceRun(cases=(case,), target_binding=binding)


def _constructive_failure(
    target: RuntimeTarget,
    envelope: BackendRealizationEnvelopeModel,
    basis: ExecutionBasis,
    diagnostics: tuple[Diagnostic, ...],
) -> RealizationConformanceRun:
    binding = _target_binding(target, envelope)
    context = _CaseContext(
        target=target,
        envelope=envelope,
        harness=None,
        basis=basis,
        observer_version="",
        probe_set_digest="",
        target_binding=binding,
    )
    case = _base_case(
        name="realization-envelope-constructive",
        outcome=ProbeOutcome.UNSUPPORTED,
        passed=False,
        diagnostics=diagnostics,
        context=context,
    )
    return RealizationConformanceRun(cases=(case,), target_binding=binding)


def _positive_case(
    *,
    index: int,
    probe: PositiveProbe,
    context: _CaseContext,
) -> RealizationProbeCase:
    try:
        execution_plan = run_reference_processor(
            Scenario.model_validate(probe.payload),
            context.target.manifest,
            scope=materialization_probe_scope(context.target),
        ).execution_plan
    # The SDL model, the processor or the planner refused the generated probe.
    except InvalidInputError, ValidationError:
        execution_plan = None
    # A plan with error diagnostics is not an executable probe; never hand it to the harness.
    if execution_plan is None or any(diagnostic.is_error for diagnostic in execution_plan.diagnostics):
        return _base_case(
            name=f"realization-positive-{index}",
            outcome=ProbeOutcome.FAILED,
            passed=False,
            diagnostics=(
                _diagnostic(
                    "conformance.positive-probe-plan-failed",
                    probe.path,
                    "The generated positive probe did not pass the ordinary processor and planning boundary.",
                ),
            ),
            context=context,
        )
    plan = execution_plan.provisioning
    request = RealizationProbeRequest(
        probe_digest=probe.digest,
        probe_kind="positive",
        payload=probe.payload,
        negative=False,
        provisioning_plan=plan,
        envelope_digest=context.envelope.digest,
        configuration_digest=context.envelope.configuration.configuration_digest,
        observer_version=context.observer_version,
    )
    evidence = _execute(context, request)
    strengths = _required_strengths(context.envelope)
    diagnostics = list(evidence.diagnostics)
    if not evidence.accepted:
        diagnostics.append(
            _diagnostic(
                "conformance.positive-probe-rejected",
                probe.path,
                "The in-envelope positive probe was rejected.",
            )
        )
    diagnostics.extend(_operation_inventory_diagnostics(plan, evidence, strengths))
    diagnostics.extend(_observation_diagnostics(request, evidence, strengths))
    diagnostics.extend(_transformation_diagnostics(evidence))
    if plan.actionable_operations and evidence.portable_state_before == evidence.portable_state_after:
        diagnostics.append(
            _diagnostic(
                "conformance.positive-portable-state-unchanged",
                "runtime.snapshot",
                "A successful actionable positive probe did not mutate portable state.",
            )
        )
    if not evidence.cleanup_verified:
        diagnostics.append(
            _diagnostic(
                "conformance.cleanup-unverified",
                _CLEANUP_ADDRESS,
                "Probe cleanup was not independently verified.",
            )
        )
    if evidence.residual_state:
        diagnostics.append(
            _diagnostic(
                "conformance.residual-state",
                _CLEANUP_ADDRESS,
                "Probe cleanup left residual owned state.",
            )
        )
    expected_operations = tuple(operation.address for operation in plan.actionable_operations)
    return RealizationProbeCase(
        name=f"realization-positive-{index}",
        contract_name="realization-envelope-v1",
        valid=True,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
        execution_basis=context.basis.value,
        outcome=(ProbeOutcome.PASSED if not diagnostics else ProbeOutcome.FAILED).value,
        probe_kind="positive",
        probe_digest=probe.digest,
        probe_set_digest=context.probe_set_digest,
        envelope_digest=context.envelope.digest,
        configuration_digest=context.envelope.configuration.configuration_digest,
        target_binding=context.target_binding,
        expected_operations=expected_operations,
        accounted_operations=evidence.accounted_operations,
        expected_observation_strengths=tuple(sorted({strength.value for strength in strengths.values()})),
        actual_observation_strengths=tuple(sorted({item.source.value for item in evidence.observations})),
        portable_state_unchanged=evidence.portable_state_before == evidence.portable_state_after,
        native_state_unchanged=evidence.native_state_before == evidence.native_state_after,
        cleanup_verified=evidence.cleanup_verified,
        residual_state=evidence.residual_state,
        evidence_refs=evidence.evidence_refs,
    )


def _negative_case(
    *,
    index: int,
    probe: NegativeProbe,
    context: _CaseContext,
) -> RealizationProbeCase:
    digest = sorted_json_digest(probe.payload)
    request = RealizationProbeRequest(
        probe_digest=digest,
        probe_kind="negative",
        payload=probe.payload,
        negative=True,
        provisioning_plan=None,
        envelope_digest=context.envelope.digest,
        configuration_digest=context.envelope.configuration.configuration_digest,
        observer_version=context.observer_version,
    )
    evidence = _execute(context, request)
    diagnostics = list(evidence.diagnostics)
    if evidence.accepted:
        diagnostics.append(
            _diagnostic(
                "conformance.negative-probe-accepted",
                probe.path,
                "The out-of-envelope probe was accepted.",
            )
        )
    if evidence.driver_invoked:
        diagnostics.append(
            _diagnostic(
                "conformance.negative-driver-invoked",
                probe.path,
                "The out-of-envelope probe reached driver invocation.",
            )
        )
    if evidence.native_mutated:
        diagnostics.append(
            _diagnostic(
                "conformance.negative-native-mutation",
                probe.path,
                "The out-of-envelope probe caused native mutation.",
            )
        )
    portable_unchanged = evidence.portable_state_before == evidence.portable_state_after
    native_unchanged = evidence.native_state_before == evidence.native_state_after
    if not portable_unchanged:
        diagnostics.append(
            _diagnostic(
                "conformance.negative-portable-state-mutated",
                probe.path,
                "The out-of-envelope probe changed portable runtime state.",
            )
        )
    if not native_unchanged:
        diagnostics.append(
            _diagnostic(
                "conformance.negative-native-state-mutated",
                probe.path,
                "The out-of-envelope probe changed independently inventoried native state.",
            )
        )
    if not evidence.cleanup_verified:
        diagnostics.append(
            _diagnostic(
                "conformance.cleanup-unverified",
                _CLEANUP_ADDRESS,
                "Negative-probe cleanup was not independently verified.",
            )
        )
    if evidence.residual_state:
        diagnostics.append(
            _diagnostic(
                "conformance.residual-state",
                _CLEANUP_ADDRESS,
                "Negative-probe cleanup left residual owned state.",
            )
        )
    return RealizationProbeCase(
        name=f"realization-negative-{index}",
        contract_name="realization-envelope-v1",
        valid=True,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
        execution_basis=context.basis.value,
        outcome=(ProbeOutcome.PASSED if not diagnostics else ProbeOutcome.FAILED).value,
        probe_kind="negative",
        probe_digest=digest,
        probe_set_digest=context.probe_set_digest,
        envelope_digest=context.envelope.digest,
        configuration_digest=context.envelope.configuration.configuration_digest,
        target_binding=context.target_binding,
        portable_state_unchanged=portable_unchanged,
        native_state_unchanged=native_unchanged,
        cleanup_verified=evidence.cleanup_verified,
        residual_state=evidence.residual_state,
        evidence_refs=evidence.evidence_refs,
    )


def _missing_harness_run(context: _CaseContext) -> RealizationConformanceRun:
    case = _base_case(
        name="realization-harness-required",
        outcome=ProbeOutcome.UNSUPPORTED,
        passed=False,
        diagnostics=(
            _diagnostic(
                "conformance.realization-harness-missing",
                "runtime.target.realization-conformance",
                "Realization certification requires an independent execution and observation harness.",
            ),
        ),
        context=context,
    )
    return RealizationConformanceRun(
        cases=(case,),
        probe_set_digest=context.probe_set_digest,
        target_binding=context.target_binding,
    )


def _probe_cases(
    context: _CaseContext,
    positive: tuple[PositiveProbe, ...],
    negative: tuple[NegativeProbe, ...],
    *,
    native_conformance: bool,
) -> list[RealizationProbeCase]:
    cases = [_positive_case(index=index, probe=probe, context=context) for index, probe in enumerate(positive, start=1)]
    cases.extend(
        _negative_case(index=index, probe=probe, context=context) for index, probe in enumerate(negative, start=1)
    )
    if native_conformance and context.basis is not ExecutionBasis.NATIVE_LIVE:
        cases.append(
            _base_case(
                name="native-conformance-basis",
                outcome=ProbeOutcome.FAILED,
                passed=False,
                diagnostics=(
                    _diagnostic(
                        "conformance.native-basis-required",
                        "runtime.target.execution-basis",
                        "Only native-live execution may support a native conformance claim.",
                    ),
                ),
                context=context,
            )
        )
    return cases


def _constructive_run(
    context: _CaseContext,
    positive: tuple[PositiveProbe, ...],
    negative: tuple[NegativeProbe, ...],
    *,
    native_conformance: bool,
) -> RealizationConformanceRun:
    if context.harness is None:
        return _missing_harness_run(context)
    cases = _probe_cases(context, positive, negative, native_conformance=native_conformance)
    passed = all(case.passed for case in cases)
    return RealizationConformanceRun(
        cases=tuple(cases),
        probe_set_digest=context.probe_set_digest,
        target_binding=context.target_binding,
        native_conformance=native_conformance and context.basis is ExecutionBasis.NATIVE_LIVE and passed,
    )


def run_realization_conformance(
    target: RuntimeTarget,
    *,
    harness: RealizationConformanceHarness | None,
    execution_basis: ExecutionBasis,
    envelope: BackendRealizationEnvelopeModel | None = None,
    observer_version: str = "raes-realization-observer/v1",
    native_conformance: bool = False,
) -> RealizationConformanceRun:
    """Return realization-honesty cases for one exact target configuration."""

    result = RealizationConformanceRun()
    offered = target.manifest.realization_envelope
    if offered is not None:
        selected = envelope or offered
        if selected.identity != offered.identity:
            result = _mismatch_run(target, offered, selected, execution_basis)
        else:
            positive, positive_diagnostics = generate_positive_probes(selected.expression)
            negative, negative_diagnostics = generate_negative_probes(selected.expression)
            diagnostics = (*positive_diagnostics, *negative_diagnostics)
            if diagnostics or not positive:
                result = _constructive_failure(target, selected, execution_basis, diagnostics)
            else:
                context = _CaseContext(
                    target=target,
                    envelope=selected,
                    harness=harness,
                    basis=execution_basis,
                    observer_version=observer_version,
                    probe_set_digest=_probe_set_digest(positive, negative),
                    target_binding=_target_binding(target, selected),
                )
                result = _constructive_run(
                    context,
                    positive,
                    negative,
                    native_conformance=native_conformance,
                )
    return result


__all__ = [
    "ExecutionBasis",
    "ExpectedRealizationObservation",
    "ProbeOutcome",
    "RealizationConformanceHarness",
    "RealizationProbeCase",
    "RealizationProbeEvidence",
    "RealizationProbeRequest",
    "RealizationTransformation",
    "run_realization_conformance",
]
