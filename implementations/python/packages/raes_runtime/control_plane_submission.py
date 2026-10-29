"""Submission-admission diagnostics for the runtime control plane.

These helpers screen provisioning, orchestration, and evaluation plans before
``RuntimeControlPlane`` submits them, mirroring the async submission contract in
``control_plane.py``.
"""

from __future__ import annotations

from collections.abc import Mapping

from raes_backend_protocols.account_features import provisioner_account_features
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.domain_topology import domain_topology_plan_diagnostics
from raes_backend_protocols.service_materialization import service_materialization_plan_diagnostics
from raes_contracts.apparatus import (
    DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND,
    RUNTIME_REALIZATION_DOMAIN,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT
from raes_contracts.planning import (
    ChangeAction,
    EvaluationPlan,
    OrchestrationPlan,
    PlanOperation,
    ProvisioningPlan,
    RuntimeDomain,
    require_plan_operation_identity,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.planner import (
    account_credential_spec_is_valid,
    generated_artifact_payload_diagnostic,
    realization_authority_diagnostics,
)

from .observation_execution import ObservationRuntime, observation_submission_diagnostic


def unavailable_backend_diagnostics(domain: RuntimeDomain, component: str) -> list[Diagnostic]:
    return [
        Diagnostic(
            code="runtime.control-plane.rejected",
            domain="runtime",
            address=f"runtime.control-plane.{domain.value}",
            message=f"Target does not provide {component}.",
        )
    ]


_STATEFUL_ADMISSION_BY_RESOURCE_TYPE = {
    "generated-artifact": (
        "supports_generated_artifacts",
        "provisioner.generated-artifacts-unsupported",
        "generated artifacts",
    ),
    "persistent-volume": (
        "supports_persistent_volumes",
        "provisioner.persistent-volumes-unsupported",
        "persistent volumes",
    ),
}


def _submitted_plan_diagnostics(
    plan: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
    domain: RuntimeDomain,
    snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None = None,
    observation_runtime: ObservationRuntime | None = None,
    *,
    durable_lifecycle_available: bool = True,
) -> list[Diagnostic]:
    if isinstance(plan, ProvisioningPlan) and plan.inventory_refresh:
        return _inventory_refresh_submission_diagnostics(plan, snapshot, manifest)
    admitted = set(snapshot.entries) | {operation.address for operation in plan.operations}
    demand_diagnostic = observation_submission_diagnostic(
        plan,
        manifest,
        observation_runtime,
        durable_lifecycle_available=durable_lifecycle_available,
    )
    diagnostics = [demand_diagnostic] if demand_diagnostic is not None else []
    if not diagnostics:
        operation_diagnostic = next(
            (
                diagnostic
                for operation in plan.operations
                if (diagnostic := _submitted_operation_diagnostic(operation, domain, snapshot, admitted)) is not None
            ),
            None,
        )
        diagnostics = [operation_diagnostic] if operation_diagnostic is not None else []
    if not diagnostics and domain is RuntimeDomain.PROVISIONING and isinstance(plan, ProvisioningPlan):
        diagnostics = _provisioning_submission_diagnostics(plan, snapshot, manifest)
    return diagnostics


def _inventory_refresh_submission_diagnostics(
    plan: ProvisioningPlan, snapshot: RuntimeSnapshot, manifest: BackendManifest | None
) -> list[Diagnostic]:
    source = plan.materialization_source
    supported = manifest is not None and RUNTIME_DESCENDANTS_CONTRACT in manifest.supported_contract_versions
    retained = source is not None and any(
        record.inventory is not None
        and record.run_id == source.run_id
        and record.inventory.source_digest == source.instantiated_digest
        for record in snapshot.materialization_attestations
    )
    if not supported or not retained:
        return [
            Diagnostic(
                code="runtime.inventory-refresh-unsupported",
                domain="runtime",
                address="runtime.inventory-refresh",
                message="Inventory refresh requires negotiated support and its accepted source inventory.",
            )
        ]
    return _provisioning_submission_diagnostics(plan, snapshot, manifest)


def control_plane_plan_diagnostics(
    control_plane: object,
    plan: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
    domain: RuntimeDomain,
) -> list[Diagnostic]:
    """Evaluate repeatable admission checks against the control plane's current cut."""

    source = plan.materialization_source
    if source is not None and source.target_scope is not None and source.target_scope != control_plane._target_scope:
        return [
            Diagnostic(
                code="runtime.plan-target-mismatch",
                domain="runtime",
                address="runtime.control-plane.plan",
                message="Inventory source context belongs to another runtime target.",
            )
        ]

    diagnostics = _submitted_plan_diagnostics(
        plan,
        domain,
        control_plane._snapshot,
        control_plane._target.manifest,
        control_plane._target.observation_runtime,
        durable_lifecycle_available=control_plane._store_commits.crash_atomic,
    )
    if not diagnostics:
        diagnostics.extend(control_plane._plan_authorization_diagnostics(plan))
    return diagnostics


def _provisioning_submission_diagnostics(
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
    manifest: BackendManifest | None,
) -> list[Diagnostic]:
    if manifest is None:
        raise ValueError("provisioning submission admission requires a backend manifest")
    diagnostics = realization_authority_diagnostics(plan, manifest)
    if not diagnostics:
        diagnostic = _account_credential_submission_diagnostic(plan, manifest) or _stateful_submission_diagnostic(
            plan, manifest
        )
        diagnostics = [diagnostic] if diagnostic is not None else []
    if not diagnostics:
        diagnostics = service_materialization_plan_diagnostics(
            plan,
            manifest.provisioner,
            manifest.realization_envelope,
            manifest.realization_support,
        )
    if not diagnostics:
        diagnostics = domain_topology_plan_diagnostics(
            plan,
            snapshot=snapshot,
            supported_domain_profiles=manifest.provisioner.supported_domain_profiles,
        )
    return diagnostics[:1]


def _account_credential_submission_diagnostic(
    plan: ProvisioningPlan,
    manifest: BackendManifest,
) -> Diagnostic | None:
    """Validate credential-bearing direct-plan account payloads before side effects."""

    for operation in plan.operations:
        if operation.action is ChangeAction.DELETE or operation.resource_type != "account-placement":
            continue
        spec = operation.payload.get("spec")
        if not isinstance(spec, Mapping) or not spec.get("credential_bindings"):
            continue
        diagnostic = _account_credential_operation_diagnostic(operation, spec, manifest)
        if diagnostic is not None:
            return diagnostic
    return None


def _account_credential_operation_diagnostic(
    operation: PlanOperation,
    spec: Mapping[str, object],
    manifest: BackendManifest,
) -> Diagnostic | None:
    account_name = operation.payload.get("account_name") or operation.payload.get("name")
    diagnostic: Diagnostic | None = None
    if not account_credential_spec_is_valid(spec):
        diagnostic = Diagnostic(
            code="provisioner.account-credential-binding-invalid",
            domain="provisioning",
            address=operation.address,
            message="Account credential binding payload does not satisfy the canonical account contract.",
        )
    elif not isinstance(account_name, str) or operation.address != f"provision.account.{account_name}":
        diagnostic = Diagnostic(
            code="provisioner.account-credential-binding-invalid",
            domain="provisioning",
            address=operation.address,
            message="Account credential binding payload does not match its canonical account address.",
        )
    elif not manifest.provisioner.supports_accounts:
        diagnostic = Diagnostic(
            code="provisioner.accounts-unsupported",
            domain="provisioning",
            address=operation.address,
            message="Provisioner does not support accounts.",
        )
    else:
        unsupported_feature = next(
            (
                feature
                for feature in sorted(provisioner_account_features(spec))
                if feature not in manifest.provisioner.supported_account_features
            ),
            None,
        )
        if unsupported_feature is not None:
            diagnostic = Diagnostic(
                code="provisioner.unsupported-account-feature",
                domain="provisioning",
                address=operation.address,
                message=f"Provisioner does not support account feature '{unsupported_feature}'.",
            )
    return diagnostic


def _operation_stateful_diagnostic(
    operation: PlanOperation,
    manifest: BackendManifest,
    *,
    node_specs: Mapping[str, object],
    content_specs: Mapping[str, object],
    exact_supported: bool,
) -> Diagnostic | None:
    """Diagnostic for one submitted operation, or ``None`` when it is admissible."""

    admission = _STATEFUL_ADMISSION_BY_RESOURCE_TYPE.get(operation.resource_type)
    if admission is None:
        return None
    capability_attribute, unsupported_code, resource_label = admission
    diagnostic: Diagnostic | None = None
    if not getattr(manifest.provisioner, capability_attribute):
        diagnostic = Diagnostic(
            code=unsupported_code,
            domain="provisioning",
            address=operation.address,
            message=f"Provisioner does not support {resource_label}.",
        )
    elif operation.resource_type == "generated-artifact":
        diagnostic = generated_artifact_payload_diagnostic(
            address=operation.address,
            spec=operation.payload.get("spec"),
            provisioner=manifest.provisioner,
            node_specs=node_specs,
            content_specs=content_specs,
        )
    if diagnostic is None and not exact_supported:
        diagnostic = Diagnostic(
            code="realization.unsupported-exact-requirement",
            domain="runtime-realization",
            address=operation.address,
            message=(
                f"Backend declares no exact realization support for the submitted {operation.resource_type} resource."
            ),
        )
    return diagnostic


def _stateful_submission_diagnostic(
    plan: ProvisioningPlan,
    manifest: BackendManifest,
) -> Diagnostic | None:
    node_specs = {
        operation.address: operation.payload.get("spec")
        for operation in plan.operations
        if operation.resource_type == "node"
    }
    content_specs = {
        operation.address: operation.payload
        for operation in plan.operations
        if operation.resource_type == "content-placement"
    }
    exact_supported = any(
        declaration.domain == RUNTIME_REALIZATION_DOMAIN
        and DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND in declaration.supported_exact_requirement_kinds
        for declaration in manifest.realization_support
    )
    for operation in plan.operations:
        diagnostic = _operation_stateful_diagnostic(
            operation,
            manifest,
            node_specs=node_specs,
            content_specs=content_specs,
            exact_supported=exact_supported,
        )
        if diagnostic is not None:
            return diagnostic
    return None


def _submitted_operation_diagnostic(
    operation: PlanOperation,
    domain: RuntimeDomain,
    snapshot: RuntimeSnapshot,
    admitted: set[str],
) -> Diagnostic | None:
    diagnostic: Diagnostic | None = None
    address = f"runtime.control-plane.{domain.value}"
    try:
        require_plan_operation_identity(domain, operation.address, operation.resource_type)
    except ValueError:
        diagnostic = Diagnostic(
            code="runtime.plan-resource-incoherent",
            domain="runtime",
            address=address,
            message="Submitted plan operation disagrees with the endpoint resource identity.",
        )

    dependencies = {*operation.ordering_dependencies, *operation.refresh_dependencies}
    if diagnostic is None and operation.action is not ChangeAction.DELETE and dependencies - admitted:
        diagnostic = Diagnostic(
            code="runtime.plan-dependency-unresolved",
            domain="runtime",
            address=address,
            message="Submitted plan contains a dependency outside its operations and admitted snapshot.",
        )

    existing = snapshot.entries.get(operation.address)
    if (
        diagnostic is None
        and existing is not None
        and (existing.domain is not domain or existing.resource_type != operation.resource_type)
    ):
        diagnostic = Diagnostic(
            code="runtime.plan-resource-incoherent",
            domain="runtime",
            address=address,
            message="Submitted plan disagrees with the admitted snapshot resource identity.",
        )
    return diagnostic
