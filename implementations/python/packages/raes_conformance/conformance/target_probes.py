"""Target/control-plane conformance probes and the default probe scenario."""

from __future__ import annotations

from types import SimpleNamespace

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import RaesError
from raes_contracts.manifest_authority import PARTICIPANT_RUNTIME_POLICY_FEATURES
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.participant_episode import (
    ParticipantEpisodeTerminalReason,
    iter_participant_episode_snapshot_violations,
)
from raes_contracts.planning import PlanScope, ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_processor.models import ExecutionPlan
from raes_processor.reference import ScenarioInput
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget
from raes_runtime.snapshot_contract import runtime_snapshot_contract_payload

from raes_conformance._materialization_scope import materialization_probe_scope
from raes_conformance.conformance.diagnostics import (
    _SEMANTIC_INVALID_DIAGNOSTIC_CODE,
    _diagnostic,
    sanitized_failure_message,
)
from raes_conformance.conformance.participant_execution_probes import (
    _drive_participant_execution_probe,
    _isolated_control_cases,
    _participant_execution_probe_snapshot,
)
from raes_conformance.conformance.probe_runtime import ProbeRuntimeOwner
from raes_conformance.conformance.profiles import (
    BackendCapabilityProfile,
    BackendProfileSelector,
    _to_known_profile,
)
from raes_conformance.conformance.report import ConformanceCaseResult
from raes_conformance.conformance.semantics import _semantic_diagnostics
from raes_conformance.conformance.target_manifest_probe import target_manifest_case
from raes_conformance.conformance.target_planning import (
    DEFAULT_TARGET_CONFORMANCE_SCENARIO,
    target_probe_execution_plan,
)
from raes_conformance.conformance.validators import _validate_payload

_LOGGER = get_logger(__name__)


class _UnavailableConformanceCrossingPolicyResolver:
    """Explicitly fail closed if an unrelated adapter probe reaches crossing policy."""

    @staticmethod
    def resolve(
        intent: object,
        snapshot: RuntimeSnapshot,
    ) -> object:
        del intent, snapshot
        # The resolver protocol refuses an unresolvable policy with ValueError (rule E4).
        raise ValueError("target adapter conformance does not supply a crossing policy")

    @staticmethod
    def validation_context(
        snapshot: RuntimeSnapshot,
        participant_address: str,
    ) -> object:
        del snapshot, participant_address
        return SimpleNamespace(
            known_subjects=(),
            policies=(),
            known_evidence_refs=frozenset(),
            known_authority_basis_refs=frozenset(),
        )


def _conformance_crossing_policy_resolver(
    target: RuntimeTarget,
) -> _UnavailableConformanceCrossingPolicyResolver | None:
    capabilities = target.manifest.participant_runtime
    if capabilities is None:
        return None
    if any(
        declaration.feature in PARTICIPANT_RUNTIME_POLICY_FEATURES
        and declaration.support_level != ParticipantFeatureSupportLevel.UNSUPPORTED
        for declaration in capabilities.feature_support
    ):
        return _UnavailableConformanceCrossingPolicyResolver()
    return None


def _participant_snapshot_consistency_case(
    control_plane: RuntimeControlPlane,
    participant_address: str,
    contract_name: str,
) -> ConformanceCaseResult:
    """Validate the post-lifecycle snapshot exposes live participant-episode state.

    A target that registers a participant runtime but never populates the
    snapshot fields fails the snapshot-state-not-empty check, so the live
    conformance probe cannot certify a backend whose runtime accepts every
    action but produces no observable state.
    """

    snapshot = control_plane.snapshot
    final_diagnostics: list[Diagnostic] = []
    if not snapshot.participant_episode_results:
        final_diagnostics.append(
            _diagnostic(
                "conformance.participant-runtime-empty",
                f"runtime.snapshot.participant-episode-results.{participant_address}",
                (
                    "Participant runtime accepted every control action but the snapshot "
                    "exposes no participant_episode_results. RUN-311 backends must publish "
                    "live episode state through the snapshot."
                ),
            )
        )
    if not snapshot.participant_episode_history:
        final_diagnostics.append(
            _diagnostic(
                "conformance.participant-runtime-empty",
                f"runtime.snapshot.participant-episode-history.{participant_address}",
                (
                    "Participant runtime accepted every control action but the snapshot "
                    "exposes no participant_episode_history. RUN-311 backends must publish "
                    "live episode history events through the snapshot."
                ),
            )
        )
    for address, message in iter_participant_episode_snapshot_violations(
        snapshot.participant_episode_results,
        snapshot.participant_episode_history,
    ):
        final_diagnostics.append(_diagnostic(_SEMANTIC_INVALID_DIAGNOSTIC_CODE, address, message))
    return ConformanceCaseResult(
        name="participant-snapshot-consistent",
        contract_name=contract_name,
        valid=True,
        passed=not final_diagnostics,
        diagnostics=tuple(final_diagnostics),
    )


