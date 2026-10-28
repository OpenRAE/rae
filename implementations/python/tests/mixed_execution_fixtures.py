"""Independent installed producers for the portable mixed execution witnesses."""

from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

from participant_crossing_fixtures import PARTICIPANT, admission_request, identity
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    MixedBackendExecutionBindingModel,
    MixedBackendStageReportModel,
    backend_operation_request_digest,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS, MIXED_BACKEND_CONTRACT_IDS
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.control_plane_store_snapshots import _snapshot_payload
from raes_runtime.mixed_backend_installation import MixedBackendInstallation, MixedBackendService
from raes_runtime.time_coordinator import ReferenceTimeRuntime
from sem233_flow_sink_fixtures import permit_resolver
from test_issue_1016_mixed_runtime_coordination import (
    _admitted_binding,
    _runtime_mixed_profile,
    _runtime_staged_profile,
)
from test_issue_1362_provider_execution import Provider
from test_issue_1371_mixed_backend_contracts import _fixture, _time_state


def report(request, sequence, stage):
    return MixedBackendStageReportModel(
        binding=request.binding,
        request_digest=backend_operation_request_digest(request),
        sequence=sequence,
        stage=stage,
    )


class Bridge(Provider):
    def __init__(self, declaration, state, runtimes, calls):
        super().__init__()
        self.declaration, self.state, self.runtimes, self.calls = declaration, state, runtimes, calls
        self.execution_status = "succeeded"
        self.handoff_status = "committed"
        self.native_targets = []

    def execution_binding(self):
        return self.declaration

    def operation_capabilities(self):
        subject = self.declaration.subject
        pin = subject.bridge if subject.kind == "edge" else subject.transfer
        return BackendOperationCapabilitiesModel(
            backend_id=pin.service_ref,
            revision=pin.digest,
            supported_operation_kinds=(subject.operation_kind,),
            guarantees=("cancellation", "cessation-evidence", "effect-observation"),
        )

    def start_operation(self, request):
        self.request = request
        self.starts += 1
        self.started.set()
        assert self.release.wait(3)
        self.calls.append("bridge")
        retained = self.state.plane._store.load_records()[request.binding.operation_id]
        assert retained.invocation.consumed
        assert retained.invocation.request == request
        assert retained.invocation.mixed_reports[0].stage.comparison == "ordered"
        predecessor = self.state.plane.snapshot
        if self.declaration.subject.kind == "edge":
            # The bridge resolves the protected native command by the original
            # request commitment. Translation changes the backend representation,
            # while the native participant boundary keeps its compiled subject.
            native_target = {self.declaration.subject.source_action_address: "native:contain-host"}[
                self.state.native_command.action_contract_address
            ]
            self.result = (
                ApplyResult(False, predecessor)
                if self.execution_status == "failed"
                else self.execute_native(native_target, self.state.native_command, predecessor)
            )
        else:
            self.result = ApplyResult(True, predecessor)
        return self.report(request, {"kind": "acknowledgement", "disposition": "accepted"})

    def execute_native(self, target, command, snapshot):
        assert target == "native:contain-host"
        self.native_targets.append(target)
        return self.runtimes["emu"].admit_action(command, snapshot)

    def stage_reports(self, control):
        self.calls.append("execution-readback")
        subject = self.declaration.subject
        if subject.kind == "edge":
            stage = dict(
                stage="execution",
                producer=subject.bridge,
                source_action_address=subject.source_action_address,
                destination_action_address=subject.destination_action_address,
                status=self.execution_status,
                evidence_refs=("evidence:execution",),
                mapping_loss_refs=(subject.mapping_loss.limitation_ref,),
                cessation_evidence_refs=("evidence:cessation",) if self.execution_status == "failed" else (),
            )
        else:
            cut = self.state.plane.snapshot.mixed_composition_states[self.state.run_id]
            stage = dict(
                stage="handoff",
                producer=subject.transfer,
                status=self.handoff_status,
                predecessor_history_head=cut["history_head"],
                phase_revision=cut["phase_revision"],
                order_ref="order:portable",
                evidence_refs=subject.required_evidence_refs,
            )
        return (report(self.request, 2, stage),)

    def observe_operation(self, control):
        digest = canonical_json_digest(_snapshot_payload(self.result.snapshot))
        unknown = self.execution_status in {"partial", "unknown"} or self.state.missing_delivery
        failed = self.handoff_status == "stale" or self.execution_status == "failed"
        reference = dict(contract_id="runtime-snapshot-v1", artifact_id="native-result", digest=digest)
        return self.report(
            self.request,
            dict(
                kind="outcome",
                proposed_state="indeterminate" if unknown else "failed" if failed else "succeeded",
                satisfaction="unknown" if unknown else "unsatisfied" if failed else "satisfied",
                release_gates_satisfied=not unknown and not failed,
                cancellation_established=False,
                result=None if self.execution_status == "partial" else reference,
                effects=dict(
                    effect="partial" if self.execution_status == "partial" else "absent",
                    cessation_established=self.execution_status != "partial",
                    residual_scope=(self.declaration.subject.destination_action_address,)
                    if self.execution_status == "partial"
                    else (),
                    residual_state=reference if self.execution_status == "partial" else None,
                    evidence_refs=(dict(contract_id="runtime-snapshot-v1", artifact_id="effects", digest=digest),),
                ),
            ),
        )


