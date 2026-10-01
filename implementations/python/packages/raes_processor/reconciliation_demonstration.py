"""Runnable demonstration of planner reconciliation across scenario versions.

Plans a baseline scenario, projects its planned state into a
:class:`~raes_contracts.runtime_state.RuntimeSnapshot`, then plans a modified
version against that snapshot and reports the resulting
``create``/``update``/``delete``/``unchanged`` actions.

The projected snapshot is **synthetic assumed state**. It is not backend
readback, an instantiated SDL snapshot, a durable checkpoint, an execution
receipt, or proof that anything was realized. Nothing here applies, provisions,
or starts a scenario.

Reconciliation itself stays where it already lives: this module composes
:func:`raes_processor.reference.run_reference_processor` and consumes the
planner's own operations. It never re-derives actions by comparing payloads,
which is the only way ``unchanged`` and refresh-driven ``update`` stay honest.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum

from raes import SDLError
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, PlannedResource, PlanOperation, PlanScope, RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry

from raes_processor.models import ExecutionPlan
from raes_processor.reference import ReferenceProcessorResult, ScenarioInput, run_reference_processor

__all__ = [
    "PLANNED_STATE_PROJECTION",
    "ReconciledOperation",
    "ReconciliationDemonstration",
    "ReconciliationInputError",
    "ReconciliationStatus",
    "ScenarioVersion",
    "ScenarioVersionRejected",
    "planned_state_snapshot",
    "reconcile_scenario_versions",
]

#: Entry status, and the reported snapshot kind, for projected planned state.
#: Deliberately not ``applied`` or ``ready``: no backend ran.
PLANNED_STATE_PROJECTION = "planned-state-projection"


class ReconciliationInputError(ValueError):
    """The demonstration was handed input outside its narrow contract."""


class ScenarioVersion(str, Enum):
    """Which of the two compared versions a result or failure belongs to."""

    BASELINE = "baseline"
    CANDIDATE = "candidate"


class ScenarioVersionRejected(ReconciliationInputError):
    """One version could not be carried as far as a plan.

    Wraps the underlying :class:`raes.SDLError` and names the version that
    raised it, so a caller can report the failure against the right source
    without re-parsing either input. The message names the version only; the
    cause is carried untouched for a caller that knows how to render it safely.
    """

    def __init__(self, version: ScenarioVersion, cause: SDLError) -> None:
        super().__init__(f"{version.value} scenario version was rejected")
        self.version = version
        self.cause = cause


class ReconciliationStatus(str, Enum):
    """How far the demonstration got before a version was rejected."""

    #: Both versions planned without error diagnostics.
    RECONCILED = "reconciled"
    #: The baseline was rejected; no snapshot was projected and the candidate
    #: was never planned, so there is no action report at all.
    BASELINE_REJECTED = "baseline_rejected"
    #: The candidate planned with error diagnostics. Its operations are
    #: reported, as the plan surface already does, but the run is not a success.
    CANDIDATE_REJECTED = "candidate_rejected"


@dataclass(frozen=True)
class ReconciledOperation:
    """One planned resource's reconciliation outcome.

    Identity and action only. Resource payloads are deliberately absent: they
    carry authored credentials and content, and the reconciliation question is
    answered without disclosing them.
    """

    domain: RuntimeDomain
    address: str
    resource_type: str
    action: ChangeAction


@dataclass(frozen=True)
class ReconciliationDemonstration:
    """Outcome of planning one scenario version against another's planned state."""

    status: ReconciliationStatus
    baseline_scenario_name: str
    baseline_diagnostics: tuple[Diagnostic, ...]
    baseline_snapshot: RuntimeSnapshot | None
    candidate_scenario_name: str | None
    candidate_diagnostics: tuple[Diagnostic, ...]
    operations: tuple[ReconciledOperation, ...] | None

    @property
    def action_counts(self) -> Mapping[ChangeAction, int] | None:
        """Every action's count, including the ones that did not occur.

        ``None`` rather than four zeros when no candidate was planned, so a
        rejected baseline cannot be read as "no changes".
        """

        if self.operations is None:
            return None
        counts = dict.fromkeys(ChangeAction, 0)
        for operation in self.operations:
            counts[operation.action] += 1
        return counts


def _domain_plans(
    execution_plan: ExecutionPlan,
) -> tuple[tuple[RuntimeDomain, tuple[PlanOperation, ...], Mapping[str, PlannedResource]], ...]:
    return tuple(
        (domain, tuple(domain_plan.operations), domain_plan.resources)
        for domain, domain_plan in (
            (RuntimeDomain.PROVISIONING, execution_plan.provisioning),
            (RuntimeDomain.ORCHESTRATION, execution_plan.orchestration),
            (RuntimeDomain.EVALUATION, execution_plan.evaluation),
        )
    )