def _drive_participant_episode_probe(
    control_plane: RuntimeControlPlane,
    *,
    participant_address: str,
) -> list[ConformanceCaseResult]:
    """Drive a full RUN-311 participant lifecycle via the control plane.

    Each control action becomes one ``ConformanceCaseResult`` so that
    ``run_target_conformance`` reports a separate failure for any step
    the backend rejects, and a final case validates the resulting
    ``participant_episode_results`` / ``participant_episode_history``
    against the shared snapshot invariants.

    A target that registers a participant runtime but never populates
    the snapshot fields fails the snapshot-state-not-empty check, so
    the live conformance probe cannot certify a backend whose runtime
    accepts every action but produces no observable state.
    """

    cases: list[ConformanceCaseResult] = []
    actions = (
        ("participant-initialize", lambda: control_plane.initialize_participant_episode(participant_address)),
        ("participant-reset", lambda: control_plane.reset_participant_episode(participant_address)),
        (
            "participant-terminate",
            lambda: control_plane.terminate_participant_episode(
                participant_address,
                terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED,
            ),
        ),
        ("participant-restart", lambda: control_plane.restart_participant_episode(participant_address)),
    )
    contract_name = "participant-episode-state-envelope-v1"
    for case_name, invoke in actions:
        try:
            receipt = invoke()
        except Exception as exc:
            # Defensive: a well-behaved backend does not raise here; surface it as a diagnostic.
            if not isinstance(exc, RaesError):
                # Isolation of the participant runtime: a refusal category needs no record.
                _LOGGER.exception("participant episode probe action failed", exc_info=foreign_failure_record(exc))
            cases.append(
                ConformanceCaseResult(
                    name=case_name,
                    contract_name=contract_name,
                    valid=True,
                    passed=False,
                    diagnostics=(
                        _diagnostic(
                            "conformance.participant-runtime-failed",
                            f"runtime.control-plane.participant.{participant_address}",
                            f"{case_name} failed: {sanitized_failure_message(exc)}",
                        ),
                    ),
                )
            )
            continue
        status = control_plane.get_operation(receipt.operation_id)
        diagnostics: list[Diagnostic] = []
        if status is None:
            diagnostics.append(
                _diagnostic(
                    "conformance.participant-runtime-missing-status",
                    f"runtime.control-plane.participant.{participant_address}",
                    f"{case_name} did not produce an OperationStatus record",
                )
            )
        elif status.state.value not in {"succeeded"}:
            diagnostics.append(
                _diagnostic(
                    "conformance.participant-runtime-failed",
                    f"runtime.control-plane.participant.{participant_address}",
                    (
                        f"{case_name} returned state {status.state.value!r} with diagnostics: "
                        + "; ".join(diag.message for diag in status.diagnostics)
                    ),
                )
            )
        cases.append(
            ConformanceCaseResult(
                name=case_name,
                contract_name=contract_name,
                valid=True,
                passed=not diagnostics,
                diagnostics=tuple(diagnostics),
            )
        )

    cases.append(_participant_snapshot_consistency_case(control_plane, participant_address, contract_name))
    return cases


