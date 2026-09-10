from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace

from raes_contracts.addressing import require_compiled_address
from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.contracts.time_model import validate_time_runtime_transition
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import ApplyResult, RealizationProvenanceEntry, RuntimeSnapshot
from raes_processor.models import CompiledRealizationRequirement
from raes_processor.planner import (
    realization_authority_disclosure,
    realization_disclosure,
    sanitize_plan_realization_snapshot,
    sanitize_realization_snapshot,
)

from .backend_account_credentials import (
    plan_arguments_have_account_credentials,
    sanitize_account_credential_result,
    value_free_backend_diagnostics,
)
from .backend_call_contracts import (
    _apply_result_contract_violation,
    _diagnostics_iterable_violation,
    _diagnostics_values_violation,
)
from .backend_realization_authority import (
    _apply_authority_diagnostics,
    _bind_submitted_plan,
    _RealizationApplyContext,
)
from .diagnostics import _failure_diagnostic
from .evaluation_result_contracts import evaluation_result_contract_diagnostics
from .participant_result_contracts import (
    participant_runtime_history_transition_diagnostics,
    participant_runtime_state_contract_diagnostics,
)
from .proposition_truth_contracts import proposition_truth_contract_diagnostics
from .workflow_result_contracts import workflow_result_contract_diagnostics

_BACKEND_CONTRACT_INVALID = "runtime.backend-contract-invalid"


def _call_backend_diagnostics(
    method: Callable[..., object],
    *args: object,
    address: str,
) -> list[Diagnostic]:
    try:
        result = method(*args)
    except Exception as exc:
        diagnostics = [_backend_call_failed(address, exc)]
    else:
        invalid_message = _diagnostics_iterable_violation(result, address)
        if invalid_message is not None:
            diagnostics = [_backend_contract_invalid(address, invalid_message)]
        else:
            diagnostics = list(result)
            invalid_message = _diagnostics_values_violation(diagnostics, address)
            if invalid_message is not None:
                diagnostics = [_backend_contract_invalid(address, invalid_message)]
    if plan_arguments_have_account_credentials(args):
        diagnostics = value_free_backend_diagnostics(diagnostics)
    return diagnostics


def _call_backend_apply(
    method: Callable[..., object],
    *args: object,
    address: str,
    snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext | None = None,
    operation_id: str | None = None,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> ApplyResult:
    realization_context = realization or _RealizationApplyContext()
    args, realization_context = _bind_submitted_plan(args, realization_context, operation_id)
    baseline_snapshot = deepcopy(snapshot)
    authority_diagnostics = _apply_authority_diagnostics(realization_context, address)
    if authority_diagnostics:
        return ApplyResult(
            success=False,
            snapshot=baseline_snapshot,
            diagnostics=authority_diagnostics,
        )
    return _invoke_backend_apply(
        method,
        args,
        address=address,
        snapshot=snapshot,
        baseline_snapshot=baseline_snapshot,
        realization=realization_context,
        information_state_context_resolver=information_state_context_resolver,
    )


def _invoke_backend_apply(
    method: Callable[..., object],
    args: tuple[object, ...],
    *,
    address: str,
    snapshot: RuntimeSnapshot,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
) -> ApplyResult:
    backend_snapshot = deepcopy(snapshot)
    backend_args = tuple(backend_snapshot if arg is snapshot else arg for arg in args)
    try:
        result = method(*backend_args)
    except (TypeError, ValueError):
        return _failed_apply_result(
            baseline_snapshot,
            _backend_contract_invalid(address, "Backend could not construct a valid apply result."),
        )
    except Exception as exc:
        return _failed_apply_result(baseline_snapshot, _backend_call_failed(address, exc))
    return _finalize_backend_apply(
        result,
        address=address,
        baseline_snapshot=baseline_snapshot,
        realization=realization,
        information_state_context_resolver=information_state_context_resolver,
    )


def _finalize_backend_apply(
    result: object,
    *,
    address: str,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
) -> ApplyResult:
    """Validate a backend's apply result and gate its realized snapshot.

    Rejects (returning the baseline snapshot, ``success=False``) on a malformed
    result, a snapshot-contract violation, or a SEM-218 non-approximation
    violation; otherwise returns the backend result, augmented with the
    realization-provenance ledger when the gate disclosed one.
    """

    invalid_message = _apply_result_contract_violation(result, address)
    if invalid_message is not None:
        finalized = _failed_apply_result(
            baseline_snapshot,
            _backend_contract_invalid(address, invalid_message),
        )
    else:
        assert isinstance(result, ApplyResult)
        contract_diagnostics, realization_provenance = _post_apply_contract_result(
            result,
            baseline_snapshot,
            realization,
            information_state_context_resolver=information_state_context_resolver,
        )
        if contract_diagnostics:
            finalized = ApplyResult(
                success=False,
                snapshot=baseline_snapshot,
                diagnostics=contract_diagnostics,
            )
        else:
            finalized = _sanitize_backend_realization(
                result,
                address=address,
                baseline_snapshot=baseline_snapshot,
                realization_requirements=realization.requirements,
                realization_plan=realization.plan,
            )
            if realization_provenance and finalized.success:
                finalized = _with_realization_provenance(finalized, realization_provenance)
    return finalized


def _post_apply_contract_result(
    result: ApplyResult,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
) -> tuple[list[Diagnostic], tuple[RealizationProvenanceEntry, ...]]:
    if result.operational_realization_observations:
        result = replace(
            result,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries),
                realization_observations=(
                    *result.snapshot.realization_observations,
                    *result.operational_realization_observations,
                ),
            ),
        )
    diagnostics = _backend_snapshot_contract_diagnostics(
        result,
        baseline_snapshot,
        information_state_context_resolver=information_state_context_resolver,
    )
    provenance: tuple[RealizationProvenanceEntry, ...] = ()
    if not diagnostics and realization.plan is not None:
        # Failed apply results are cleanup inventory, not observation-success
        # claims. Still check materialization authority and sanitize the snapshot;
        # requiring the failed readback here would erase recoverable resources.
        validation_plan = realization.plan if result.success else replace(realization.plan, observation_demands=())
        diagnostics, provenance = realization_authority_disclosure(
            validation_plan,
            result.snapshot,
            manifest=realization.manifest,
        )
        supplemental = _supplemental_realization_requirements(realization)
        if not diagnostics and supplemental:
            supplemental_diagnostics, supplemental_provenance = realization_disclosure(
                supplemental,
                validation_plan,
                result.snapshot,
                manifest=realization.manifest,
                artifact_availability=realization.artifact_availability,
            )
            diagnostics.extend(supplemental_diagnostics)
            provenance = (*provenance, *supplemental_provenance)
    return diagnostics, provenance


