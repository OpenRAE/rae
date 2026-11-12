"""Trusted test embedders for the mixed-backend probe family (issue #1017).

The services are the independent test producers from ``mixed_execution_fixtures``
and the reusable-control fixtures. They are test doubles, never concrete
backend realization. Each request gets fresh services and a fresh store.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mixed_control_rev1_scenarios import edge, parse, rev1_scenario
from mixed_execution_fixtures import portable_configuration, seed_store
from participant_crossing_fixtures import (
    PARTICIPANT,
    admission_request,
    behavior,
    evidence,
    identity,
    policy_capable_target,
)
from raes_conformance.conformance import (
    MixedBackendCondition,
    MixedBackendSubject,
    MixedCompositionProbeConfiguration,
    MixedControlProbeConfiguration,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionApplyResult
from raes_runtime.control_plane_security import ParticipantControlSubjectBinding
from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore
from reusable_control_runtime_fixtures import SPEC, CutOwner, control_intent
from reusable_control_runtime_fixtures import identity as control_identity
from sem233_flow_sink_fixtures import permit_resolver

_Condition = MixedBackendCondition
ENVIRONMENT = "sha256:" + "e" * 64


class _StoreView:
    """Give the test bridge the committed cut through the store the runtime shares."""

    def __init__(self, store: object) -> None:
        self._store = store

    @property
    def snapshot(self) -> object:
        return self._store.load_snapshot_state().snapshot


def _refused_start(bridge: object):
    def start_operation(request):
        bridge.request = request
        bridge.requests.append(request)
        bridge.starts += 1
        return bridge.report(request, {"kind": "acknowledgement", "disposition": "refused", "reason": "unavailable"})

    return start_operation


def apply_portable_condition(configured: object, condition: MixedBackendCondition) -> bool:
    """Realize one condition in the test services; the runner never sees these switches."""

    bridge, state = configured.roles["bridge"], configured.state
    if condition is _Condition.NOMINAL:
        bridge.refuse, bridge.execution_status, bridge.handoff_status = False, "succeeded", "committed"
        state.missing_delivery = False
        bridge.__dict__.pop("start_operation", None)
    elif condition is _Condition.WILLINGNESS_WITHDRAWN:
        bridge.refuse = True
    elif condition is _Condition.START_REFUSED:
        bridge.start_operation = _refused_start(bridge)
    elif condition is _Condition.PARTIAL_EXECUTION:
        bridge.execution_status = "partial"
    elif condition is _Condition.MISSING_DELIVERY:
        state.missing_delivery = True
    elif condition is _Condition.STALE_TRANSFER:
        bridge.handoff_status = "stale"
    else:
        return False
    return True


class PortableHarness:
    """Healthy trusted embedder; ``mutate(configured, request)`` derives negative embedders."""

    environment_digest = ENVIRONMENT

    def __init__(
        self,
        root: Path,
        *,
        mutate=None,
        conditions=None,
        dispatcher=None,
        control=True,
        durable=True,
        honor_time=True,
        affine_destination=None,
        supply_cuts=True,
        behavior_supplied=True,
    ):
        self.root = root
        self.honor_time = honor_time
        self.supply_cuts = supply_cuts
        self.behavior_supplied = behavior_supplied
        self.affine_destination = affine_destination
        self.mutate = mutate
        self.conditions = conditions
        self.dispatcher = dispatcher
        self.control_enabled = control
        self.durable = durable
        self.requests = []
        self.composed = []
        self.resolvers = {}

    def composition(self, request):
        self.requests.append(request)
        if request.time_state is not None and not self.supply_cuts:
            return None
        handoff = request.subject is MixedBackendSubject.HANDOFF
        # A restart keeps its durable crossing-policy owner; only the services are fresh.
        configured = portable_configuration(
            handoff=handoff,
            time_state=request.time_state if self.honor_time else None,
            affine_destination=self.affine_destination,
            resolver=self.resolvers.get(request.restart_of),
        )
        self.resolvers[request.collection_id] = configured.state.resolver
        if self.mutate is not None:
            self.mutate(configured, request)
        store = self._store(request, configured)
        if store is None:
            return None
        configured.state.plane = _StoreView(store)
        self.composed.append(configured)
        subject = configured.declaration.subject

        def apply(condition):
            if self.conditions is not None and condition not in self.conditions:
                return False
            return apply_portable_condition(configured, condition)

        return MixedCompositionProbeConfiguration(
            binding=configured.binding,
            target=configured.target,
            crossing_policy_resolver=configured.state.resolver,
            store=store,
            identity=identity(),
            obligation_id=subject.transition_id if handoff else subject.edge_id,
            apply_condition=apply,
            participant_address=PARTICIPANT,
            episode_id="episode-1",
            behavior=behavior() if self.behavior_supplied else None,
            admission_request=admission_request(),
            crossing_evidence=evidence(),
            distributed_execution=self.dispatcher,
        )

    def _store(self, request, configured):
        if request.restart_of is not None:
            return LocalControlPlaneStore(self.root / request.restart_of) if self.durable else None
        if request.case_id == "edge-restart-no-reissue":
            store = LocalControlPlaneStore(self.root / request.collection_id)
            return seed_store(store, configured.initial, configured.run_id)
        return InMemoryControlPlaneStore(snapshot=configured.initial)

    def control(self, request):
        self.requests.append(request)
        if not self.control_enabled:
            return None
        return control_configuration(self.conditions)


def control_configuration(conditions=None) -> MixedControlProbeConfiguration:
    """Reusable-control inputs on one policy-capable stub target."""

    from raes_processor.compiler import compile_runtime_model
    from raes_runtime.participant_control_runtime import MixedControlRuntimeBinding

    payload = rev1_scenario(form="reusable-policy")
    payload["behavior_specifications"]["controlled-red"]["mixed_control"]["permitted_transitions"]["cancel"] = edge(
        "cancellation", "autonomous", "autonomous", "red-team"
    )
    model = compile_runtime_model(parse(payload))
    owner = CutOwner()
    target = policy_capable_target("participant_ingress_admission", "participant_intervention")
    runtime = target.participant_runtime
    policy = model.behavior_specifications[SPEC].mixed_control_policy

    def refuse(request, snapshot):
        diagnostic = Diagnostic(
            code="runtime.test-provider-rejected",
            domain="participant",
            address=request.participant_address,
            message="The test backend refused the action.",
        )
        return ParticipantActionApplyResult(success=False, snapshot=snapshot, diagnostics=[diagnostic])

    def apply(condition):
        if conditions is not None and condition not in conditions:
            return False
        if condition is _Condition.DISPATCH_REFUSED:
            runtime.admit_action = refuse
            return True
        return condition is _Condition.NOMINAL

    def intent(transition, *, revision, head, order, key):
        return control_intent(policy, owner, transition, revision=revision, head=head, order=order, key=key)

    actor = replace(
        control_identity(), participant_control_subjects=(ParticipantControlSubjectBinding(PARTICIPANT, PARTICIPANT),)
    )
    return MixedControlProbeConfiguration(
        target=target,
        behavior_specifications=model.behavior_specifications,
        mixed_control=MixedControlRuntimeBinding(model=model, resolver=owner),
        store=InMemoryControlPlaneStore(),
        identity=control_identity(),
        actor_identity=actor,
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        take_transition="take",
        return_transition="return",
        control_intent=intent,
        behavior=behavior(),
        admission_request=admission_request(),
        apply_condition=apply,
        crossing_policy_resolver=permit_resolver(),
        crossing_evidence=evidence(),
    )


class Dispatcher:
    """A shaped distributed dispatcher with no worker authority."""

    worker_identity = "worker:unbound"

    def submit(self, request):
        raise AssertionError("the unsupported combination must not dispatch")

    def binding(self, request):
        raise AssertionError("the unsupported combination must not dispatch")

    def deliver_control(self, request, control):
        raise AssertionError("the unsupported combination must not dispatch")

    def close(self):
        pass