class Coordinator:
    def __init__(self, declaration, calls, model):
        self.declaration, self.calls, self.model = declaration, calls, model
        self.fail = False

    def grant(self, request, time_state):
        self.calls.append("coordinate")
        if self.fail:
            raise RuntimeError("private coordinator failure")
        time = self.declaration.subject.time
        mapping = self.model.mappings[time.mapping_ref]
        source = time_state.clocks[time.source_clock_address].coordinate
        destination = time_state.clocks[time.destination_clock_address].coordinate
        mapped_tick = Fraction(source.tick * mapping.scale.numerator, mapping.scale.denominator) + mapping.offset_ticks
        ordered = source.segment == destination.segment and (mapped_tick, source.microstep) <= (
            destination.tick,
            destination.microstep,
        )
        return report(
            request,
            1,
            dict(
                stage="time-grant",
                producer=time.coordinator,
                mapping_ref=time.mapping_ref,
                ordering_basis=time.ordering_basis,
                order_ref="order:portable",
                comparison="ordered" if ordered else "incomparable",
                source_coordinate=time_state.clocks[time.source_clock_address].coordinate,
                destination_coordinate=time_state.clocks[time.destination_clock_address].coordinate,
                mapping_evidence_refs=("evidence:mapping",),
                timing_evidence_refs=self.declaration.subject.required_evidence_refs,
            ),
        )


class Reader:
    def __init__(self, declaration, kind, state, calls):
        self.declaration, self.kind, self.state, self.calls = declaration, kind, state, calls
        self.foreign = False

    def read_stage(self, control):
        self.calls.append(self.kind)
        request = self.state.bridge.request
        subject = self.declaration.subject
        if self.kind == "delivery":
            if self.state.missing_delivery:
                raise RuntimeError("destination receipt unavailable")
            stage = dict(
                stage=self.kind,
                producer=subject.delivery_reader,
                destination_component_id=subject.owner_component_id,
                receipt_ref="receipt:destination",
                evidence_refs=("evidence:delivery",),
            )
            sequence = 3
        elif self.kind == "observation":
            stage = dict(
                stage=self.kind,
                producer=subject.observation_reader,
                participant_address=subject.participant_address,
                audience_scope_ref=subject.audience_scope_ref,
                observation_ref="observation:participant",
                evidence_refs=("evidence:observation",),
            )
            sequence = 4
        else:
            retained = self.state.bridge.handoff_status == "stale"
            stage = dict(
                stage="owner-readback",
                producer=subject.owner_reader,
                owner_component_id=subject.source_component_id if retained else subject.destination_component_id,
                owner_ref=subject.source_owner_ref if retained else subject.destination_owner_ref,
                phase_revision=0 if retained else 1,
                evidence_refs=("evidence:owner",),
            )
            sequence = 3
        if self.foreign:
            stage["producer"] = subject.bridge
        return report(request, sequence, stage)


