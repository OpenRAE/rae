"""Focused optional-component validation for runtime target composition."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.operation_supervision import BackendOperationProvider, require_operation_provider
from raes_backend_protocols.protocols import Evaluator, Orchestrator, ParticipantRuntime, Provisioner, TimeRuntime
from raes_backend_protocols.recovery_observation import RecoveryObservationRequest, RecoveryObserver
from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS


def validate_inventory_contract(
    manifest: BackendManifest, provisioner: Provisioner, require_invokable_method: Callable[..., None]
) -> None:
    if RUNTIME_DESCENDANTS_CONTRACT not in manifest.supported_contract_versions:
        return
    if "backend-materialization-attestation-v1" not in manifest.supported_contract_versions:
        raise ValueError("runtime descendants require materialization attestation support")
    require_invokable_method(
        provisioner, label="provisioner", method_name="refresh_inventory", invocation_args=(object(), object())
    )


def validate_operation_provider(provider: BackendOperationProvider | None, declared_contracts: Iterable[str]) -> None:
    declared = tuple(declared_contracts)
    if provider is not None:
        require_operation_provider(provider, declared)
    elif set(BACKEND_OPERATION_CONTRACT_IDS) & set(declared):
        raise ValueError("declared backend operation protocol requires an installed provider")


def validate_optional_component_presence(
    manifest: BackendManifest,
    *,
    orchestrator: Orchestrator | None,
    evaluator: Evaluator | None,
    participant_runtime: ParticipantRuntime | None,
    time_runtime: TimeRuntime | None,
    recovery_observer: RecoveryObserver | None,
) -> None:
    """Require exact agreement between optional components and their manifest declarations."""

    if manifest.has_orchestrator != (orchestrator is not None):
        raise ValueError("registry.target-shape-mismatch: orchestrator presence does not match the manifest.")
    if manifest.has_evaluator != (evaluator is not None):
        raise ValueError("registry.target-shape-mismatch: evaluator presence does not match the manifest.")
    if manifest.has_participant_runtime != (participant_runtime is not None):
        raise ValueError("registry.target-shape-mismatch: participant_runtime presence does not match the manifest.")
    if manifest.has_time != (time_runtime is not None):
        raise ValueError("registry.target-shape-mismatch: time_runtime presence does not match the manifest.")
    if (manifest.recovery_observation is not None) != (recovery_observer is not None):
        raise ValueError("registry.target-shape-mismatch: recovery_observer presence does not match the manifest.")
    if manifest.time and manifest.time.supports_coordinated_participant_reset and participant_runtime is None:
        raise ValueError(
            "registry.target-shape-mismatch: coordinated participant reset requires a participant_runtime."
        )


def validate_recovery_observer_contract(
    manifest: BackendManifest,
    recovery_observer: RecoveryObserver | None,
    *,
    require_invokable_method: Callable[..., None],
) -> None:
    """Validate the declared recovery observer against its single runtime call shape."""

    if recovery_observer is None:
        return
    assert manifest.recovery_observation is not None
    require_invokable_method(
        recovery_observer,
        label="recovery_observer",
        method_name="observe_effect",
        invocation_args=(
            RecoveryObservationRequest(
                operation_id="registry-probe",
                operation_kind=next(iter(manifest.recovery_observation.supported_operation_kinds)),
                target_scope="target:registry-probe",
                run_scope="run:registry-probe",
                request_commitment=f"sha256:{'0' * 64}",
                baseline_snapshot=RuntimeSnapshot(),
            ),
        ),
    )


__all__ = ("validate_optional_component_presence", "validate_recovery_observer_contract")
