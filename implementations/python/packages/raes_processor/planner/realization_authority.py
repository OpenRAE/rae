"""Resolve complete SEM-218 compiler posture into provisioning-plan authority."""

from __future__ import annotations

from raes.explicitness import ExplicitnessClass
from raes.runtime_resource_limits import process_resource_limit_identity_digest
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.bounded_domains import EnumDomain, scalar_in_domain
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import (
    ChangeAction,
    ProvisioningPlan,
    RealizationAuthorityBound,
    RealizationAuthorityMode,
    ResolvedRealizationAuthority,
    planned_realization_authority,
)
from raes_contracts.realization_authority import planned_realization_selection_diagnostics
from raes_contracts.realization_structure import evaluate_realization_constraint, realization_constraint_binding
from raes_contracts.runtime_state import RealizationProvenanceEntry, RuntimeSnapshot
from raes_contracts.vocabulary import ProcessResourceLimitKind, ProcessResourceLimitScope

from ..semantics.realization import (
    CompiledRealizationRequirement,
    ProcessResourceLimitDemand,
    RealizationValueConstraint,
    realization_support_diagnostics,
)
from ..semantics.realization_concerns import (
    CONCERN_PAYLOAD_PATH,
    processor_derived_provisioning_concern_kinds,
    project_realization_concern,
    realization_concern_descriptors,
)
from ..semantics.realization_runtime_evaluation import evaluate_registered_realization
from .realization_authority_materialization import materialize_realization_authority
from .realization_constraint_views import planned_constraint_admission, planned_constraint_disclosure


def _payload_pointer(path: tuple[str, ...]) -> str:
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in path)


_MISSING = object()


def _nested_value(payload: object, path: tuple[str, ...]) -> object:
    current = payload
    for token in path:
        if not isinstance(current, dict) or token not in current:
            return _MISSING
        current = current[token]
    return current


def _applicable_descriptor(operation: object, descriptor: object) -> bool:
    resource_type = getattr(operation, "resource_type", None)
    section = getattr(descriptor, "section", None)
    if section == "nodes":
        applies = resource_type in {"node", "network"}
    else:
        applies = section == "content" and resource_type == "content-placement"
    if not applies:
        return False
    value = _nested_value(getattr(operation, "payload", None), descriptor.payload_path)
    authored_value = None if value is _MISSING else value
    return descriptor.includes_authored_value(authored_value)


def _expected_realization_authority(plan: ProvisioningPlan) -> dict[tuple[str, str], str]:
    expected: dict[tuple[str, str], str] = {}
    for operation in plan.operations:
        if operation.action is ChangeAction.DELETE:
            continue
        for descriptor in realization_concern_descriptors():
            if _applicable_descriptor(operation, descriptor):
                expected[(operation.address, descriptor.concern_kind)] = _payload_pointer(descriptor.payload_path)
        for concern_kind in processor_derived_provisioning_concern_kinds(
            operation.resource_type,
            operation.payload,
        ):
            expected[(operation.address, concern_kind)] = _payload_pointer(CONCERN_PAYLOAD_PATH[concern_kind])
    return expected


def _authority_payload_pointer_diagnostic(
    plan: ProvisioningPlan,
    expected: dict[tuple[str, str], str],
) -> Diagnostic | None:
    diagnostic = None
    for identity, pointer in expected.items():
        entry = planned_realization_authority(plan, *identity)
        if entry is None:
            raise AssertionError("realization authority identity disappeared after completeness validation")
        if entry.payload_pointer != pointer:
            diagnostic = Diagnostic(
                code="realization.authority-payload-pointer-invalid",
                domain=entry.domain,
                address=entry.address,
                message=(
                    f"Provisioning plan authority uses a non-canonical payload pointer for '{entry.requirement_kind}'."
                ),
            )
            break
    return diagnostic


def _authority_inventory_diagnostic(
    plan: ProvisioningPlan,
    expected: dict[tuple[str, str], str],
) -> Diagnostic | None:
    actual = {(entry.address, entry.requirement_kind) for entry in plan.realization_authority}
    missing = sorted(set(expected) - actual)
    excess = sorted(actual - set(expected))
    diagnostic = None
    if missing:
        address, kind = missing[0]
        diagnostic = Diagnostic(
            code="realization.authority-incomplete",
            domain="runtime-realization",
            address=address,
            message=f"Provisioning plan is missing resolved authority for '{kind}'.",
        )
    elif excess:
        address, kind = excess[0]
        diagnostic = Diagnostic(
            code="realization.authority-excess",
            domain="runtime-realization",
            address=address,
            message=f"Provisioning plan carries authority for inapplicable concern '{kind}'.",
        )
    else:
        diagnostic = _authority_payload_pointer_diagnostic(plan, expected)
    return diagnostic


