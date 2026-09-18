"""Composition-time validation for runtime control-plane dependencies."""

from __future__ import annotations

from raes_contracts.manifest_authority import PARTICIPANT_RUNTIME_POLICY_FEATURES
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

from .participant_crossing_mediation import ParticipantCrossingPolicyResolver
from .registry import RuntimeTarget


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


def require_final_sink_flow_control_configuration(
    resolver: ParticipantCrossingPolicyResolver | None,
    enforce_final_sink_flow_control: bool,
) -> None:
    """Reject a policy resolver that cannot resolve the SEM-233 final-sink permit."""

    if not enforce_final_sink_flow_control or resolver is None:
        return
    if not callable(getattr(resolver, "resolve_flow_sink_decision", None)):
        raise ValueError(
            "participant final-sink flow-control enforcement requires the crossing policy "
            "resolver to implement resolve_flow_sink_decision; pass "
            "enforce_final_sink_flow_control=False to run the legacy API-423-only path"
        )


__all__ = (
    "require_crossing_policy_configuration",
    "require_final_sink_flow_control_configuration",
)
