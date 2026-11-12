"""Gate and disclose one backend apply result before it becomes runtime state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import InvalidInputError
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_contracts.runtime_state import ApplyResult, RealizationProvenanceEntry, RuntimeSnapshot
from raes_processor.models import CompiledRealizationRequirement
from raes_processor.planner import (
    prepared_delivery_violation,
    prepared_node_disclosure,
    realization_authority_disclosure,
    realization_cleanup_diagnostics,
    realization_disclosure,
    sanitize_plan_realization_snapshot,
    sanitize_prepared_node_snapshot,
    sanitize_realization_snapshot,
)
from raes_processor.semantics.realization_comparison import portable_realization_plan, portable_realization_value

from .backend_account_credentials import sanitize_account_credential_result
from .backend_call_contracts import _apply_result_contract_violation
from .backend_effect_transitions import backend_effect_transition_diagnostics
from .backend_entry_transitions import backend_entry_transition_diagnostics
from .backend_realization_authority import _RealizationApplyContext
from .backend_result_diagnostics import (
    _backend_contract_invalid,
    _changed_address_transition_diagnostics,
    _failed_apply_result,
    _snapshot_contract_diagnostics,
    _snapshot_transition_contract_diagnostics,
)
from .backend_snapshot_contracts import snapshot_address_contract_diagnostics, snapshot_values_equal

__all__ = ["_finalize_backend_apply"]


def _revalidated_diagnostics(
    result: ApplyResult,
    finalized: ApplyResult,
    *,
    address: str,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
) -> tuple[list[Diagnostic], tuple[RealizationProvenanceEntry, ...]]:
    """Revalidate one gated result, reusing the admitted transient observations."""

    invalid = _apply_result_contract_violation(finalized, address)
    if invalid:
        return [_backend_contract_invalid(address, invalid)], ()
    # Reuse the admitted transient observations to validate the safe values.
    # This performs no collection and does not retain them.
    validation_projection = cast(
        "ApplyResult",
        replace(
            finalized,
            snapshot=replace(finalized.snapshot, realization_observations=result.snapshot.realization_observations),
            operational_realization_observations=result.operational_realization_observations,
        ),
    )
    return _post_apply_contract_result(
        validation_projection,
        baseline_snapshot,
        realization,
        information_state_context_resolver=information_state_context_resolver,
    )


def _gated_backend_result(
    result: ApplyResult,
    *,
    address: str,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
) -> ApplyResult:
    """Sanitize the realized snapshot, then revalidate the gated result."""

    finalized = _sanitize_backend_realization(
        result,
        address=address,
        baseline_snapshot=baseline_snapshot,
        realization=realization,
    )
    if result.success and not finalized.success:
        return finalized
    if realization.completion_plan is not None:
        finalized = _with_snapshot(
            finalized, sanitize_prepared_node_snapshot(realization.completion_plan, finalized.snapshot)
        )
    final_diagnostics, realization_provenance = _revalidated_diagnostics(
        result,
        finalized,
        address=address,
        baseline_snapshot=baseline_snapshot,
        realization=realization,
        information_state_context_resolver=information_state_context_resolver,
    )
    if final_diagnostics:
        finalized = ApplyResult(False, baseline_snapshot, diagnostics=final_diagnostics)
    elif finalized.success:
        finalized = _with_retained_realization_provenance(
            finalized, baseline_snapshot, realization, realization_provenance
        )
    return finalized


def _with_retained_realization_provenance(
    result: ApplyResult,
    baseline_snapshot: RuntimeSnapshot,
    realization: _RealizationApplyContext,
    provenance: tuple[RealizationProvenanceEntry, ...],
) -> ApplyResult:
    """Retain unaffected live-resource rows alongside newly disclosed rows."""

    affected = (
        {
            operation.address
            for operation in (realization.completion_plan or realization.operation_plan).operations
            if operation.action is not ChangeAction.UNCHANGED
        }
        if realization.operation_plan is not None
        else set()
    )
    retained = tuple(
        entry
        for entry in baseline_snapshot.realization_provenance
        if entry.address in result.snapshot.entries and entry.address not in affected
    )
    return _with_realization_provenance(result, (*retained, *provenance))


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
        return deepcopy(_failed_apply_result(baseline_snapshot, _backend_contract_invalid(address, invalid_message)))
    assert isinstance(result, ApplyResult)
    contract_diagnostics, _provenance = _post_apply_contract_result(
        result,
        baseline_snapshot,
        realization,
        information_state_context_resolver=information_state_context_resolver,
    )
    if contract_diagnostics:
        return deepcopy(ApplyResult(success=False, snapshot=baseline_snapshot, diagnostics=contract_diagnostics))
    return deepcopy(
        _gated_backend_result(
            result,
            address=address,
            baseline_snapshot=baseline_snapshot,
            realization=realization,
            information_state_context_resolver=information_state_context_resolver,
        )
    )


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
    if not diagnostics and result.success and realization.completion_plan is not None:
        selected, returned = _portable_payloads(realization.completion_plan, result.snapshot)
        violation = prepared_delivery_violation(selected, returned)
        if violation:
            diagnostics = [_backend_contract_invalid("runtime.preparation", violation)]
    if diagnostics or realization.plan is None:
        return diagnostics, ()
    return _realization_disclosure_result(result, realization)


def _portable_payloads(plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> tuple[ProvisioningPlan, RuntimeSnapshot]:
    """Present declared and returned payloads as portable JSON to disclosure and sanitization.

    Admission accepts tuple, enum, dataclass and model carriers that the portable
    codec serializes. The disclosure readers and the safe-persistence sanitizer
    traverse JSON objects and arrays, so a carrier would otherwise hide the
    realization concern it encloses.
    """

    entries = {
        address: replace(entry, payload=portable_realization_value(entry.payload))
        for address, entry in snapshot.entries.items()
    }
    return portable_realization_plan(plan), snapshot.with_entries(entries)


def _realization_disclosure_result(
    result: ApplyResult, realization: _RealizationApplyContext
) -> tuple[list[Diagnostic], tuple[RealizationProvenanceEntry, ...]]:
    """Disclose plan and supplemental realization authority over one result."""

    plan = realization.plan
    validation_plan, returned = _portable_payloads(plan, result.snapshot)
    supplemental = _supplemental_realization_requirements(realization)
    if not result.success:
        return realization_cleanup_diagnostics(
            validation_plan,
            returned,
            manifest=realization.manifest,
            requirements=supplemental,
            artifact_availability=realization.artifact_availability,
        ), ()
    diagnostics, provenance = realization_authority_disclosure(
        validation_plan,
        returned,
        manifest=realization.manifest,
    )
    if diagnostics:
        return diagnostics, provenance
    supplemental_diagnostics, supplemental_provenance = realization_disclosure(
        supplemental,
        validation_plan,
        returned,
        manifest=realization.manifest,
        artifact_availability=realization.artifact_availability,
    )
    diagnostics.extend(supplemental_diagnostics)
    prepared_provenance = ()
    if not diagnostics and realization.completion_plan is not None:
        selected = portable_realization_plan(realization.completion_plan)
        prepared_diagnostics, prepared_provenance = prepared_node_disclosure(
            selected,
            returned,
            manifest=realization.manifest,
            artifact_availability=realization.artifact_availability,
        )
        diagnostics.extend(prepared_diagnostics)
    return diagnostics, (*provenance, *supplemental_provenance, *prepared_provenance)


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
                sanitized,
                realization.completion_plan or realization_plan,
                baseline_snapshot,
                requirements=_supplemental_realization_requirements(realization),
            )
        except InvalidInputError:
            return _failed_apply_result(
                baseline_snapshot,
                _backend_contract_invalid(
                    address, "Backend returned credential material outside its canonical material node."
                ),
            )
    if realization_plan is not None and (realization_plan.realization_authority or realization_requirements):
        try:
            safe_snapshot = _safe_realization_snapshot(realization_plan, realization_requirements, sanitized.snapshot)
        except TypeError, ValueError:
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
    return cast("ApplyResult", replace(sanitized, operational_realization_observations=()))


def _sanitized_realization(
    plan: ProvisioningPlan,
    requirements: tuple[CompiledRealizationRequirement, ...],
    snapshot: RuntimeSnapshot,
) -> RuntimeSnapshot:
    if plan.realization_authority:
        return sanitize_plan_realization_snapshot(plan, snapshot)
    return sanitize_realization_snapshot(requirements, snapshot)


def _safe_realization_snapshot(
    plan: ProvisioningPlan,
    requirements: tuple[CompiledRealizationRequirement, ...],
    snapshot: RuntimeSnapshot,
) -> RuntimeSnapshot:
    """Sanitize the portable view that the disclosure readers judged.

    An entry keeps the backend's own representation, sanitized in place, when
    that serializes to its sanitized view. Otherwise, as when an admitted carrier
    encloses a registered concern, the sanitized view is committed in its place.
    """

    view_plan, view = _portable_payloads(plan, snapshot)
    safe_view = _sanitized_realization(view_plan, requirements, view)
    try:
        kept = _sanitized_realization(plan, requirements, snapshot)
    except TypeError, ValueError:
        # The sanitized view is authoritative; an entry the sanitizer cannot
        # rewrite in place is replaced by its view below.
        kept = snapshot
    entries = {
        address: entry
        if snapshot_values_equal(entry.payload, safe_view.entries[address].payload)
        else safe_view.entries[address]
        for address, entry in kept.entries.items()
    }
    return kept.with_entries(entries)


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
    return cast("ApplyResult", replace(result, snapshot=snapshot))


def _with_realization_provenance(
    result: ApplyResult,
    provenance: tuple[RealizationProvenanceEntry, ...],
) -> ApplyResult:
    """Attach the SEM-218 provenance ledger to a successful apply's snapshot."""

    return cast(
        "ApplyResult",
        replace(
            result,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries),
                realization_provenance=tuple(
                    {
                        (entry.address, entry.field_path, entry.domain, entry.requirement_kind): entry
                        for entry in provenance
                    }.values()
                ),
            ),
        ),
    )
