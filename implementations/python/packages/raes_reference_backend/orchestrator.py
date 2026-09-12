"""Reference orchestrator: portable workflow result/history envelopes.

Mirrors the portable orchestration result/history shape the conformance
contracts require. State lives in the snapshot's first-class
``orchestration_results`` / ``orchestration_history`` carriers; this object
keeps a small private mirror only for the status/results/history probe
methods the runtime call shape requires.
"""

from __future__ import annotations

from datetime import UTC, datetime

from raes_contracts.planning import ChangeAction, OrchestrationPlan, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry

_QUEUED_RESOURCE_TYPES = frozenset({"event", "script", "story", "workflow"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ReferenceOrchestrator:
    """In-process orchestrator over portable runtime snapshots."""

    def __init__(self) -> None:
        self._running = False
        self._startup_order: list[str] = []
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def start(self, plan: OrchestrationPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = dict(snapshot.entries)
        results = dict(snapshot.orchestration_results)
        history = {address: list(events) for address, events in snapshot.orchestration_history.items()}
        changed_addresses: list[str] = []
        now = _now_iso()
        for op in plan.operations:
            if op.action == ChangeAction.UNCHANGED:
                continue
            if op.action == ChangeAction.DELETE:
                entries.pop(op.address, None)
                results.pop(op.address, None)
                history.pop(op.address, None)
                changed_addresses.append(op.address)
                continue
            status = "queued" if op.resource_type in _QUEUED_RESOURCE_TYPES else "bound"
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
                results[op.address] = self._workflow_result(op.payload, now)
                history[op.address] = [self._workflow_started_event(op.payload, now)]
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

    @staticmethod
    def _workflow_result(payload: dict[str, object], now: str) -> dict[str, object]:
        result_contract = payload.get("result_contract", {})
        if not isinstance(result_contract, dict):
            result_contract = {}
        observable_steps_raw = result_contract.get("observable_steps", {})
        observable_steps = {
            step_name: {"lifecycle": "pending", "outcome": None, "attempts": 0}
            for step_name, step_payload in (
                observable_steps_raw.items() if isinstance(observable_steps_raw, dict) else []
            )
            if isinstance(step_payload, dict)
        }
        return {
            "state_schema_version": result_contract.get(
                "state_schema_version",
                payload.get("state_schema_version", "workflow-step-state/v1"),
            ),
            "workflow_status": "running",
            "run_id": f"{payload.get('name', 'workflow')}-run",
            "started_at": now,
            "updated_at": now,
            "terminal_reason": None,
            "compensation_status": "not_required",
            "compensation_started_at": None,
            "compensation_updated_at": None,
            "compensation_failures": [],
            "steps": observable_steps,
        }

    @staticmethod
    def _workflow_started_event(payload: dict[str, object], now: str) -> dict[str, object]:
        execution_contract = payload.get("execution_contract", {})
        start_step = execution_contract.get("start_step") if isinstance(execution_contract, dict) else None
        return {
            "event_type": "workflow_started",
            "timestamp": now,
            "step_name": start_step,
            "branch_name": None,
            "join_step": None,
            "outcome": None,
            "details": {},
        }

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
            snapshot=snapshot.with_entries(entries, orchestration_results={}, orchestration_history={}),
            changed_addresses=removed,
        )