def _backend_snapshot_contract_diagnostics(
    result: ApplyResult,
    baseline_snapshot: RuntimeSnapshot,
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
) -> list[Diagnostic]:
    diagnostics = _snapshot_address_contract_diagnostics(result.snapshot)
    if not diagnostics:
        diagnostics = _changed_address_transition_diagnostics(result, baseline_snapshot)
    if not diagnostics:
        diagnostics = _snapshot_contract_diagnostics(
            result.snapshot,
            information_state_context_resolver=information_state_context_resolver,
            trusted_information_state_history=baseline_snapshot.information_state_history,
        )
    if not diagnostics:
        diagnostics = _snapshot_transition_contract_diagnostics(baseline_snapshot, result.snapshot)
    return diagnostics


def _sanitize_backend_realization(
    result: ApplyResult,
    *,
    address: str,
    baseline_snapshot: RuntimeSnapshot,
    realization_requirements: tuple[CompiledRealizationRequirement, ...],
    realization_plan: ProvisioningPlan | None,
) -> ApplyResult:
    sanitized = result
    if realization_plan is not None and (realization_plan.realization_authority or realization_requirements):
        try:
            safe_snapshot = (
                sanitize_plan_realization_snapshot(realization_plan, result.snapshot)
                if realization_plan.realization_authority
                else sanitize_realization_snapshot(realization_requirements, result.snapshot)
            )
        except (TypeError, ValueError):
            return _failed_apply_result(
                baseline_snapshot,
                _backend_contract_invalid(
                    address,
                    "Backend returned an invalid realization concern observation.",
                ),
            )
        sanitized = _with_snapshot(result, safe_snapshot)
    if realization_plan is not None:
        sanitized = _with_snapshot(
            sanitized,
            sanitized.snapshot.with_entries(
                dict(sanitized.snapshot.entries),
                realization_observations=(),
            ),
        )
        try:
            sanitized = sanitize_account_credential_result(sanitized, realization_plan, baseline_snapshot)
        except ValueError:
            return _failed_apply_result(
                baseline_snapshot,
                _backend_contract_invalid(
                    address,
                    "Backend returned credential material outside its canonical material node.",
                ),
            )
    return sanitized


def _supplemental_realization_requirements(
    realization: _RealizationApplyContext,
) -> tuple[CompiledRealizationRequirement, ...]:
    """Keep non-registry contracts while the plan owns registry concerns."""

    if realization.plan is None or not realization.plan.realization_authority:
        return realization.requirements
    plan_identities = {
        (entry.address, entry.field_path, entry.requirement_kind) for entry in realization.plan.realization_authority
    }
    return tuple(
        requirement
        for requirement in realization.requirements
        if (requirement.address, requirement.field_path, requirement.requirement_kind) not in plan_identities
    )


