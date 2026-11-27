"""Exact input, receipt and durable-state evidence for finite replay probes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from pydantic import TypeAdapter
from raes_contracts.canonical import canonical_json_digest
from raes_runtime.control_plane import operation_actor_scope

from .modular_control_types import ModularControlOperation

if TYPE_CHECKING:
    from .modular_control_execution import _Measurement

_JSON = TypeAdapter(object)
_REPLAY_OPERATIONS = frozenset({ModularControlOperation.ACTION, ModularControlOperation.DISPATCH})


def ledger_digest(measured: _Measurement) -> str:
    records = {key: _JSON.dump_python(record, mode="json") for key, record in measured.records.items()}
    return canonical_json_digest({"records": records, "snapshot": measured.snapshot_digest})


def replay_input(operation: ModularControlOperation, arguments: Mapping[str, object]) -> str | None:
    if operation not in _REPLAY_OPERATIONS:
        return None
    if operation is ModularControlOperation.ACTION and not arguments.get("idempotency_key"):
        return None
    values = dict(arguments)
    identity = values.pop("identity", None)
    values["identity"] = [operation_actor_scope(identity), getattr(identity, "target_name", None)]
    return canonical_json_digest({"operation": operation.value, "inputs": _JSON.dump_python(values, mode="json")})


def record_replay(measured: _Measurement, key: str | None, output: object, before: str) -> None:
    if key is None:
        return
    after = ledger_digest(measured)
    receipt = canonical_json_digest(_JSON.dump_python(output, mode="json"))
    prior = measured.replay_records.get(key)
    if prior is not None:
        prior_receipt, prior_state, epoch = prior
        stable = prior_receipt == receipt and prior_state == before == after
        measured.duplicate_stable &= stable
        if stable:
            measured.exact_replays += 1
            measured.replayed_after_reopen |= epoch < measured.reopen_epoch
    measured.replay_records[key] = (receipt, after, measured.reopen_epoch)
