"""Stable selector-family capability matching for observation runtimes."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from raes_contracts.observation_demand import ObservationBasis, ObservationLifecycleStage, ObservationSelector
from raes_contracts.realization_structure import semantic_address_contains


@dataclass(frozen=True)
class ObservationSelectorPattern:
    """Scenario-independent selector family supported by a backend adapter."""

    data_kind: str
    names: frozenset[str]
    semantic_scope_prefix: str = ""
    component_ref_prefixes: tuple[str, ...] = ()
    window_refs: frozenset[str] = frozenset()
    coverage_profiles: frozenset[str] = frozenset()
    max_items: int | None = None

    def __post_init__(self) -> None:
        _require_valid_data_kind(self.data_kind)
        _require_selector_names(self.names)
        _require_semantic_scope_prefix(self.semantic_scope_prefix)
        _require_non_blank_values(self.component_ref_prefixes, "component prefixes")
        _require_non_blank_values(self.window_refs, "window references")
        _require_non_blank_values(self.coverage_profiles, "coverage profiles")
        _require_positive_max_items(self.max_items)

    def matches(self, selector: ObservationSelector) -> bool:
        """Return whether one concrete normalized selector belongs to this family."""

        return bool(
            selector.data_kind == self.data_kind
            and set(selector.names).issubset(self.names)
            and semantic_address_contains(self.semantic_scope_prefix, selector.semantic_scope)
            and _references_match(selector.component_refs, self.component_ref_prefixes)
            and set(selector.window_refs).issubset(self.window_refs)
            and _coverage_matches(selector, self)
        )

    def specificity(self) -> tuple[int, int, int, int, int]:
        """Rank matching families without consulting scenario-specific identities."""

        return (
            self.semantic_scope_prefix.count("/"),
            max((prefix.count(".") + 1 for prefix in self.component_ref_prefixes), default=0),
            1 if self.window_refs else 0,
            1 if self.coverage_profiles else 0,
            -len(self.names),
        )


@dataclass(frozen=True)
class ObservationRuntimeCapability:
    """Concrete execution support for one stable selector family."""

    capability_id: str
    selector_pattern: ObservationSelectorPattern
    capture_kind: str
    channel_kind: str
    stages: frozenset[ObservationLifecycleStage]
    bases: frozenset[ObservationBasis] = frozenset()
    redaction_policies: frozenset[str] = frozenset()
    integrity_policies: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for field_name in ("capability_id", "capture_kind", "channel_kind"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"observation runtime capability {field_name} must be non-empty")
        if not self.stages and not self.bases:
            raise ValueError("observation runtime capability must support a lifecycle stage or reporting basis")


def resolve_observation_runtime_capability(
    capabilities: tuple[ObservationRuntimeCapability, ...],
    selector: ObservationSelector,
) -> ObservationRuntimeCapability | None:
    """Resolve a concrete selector to one unambiguous most-specific family."""

    matches = tuple(capability for capability in capabilities if capability.selector_pattern.matches(selector))
    if not matches:
        return None
    top_score = max(capability.selector_pattern.specificity() for capability in matches)
    winners = tuple(capability for capability in matches if capability.selector_pattern.specificity() == top_score)
    return winners[0] if len(winners) == 1 else None


def _references_match(references: tuple[str, ...], prefixes: tuple[str, ...]) -> bool:
    if not references:
        return True
    return bool(
        prefixes
        and all(
            any(reference == prefix or reference.startswith(f"{prefix}.") for prefix in prefixes)
            for reference in references
        )
    )


def _coverage_matches(selector: ObservationSelector, pattern: ObservationSelectorPattern) -> bool:
    if selector.coverage_profile is None:
        return True
    return bool(
        selector.coverage_profile in pattern.coverage_profiles
        and pattern.max_items is not None
        and selector.max_items is not None
        and selector.max_items <= pattern.max_items
    )


def _require_valid_data_kind(data_kind: str) -> None:
    if data_kind not in {"field", "stream", "artifact"}:
        raise ValueError("observation selector pattern data_kind is invalid")


def _require_selector_names(names: Collection[str]) -> None:
    if not names or any(not name.strip() for name in names):
        raise ValueError("observation selector pattern names must be non-empty")


def _require_non_blank_values(values: Collection[str], label: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"observation selector pattern {label} must be non-empty")


def _require_semantic_scope_prefix(prefix: str) -> None:
    if prefix and not prefix.startswith("/"):
        raise ValueError("observation selector pattern scope prefix must be a semantic address")


def _require_positive_max_items(max_items: int | None) -> None:
    if max_items is not None and max_items < 1:
        raise ValueError("observation selector pattern max_items must be positive")


__all__ = [
    "ObservationRuntimeCapability",
    "ObservationSelectorPattern",
    "resolve_observation_runtime_capability",
]
