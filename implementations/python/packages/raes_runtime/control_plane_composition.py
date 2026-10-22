"""Composition-time validation for runtime control-plane dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from raes_contracts.manifest_authority import PARTICIPANT_RUNTIME_POLICY_FEATURES
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

from .participant_control_binding import ParticipantControlRuntimeBinding
from .participant_crossing_mediation import ParticipantCrossingPolicyResolver
from .participant_flow_sink import ParticipantFlowSinkResolver
from .registry import RuntimeTarget

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane
    from .control_plane_configuration import ControlPlaneConfiguration


def compose_operation_execution(control_plane: RuntimeControlPlane, config: ControlPlaneConfiguration) -> None:
    from secrets import token_bytes
    from uuid import uuid4

    from .registry_target_validation import validate_operation_provider

    control_plane._supervision = config.supervision
    control_plane._operation_evidence = config.operation_evidence
    control_plane._inject_execution = config.inject_execution
    control_plane._distributed_execution = config.distributed_execution
    control_plane._admitted_backend_requests = {}
    control_plane._execution_deadlines = {}
    control_plane._control_deadlines = {}
    control_plane._command_commitment_key = token_bytes(32)
    provider = getattr(control_plane._target, "operation_provider", None)
    declared = control_plane._target.manifest.supported_contract_versions
    validate_operation_provider(provider, declared)
    if config.distributed_execution is not None and getattr(control_plane._target, "operation_provider", None) is None:
        raise ValueError("distributed execution requires an installed operation provider")
    control_plane._deployment_id = str(uuid4())
    control_plane._effect_admission_stopped = False


def bind_execution_store(control_plane: RuntimeControlPlane, config: ControlPlaneConfiguration) -> None:
    from .control_plane_store_bounded import BoundedControlPlaneStore
    from .control_plane_store_compatibility import adapt_control_plane_store
    from .operation_execution_adapter import LocalExecutionAdapter
    from .runtime_resource_ownership import RuntimeResourceClaim, ledger_identity

    bounds = config.supervision
    control_plane._resource_claim = RuntimeResourceClaim(
        control_plane, control_plane._target, ledger=ledger_identity(control_plane._store)
    )
    control_plane._execution_adapter = LocalExecutionAdapter(
        effect_capacity=bounds.effect_capacity,
        control_capacity=bounds.control_capacity,
        store_capacity=bounds.store_capacity,
    )
    control_plane._store = BoundedControlPlaneStore(
        control_plane._store, control_plane._execution_adapter, bounds.commit_ms
    )
    control_plane._store_commits = adapt_control_plane_store(control_plane._store)
    generation = getattr(control_plane._store, "admit_execution_generation", None)
    control_plane._execution_generation = generation() if callable(generation) else 0
    stopped = getattr(control_plane._store, "effect_admission_stopped", None)
    control_plane._effect_admission_stopped = stopped() if callable(stopped) else False


PARTICIPANT_MODULAR_CONTROL_FEATURE = "participant_modular_control"


def require_crossing_policy_configuration(
    target: RuntimeTarget,
    resolver: ParticipantCrossingPolicyResolver | None,
) -> None:
    """Require a resolver when the target declares participant policy support."""

    capabilities = target.manifest.participant_runtime
    if capabilities is None:
        return
    enabled_policy_features = {
        declaration.feature
        for declaration in capabilities.feature_support
        if declaration.feature in PARTICIPANT_RUNTIME_POLICY_FEATURES
        and declaration.support_level != ParticipantFeatureSupportLevel.UNSUPPORTED
    }
    if enabled_policy_features and resolver is None:
        features = ", ".join(sorted(enabled_policy_features))
        raise ValueError(f"participant policy capabilities require a crossing policy resolver: {features}")


def select_final_sink_flow_control_resolver(
    resolver: ParticipantCrossingPolicyResolver | None,
    enforce_final_sink_flow_control: bool,
) -> ParticipantFlowSinkResolver | None:
    """Select the legacy SEM-233 adapter once, explicitly, at construction.

    PC-15 retains the legacy final-sink path only as an explicitly negotiated
    selection. ``enforce_final_sink_flow_control`` is that selection: the
    adapter is bound once here, so no sink discovers it by method presence.
    """

    if not enforce_final_sink_flow_control or resolver is None:
        return None
    if not callable(getattr(resolver, "resolve_flow_sink_decision", None)):
        raise ValueError(
            "participant final-sink flow-control enforcement requires the crossing policy "
            "resolver to implement resolve_flow_sink_decision; pass "
            "enforce_final_sink_flow_control=False to run the legacy API-423-only path"
        )
    return cast(ParticipantFlowSinkResolver, resolver)


def require_participant_control_configuration(
    target: RuntimeTarget,
    resolver: ParticipantCrossingPolicyResolver | None,
    participant_control: ParticipantControlRuntimeBinding | None,
) -> None:
    """Admit a modular participant-control binding only where it can be enforced.

    RUN-320 composes inside the incumbent RUN-319 crossing boundary, so the
    binding needs that boundary's resolver and a target that declares the
    API-407 ``participant_modular_control`` feature. A declaration is not an
    installed provider; it is the backend's own statement that this runtime may
    orchestrate one.
    """

    if participant_control is None:
        return
    if not isinstance(participant_control, ParticipantControlRuntimeBinding):
        raise TypeError("participant control must be an exact ParticipantControlRuntimeBinding")
    if resolver is None:
        raise ValueError("participant control orchestration requires a crossing policy resolver")
    capabilities = target.manifest.participant_runtime
    declared = () if capabilities is None else capabilities.feature_support
    if not any(
        declaration.feature == PARTICIPANT_MODULAR_CONTROL_FEATURE
        and declaration.support_level != ParticipantFeatureSupportLevel.UNSUPPORTED
        for declaration in declared
    ):
        raise ValueError(
            "participant control orchestration requires the backend to declare participant_modular_control support"
        )


def compose_participant_boundary(target: object, config: object) -> object | None:
    """Validate the participant boundary configuration and select its sink adapter.

    One construction-time step: the crossing policy resolver the target needs,
    the explicitly selected SEM-233 final-sink adapter, and a modular control
    binding only where it can be enforced.
    """

    resolver = config.crossing_policy_resolver
    require_crossing_policy_configuration(target, resolver)
    flow_sink_resolver = select_final_sink_flow_control_resolver(resolver, config.enforce_final_sink_flow_control)
    require_participant_control_configuration(target, resolver, config.participant_control)
    return flow_sink_resolver


__all__ = (
    "compose_participant_boundary",
    "require_crossing_policy_configuration",
    "select_final_sink_flow_control_resolver",
    "require_participant_control_configuration",
)
