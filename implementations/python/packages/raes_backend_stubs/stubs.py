"""Stub runtime backends for compiler/planner testing."""

from datetime import UTC, datetime

from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.participant_runtime_base import BaseParticipantRuntime
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, EvaluationPlan, OrchestrationPlan, ProvisioningPlan, RuntimeDomain
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    ObservationStrength,
    RealizationConcern,
)
from raes_contracts.realization_observation import (
    RealizationObservation,
    bind_compute_substrate_observations,
    compute_substrate_readback_addresses,
)
from raes_contracts.realization_observation_demand import compute_substrate_collection_addresses
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_runtime.registry import (
    ReferenceTimeRuntime,
    RuntimeTarget,
    RuntimeTargetComponents,
    backend_selection_observation_runtime,
)

from .evaluation_support import apply_evaluation_operation
from .manifest import (
    REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS,
    REFERENCE_PARTICIPANT_BEHAVIOR_FEATURES,
    REFERENCE_PARTICIPANT_INTERACTION_FEATURES,
    REFERENCE_PARTICIPANT_ROLES,
    create_stub_manifest,
)

__all__ = [
    "REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS",
    "REFERENCE_PARTICIPANT_BEHAVIOR_FEATURES",
    "REFERENCE_PARTICIPANT_INTERACTION_FEATURES",
    "REFERENCE_PARTICIPANT_ROLES",
    "StubEvaluator",
    "StubOrchestrator",
    "StubParticipantRuntime",
    "StubProvisioner",
    "create_stub_components",
    "create_stub_manifest",
    "create_stub_target",
]


def _applied_entries(
    plan: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
) -> tuple[dict[str, SnapshotEntry], list[str]]:
    """Fold the plan's operations into snapshot entries and changed addresses."""

    entries = dict(snapshot.entries)
    changed_addresses: list[str] = []
    for op in plan.operations:
        if op.action == ChangeAction.DELETE:
            entries.pop(op.address, None)
            changed_addresses.append(op.address)
            continue
        status = "unchanged" if op.action == ChangeAction.UNCHANGED else "applied"
        entries[op.address] = SnapshotEntry(
            address=op.address,
            domain=RuntimeDomain.PROVISIONING,
            resource_type=op.resource_type,
            payload=op.payload,
            ordering_dependencies=op.ordering_dependencies,
            refresh_dependencies=op.refresh_dependencies,
            status=status,
        )
        if op.action != ChangeAction.UNCHANGED:
            changed_addresses.append(op.address)
    return entries, changed_addresses


class StubProvisioner:
    """In-memory provisioner."""

    def __init__(self, realization_envelope: BackendRealizationEnvelopeModel | None = None) -> None:
        self._realization_envelope = realization_envelope

    def validate(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        return []

    def apply(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        if (
            self._realization_envelope is not None
            and plan.realization_constraints
            and (plan.operation_id is None or plan.realization_envelope != self._realization_envelope.identity)
        ):
            return ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=[
                    Diagnostic(
                        code="stub-backend.realization-envelope.mismatch",
                        domain="runtime",
                        address="runtime.stub.provisioning",
                        message="Provisioning plan does not match the selected stub realization envelope.",
                    )
                ],
            )
        entries, changed_addresses = _applied_entries(plan, snapshot)

        if self._realization_envelope is None:
            return ApplyResult(
                success=True,
                snapshot=snapshot.with_entries(entries),
                changed_addresses=changed_addresses,
            )
        readback_addresses = set(
            compute_substrate_readback_addresses(
                plan=plan,
                envelope=self._realization_envelope,
                previous=snapshot.realization_observations,
            )
        )
        observations = tuple(
            RealizationObservation(
                address=constraint.address,
                field_path=constraint.field_path,
                concern=RealizationConcern.COMPUTE_SUBSTRATE,
                source=ObservationStrength.DRIVER_REPORTED,
                value="x-openrae:in-process-emulation",
                envelope_digest=self._realization_envelope.digest,
                configuration_digest=self._realization_envelope.configuration.configuration_digest,
                observer_version="stub-in-process/v1",
                sequence=index,
                binding_verified=True,
            )
            for index, constraint in enumerate(plan.realization_constraints)
            if constraint.address in readback_addresses and constraint.concern == "compute-substrate"
        )
        observation_disclosures = bind_compute_substrate_observations(
            plan=plan,
            observations=observations,
            envelope=self._realization_envelope,
            previous=snapshot.realization_observations,
            selected_addresses=set(compute_substrate_collection_addresses(plan=plan)),
        )
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                realization_observations=(),
                realization_envelope=self._realization_envelope.identity,
            ),
            changed_addresses=changed_addresses,
            operational_realization_observations=observation_disclosures,
        )