def _with_snapshot(
    result: ApplyResult,
    snapshot: RuntimeSnapshot,
) -> ApplyResult:
    return ApplyResult(
        success=result.success,
        snapshot=snapshot,
        diagnostics=result.diagnostics,
        changed_addresses=result.changed_addresses,
        details=result.details,
    )


def _with_realization_provenance(
    result: ApplyResult,
    provenance: tuple[RealizationProvenanceEntry, ...],
) -> ApplyResult:
    """Attach the SEM-218 provenance ledger to a successful apply's snapshot."""

    return ApplyResult(
        success=result.success,
        snapshot=result.snapshot.with_entries(
            dict(result.snapshot.entries),
            realization_provenance=provenance,
        ),
        diagnostics=result.diagnostics,
        changed_addresses=result.changed_addresses,
        details=result.details,
    )


def _backend_call_failed(address: str, exc: Exception) -> Diagnostic:
    return _failure_diagnostic(
        "runtime.backend-call-failed",
        address,
        f"Backend method '{address}' did not complete ({type(exc).__name__}).",
    )


def _backend_contract_invalid(address: str, message: str) -> Diagnostic:
    return _failure_diagnostic(_BACKEND_CONTRACT_INVALID, address, message)


def _failed_apply_result(snapshot: RuntimeSnapshot, diagnostic: Diagnostic) -> ApplyResult:
    return ApplyResult(success=False, snapshot=snapshot, diagnostics=[diagnostic])


def _snapshot_contract_diagnostics(
    snapshot: RuntimeSnapshot,
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
    trusted_information_state_history: dict[str, list[dict[str, object]]],
) -> list[Diagnostic]:
    checks = (
        workflow_result_contract_diagnostics,
        evaluation_result_contract_diagnostics,
        proposition_truth_contract_diagnostics,
    )
    diagnostics: list[Diagnostic] = []
    for check in checks:
        diagnostics = check(snapshot)
        if diagnostics:
            break
    if not diagnostics:
        diagnostics = participant_runtime_state_contract_diagnostics(
            snapshot,
            information_state_context_resolver=information_state_context_resolver,
            trusted_information_state_history=trusted_information_state_history,
        )
    return diagnostics


def _snapshot_address_contract_diagnostics(snapshot: RuntimeSnapshot) -> list[Diagnostic]:
    for map_key, entry in snapshot.entries.items():
        try:
            require_compiled_address(map_key, field_name="snapshot map key")
            require_compiled_address(entry.address)
        except ValueError:
            return [
                _backend_contract_invalid(
                    "runtime.snapshot",
                    "Backend snapshot contains a non-canonical resource address.",
                )
            ]
        if map_key != entry.address:
            return [
                _backend_contract_invalid(
                    "runtime.snapshot",
                    "Backend snapshot map key does not equal its embedded address.",
                )
            ]
    return []


def _changed_address_transition_diagnostics(
    result: ApplyResult,
    baseline_snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    admitted = _snapshot_carrier_addresses(baseline_snapshot) | _snapshot_carrier_addresses(result.snapshot)
    if set(result.changed_addresses) - admitted:
        return [
            _backend_contract_invalid(
                "runtime.changed-addresses",
                "Backend reported a changed address outside the snapshot transition.",
            )
        ]
    return []


def _snapshot_carrier_addresses(snapshot: RuntimeSnapshot) -> set[str]:
    carriers = (
        snapshot.entries,
        snapshot.orchestration_results,
        snapshot.orchestration_history,
        snapshot.evaluation_results,
        snapshot.evaluation_history,
        snapshot.proposition_truth_results,
        snapshot.participant_episode_results,
        snapshot.participant_episode_history,
        snapshot.participant_behavior_history,
        snapshot.participant_control_history,
        snapshot.participant_crossing_history,
        snapshot.information_state_history,
        snapshot.participant_autonomous_execution_states,
        snapshot.participant_execution_services,
        snapshot.shared_state_records,
        snapshot.shared_state_history,
        snapshot.joint_action_records,
        snapshot.time_management_contexts,
    )
    addresses = {str(address) for carrier in carriers for address in carrier}
    if snapshot.time_model_state is not None:
        addresses.update(snapshot.time_model_state.clocks)
    return addresses


def _snapshot_transition_contract_diagnostics(
    previous_snapshot: RuntimeSnapshot,
    next_snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    diagnostics = participant_runtime_history_transition_diagnostics(previous_snapshot, next_snapshot)
    try:
        validate_time_runtime_transition(previous_snapshot.time_model_state, next_snapshot.time_model_state)
    except ValueError as exc:
        diagnostics.append(
            _backend_contract_invalid(
                "runtime.snapshot.time-model-state",
                str(exc),
            )
        )
    return diagnostics
