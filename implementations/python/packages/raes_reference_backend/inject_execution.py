"""Opt-in reference OCI occurrence provider; RAE retains every dispatch/commit authority."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from time import monotonic

from raes_backend_protocols.inject_execution import InjectAdmission, ResolvedInjectOutcome
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    BackendOperationOutcomeModel,
    BackendOperationResponseModel,
    InjectOccurrenceModel,
    InjectOccurrenceOutcomeModel,
    OperationArtifactReferenceModel,
    backend_operation_control_digest,
    backend_operation_request_digest,
    canonical_backend_operation_capabilities_digest,
    inject_occurrence_effect,
    inject_occurrence_reference,
    inject_trigger_request_digest,
    require_inject_occurrence_invocation,
)
from raes_contracts.plan_projection import runtime_plan_digest

from .drivers.oci_inject import OciInjectDriver
from .drivers.oci_process import run_bounded_process
from .inject_bindings import OciInjectProgram
from .inject_evidence import evidence_requirement, read_world_effect


class ReferenceOciInjectExecutor:
    """Execute only operator-admitted image entrypoints and synchronous world probes.

    No HTTP request selects an image, argv, environment, mount or native target.
    The configured source/target pair must implement the versioned synchronous
    probe-transition contract; arbitrary asynchronous image effects are outside
    this realization. Retained native containers support observation after loss.
    """

    def __init__(self, deployment, *, programs: tuple[OciInjectProgram, ...], runner=run_bounded_process):
        if not 1 <= len(programs) <= 32 or any(not isinstance(item, OciInjectProgram) for item in programs):
            raise ValueError("OCI inject execution requires bounded admitted programs")
        self.deployment, self.native = deployment, OciInjectDriver(deployment, runner=runner)
        self._programs = deepcopy(programs)
        self._reader = None
        self._realization = None
        self._candidates = {}
        self._sequences, self._lock = {}, Lock()
        self._deadlines = {}

    def bind_manifest(self, manifest):
        reference = OperationArtifactReferenceModel(
            contract_id="backend-manifest-v2",
            artifact_id=manifest.name,
            digest=canonical_json_digest(backend_manifest_payload(manifest)),
        )
        if self._realization is not None and reference != self._realization:
            raise ValueError("OCI inject realization pins cannot change")
        self._realization = reference

    def bind_record_reader(self, reader):
        if not callable(reader) or self._reader is not None:
            raise ValueError("OCI inject execution requires one protected operation reader")
        self._reader = reader

    def _program(self, request):
        matches = [
            (program, permit)
            for program in self._programs
            for permit in program.permits
            if inject_trigger_request_digest(permit.request) == inject_trigger_request_digest(request)
        ]
        if len(matches) != 1:
            raise ValueError("OCI inject request has no unique trusted ordering permit")
        return matches[0]

    def _require_program(self, program, request):
        if (
            self._reader is None
            or self._realization is None
            or request.input_ref is not None
            or runtime_plan_digest(program.plan) != request.plan.digest
            or request.placement.kind == "schedule"
        ):
            raise ValueError("OCI inject realization or input/time contract is unsupported")
        operations = {item.address: item for item in program.plan.operations}
        inject = operations.get(request.inject)
        spec = {} if inject is None else inject.payload.get("spec", {})
        source = spec.get("source") or {}
        artifact_id = next(iter(program.source_manifest.artifacts))
        if (
            source.get("name") != artifact_id
            or source.get("version") != program.source_manifest.manifest_version
            or source.get("build") is not None
            or source.get("artifact_requirement") is not None
            or spec.get("environment")
        ):
            raise ValueError("OCI inject authored source requires its exact supported artifact association")
        events = [
            op
            for op in program.plan.operations
            if op.resource_type == "event" and request.inject in op.payload.get("inject_addresses", ())
        ]
        # No clock/assertion fallback: a richer owner must explicitly adopt those
        # contracts. Independent placement cannot evade an applicable assertion.
        if any(op.payload.get("assertion_addresses") for op in events):
            raise ValueError("OCI inject assertion evidence is unsupported")
        if request.placement.kind == "event" and request.placement.event not in {op.address for op in events}:
            raise ValueError("OCI inject event does not contain the selected inject")
        selected = {(probe.binding.binding, probe.binding.instance): probe for probe in program.probes}
        if any(
            selected.get((item.binding, item.instance)) is None
            or selected[(item.binding, item.instance)].binding != item
            for item in request.bindings
        ):
            raise ValueError("OCI inject target instance or revision is not admitted")
        return [selected[(item.binding, item.instance)] for item in request.bindings]

    def _live(self, program, request, *, deadline):
        probes = self._require_program(program, request)
        self.native.image(program.source, deadline=deadline)
        for probe in probes:
            if self.native.read_probe(probe, deadline=deadline) != probe.before:
                raise ValueError("OCI inject world predecessor does not match its admitted readback")

    def admit(self, request, context, operation_id, revision, snapshot):
        program, permit = self._program(request)
        self._live(program, request, deadline=monotonic() + 2)
        claim = InjectOccurrenceModel(
            operation_id=operation_id,
            request=request,
            admission=context,
            admission_evidence=permit.evidence,
            store_revision=str(revision),
            order=permit.order,
            scenario=program.scenario_reference,
            source=program.source_reference,
            realization=self._realization,
            evidence_requirements=(evidence_requirement(program),),
        )
        if len(self._candidates) >= 1024:
            raise ValueError("OCI inject candidate artifact capacity exhausted")
        self._candidates[operation_id] = claim
        return InjectAdmission(program.plan, claim)

    def revalidate(self, occurrence, snapshot):
        program, _ = self._program(occurrence.request)
        if (
            occurrence.source != program.source_reference
            or occurrence.realization != self._realization
            or occurrence.evidence_requirements != (evidence_requirement(program),)
        ):
            raise ValueError("OCI inject immutable realization pins do not resolve")
        self._live(program, occurrence.request, deadline=monotonic() + 2)

    def operation_capabilities(self):
        return BackendOperationCapabilitiesModel(
            backend_id="reference-emulation",
            revision=self._realization.digest,
            supported_operation_kinds=("orchestration",),
            guarantees=("effect-observation", "cessation-evidence"),
        )

    def _claim(self, request, *, dispatch=False):
        record = None if self._reader is None else self._reader(request.binding.operation_id)
        claim = self._candidates.get(request.binding.operation_id) if record is None else record.inject_occurrence
        if claim is None or (record is not None and record.invocation.request != request):
            raise ValueError("OCI inject occurrence command does not resolve")
        require_inject_occurrence_invocation(claim, request)
        if dispatch and (
            record is None
            or record.status.state.value != "running"
            or not record.invocation.consumed
            or not record.invocation.reserved
        ):
            raise ValueError("OCI inject invocation has no retained running permission")
        program, _ = self._program(claim.request)
        if (
            claim.source != program.source_reference
            or claim.realization != self._realization
            or claim.evidence_requirements != (evidence_requirement(program),)
        ):
            raise ValueError("OCI inject historical pins no longer resolve")
        return claim, program

    def _report(self, request, message):
        record = None if self._reader is None else self._reader(request.binding.operation_id)
        previous = [] if record is None else record.invocation.responses
        with self._lock:
            sequence = (
                max(
                    self._sequences.get(request.binding.operation_id, 0),
                    max((item.sequence for item in previous), default=0),
                )
                + 1
            )
            self._sequences[request.binding.operation_id] = sequence
        return BackendOperationResponseModel(
            binding=request.binding,
            request_digest=backend_operation_request_digest(request),
            sequence=sequence,
            message=message,
        )

    def check_operation(self, request):
        disposition, reason = "willing", None
        try:
            claim, program = self._claim(request)
            started = datetime.fromisoformat(request.budget.started_at.replace("Z", "+00:00"))
            elapsed_ms = max(0, (datetime.now(UTC) - started).total_seconds() * 1000)
            remaining_ms = min(request.budget.remaining_ms, request.budget.limit_ms - elapsed_ms)
            with self._lock:
                deadline = self._deadlines.setdefault(request.binding.operation_id, monotonic() + remaining_ms / 1000)
            if deadline <= monotonic():
                raise ValueError("OCI inject original execution budget is exhausted")
            self._live(program, claim.request, deadline=min(monotonic() + 2, deadline))
        except (ValueError, KeyError):
            disposition, reason = "refused", "context-refused"
        return self._report(
            request,
            {
                "kind": "admission",
                "disposition": disposition,
                "reason": reason,
                "capability_digest": canonical_backend_operation_capabilities_digest(self.operation_capabilities()),
            },
        )

    def start_operation(self, request):
        claim, program = self._claim(request, dispatch=True)
        deadline = self._deadlines.get(request.binding.operation_id)
        if deadline is None or deadline <= monotonic():
            raise ValueError("OCI inject original execution budget is exhausted")
        for probe in self._require_program(program, claim.request):
            self.native.start(request, probe, program.source, deadline=deadline)
        return self._report(request, {"kind": "acknowledgement", "disposition": "accepted"})

    def _read(self, request, *, deadline):
        claim, program = self._claim(request)
        return claim, read_world_effect(self.native, program, claim, request, deadline=deadline)

    @staticmethod
    def _outcome(readback):
        return BackendOperationOutcomeModel(
            kind="outcome",
            proposed_state=readback.state,
            effects=readback.effects,
            satisfaction={"succeeded": "satisfied", "failed": "unsatisfied", "indeterminate": "unknown"}[
                readback.state
            ],
            release_gates_satisfied=readback.state == "succeeded",
            cancellation_established=False,
            result=readback.result,
        )

    def _request_for_control(self, control):
        record = self._reader(control.binding.operation_id)
        if record is None or record.invocation is None or record.invocation.request.binding != control.binding:
            raise ValueError("OCI inject control has no exact retained invocation")
        request = record.invocation.request
        if backend_operation_request_digest(request) != control.request_digest:
            raise ValueError("OCI inject control commitment mismatch")
        return request

    def observe_operation(self, control):
        request = self._request_for_control(control)
        _, readback = self._read(request, deadline=monotonic() + control.budget.remaining_ms / 1000)
        if readback.state == "running":
            return self._report(request, {"kind": "progress", "phase": "executing"})
        return self._report(request, self._outcome(readback))

    def cancel_operation(self, control):
        return self._report(
            self._request_for_control(control),
            {
                "kind": "control",
                "control_id": control.control_id,
                "control_digest": backend_operation_control_digest(control),
                "disposition": "unsupported",
            },
        )

    def reconcile_operation(self, control):
        request = self._request_for_control(control)
        _, readback = self._read(request, deadline=monotonic() + control.budget.remaining_ms / 1000)
        return self._report(
            request,
            {
                "kind": "reconciliation",
                "control_id": control.control_id,
                "control_digest": backend_operation_control_digest(control),
                "effects": readback.effects,
            },
        )

    def validate_effects(self, request, response):
        _, readback = self._read(request, deadline=monotonic() + 2)
        if response.message.kind == "reconciliation":
            return response.message.effects == readback.effects
        return readback.state != "running" and response.message == self._outcome(readback)

    def resolve_outcome(self, occurrence, request, response):
        claim, readback = self._read(request, deadline=monotonic() + 2)
        if claim != occurrence or readback.state == "running" or response.message != self._outcome(readback):
            raise ValueError("OCI inject produced artifact or readback changed during validation")
        outcome = InjectOccurrenceOutcomeModel(
            occurrence=inject_occurrence_reference(claim),
            response=response,
            bindings=readback.bindings,
            effect=inject_occurrence_effect(readback.bindings),
        )
        return ResolvedInjectOutcome(outcome, readback.evidence)

    def resolve_result(self, request, response, predecessor):
        raise ValueError("OCI inject provider resolves artifact outcomes, not native plan snapshots")
