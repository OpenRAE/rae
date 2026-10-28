"""Scoped state writer for Temporal progress; delivery references grant no rights."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from raes_contracts.canonical import canonical_json_digest

from .control_plane_operation_context import operation_actor_scope
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .runtime_decisions import runtime_store_digest
from .runtime_run_driver import program_decision
from .runtime_sequence_reference import RuntimeSequenceDecision, RuntimeSequenceReference

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan

    from .control_plane import RuntimeControlPlane


class RuntimeSequenceOptions(TypedDict):
    kind: Literal["run", "experiment"]
    scope_id: str
    execution_id: str
    worker_id: str
    state_queue: str
    identity: NotRequired[object | None]
    plan: NotRequired[ExecutionPlan | None]
    activity_budget_ms: NotRequired[int]
    poll_interval_ms: NotRequired[int]


@dataclass(frozen=True)
class RuntimeSequenceBinding:
    decision: RuntimeSequenceDecision
    identity: object | None
    plan: ExecutionPlan | None = None


def bind_sequence(engine: RuntimeControlPlane, options: RuntimeSequenceOptions) -> RuntimeSequenceReference:
    required = {"kind", "scope_id", "execution_id", "worker_id", "state_queue"}
    if required - options.keys() or options.keys() - RuntimeSequenceOptions.__annotations__.keys():
        raise TypeError("runtime sequence options contain missing or unexpected arguments")
    kind, scope_id, execution_id = options["kind"], options["scope_id"], options["execution_id"]
    identity, plan = options.get("identity"), options.get("plan")
    if kind == "run":
        run = engine.get_run(scope_id)
        plan = deepcopy(plan)
        if plan is None or plan.manifest != engine._target.manifest:
            raise ValueError("run delivery requires its exact planner artifact")
        commitment = program_decision(run, plan, execution_id, identity).plan_digest
    else:
        experiment = engine._experiments[scope_id]
        experiment._authorize(identity)
        commitment = canonical_json_digest(experiment.admission.model_dump(mode="json"))
    actor, scopes = operation_actor_scope(identity)
    reference = RuntimeSequenceReference(
        engine_id=runtime_store_digest(engine._store),
        kind=kind,
        execution_id=execution_id,
        scope_id=scope_id,
        request_digest=commitment,
        worker_id=options["worker_id"],
        state_queue=options["state_queue"],
        activity_budget_ms=options.get("activity_budget_ms", 60_000),
        poll_interval_ms=options.get("poll_interval_ms", 1000),
    )
    decision = RuntimeSequenceDecision(reference=reference, actor_id=actor, authorization_scope=scopes)
    engine._store.claim_runtime_decision(decision)
    engine._sequence_bindings.setdefault(reference.workflow_id, RuntimeSequenceBinding(decision, identity, plan))
    return reference


def advance_sequence(engine: RuntimeControlPlane, reference: RuntimeSequenceReference, identity: object | None) -> str:
    reference = RuntimeSequenceReference.model_validate(reference.model_dump(mode="json"))
    if (
        not isinstance(identity, ControlPlaneIdentity)
        or ControlPlaneRole.BACKEND not in identity.roles
        or identity.target_name != engine.target_name
        or identity.identity != reference.worker_id
        or reference.engine_id != runtime_store_digest(engine._store)
    ):
        raise PermissionError("runtime sequence worker is forbidden")
    binding = engine._sequence_bindings.get(reference.workflow_id)
    if binding is None or binding.decision.reference != reference:
        raise PermissionError("runtime sequence requires restored admitted artifacts")
    if reference.kind == "experiment":
        progress = engine.advance_experiment(reference.scope_id, identity=binding.identity)
    else:
        run = engine.get_run(reference.scope_id)
        progress = run.advance_plan(binding.plan, execution_id=reference.execution_id, identity=binding.identity)
    return progress.state
