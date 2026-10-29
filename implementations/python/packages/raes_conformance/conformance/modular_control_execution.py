"""Runner-owned public dispatch and durable measurements for modular probes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import cast

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import RuntimeSnapshotEnvelopeModel
from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
from raes_contracts.runtime_state import OperationReceipt, OperationState
from raes_runtime.control_plane import LocalControlPlaneStore, ParticipantControlEffectRealization, RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget
from raes_runtime.snapshot_contract import runtime_snapshot_contract_payload

from .modular_control_observation import observed_binding
from .modular_control_replay import ledger_digest, record_replay, replay_input
from .modular_control_types import (
    ModularControlCase,
    ModularControlOperation,
    ModularControlStep,
    ModularOwnerObservation,
)

_METHODS = {
    ModularControlOperation.ACTION: "admit_participant_action",
    ModularControlOperation.SELECTION_V2: "admit_participant_decision_surface_selection_v2",
    ModularControlOperation.CONTROL: "record_participant_control",
    ModularControlOperation.DISPATCH: "dispatch_participant_control_effects",
    ModularControlOperation.PROJECTION: "get_participant_status_view",
    ModularControlOperation.INJECT: "submit_inject",
    ModularControlOperation.PROVISION: "submit_provisioning",
    ModularControlOperation.RESOLVE: "resolve_indeterminate_operation",
    ModularControlOperation.REGISTER_PLAN: "register_planner_produced_plan",
}


@dataclass
class _Counter:
    inner: object
    prefix: str
    counts: Counter[str]
    lock: Lock

    def __getattr__(self, name: str) -> object:
        method = getattr(self.inner, name)
        if not callable(method):
            return method

        def counted(*args: object, **kwargs: object) -> object:
            # Readback/capability calls cannot become evidence of an effect.
            if name not in {
                "status",
                "results",
                "history",
                "execution_state",
                "operation_capabilities",
                "check_operation",
                "observe_operation",
                "reconcile_operation",
                "validate",
                "validate_profiles",
            }:
                with self.lock:
                    self.counts[f"{self.prefix}.{name}"] += 1
            return method(*args, **kwargs)

        return counted


@dataclass
class _Measurement:
    counts: Counter[str] = field(default_factory=Counter)
    count_lock: Lock = field(default_factory=Lock)
    evaluations: tuple[ParticipantControlEvaluationV2Model, ...] = ()
    outcomes: dict[str, str] = field(default_factory=dict)
    observations: tuple[ModularOwnerObservation, ...] = ()
    records: Mapping[str, object] = field(default_factory=dict)
    outputs: list[object] = field(default_factory=list)
    parent_states: list[OperationState] = field(default_factory=list)
    parent_operation_ids: list[str] = field(default_factory=list)
    refusals: int = 0
    reopened: bool = False
    duplicate_stable: bool = True
    history: Mapping[str, object] = field(default_factory=dict)
    audit: tuple[object, ...] = ()
    cleanup_verified: bool = False
    residual_state: tuple[str, ...] = ()
    snapshot_digest: str | None = None
    invocation_digest: str | None = None
    resolutions: list[object] = field(default_factory=list)
    integrity_slots: set[tuple[str, str]] = field(default_factory=set)
    replay_records: dict[str, tuple[str, str, int]] = field(default_factory=dict)
    exact_replays: int = 0
    reopen_epoch: int = 0
    replayed_after_reopen: bool = False
    refusal_causes: set[str] = field(default_factory=set)


def _instrument(target: RuntimeTarget, measured: _Measurement) -> RuntimeTarget:
    return cast(
        RuntimeTarget,
        replace(
            target,
            **{
                field: _Counter(getattr(target, field), field, measured.counts, measured.count_lock)
                for field in ("participant_runtime", "operation_provider", "provisioner", "orchestrator")
                if getattr(target, field) is not None
            },
        ),
    )


def _capture(plane: RuntimeControlPlane, store: LocalControlPlaneStore, measured: _Measurement) -> None:
    measured.records = store.load_records()
    measured.snapshot_digest = canonical_json_digest(
        RuntimeSnapshotEnvelopeModel.model_validate(runtime_snapshot_contract_payload(plane.get_snapshot())).model_dump(
            mode="json"
        )
    )
    measured.invocation_digest = canonical_json_digest(
        [
            record.invocation.request.model_dump(mode="json")
            for record in measured.records.values()
            if record.invocation is not None
        ]
    )
    measured.evaluations = tuple(
        ParticipantControlEvaluationV2Model.model_validate(item)
        for records in plane.snapshot.participant_control_evaluation_history.values()
        for item in records
    )
    measured.history = {
        "crossings": plane.snapshot.participant_crossing_history,
        "controls": plane.snapshot.participant_control_history,
        "behavior": plane.snapshot.participant_behavior_history,
    }
    measured.audit = plane.audit_log()


def _drive(
    plane: RuntimeControlPlane, store: LocalControlPlaneStore, step: ModularControlStep, measured: _Measurement
) -> None:
    arguments = step.arguments(plane, tuple(measured.outputs)) if callable(step.arguments) else step.arguments
    if not isinstance(arguments, Mapping):
        raise TypeError("modular probe inputs must be a keyword mapping")
    replay_key = replay_input(step.operation, arguments)
    _capture(plane, store, measured)
    before = ledger_digest(measured)
    try:
        output = getattr(plane, _METHODS[step.operation])(**dict(arguments))
    except PermissionError, ValueError:
        if not step.expect_refusal:
            raise
        measured.refusals += 1
        measured.outputs.append(None)
        return
    if step.expect_refusal:
        raise ValueError("modular probe expected an explicit refusal")
    measured.outputs.append(output)
    _capture(plane, store, measured)
    record_replay(measured, replay_key, output, before)
    _record_output(plane, step, output, measured)


def _record_output(
    plane: RuntimeControlPlane, step: ModularControlStep, output: object, measured: _Measurement
) -> None:
    if step.operation in {
        ModularControlOperation.ACTION,
        ModularControlOperation.SELECTION_V2,
        ModularControlOperation.CONTROL,
    }:
        receipt = cast(OperationReceipt, output)
        status = plane.get_operation(receipt.operation_id)
        if status is None:
            raise ValueError("modular parent has no recorded status")
        measured.parent_states.append(status.state)
        if receipt.operation_id not in measured.parent_operation_ids:
            measured.parent_operation_ids.append(receipt.operation_id)
    if step.operation is ModularControlOperation.DISPATCH:
        for item in cast(tuple[ParticipantControlEffectRealization, ...], output):
            prior = measured.outcomes.get(item.effect_id)
            if prior is not None and prior != item.disposition:
                measured.duplicate_stable = False
            measured.outcomes[item.effect_id] = item.disposition


def _run_steps(
    target: RuntimeTarget,
    case: ModularControlCase,
    directory: Path,
    measured: _Measurement,
) -> None:
    options = dict(case.options)
    if options.get("participant_control") is not None:
        options["participant_control"] = observed_binding(options["participant_control"], measured)
    if "store" in options:
        raise ValueError("modular probes own their isolated durable store")
    if options.get("enforce_final_sink_flow_control", True) is not True:
        raise ValueError("modular probes require final-sink enforcement")
    store = LocalControlPlaneStore(directory)
    initial = options.pop("initial_snapshot", None)
    if initial is not None:
        lease = store.admit_runtime(
            target_scope="target:" + target.name, run_scope=options.get("run_scope", "run:default")
        )
        try:
            store.save_snapshot(initial, expected_revision=store.load_snapshot_state().revision)
        finally:
            lease.close()
    plane = RuntimeControlPlane(target, store=store, **options)
    try:
        plane.initialize_participant_episode(
            case.participant_address, episode_id=case.episode_id, identity=case.identity
        )
        measured.counts.clear()
        for step in case.steps:
            if step.operation is ModularControlOperation.REOPEN:
                _capture(plane, store, measured)
                before = ledger_digest(measured)
                plane.close()
                store = LocalControlPlaneStore(directory)
                plane = RuntimeControlPlane(target, store=store, **options)
                _capture(plane, store, measured)
                after = ledger_digest(measured)
                measured.duplicate_stable &= before == after
                measured.reopened = True
                measured.reopen_epoch += 1
                measured.replayed_after_reopen = False
            else:
                _drive(plane, store, step, measured)
        _capture(plane, store, measured)
        if case.observe is not None:
            observed = case.observe(plane)
            if not isinstance(observed, tuple) or any(type(item) is not ModularOwnerObservation for item in observed):
                raise TypeError("modular owner observations require typed records")
            measured.observations = observed
    finally:
        plane.close()


def execute_case(
    target: RuntimeTarget,
    case: ModularControlCase,
    measured: _Measurement,
    store_root: Path | None,
) -> None:
    """Keep cleanup visible without allowing its failure to erase a primary error."""

    try:
        with TemporaryDirectory(prefix="raes-control-probe-", dir=store_root) as directory:
            _run_steps(_instrument(target, measured), case, Path(directory) / "ledger", measured)
    finally:
        if case.cleanup is not None:
            try:
                residual = case.cleanup()
                if not isinstance(residual, tuple) or any(not isinstance(item, str) for item in residual):
                    raise TypeError("cleanup requires bounded residual references")
                measured.residual_state = tuple(canonical_json_digest(item) for item in residual)
                measured.cleanup_verified = not residual
            except Exception:
                measured.residual_state = ("cleanup-unverified",)
                measured.cleanup_verified = False
