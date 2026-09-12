from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import is_dataclass, replace

from pydantic import BaseModel
from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.contracts.time_model import validate_time_runtime_transition
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, RealizationProvenanceEntry, RuntimeSnapshot
from raes_processor.models import CompiledRealizationRequirement
from raes_processor.planner import (
    prepared_delivery_violation,
    realization_authority_disclosure,
    realization_disclosure,
    sanitize_plan_realization_snapshot,
    sanitize_prepared_node_snapshot,
    sanitize_realization_snapshot,
)

from .backend_account_credentials import (
    plan_arguments_have_account_credentials,
    sanitize_account_credential_result,
    value_free_backend_diagnostics,
)
from .backend_call_contracts import (
    _apply_result_contract_violation,
    _materialize_diagnostics,
)
from .backend_effect_transitions import backend_effect_transition_diagnostics
from .backend_entry_transitions import backend_entry_transition_diagnostics
from .backend_input_contracts import backend_input_violation
from .backend_preparation import prepare_backend_invocation
from .backend_realization_authority import (
    _apply_authority_diagnostics,
    _bind_submitted_plan,
    _RealizationApplyContext,
)
from .backend_snapshot_contracts import snapshot_address_contract_diagnostics, snapshot_carrier_addresses
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
    if invalid := backend_input_violation(args):
        return [_backend_contract_invalid(address, invalid)]
    try:
        result = method(*(_isolated_argument(argument) for argument in args))
    except Exception as exc:
        diagnostics = [_backend_call_failed(address, exc)]
    else:
        diagnostics, invalid_message = _materialize_diagnostics(result, address)
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
    service_dependencies: tuple[object, ...] = (),
) -> ApplyResult:
    realization_context = realization or _RealizationApplyContext()
    if invalid := backend_input_violation(
        (*args, snapshot), authority=realization_context, service_dependencies=service_dependencies
    ):
        return _failed_apply_result(snapshot, _backend_contract_invalid(address, invalid))
    args, realization_context = _bind_submitted_plan(args, realization_context, operation_id)
    baseline_snapshot = deepcopy(snapshot)
    authority_diagnostics = _apply_authority_diagnostics(realization_context, address)
    if authority_diagnostics:
        return ApplyResult(
            success=False,
            snapshot=baseline_snapshot,
            diagnostics=authority_diagnostics,
        )
    args, realization_context, diagnostics = prepare_backend_invocation(
        method, args, baseline_snapshot, realization_context
    )
    if args is None:
        return ApplyResult(False, baseline_snapshot, diagnostics=diagnostics)
    result = _invoke_backend_apply(
        method,
        args,
        address=address,
        snapshot=snapshot,
        baseline_snapshot=baseline_snapshot,
        realization=deepcopy(realization_context),
        information_state_context_resolver=information_state_context_resolver,
        service_dependencies=service_dependencies,
    )
    result.diagnostics = [*diagnostics, *result.diagnostics]
    return result


def _invoke_backend_apply(
    method: Callable[..., object],
    args: tuple[object, ...],
    *,
    address: str,
    snapshot: RuntimeSnapshot,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
    service_dependencies: tuple[object, ...],
) -> ApplyResult:
    backend_snapshot = deepcopy(snapshot)
    backend_args = tuple(
        backend_snapshot if arg is snapshot else _isolated_argument(arg, service_dependencies) for arg in args
    )
    try:
        result = method(*backend_args)
    except (TypeError, ValueError):
        return _failed_apply_result(
            baseline_snapshot,
            _backend_contract_invalid(address, "Backend could not construct a valid apply result."),
        )
    except Exception as exc:
        return _failed_apply_result(baseline_snapshot, _backend_call_failed(address, exc))
    try:
        return _finalize_backend_apply(
            result,
            address=address,
            baseline_snapshot=baseline_snapshot,
            realization=realization,
            information_state_context_resolver=information_state_context_resolver,
        )
    except Exception:
        return _failed_apply_result(
            baseline_snapshot,
            _backend_contract_invalid(address, "Backend returned an apply result that could not be validated."),
        )


