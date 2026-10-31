"""Observability/evidence planes of SDL sections and runtime families (SEM-224).

ADR-066 and ``specs/formal/observability-evidence-plane.md`` define five named
planes for observability and evidence concerns. This module assigns exactly one
primary plane to an SDL authoring section or a runtime family by its identity,
never by a free-form string such as ``log``, ``trace``, ``telemetry``,
``observation``, or ``evidence`` (OE-11). Claim-bearing contracts get their
plane in ``raes_contracts.observability_planes``.

It deliberately holds no runtime internals, inspects no backend-native DTOs, and
infers nothing from arbitrary text.
"""

from __future__ import annotations

from collections.abc import Iterable

from raes_contracts.observability_planes import ObservabilityEvidencePlane as _ObservabilityEvidencePlane

from ._runtime_service_families import RUNTIME_SERVICE_FAMILIES, collect_qualified_runtime_family_refs

# SDL authoring sections whose carrier role decides a single primary plane.
PLANE_BY_SDL_SECTION: dict[str, _ObservabilityEvidencePlane] = {
    "evidence_requirements": _ObservabilityEvidencePlane.AUTHORED_EVIDENCE_REQUIREMENT,
}

# Scenario-native observability systems are in-world SDL runtime families
# (``specs/sdl/observability-and-evidence.md``). Names are validated against the
# canonical runtime-family registry so a rename fails closed rather than letting
# the classifier silently drift.
_SCENARIO_NATIVE_FAMILY_NAMES: tuple[str, ...] = (
    "network_sensors",
    "network_detection_engines",
    "security_monitoring_managers",
    "forwarding_agents",
    "service_listeners",
    "platform_applications",
    "datastore_services",
)

_REGISTERED_FAMILY_NAMES = frozenset(family.collection_name for family in RUNTIME_SERVICE_FAMILIES)


def _validate_scenario_native_families(names: tuple[str, ...], registered: frozenset[str]) -> frozenset[str]:
    """Fail closed if a scenario-native family name is not a registered runtime family.

    Keeps the classifier from silently drifting when a runtime family is renamed.
    """

    unregistered = frozenset(names) - registered
    if unregistered:
        raise RuntimeError(
            "SEM-224 scenario-native observability families are not registered in "
            f"RUNTIME_SERVICE_FAMILIES: {sorted(unregistered)}"
        )
    return frozenset(names)


SCENARIO_NATIVE_OBSERVABILITY_FAMILIES: frozenset[str] = _validate_scenario_native_families(
    _SCENARIO_NATIVE_FAMILY_NAMES, _REGISTERED_FAMILY_NAMES
)

# Strings the ADR calls out as ambiguous: they appear across multiple planes and
# therefore never decide ownership on their own (OE-11).
AMBIGUOUS_PLANE_TOKENS: frozenset[str] = frozenset(
    {
        "log",
        "logs",
        "trace",
        "traces",
        "telemetry",
        "observation",
        "observations",
        "evidence",
        "monitor",
        "monitoring",
        "metric",
        "metrics",
    }
)

# OE-11 made structural: the set of strings authorized to decide a plane is empty
# by construction. Plane ownership is a carrier-role decision, never a token one.
_PLANE_DECIDING_TOKENS: frozenset[str] = frozenset()


def classify_runtime_family(collection_name: str) -> _ObservabilityEvidencePlane:
    """Classify an SDL runtime family as scenario-native observability.

    Raises ``ValueError`` for a runtime family that is not a scenario-native
    observability surface.
    """

    if collection_name in SCENARIO_NATIVE_OBSERVABILITY_FAMILIES:
        return _ObservabilityEvidencePlane.SCENARIO_NATIVE_OBSERVABILITY
    raise ValueError(f"runtime family '{collection_name}' is not a scenario-native observability surface")


def classify_sdl_section_plane(section_name: str) -> _ObservabilityEvidencePlane:
    """Return the primary plane for a registered SDL authoring carrier."""

    try:
        return PLANE_BY_SDL_SECTION[section_name]
    except KeyError:
        raise ValueError(
            f"no observability/evidence plane is registered for SDL section '{section_name}'; "
            "plane ownership is decided by carrier role, not inferred"
        ) from None


def collect_scenario_native_observability_refs(scenario: object) -> set[str]:
    """Return targetable refs for scenario-native observability runtime families.

    This is a filtered view over the canonical runtime-family ref collector. It
    gives DSL-123 callers an explicit observability surface without creating a
    second resolver or registry.
    """

    return collect_qualified_runtime_family_refs(
        scenario,
        family_keys=SCENARIO_NATIVE_OBSERVABILITY_FAMILIES,
    )


def assert_single_primary_plane(
    planes: Iterable[_ObservabilityEvidencePlane],
) -> _ObservabilityEvidencePlane:
    """Enforce OE-01: a claim-bearing artifact has exactly one primary plane."""

    distinct = set(planes)
    if len(distinct) != 1:
        observed = sorted(plane.value for plane in distinct)
        raise ValueError(
            f"a claim-bearing observability/evidence artifact must have exactly one primary plane, got {observed}"
        )
    return next(iter(distinct))


def token_decides_plane(token: str) -> bool:
    """OE-11: a bare string never decides plane ownership; the carrier does.

    The set of plane-deciding tokens is empty by construction, so the answer is
    always ``False`` -- plane ownership comes from the carrier role, not a token.
    """

    return token in _PLANE_DECIDING_TOKENS


__all__ = [
    "AMBIGUOUS_PLANE_TOKENS",
    "PLANE_BY_SDL_SECTION",
    "SCENARIO_NATIVE_OBSERVABILITY_FAMILIES",
    "assert_single_primary_plane",
    "classify_runtime_family",
    "classify_sdl_section_plane",
    "collect_scenario_native_observability_refs",
    "token_decides_plane",
]
