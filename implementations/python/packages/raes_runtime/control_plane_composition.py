"""Composition-time validation for runtime control-plane dependencies."""

from __future__ import annotations

from typing import cast

from raes_contracts.manifest_authority import PARTICIPANT_RUNTIME_POLICY_FEATURES
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

from .participant_control_binding import ParticipantControlRuntimeBinding
from .participant_crossing_mediation import ParticipantCrossingPolicyResolver
from .participant_flow_sink import ParticipantFlowSinkResolver
from .registry import RuntimeTarget

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


__all__ = (
    "require_crossing_policy_configuration",
    "select_final_sink_flow_control_resolver",
    "require_participant_control_configuration",
)