def _requires_realization_envelope(plan: ProvisioningPlan) -> bool:
    return any(
        entry.mode in {RealizationAuthorityMode.OPEN, RealizationAuthorityMode.CONSTRAINED}
        for entry in plan.realization_authority
    )


def _manifest_authority_diagnostic(
    plan: ProvisioningPlan,
    manifest: BackendManifest,
) -> Diagnostic | None:
    target_envelope = manifest.realization_envelope.identity if manifest.realization_envelope is not None else None
    envelope_mismatch = _requires_realization_envelope(plan) and (
        plan.realization_envelope is None or target_envelope is None or plan.realization_envelope != target_envelope
    )
    diagnostic = None
    if envelope_mismatch:
        diagnostic = Diagnostic(
            code="realization.authority-envelope-mismatch",
            domain="runtime-realization",
            address="runtime.realization-envelope",
            message="Provisioning plan authority was not admitted against the selected realization envelope.",
        )
    else:
        try:
            requirements = _compiled_runtime_views(plan)
        except (TypeError, ValueError):
            diagnostic = _invalid_runtime_view_diagnostic(plan)
        else:
            support_diagnostics = [
                *realization_support_diagnostics(requirements, manifest),
                *planned_constraint_admission(plan, manifest),
            ]
            diagnostic = support_diagnostics[0] if support_diagnostics else None
    return diagnostic


def realization_authority_diagnostics(
    plan: ProvisioningPlan,
    manifest: BackendManifest | None = None,
) -> list[Diagnostic]:
    """Recompute registry-derived authority completeness from plan operations."""

    expected = _expected_realization_authority(plan)
    diagnostic = _authority_inventory_diagnostic(plan, expected)
    if diagnostic is None:
        diagnostic = _recursive_binding_diagnostic(plan)
    if diagnostic is None:
        selection_diagnostics = planned_realization_selection_diagnostics(plan)
        diagnostic = selection_diagnostics[0] if selection_diagnostics else None
    if diagnostic is None and manifest is not None:
        diagnostic = _manifest_authority_diagnostic(plan, manifest)
    return [diagnostic] if diagnostic is not None else []


def _recursive_binding_diagnostic(plan: ProvisioningPlan) -> Diagnostic | None:
    operations = {operation.address: operation for operation in plan.operations}
    for authority in plan.realization_authority:
        if authority.constraint_document is None:
            continue
        operation = operations.get(authority.address)
        try:
            selected = _pointer_value(getattr(operation, "payload", None), authority.payload_pointer)
            projected = project_realization_concern(authority.requirement_kind, selected, recursive=True)
            binding = realization_constraint_binding(authority.constraint_document, projected)
            valid = binding == authority.constraint_binding
            if valid and authority.mode is not RealizationAuthorityMode.OPEN:
                valid = evaluate_realization_constraint(authority.constraint_document, projected).conformant
        except (TypeError, ValueError, AttributeError):
            valid = False
        if not valid:
            return Diagnostic(
                code="realization.authority-selection-invalid",
                domain=authority.domain,
                address=authority.address,
                message="Recursive authority is not bound to the submitted source projection.",
            )
    return None


def _explicitness(mode: RealizationAuthorityMode) -> ExplicitnessClass:
    return ExplicitnessClass(mode.value)


def _compiled_runtime_views(plan: ProvisioningPlan) -> tuple[CompiledRealizationRequirement, ...]:
    declared_ops = {operation.address: operation for operation in plan.operations}
    return tuple(
        _compiled_runtime_view(authority, declared_ops)
        for authority in plan.realization_authority
        if authority.mode is not RealizationAuthorityMode.CLOSED
    )


