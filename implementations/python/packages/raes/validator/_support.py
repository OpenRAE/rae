"""Shared module-level helpers for the SemanticValidator package."""

from collections import defaultdict
from dataclasses import dataclass, field

from ..orchestration import WorkflowStep

# Common ref-path prefix used by qualified runtime/service refs (e.g.
# ``nodes.vm.services.http``, ``nodes.vm.runtime.applications.webapp``).
_NODES_PREFIX = "nodes."


@dataclass
class _WorkflowBuildState:
    """Per-workflow graph-build accumulators threaded through edge collection."""

    graph: dict[str, list[str]]
    predicate_step_refs: dict[str, list[str]] = field(default_factory=dict)
    join_targets: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


@dataclass
class _CompensationState:
    """Cross-workflow call- and compensation-graph accumulators."""

    call_graph: dict[str, set[str]]
    compensation_graph: dict[str, set[str]]
    compensation_targets: set[str] = field(default_factory=set)
    workflows_with_compensation: set[str] = field(default_factory=set)


@dataclass
class _AvailableStateContext:
    """State threaded through the predicate available-step-state recursion."""

    workflow_steps: dict[str, WorkflowStep]
    graph: dict[str, list[str]]
    predecessors: dict[str, set[str]]
    start: str
    join_targets: dict[str, list[str]]
    available_memo: dict[str, set[str]] = field(default_factory=dict)
    branch_memo: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    visiting: set[str] = field(default_factory=set)
