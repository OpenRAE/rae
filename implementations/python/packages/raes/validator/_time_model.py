"""Semantic checks for the shared RAES time model."""

from ..time_model import TimeDomainMapping, TimeReplayBehavior, TimeResetBehavior
from ._support import _topological_sort


class _TimeModelMixin:
    def _verify_time_model(self) -> None:
        self._verify_clock_refs()
        self._verify_time_domain_mappings()
        self._verify_time_progression_policies()
        self._verify_temporal_constraints()

    def _verify_clock_refs(self) -> None:
        for name, clock in self._s.clocks.items():
            if clock.time_domain_ref not in self._s.time_domains:
                self._err(
                    f"Clock '{name}' time_domain_ref '{clock.time_domain_ref}' "
                    "does not reference a declared time domain"
                )

    def _verify_time_domain_mappings(self) -> None:
        graph: dict[str, list[str]] = {name: [] for name in self._s.time_domains}
        pairs: set[tuple[str, str]] = set()
        for name, mapping in self._s.time_domain_mappings.items():
            self._verify_time_domain_mapping(name, mapping, graph, pairs)
        if graph and _topological_sort(graph) is None:
            self._err("Time-domain mapping graph contains a cycle")

    def _verify_time_domain_mapping(
        self,
        name: str,
        mapping: TimeDomainMapping,
        graph: dict[str, list[str]],
        pairs: set[tuple[str, str]],
    ) -> None:
        source = mapping.source_domain_ref
        target = mapping.target_domain_ref
        if source not in self._s.time_domains:
            self._err(f"Time-domain mapping '{name}' references undefined source domain '{source}'")
        if target not in self._s.time_domains:
            self._err(f"Time-domain mapping '{name}' references undefined target domain '{target}'")
        pair = (source, target)
        if pair in pairs:
            self._err(f"Time-domain mapping '{name}' duplicates the mapping from '{source}' to '{target}'")
        pairs.add(pair)
        if source not in graph or target not in graph:
            return
        graph[source].append(target)
        source_domain = self._s.time_domains[source]
        target_domain = self._s.time_domains[target]
        if mapping.mapping_kind.value == "identity" and (
            source_domain.tick_period_seconds != target_domain.tick_period_seconds
            or source_domain.epoch != target_domain.epoch
        ):
            self._err(f"Time-domain mapping '{name}' identity endpoints must have the same tick period and epoch")

    def _verify_time_progression_policies(self) -> None:
        owners: dict[str, str] = {}
        for name, policy in self._s.time_progression_policies.items():
            previous_owner = owners.get(policy.clock_ref)
            if previous_owner is not None:
                self._err(
                    f"Time progression policy '{name}' duplicates clock_ref "
                    f"'{policy.clock_ref}' already owned by '{previous_owner}'"
                )
            owners[policy.clock_ref] = name
            clock = self._s.clocks.get(policy.clock_ref)
            if clock is None:
                self._err(
                    f"Time progression policy '{name}' clock_ref '{policy.clock_ref}' "
                    "does not reference a declared clock"
                )
                continue
            if policy.reset_behavior != TimeResetBehavior.UNSUPPORTED and not clock.supports_reset:
                self._err(
                    f"Time progression policy '{name}' requires reset behavior but clock "
                    f"'{policy.clock_ref}' does not support reset"
                )
            if policy.replay_behavior != TimeReplayBehavior.UNSUPPORTED and not clock.supports_reset:
                self._err(
                    f"Time progression policy '{name}' requires replay behavior but clock "
                    f"'{policy.clock_ref}' cannot establish a reset segment"
                )

    def _verify_temporal_constraints(self) -> None:
        workflow_steps = self._workflow_step_refs()
        for name, constraint in self._s.temporal_constraints.items():
            if constraint.clock_ref not in self._s.clocks:
                self._err(
                    f"Temporal constraint '{name}' clock_ref '{constraint.clock_ref}' "
                    "does not reference a declared clock"
                )
            for subject_ref in constraint.subject_refs:
                if subject_ref in workflow_steps:
                    continue
                self._validate_named_ref(
                    subject_ref,
                    owner_label=f"Temporal constraint '{name}'",
                    ref_label="subject_ref",
                )
