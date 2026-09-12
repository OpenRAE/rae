"""Evaluation-operation support for the in-memory reference stub."""

from raes_contracts.planning import ChangeAction, EvaluationOp, RuntimeDomain
from raes_contracts.runtime_state import SnapshotEntry
from raes_contracts.versions import EVALUATION_STATE_SCHEMA_VERSION


def _result_payload(op: EvaluationOp, now: str) -> dict[str, object]:
    result_contract = op.payload.get("result_contract", {})
    resource_type = str(result_contract.get("resource_type", op.resource_type))
    payload: dict[str, object] = {
        "state_schema_version": result_contract.get("state_schema_version", EVALUATION_STATE_SCHEMA_VERSION),
        "resource_type": resource_type,
        "run_id": "evaluation-run",
        "status": "ready",
        "observed_at": now,
        "updated_at": now,
        "detail": f"stub result for {op.address}",
        "evidence_refs": [],
    }
    if result_contract.get("supports_score"):
        fixed_max_score = result_contract.get("fixed_max_score")
        payload["score"] = fixed_max_score if fixed_max_score is not None else 100
        payload["max_score"] = fixed_max_score if fixed_max_score is not None else 100
    if result_contract.get("supports_passed"):
        payload["passed"] = True
    return payload


def _history(result: dict[str, object], now: str) -> list[dict[str, object]]:
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
            "passed": result.get("passed"),
            "score": result.get("score"),
            "max_score": result.get("max_score"),
            "detail": result.get("detail"),
            "evidence_refs": list(result.get("evidence_refs", [])),
            "details": {},
        },
    ]


def apply_evaluation_operation(
    op: EvaluationOp,
    entries: dict[str, SnapshotEntry],
    results: dict[str, dict[str, object]],
    history: dict[str, list[dict[str, object]]],
    changed_addresses: list[str],
    now: str,
) -> None:
    """Apply one evaluation plan operation to mutable stub state."""

    if op.action == ChangeAction.UNCHANGED:
        return
    if op.action == ChangeAction.DELETE:
        entries.pop(op.address, None)
        results.pop(op.address, None)
        history.pop(op.address, None)
        changed_addresses.append(op.address)
        return
    entries[op.address] = SnapshotEntry(
        address=op.address,
        domain=RuntimeDomain.EVALUATION,
        resource_type=op.resource_type,
        payload=op.payload,
        ordering_dependencies=op.ordering_dependencies,
        refresh_dependencies=op.refresh_dependencies,
        status="admitted" if op.resource_type in {"proposition", "assertion"} else "evaluating",
    )
    if op.resource_type not in {"proposition", "assertion"}:
        result = _result_payload(op, now)
        results[op.address] = result
        history[op.address] = _history(result, now)
    if op.action != ChangeAction.UNCHANGED:
        changed_addresses.append(op.address)


__all__ = ["apply_evaluation_operation"]