def _compiled_runtime_view(
    authority: ResolvedRealizationAuthority,
    declared_ops: dict[str, object],
) -> CompiledRealizationRequirement:
    value_constraints: tuple[RealizationValueConstraint, ...] = ()
    process_resource_limits: tuple[ProcessResourceLimitDemand, ...] = ()
    if authority.requirement_kind == "process-resource-limits":
        process_resource_limits = _process_resource_limit_demands(authority, declared_ops)
        demand_identities = {demand.identity_digest for demand in process_resource_limits}
        constraints: list[RealizationValueConstraint] = []
        for bound in authority.bounds:
            if (
                bound.identity_digest is None
                or bound.identity_digest not in demand_identities
                or not isinstance(bound.domain, EnumDomain)
            ):
                raise ValueError("process-resource-limit authority bound does not identify a declared demand")
            constraints.append(
                RealizationValueConstraint(
                    identity_digest=bound.identity_digest,
                    leaf=bound.value_pointer.removeprefix("/"),
                    parameter=("plan-authority",),
                    allowed_values=tuple(bound.domain.values),
                )
            )
        value_constraints = tuple(constraints)
    return CompiledRealizationRequirement(
        field_path=authority.field_path,
        address=authority.address,
        domain=authority.domain,
        requirement_kind=authority.requirement_kind,
        explicitness=_explicitness(authority.mode),
        provenance=authority.provenance,
        governing_scope=authority.governing_scope,
        verification_scope=authority.verification_scope,
        required_observation_strength=authority.required_observation_strength,
        value_constraints=value_constraints,
        process_resource_limits=process_resource_limits,
        structure=authority.structure,
        constraint_document=authority.constraint_document,
        constraint_binding=authority.constraint_binding,
    )


def _process_resource_limit_demands(
    authority: ResolvedRealizationAuthority,
    declared_ops: dict[str, object],
) -> tuple[ProcessResourceLimitDemand, ...]:
    operation = declared_ops.get(authority.address)
    declared = (
        _pointer_value(getattr(operation, "payload", None), authority.payload_pointer)
        if operation is not None
        else _MISSING
    )
    if declared is _MISSING:
        if authority.mode is RealizationAuthorityMode.OPEN:
            return ()
        raise ValueError("declared process-resource-limit authority has no operation payload")
    projected = project_realization_concern("process-resource-limits", declared)
    if not isinstance(projected, list) or any(not isinstance(item, dict) for item in projected):
        raise ValueError("process-resource-limit projection must be a list")
    return tuple(
        ProcessResourceLimitDemand(
            identity_digest=process_resource_limit_identity_digest(item),
            resource=ProcessResourceLimitKind(str(item["resource"])),
            scope=ProcessResourceLimitScope(str(item["scope"])),
            soft=item["soft"],
            hard=item["hard"],
        )
        for item in projected
    )


def _invalid_runtime_view_diagnostic(plan: ProvisioningPlan) -> Diagnostic:
    address = next(
        (entry.address for entry in plan.realization_authority if entry.mode is not RealizationAuthorityMode.CLOSED),
        "runtime.realization-authority",
    )
    return Diagnostic(
        code="realization.authority-demand-invalid",
        domain="runtime-realization",
        address=address,
        message="Provisioning plan authority cannot reconstruct its canonical realization demand.",
    )


def _closed_materialization_diagnostic(
    authority: ResolvedRealizationAuthority,
    declared_ops: dict[str, object],
    returned_snapshot: RuntimeSnapshot,
) -> Diagnostic | None:
    declared_op = declared_ops.get(authority.address)
    snapshot_entry = returned_snapshot.entries.get(authority.address)
    if declared_op is None or snapshot_entry is None:
        return None
    declared = _pointer_value(getattr(declared_op, "payload", None), authority.payload_pointer)
    realized = _pointer_value(snapshot_entry.payload, authority.payload_pointer)
    if realized is _MISSING or (declared is not _MISSING and realized == declared):
        return None
    return Diagnostic(
        code="runtime.backend-contract-invalid",
        domain=authority.domain,
        address=authority.address,
        message=f"Backend materialized closed realization concern '{authority.requirement_kind}'.",
        severity=Severity.ERROR,
    )


def _pointer_value(value: object, pointer: str) -> object:
    current = value
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return _MISSING
    return current


def _runtime_authority_diagnostic(authority: ResolvedRealizationAuthority) -> Diagnostic:
    return Diagnostic(
        code="runtime.backend-contract-invalid",
        domain=authority.domain,
        address=authority.address,
        message=f"Backend cannot satisfy resolved realization authority for '{authority.requirement_kind}'.",
        severity=Severity.ERROR,
    )


def _bound_value(value: object, bound: RealizationAuthorityBound) -> object:
    target = value
    if bound.identity_digest is not None:
        if not isinstance(value, list):
            return _MISSING
        target = next(
            (item for item in value if _safe_process_limit_identity(item) == bound.identity_digest),
            _MISSING,
        )
    return _pointer_value(target, bound.value_pointer)