def _provisioning_probe_case(
    control_plane: RuntimeControlPlane,
    provisioning_plan: ProvisioningPlan,
) -> ConformanceCaseResult:
    """Drive hermetic target-adapter provisioning and prove portable mutation.

    Backend-neutral (issue #606): every known profile requires a provisioner,
    so target conformance always submits the reference scenario's provisioning
    plan through the control plane. A backend that accepts the plan but realizes
    nothing — a failed apply, or a success that reports no changed addresses —
    fails here rather than certifying clean on manifest validation alone.
    """

    address = "runtime.control-plane.provisioning"
    receipt = control_plane.submit_provisioning(provisioning_plan)
    status = control_plane.get_operation(receipt.operation_id)
    diagnostics: list[Diagnostic] = []
    if status is None:
        diagnostics.append(
            _diagnostic(
                "conformance.provisioning-missing-status",
                address,
                "Provisioning submission did not produce an OperationStatus record.",
            )
        )
    elif status.state.value != "succeeded":
        diagnostics.append(
            _diagnostic(
                "conformance.provisioning-failed",
                address,
                (
                    f"Provisioning returned state {status.state.value!r} with diagnostics: "
                    + "; ".join(diag.message for diag in status.diagnostics)
                ),
            )
        )
    elif not status.changed_addresses:
        diagnostics.append(
            _diagnostic(
                "conformance.provisioning-empty",
                address,
                (
                    "Provisioning succeeded but reported no changed addresses; the backend "
                    "did not realize the scenario, so the snapshot was not mutated."
                ),
            )
        )
    return ConformanceCaseResult(
        name="target-provisioning",
        contract_name="operation-status-v1",
        valid=True,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
    )


def _hermetic_snapshot_case(
    control_plane: RuntimeControlPlane,
    *,
    materialization_required: bool = False,
) -> ConformanceCaseResult:
    """Validate the post-provisioning snapshot and prove it was mutated.

    Runs the ``runtime-snapshot-v1`` schema + semantic checks on the payload the
    control plane's ``/snapshot`` route publishes (issue #1551), including the
    realization envelope and realization provenance. Semantic checks run only on a
    schema-valid payload, because they would raise on an invalid one instead of
    reporting a diagnostic. The case also requires at least one provisioning-domain
    entry (issue #606), so a target cannot pass with a schema-valid but empty
    (unmutated) snapshot. A negotiated materialization producer must also leave
    an archived attestation reference (issue #1667).
    """

    snapshot_payload = runtime_snapshot_contract_payload(control_plane.get_snapshot())
    diagnostics = _validate_payload("runtime-snapshot-v1", snapshot_payload)
    if not diagnostics:
        diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)
    has_provisioning_entry = any(
        entry.domain == RuntimeDomain.PROVISIONING for entry in control_plane.snapshot.entries.values()
    )
    if not has_provisioning_entry:
        diagnostics.append(
            _diagnostic(
                "conformance.snapshot-not-mutated",
                "runtime.snapshot.entries",
                (
                    "Hermetic snapshot carries no provisioning-domain entry after the provisioning "
                    "probe; the backend validated contracts without realizing runtime state."
                ),
            )
        )
    if materialization_required and not control_plane.snapshot.materialization_attestations:
        diagnostics.append(
            _diagnostic(
                "conformance.materialization-not-archived",
                "runtime.snapshot.materialization_attestations",
                (
                    "Hermetic snapshot carries no archived materialization attestation; the negotiated "
                    "producer did not deliver an admitted report."
                ),
            )
        )
    return ConformanceCaseResult(
        name="target-snapshot",
        contract_name="runtime-snapshot-v1",
        valid=True,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
    )


