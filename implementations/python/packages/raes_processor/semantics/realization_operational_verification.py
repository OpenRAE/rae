"""Operational verification policy kept separate from experimental demand."""

from __future__ import annotations

from collections.abc import Mapping

from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope

from .realization_runtime_concern_profiles import RUNTIME_CONCERN_PROFILES

_OPERATING_SYSTEM_KINDS = frozenset({"os-family", "os-distribution", "os-version"})
_GUEST_CONFIGURATION_KINDS = frozenset(
    {
        "runtime-environment",
        "runtime-mounts",
        "linux-capabilities",
        "process-resource-limits",
        "published-ports",
        "service-listeners",
        *(profile.concern_kind for profile in RUNTIME_CONCERN_PROFILES),
    }
)


def operational_verification_requirement(
    concern_kind: str,
    authored_value: object,
) -> tuple[RealizationVerificationScope | None, ObservationStrength | None]:
    """Return the non-retained runtime verification floor for one concern."""

    if concern_kind in _OPERATING_SYSTEM_KINDS:
        return (
            (RealizationVerificationScope.PRESENCE, ObservationStrength.GUEST_OBSERVED)
            if authored_value
            else (None, None)
        )
    if concern_kind == "forwarding-agents":
        return _forwarding_agent_scope(authored_value), ObservationStrength.DAEMON_OBSERVED
    if concern_kind in _GUEST_CONFIGURATION_KINDS:
        return RealizationVerificationScope.CONFIGURATION, ObservationStrength.GUEST_OBSERVED
    return None, None


def _forwarding_agent_scope(value: object) -> RealizationVerificationScope:
    for agent in value if isinstance(value, list) else ():
        for field_name in ("sources", "transforms", "ship_targets", "reload_channels", "settings"):
            field_value = agent.get(field_name) if isinstance(agent, Mapping) else getattr(agent, field_name, None)
            if field_value:
                return RealizationVerificationScope.CONFIGURATION
        buffer_policy = (
            agent.get("buffer_policy") if isinstance(agent, Mapping) else getattr(agent, "buffer_policy", None)
        )
        if buffer_policy is not None:
            return RealizationVerificationScope.CONFIGURATION
    return RealizationVerificationScope.PRESENCE


__all__ = ["operational_verification_requirement"]