class StubOrchestrator:
    """In-memory orchestrator."""

    def __init__(self) -> None:
        self._running = False
        self._startup_order: list[str] = []
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def start(
        self,
        plan: OrchestrationPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        entries = dict(snapshot.entries)
        results = dict(snapshot.orchestration_results)
        history = {
            workflow_address: list(events) for workflow_address, events in snapshot.orchestration_history.items()
        }
        changed_addresses: list[str] = []
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        for op in plan.operations:
            if op.action == ChangeAction.UNCHANGED:
                continue
            if op.action == ChangeAction.DELETE:
                entries.pop(op.address, None)
                results.pop(op.address, None)
                history.pop(op.address, None)
                changed_addresses.append(op.address)
                continue
            status = "queued" if op.resource_type in {"event", "script", "story", "workflow"} else "bound"
            entries[op.address] = SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.ORCHESTRATION,
                resource_type=op.resource_type,
                payload=op.payload,
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
                status=status,
            )
            if op.resource_type == "workflow":
                result_contract = op.payload.get("result_contract", {})
                observable_steps = result_contract.get("observable_steps", {})
                observable_steps = {
                    step_name: {
                        "lifecycle": "pending",
                        "outcome": None,
                        "attempts": 0,
                    }
                    for step_name, step_payload in observable_steps.items()
                    if isinstance(step_payload, dict)
                }
                results[op.address] = {
                    "state_schema_version": result_contract.get(
                        "state_schema_version",
                        op.payload.get("state_schema_version", "workflow-step-state/v1"),
                    ),
                    "workflow_status": "running",
                    "run_id": f"{op.address}-run",
                    "started_at": now,
                    "updated_at": now,
                    "terminal_reason": None,
                    "compensation_status": "not_required",
                    "compensation_started_at": None,
                    "compensation_updated_at": None,
                    "compensation_failures": [],
                    "steps": observable_steps,
                }
                history[op.address] = [
                    {
                        "event_type": "workflow_started",
                        "timestamp": now,
                        "step_name": op.payload.get("execution_contract", {}).get("start_step"),
                        "branch_name": None,
                        "join_step": None,
                        "outcome": None,
                        "details": {},
                    }
                ]
            if op.action != ChangeAction.UNCHANGED:
                changed_addresses.append(op.address)
        self._running = bool(plan.resources)
        self._startup_order = list(plan.startup_order)
        self._results = results
        self._history = history
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                orchestration_results=results,
                orchestration_history=history,
            ),
            changed_addresses=changed_addresses,
        )

    def status(self) -> dict[str, object]:
        return {
            "running": self._running,
            "startup_order": list(self._startup_order),
            "results": len(self._results),
        }

    def results(self) -> dict[str, dict[str, object]]:
        return dict(self._results)

    def history(self) -> dict[str, list[dict[str, object]]]:
        return {workflow_address: list(events) for workflow_address, events in self._history.items()}

    def stop(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = {
            address: entry for address, entry in snapshot.entries.items() if entry.domain != RuntimeDomain.ORCHESTRATION
        }
        removed = [
            address for address, entry in snapshot.entries.items() if entry.domain == RuntimeDomain.ORCHESTRATION
        ]
        self._running = False
        self._startup_order = []
        self._results = {}
        self._history = {}
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                orchestration_results={},
                orchestration_history={},
            ),
            changed_addresses=removed,
        )


class StubEvaluator:
    """In-memory evaluator."""

    def __init__(self) -> None:
        self._running = False
        self._startup_order: list[str] = []
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def start(
        self,
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        entries = dict(snapshot.entries)
        changed_addresses: list[str] = []
        results = dict(snapshot.evaluation_results)
        history = {address: list(events) for address, events in snapshot.evaluation_history.items()}
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        for op in plan.operations:
            apply_evaluation_operation(op, entries, results, history, changed_addresses, now)
        self._running = bool(plan.resources)
        self._startup_order = list(plan.startup_order)
        self._results = results
        self._history = history
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                evaluation_results=results,
                evaluation_history=history,
            ),
            changed_addresses=changed_addresses,
        )

    def status(self) -> dict[str, object]:
        return {
            "running": self._running,
            "startup_order": list(self._startup_order),
            "results": len(self._results),
        }

    def results(self) -> dict[str, dict[str, object]]:
        return dict(self._results)

    def history(self) -> dict[str, list[dict[str, object]]]:
        return {address: list(events) for address, events in self._history.items()}

    def stop(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = {
            address: entry for address, entry in snapshot.entries.items() if entry.domain != RuntimeDomain.EVALUATION
        }
        removed = [address for address, entry in snapshot.entries.items() if entry.domain == RuntimeDomain.EVALUATION]
        self._running = False
        self._startup_order = []
        self._results = {}
        self._history = {}
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                evaluation_results={},
                evaluation_history={},
            ),
            changed_addresses=removed,
        )


class StubParticipantRuntime(BaseParticipantRuntime):
    """In-memory participant runtime that drives RUN-311 transitions.

    Delegates the full episode lifecycle to ``BaseParticipantRuntime``; the
    stub backend injects no domain side-effects.
    """


def create_stub_components(
    *,
    manifest: BackendManifest,
    **config,
) -> RuntimeTargetComponents:
    """Factory for stub runtime components."""

    del config
    return RuntimeTargetComponents(
        provisioner=StubProvisioner(manifest.realization_envelope),
        orchestrator=StubOrchestrator(),
        evaluator=StubEvaluator(),
        participant_runtime=StubParticipantRuntime() if manifest.has_participant_runtime else None,
        time_runtime=ReferenceTimeRuntime() if manifest.has_time else None,
        observation_runtime=backend_selection_observation_runtime(manifest),
    )


def create_stub_target(**config) -> RuntimeTarget:
    """Convenience helper returning the fully configured stub target."""

    config.setdefault("with_time", True)
    config.setdefault("with_realization_envelope", True)
    manifest = create_stub_manifest(**config)
    components = create_stub_components(manifest=manifest, **config)
    return RuntimeTarget(
        name="stub",
        manifest=manifest,
        provisioner=components.provisioner,
        orchestrator=components.orchestrator,
        evaluator=components.evaluator,
        participant_runtime=components.participant_runtime,
        time_runtime=components.time_runtime,
        observation_runtime=components.observation_runtime,
    )