def _isolated_argument(argument: object, service_dependencies: tuple[object, ...] = ()) -> object:
    """Isolate value carriers, retaining injected service dependency identity."""

    if any(argument is service for service in service_dependencies):
        return argument
    if is_dataclass(argument) or isinstance(argument, (BaseModel, dict, list, tuple)):
        return deepcopy(argument)
    return argument


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
                realization=realization,
            )
            if result.success and not finalized.success:
                return deepcopy(finalized)
            if realization.completion_plan is not None:
                finalized = _with_snapshot(
                    finalized, sanitize_prepared_node_snapshot(realization.completion_plan, finalized.snapshot)
                )
            invalid = _apply_result_contract_violation(finalized, address)
            if invalid:
                final_diagnostics = [_backend_contract_invalid(address, invalid)]
            else:
                # Reuse the admitted transient observations to validate the safe
                # values. This performs no collection and does not retain them.
                validation_projection = replace(
                    finalized,
                    snapshot=replace(
                        finalized.snapshot, realization_observations=result.snapshot.realization_observations
                    ),
                    operational_realization_observations=result.operational_realization_observations,
                )
                final_diagnostics, realization_provenance = _post_apply_contract_result(
                    validation_projection,
                    baseline_snapshot,
                    realization,
                    information_state_context_resolver=information_state_context_resolver,
                )
            if final_diagnostics:
                finalized = ApplyResult(False, baseline_snapshot, diagnostics=final_diagnostics)
            elif realization_provenance and finalized.success:
                finalized = _with_realization_provenance(finalized, realization_provenance)
    return deepcopy(finalized)


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
        realization=realization,
        information_state_context_resolver=information_state_context_resolver,
    )
    provenance: tuple[RealizationProvenanceEntry, ...] = ()
    if not diagnostics and result.success and realization.completion_plan is not None:
        violation = prepared_delivery_violation(realization.completion_plan, result.snapshot)
        if violation:
            diagnostics = [_backend_contract_invalid("runtime.preparation", violation)]
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
    realization: _RealizationApplyContext,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
) -> list[Diagnostic]:
    diagnostics = snapshot_address_contract_diagnostics(result.snapshot)
    if not diagnostics:
        diagnostics = _changed_address_transition_diagnostics(result, baseline_snapshot)
    if not diagnostics:
        diagnostics = backend_entry_transition_diagnostics(result, baseline_snapshot, realization.operation_plan)
    if not diagnostics:
        diagnostics = backend_effect_transition_diagnostics(result, baseline_snapshot, realization)
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
    realization: _RealizationApplyContext,
) -> ApplyResult:
    sanitized = result
    realization_plan, realization_requirements = realization.plan, realization.requirements
    if realization_plan is not None:
        try:
            sanitized = sanitize_account_credential_result(
                sanitized, realization.completion_plan or realization_plan, baseline_snapshot
            )
        except ValueError:
            return _failed_apply_result(
                baseline_snapshot,
                _backend_contract_invalid(
                    address, "Backend returned credential material outside its canonical material node."
                ),
            )
    if realization_plan is not None and (realization_plan.realization_authority or realization_requirements):
        try:
            safe_snapshot = (
                sanitize_plan_realization_snapshot(realization_plan, sanitized.snapshot)
                if realization_plan.realization_authority
                else sanitize_realization_snapshot(realization_requirements, sanitized.snapshot)
            )
        except (TypeError, ValueError):
            return _failed_apply_result(
                baseline_snapshot,
                _backend_contract_invalid(
                    address,
                    "Backend returned an invalid realization concern observation.",
                ),
            )
        sanitized = _with_snapshot(sanitized, safe_snapshot)
    if realization_plan is not None:
        sanitized = _with_snapshot(
            sanitized,
            sanitized.snapshot.with_entries(
                dict(sanitized.snapshot.entries),
                realization_observations=(),
            ),
        )
    return replace(sanitized, operational_realization_observations=())


def _supplemental_realization_requirements(
    realization: _RealizationApplyContext,
) -> tuple[CompiledRealizationRequirement, ...]:
    """Keep non-registry contracts while the plan owns registry concerns."""

    if realization.plan is None or not realization.plan.realization_authority:
        return realization.requirements
    plan_identities = {
        (entry.address, entry.field_path, entry.requirement_kind) for entry in realization.plan.realization_authority
    }
    plan_identities.update(
        (entry.address, entry.field_path, entry.concern) for entry in realization.plan.realization_constraints
    )
    return tuple(
        requirement
        for requirement in realization.requirements
        if (requirement.address, requirement.field_path, requirement.requirement_kind) not in plan_identities
    )


def _with_snapshot(
    result: ApplyResult,
    snapshot: RuntimeSnapshot,
) -> ApplyResult:
    return replace(result, snapshot=snapshot)


def _with_realization_provenance(
    result: ApplyResult,
    provenance: tuple[RealizationProvenanceEntry, ...],
) -> ApplyResult:
    """Attach the SEM-218 provenance ledger to a successful apply's snapshot."""

    return replace(
        result,
        snapshot=result.snapshot.with_entries(
            dict(result.snapshot.entries),
            realization_provenance=provenance,
        ),
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


def _changed_address_transition_diagnostics(
    result: ApplyResult,
    baseline_snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    admitted = snapshot_carrier_addresses(baseline_snapshot) | snapshot_carrier_addresses(result.snapshot)
    if set(result.changed_addresses) - admitted:
        return [
            _backend_contract_invalid(
                "runtime.changed-addresses",
                "Backend reported a changed address outside the snapshot transition.",
            )
        ]
    return []


def _snapshot_transition_contract_diagnostics(
    previous_snapshot: RuntimeSnapshot,
    next_snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    diagnostics = participant_runtime_history_transition_diagnostics(previous_snapshot, next_snapshot)
    try:
        validate_time_runtime_transition(previous_snapshot.time_model_state, next_snapshot.time_model_state)
    except ValueError:
        diagnostics.append(
            _backend_contract_invalid(
                "runtime.snapshot.time-model-state",
                "Backend returned an invalid shared-time transition.",
            )
        )
    return diagnostics