def _target_adapter_cases(
    target: RuntimeTarget,
    profile: BackendProfileSelector,
    *,
    reference_scenario: ScenarioInput | None = None,
) -> tuple[ConformanceCaseResult, ...]:
    """Run target-adapter probes appropriate for known runtime surfaces only.

    Every known profile requires a provisioner, so target conformance always
    runs a backend-neutral provisioning probe that proves adapter-driven snapshot
    mutation (issue #606), not daemon or guest observation — provisioning-only backends included, which must not
    pass on manifest validation alone. Orchestration, evaluation, and the
    participant-episode probe additionally run for the richer runtime surfaces
    that declare those roles. For an unknown profile id we run only the
    universally-safe manifest validation case and skip the target probes, since
    their runtime contract is not known to this implementation.

    The probe drives ``reference_scenario`` when supplied, else
    ``_DEFAULT_CONFORMANCE_SCENARIO`` (issue #663). Whichever scenario is
    selected is held to adapter-level operation accounting (the #606 mutation
    guard is unchanged); the parameter only stops the probe assuming *every* backend can
    realize one hard-coded scenario.
    """

    cases = [target_manifest_case(target)]
    known = _to_known_profile(profile)
    if not cases[0].valid or known is None:
        return tuple(cases)

    scenario = DEFAULT_TARGET_CONFORMANCE_SCENARIO if reference_scenario is None else reference_scenario
    scope = materialization_probe_scope(target)
    execution_plan = target_probe_execution_plan(
        scenario,
        target,
        provisioning_only=known == BackendCapabilityProfile.PROVISIONING_ONLY,
        scope=scope,
    )
    planning_errors = tuple(diagnostic for diagnostic in execution_plan.diagnostics if diagnostic.is_error)
    if planning_errors:
        cases.append(
            ConformanceCaseResult(
                name="target-provisioning",
                contract_name="provisioning-plan-v1",
                valid=False,
                passed=False,
                diagnostics=(
                    _diagnostic(
                        "conformance.provisioning-failed",
                        "runtime.control-plane.provisioning",
                        "Composite planning rejected the target probe before backend execution: "
                        + "; ".join(diagnostic.code for diagnostic in planning_errors),
                    ),
                ),
            )
        )
    else:
        cases.extend(_target_runtime_cases(target, known, execution_plan, scope))
    return tuple(cases)


def _target_runtime_cases(
    target: RuntimeTarget,
    known: BackendCapabilityProfile,
    execution_plan: ExecutionPlan,
    scope: PlanScope | None = None,
) -> tuple[ConformanceCaseResult, ...]:
    """Drive the runtime surfaces that are valid for one known backend profile."""

    owner = ProbeRuntimeOwner(scope)
    try:
        return _target_runtime_probe_cases(target, known, execution_plan, owner)
    finally:
        owner.close()


def _target_runtime_probe_cases(
    target: RuntimeTarget,
    known: BackendCapabilityProfile,
    execution_plan: ExecutionPlan,
    owner: ProbeRuntimeOwner,
) -> tuple[ConformanceCaseResult, ...]:
    cases: list[ConformanceCaseResult] = []
    materialization_required = owner.materialization_required
    # Legacy API-423-only conformance resolver: opt out of the SEM-233 final-sink
    # permit that this probe's resolver does not produce.
    control_plane = owner.runtime(
        target,
        initial_snapshot=_participant_execution_probe_snapshot(target),
        crossing_policy_resolver=_conformance_crossing_policy_resolver(target),
        enforce_final_sink_flow_control=False,
    )
    controls = frozenset()
    with control_plane:
        control_plane.register_planner_produced_plan(execution_plan)
        provisioning = _provisioning_probe_case(control_plane, execution_plan.provisioning)
        cases.append(provisioning)
        if not provisioning.passed:
            cases.append(_hermetic_snapshot_case(control_plane, materialization_required=materialization_required))
            return tuple(cases)
        if known != BackendCapabilityProfile.PROVISIONING_ONLY:
            if target.orchestrator is not None:
                control_plane.submit_orchestration(execution_plan.orchestration)
            if target.evaluator is not None:
                control_plane.submit_evaluation(execution_plan.evaluation)
            if target.participant_runtime is not None:
                cases.extend(
                    _drive_participant_episode_probe(control_plane, participant_address="participant.conformance")
                )
                capability = target.manifest.participant_runtime
                if capability is not None and capability.supports_autonomous_execution:
                    cases.extend(_drive_participant_execution_probe(target, control_plane))
                    controls = capability.supported_execution_control_actions
        cases.append(_hermetic_snapshot_case(control_plane, materialization_required=materialization_required))
        snapshot = control_plane.snapshot
    if controls and controls != {"start", "pause", "resume", "drain", "reset", "teardown"}:
        cases.extend(
            _isolated_control_cases(
                target,
                snapshot,
                "participant.autonomous-execution.conformance",
                controls - {"start"},
                owner.runtime,
            )
        )
    return tuple(cases)