class Evidence:
    def __init__(self, state):
        self.state = state

    def validate_effects(self, request, response):
        return response.binding == request.binding and self.state.bridge.starts == 1

    def resolve_result(self, request, response, predecessor):
        return self.state.bridge.result


def portable_plane(
    *,
    handoff=False,
    store=None,
    supervision=None,
    affine_destination=None,
    resolver=None,
    required_operation_guarantees=(),
):
    binding, run_id, runtimes = _admitted_binding(_runtime_staged_profile if handoff else _runtime_mixed_profile)
    payload = _fixture("mixed-backend-execution-binding-v1", "valid", "mixed-handoff" if handoff else "mixed-edge")
    payload["profile_digest"] = binding.profile.profile_digest
    payload["profile_id"] = binding.profile.profile_id
    model_ref, model = next(iter(binding.context.time_models.items()))
    if affine_destination is not None:
        fields = model.model_dump(mode="python")
        fields["mappings"]["time.mappings.sim-to-emu"]["scale"] = {"numerator": 2, "denominator": 1}
        fields["mappings"]["time.mappings.sim-to-emu"]["mapping_kind"] = "affine_rational"
        model = type(model).model_validate(fields)
        binding = replace(binding, context=replace(binding.context, time_models={model_ref: model}))
    declaration = MixedBackendExecutionBindingModel.model_validate(payload)
    calls = []
    state = SimpleNamespace(run_id=run_id, missing_delivery=False, native_command=admission_request())
    bridge = Bridge(declaration, state, runtimes, calls)
    state.bridge = bridge
    coordinator = Coordinator(declaration, calls, model)
    subject = declaration.subject
    roles = {"bridge": bridge, "coordinator": coordinator}
    pins = {"bridge": subject.transfer if handoff else subject.bridge, "coordinator": subject.time.coordinator}
    for kind, pin in (
        (("owner-readback", subject.owner_reader),)
        if handoff
        else (("delivery", subject.delivery_reader), ("observation", subject.observation_reader))
    ):
        roles[kind] = Reader(declaration, kind, state, calls)
        pins[kind] = pin
    time_runtime = ReferenceTimeRuntime()
    initial = time_runtime.initialize(model, RuntimeSnapshot()).snapshot
    if affine_destination is not None:
        initial = initial.with_entries(
            dict(initial.entries),
            time_model_state=_time_state((0, 2, 0), (0, affine_destination, 1), declaration=model),
        )
    installed = MixedBackendInstallation(
        binding=declaration,
        services={
            pin.service_ref: MixedBackendService(
                pin, roles[kind], (*BACKEND_OPERATION_CONTRACT_IDS, *MIXED_BACKEND_CONTRACT_IDS)
            )
            for kind, pin in pins.items()
        },
        time_runtime=time_runtime,
        evidence=Evidence(state),
    )
    binding = replace(binding, backend_installations={declaration.binding_id: installed}, handoff_bindings={})
    if store is None:
        store = InMemoryControlPlaneStore(snapshot=initial)
    else:
        owner = store.admit_runtime(target_scope="target:stub", run_scope=f"run:{run_id}")
        try:
            current = store.load_snapshot_state()
            if current.snapshot.time_model_state is None:
                store.save_snapshot(initial, expected_revision=current.revision)
        finally:
            owner.close()
    state.resolver = resolver or permit_resolver()
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=state.resolver,
        run_scope=f"run:{run_id}",
        store=store,
        required_operation_guarantees=required_operation_guarantees,
        **({"supervision": supervision} if supervision else {}),
    )
    state.plane = plane
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    if not handoff and not plane.snapshot.participant_episode_history.get(PARTICIPANT):
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
    return plane, state, roles, calls, runtimes