def _safe_process_limit_identity(value: object) -> str | None:
    try:
        return process_resource_limit_identity_digest(value)
    except (TypeError, ValueError):
        return None


def _constraint_diagnostic(
    authority: ResolvedRealizationAuthority,
    returned_snapshot: RuntimeSnapshot,
) -> Diagnostic | None:
    snapshot_entry = returned_snapshot.entries.get(authority.address)
    realized = (
        _pointer_value(snapshot_entry.payload, authority.payload_pointer) if snapshot_entry is not None else _MISSING
    )
    diagnostic = None
    if realized is not _MISSING:
        try:
            projection = project_realization_concern(authority.requirement_kind, realized, observed=True)
        except (TypeError, ValueError):
            diagnostic = _runtime_authority_diagnostic(authority)
        else:
            outside_bounds = any(
                (value := _bound_value(projection, bound)) is _MISSING or not scalar_in_domain(value, bound.domain)
                for bound in authority.bounds
            )
            diagnostic = _runtime_authority_diagnostic(authority) if outside_bounds else None
    return diagnostic


def _evaluate_authority_disclosure(
    authority: ResolvedRealizationAuthority,
    runtime_views: dict[tuple[str, str], CompiledRealizationRequirement],
    declared_plan: ProvisioningPlan,
    declared_ops: dict[str, object],
    returned_snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
) -> tuple[Diagnostic | None, RealizationProvenanceEntry | None]:
    entry = None
    if authority.mode is RealizationAuthorityMode.CLOSED:
        diagnostic = _closed_materialization_diagnostic(authority, declared_ops, returned_snapshot)
    else:
        requirement = runtime_views[(authority.address, authority.requirement_kind)]
        diagnostic, entry = evaluate_registered_realization(
            requirement,
            declared_plan,
            returned_snapshot,
            manifest=manifest,
        )
        if diagnostic is None and authority.mode is RealizationAuthorityMode.CONSTRAINED:
            diagnostic = _constraint_diagnostic(authority, returned_snapshot)
            entry = None if diagnostic is not None else entry
    return diagnostic, entry


def realization_authority_disclosure(
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
    *,
    manifest: BackendManifest | None = None,
) -> tuple[list[Diagnostic], tuple[RealizationProvenanceEntry, ...]]:
    """Apply the plan-owned boundary to backend state and derive provenance."""

    completeness = realization_authority_diagnostics(declared_plan, manifest)
    if completeness:
        return completeness, ()
    declared_ops = {operation.address: operation for operation in declared_plan.operations}
    try:
        runtime_views = {
            (authority.address, authority.requirement_kind): _compiled_runtime_view(authority, declared_ops)
            for authority in declared_plan.realization_authority
            if authority.mode is not RealizationAuthorityMode.CLOSED
        }
    except (TypeError, ValueError):
        return [_invalid_runtime_view_diagnostic(declared_plan)], ()
    diagnostics: list[Diagnostic] = []
    provenance: list[RealizationProvenanceEntry] = []
    for authority in declared_plan.realization_authority:
        diagnostic, entry = _evaluate_authority_disclosure(
            authority,
            runtime_views,
            declared_plan,
            declared_ops,
            returned_snapshot,
            manifest,
        )
        if diagnostic is not None:
            diagnostics.append(diagnostic)
        if entry is not None:
            provenance.append(entry)
    constraint_diagnostics, constraint_provenance = planned_constraint_disclosure(
        declared_plan, returned_snapshot, manifest
    )
    diagnostics.extend(constraint_diagnostics)
    provenance.extend(constraint_provenance)
    return diagnostics, tuple(provenance)


def sanitize_plan_realization_snapshot(
    declared_plan: ProvisioningPlan,
    returned_snapshot: RuntimeSnapshot,
) -> RuntimeSnapshot:
    """Sanitize admitted realization observations from plan-owned authority."""

    from ..semantics.realization_snapshot_sanitization import sanitize_realization_snapshot

    declared_ops = {operation.address: operation for operation in declared_plan.operations}
    return sanitize_realization_snapshot(
        tuple(
            _compiled_runtime_view(authority, declared_ops)
            for authority in declared_plan.realization_authority
            if authority.mode is not RealizationAuthorityMode.CLOSED
        ),
        returned_snapshot,
    )


__all__ = [
    "materialize_realization_authority",
    "realization_authority_diagnostics",
    "realization_authority_disclosure",
    "sanitize_plan_realization_snapshot",
]
