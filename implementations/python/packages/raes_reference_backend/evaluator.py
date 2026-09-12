"""Reference evaluator: portable evaluation result/history envelopes."""

from __future__ import annotations

from datetime import UTC, datetime

from raes_contracts.planning import ChangeAction, EvaluationOp, EvaluationPlan, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_contracts.versions import EVALUATION_STATE_SCHEMA_VERSION


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ReferenceEvaluator:
    """In-process evaluator over portable runtime snapshots."""

    def __init__(self) -> None:
        self._running = False
        self._startup_order: list[str] = []
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def start(self, plan: EvaluationPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = dict(snapshot.entries)
        changed_addresses: list[str] = []
        results = dict(snapshot.evaluation_results)
        history = {address: list(events) for address, events in snapshot.evaluation_history.items()}
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
            entries[op.address] = SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.EVALUATION,
                resource_type=op.resource_type,
                payload=op.payload,
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
                status="admitted" if op.resource_type in {"proposition", "assertion"} else "evaluating",
            )
            if op.resource_type in {"proposition", "assertion"}:
                if op.action != ChangeAction.UNCHANGED:
                    changed_addresses.append(op.address)
                continue
            result_payload = self._result_payload(op, now)
            results[op.address] = result_payload
            history[op.address] = self._history_events(result_payload, now)
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
                evaluation_results=results,
                evaluation_history=history,
            ),
            changed_addresses=changed_addresses,
        )

    @staticmethod
    def _result_payload(op: EvaluationOp, now: str) -> dict[str, object]:
        result_contract = op.payload.get("result_contract", {})
        if not isinstance(result_contract, dict):
            result_contract = {}
        resource_type = str(result_contract.get("resource_type", op.resource_type))
        payload: dict[str, object] = {
            "state_schema_version": result_contract.get(
                "state_schema_version",
                EVALUATION_STATE_SCHEMA_VERSION,
            ),
            "resource_type": resource_type,
            "run_id": "evaluation-run",
            "status": "ready",
            "observed_at": now,
            "updated_at": now,
            "detail": f"reference result for {op.address}",
            "evidence_refs": [],
        }
        if result_contract.get("supports_score"):
            fixed_max_score = result_contract.get("fixed_max_score")
            payload["score"] = fixed_max_score if fixed_max_score is not None else 100
            payload["max_score"] = fixed_max_score if fixed_max_score is not None else 100
        if result_contract.get("supports_passed"):
            payload["passed"] = True
        return payload

    @staticmethod
    def _history_events(result_payload: dict[str, object], now: str) -> list[dict[str, object]]:
        return [
            {
                "event_type": "evaluation_started",
                "timestamp": now,
                "status": "running",
                "passed": None,
                "score": None,
                "max_score": None,
                "detail": None,
                "evidence_refs": [],
                "details": {},
            },
            {
                "event_type": "evaluation_ready",
                "timestamp": now,
                "status": "ready",
                "passed": result_payload.get("passed"),
                "score": result_payload.get("score"),
                "max_score": result_payload.get("max_score"),
                "detail": result_payload.get("detail"),
                "evidence_refs": list(result_payload.get("evidence_refs", [])),
                "details": {},
            },
        ]

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
            snapshot=snapshot.with_entries(entries, evaluation_results={}, evaluation_history={}),
            changed_addresses=removed,
        )