def planned_state_snapshot(execution_plan: ExecutionPlan) -> RuntimeSnapshot:
    """Project a plan's non-delete operations into assumed runtime state.

    Only sound for a plan reconciled against an empty snapshot: delete
    operations are skipped, which would silently retain removed resources if
    the plan had carried an existing baseline forward. This is a narrow
    demonstration adapter, not a general operation-replay engine, so that case
    fails closed rather than producing a plausible-looking snapshot.

    Every field ``planner.ordering._entry_matches_resource`` compares is
    carried across -- domain, resource type, payload, both dependency sets, and
    profile bindings -- so replanning the same scenario against the projection
    reconciles as ``unchanged``. Profile bindings come from the planned
    resource because only provisioning operations carry them. Payloads are
    deep-copied so inspecting or mutating the snapshot cannot reach back into
    the plan.
    """

    if execution_plan.base_snapshot.entries:
        raise ReconciliationInputError("planned-state projection requires a plan reconciled against an empty snapshot")

    entries: dict[str, SnapshotEntry] = {}
    for domain, operations, resources in _domain_plans(execution_plan):
        for operation in operations:
            if operation.action == ChangeAction.DELETE:
                continue
            resource = resources.get(operation.address)
            entries[operation.address] = SnapshotEntry(
                address=operation.address,
                domain=domain,
                resource_type=operation.resource_type,
                payload=deepcopy(operation.payload),
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
                status=PLANNED_STATE_PROJECTION,
                profile_bindings=() if resource is None else resource.profile_bindings,
            )
    return RuntimeSnapshot(entries=entries)


def _reconciled_operations(execution_plan: ExecutionPlan) -> tuple[ReconciledOperation, ...]:
    """Flatten every domain's operations, keeping the planner's own ordering.

    Each domain plan already orders applies topologically and deletes in
    reverse, and it reports ``unchanged`` operations that
    ``actionable_operations`` filters out. Both properties are what makes the
    listing a faithful picture of reconciliation, so neither is re-derived.
    """

    return tuple(
        ReconciledOperation(
            domain=domain,
            address=operation.address,
            resource_type=operation.resource_type,
            action=operation.action,
        )
        for domain, operations, _ in _domain_plans(execution_plan)
        for operation in operations
    )


def _planned_version(
    version: ScenarioVersion,
    scenario: ScenarioInput,
    backend_manifest: BackendManifest,
    *,
    parameters: Mapping[str, object] | None,
    profile: str | None,
    base_snapshot: RuntimeSnapshot | None,
    scope: PlanScope | None,
) -> ReferenceProcessorResult:
    try:
        return run_reference_processor(
            scenario,
            backend_manifest,
            parameters=parameters,
            profile=profile,
            base_snapshot=base_snapshot,
            scope=scope,
        )
    except SDLError as exc:
        raise ScenarioVersionRejected(version, exc) from exc


def _rejected_baseline(baseline: ReferenceProcessorResult) -> ReconciliationDemonstration:
    return ReconciliationDemonstration(
        status=ReconciliationStatus.BASELINE_REJECTED,
        baseline_scenario_name=baseline.scenario_name,
        baseline_diagnostics=tuple(baseline.diagnostics),
        baseline_snapshot=None,
        candidate_scenario_name=None,
        candidate_diagnostics=(),
        operations=None,
    )


def reconcile_scenario_versions(
    baseline: ScenarioInput,
    candidate: ScenarioInput,
    backend_manifest: BackendManifest,
    *,
    parameters: Mapping[str, object] | None = None,
    profile: str | None = None,
    scope: PlanScope | None = None,
) -> ReconciliationDemonstration:
    """Plan ``candidate`` against ``baseline``'s planned state and report the actions.

    Both versions are planned against the same manifest, instantiation
    parameters, profile, and plan scope. Varying those between the two rounds
    would change actions for reasons unrelated to the authored difference --
    generated values with per-run or per-instantiation regeneration depend on
    scope identity -- so the comparison deliberately holds them fixed.

    ``baseline`` and ``candidate`` are :data:`ScenarioInput` values. A
    :class:`~pathlib.Path` is read as an SDL file; a plain :class:`str` is SDL
    text, not a filename.

    An invalid baseline stops the run before any snapshot is projected: there
    is no trustworthy planned state to reconcile against. An invalid candidate
    still reports its operations, matching the plan surface, but never reports
    as a success. A version that cannot be carried to a plan at all raises
    :class:`ScenarioVersionRejected`, which names the offending version.
    """

    baseline_result = _planned_version(
        ScenarioVersion.BASELINE,
        baseline,
        backend_manifest,
        parameters=parameters,
        profile=profile,
        base_snapshot=None,
        scope=scope,
    )
    if not baseline_result.is_valid:
        return _rejected_baseline(baseline_result)

    snapshot = planned_state_snapshot(baseline_result.execution_plan)
    candidate_result = _planned_version(
        ScenarioVersion.CANDIDATE,
        candidate,
        backend_manifest,
        parameters=parameters,
        profile=profile,
        base_snapshot=snapshot,
        scope=scope,
    )
    return ReconciliationDemonstration(
        status=(
            ReconciliationStatus.RECONCILED if candidate_result.is_valid else ReconciliationStatus.CANDIDATE_REJECTED
        ),
        baseline_scenario_name=baseline_result.scenario_name,
        baseline_diagnostics=tuple(baseline_result.diagnostics),
        baseline_snapshot=snapshot,
        candidate_scenario_name=candidate_result.scenario_name,
        candidate_diagnostics=tuple(candidate_result.diagnostics),
        operations=_reconciled_operations(candidate_result.execution_plan),
    )
