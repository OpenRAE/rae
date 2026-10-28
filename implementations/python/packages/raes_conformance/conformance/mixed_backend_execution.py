"""Runner-owned execution and fact collection for mixed-backend probes.

This half builds the real control plane from fresh harness configuration. It
wraps every installed role so that each call is recorded, rebuilds the
installation and binding so that their own validators run again, drives the
governed operations itself and reads back what the runtime retained. No
harness-supplied value reaches a fact collected here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from functools import wraps
from threading import Lock

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    MixedBackendExecutionBindingModel,
    MixedBackendServiceModel,
    MixedBackendStageReportModel,
    mixed_backend_binding_reference,
)
from raes_runtime.control_plane import RuntimeControlPlane

from raes_conformance.conformance.diagnostics import sanitized_failure_message
from raes_conformance.conformance.mixed_backend_types import (
    MixedComponentCoordinate,
    MixedCompositionProbeConfiguration,
    MixedEvidenceRecord,
    MixedServiceCoordinate,
)
from raes_conformance.conformance.participant_opacity_execution import _qualified_name_of, _raes_version
from raes_conformance.conformance.participant_policy_execution import _CallCounter

_TOOL_REVISION = "mixed-backend-executed/rev1"
EFFECT_METHODS = ("grant", "start_operation", "stage_reports", "read_stage")


class CallLog:
    """Thread-safe record of installed-role calls in call order."""

    def __init__(self) -> None:
        self._entries: list[str] = []
        self._lock = Lock()

    def record(self, entry: str) -> None:
        with self._lock:
            self._entries.append(entry)

    def entries(self, start: int = 0) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._entries[start:])

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


class _RecordedRole:
    """Record each call to one installed role.

    ``functools.wraps`` keeps the wrapped signature, so the installation
    validator binds call shapes against the role, not against this wrapper.
    """

    def __init__(self, inner: object, label: str, log: CallLog, after: Mapping[str, Callable[[], None]]) -> None:
        self._inner = inner
        self._label = label
        self._log = log
        self._after = after

    def __getattr__(self, name: str) -> object:
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        @wraps(attribute)
        def recorded(*args: object, **kwargs: object) -> object:
            self._log.record(f"{self._label}.{name}")
            result = attribute(*args, **kwargs)
            hook = self._after.get(name)
            if hook is not None:
                hook()
            return result

        return recorded


def role_pins(declaration: MixedBackendExecutionBindingModel) -> tuple[tuple[str, MixedBackendServiceModel], ...]:
    """Return each pinned role of one obligation in a fixed order."""

    subject = declaration.subject
    pins: list[tuple[str, MixedBackendServiceModel]] = [("coordinator", subject.time.coordinator)]
    if subject.kind == "edge":
        pins += [("bridge", subject.bridge), ("delivery-reader", subject.delivery_reader)]
        if subject.observation_reader is not None:
            pins.append(("observation-reader", subject.observation_reader))
    else:
        pins += [("transfer", subject.transfer), ("owner-reader", subject.owner_reader)]
    return tuple(pins)


def obligation_ref(declaration: MixedBackendExecutionBindingModel) -> str:
    subject = declaration.subject
    return subject.edge_id if subject.kind == "edge" else subject.transition_id


def probed_installation(binding: object, subject: str, obligation_id: str) -> object | None:
    """Return the one portable installation pinned to the probed obligation."""

    matches = [
        item
        for item in getattr(binding, "backend_installations", {}).values()
        if isinstance(item.binding, MixedBackendExecutionBindingModel)
        and item.binding.subject.kind == subject
        and obligation_ref(item.binding) == obligation_id
    ]
    return matches[0] if len(matches) == 1 else None


@dataclass
class Instrumented:
    """The rebuilt binding and the counters that observe it."""

    binding: object
    log: CallLog
    component_counters: dict[str, _CallCounter] = field(default_factory=dict)

    def component_calls(self, method: str) -> int:
        return sum(counter.called_methods.count(method) for counter in self.component_counters.values())


def instrument(
    binding: object,
    probed_id: str,
    *,
    log: CallLog | None = None,
    after_grant: Callable[[], None] | None = None,
    installations: Mapping[str, object] | None = None,
) -> Instrumented:
    """Wrap every installed role and component runtime, then rebuild the binding.

    ``dataclasses.replace`` runs each installation and binding validator again.
    ``installations`` replaces the installed set before wrapping, for the
    binding-variant cases.
    """

    log = log or CallLog()
    source = binding.backend_installations if installations is None else installations
    rebuilt = {}
    for key, installation in source.items():
        prefix = "" if obligation_ref(installation.binding) == probed_id else f"{obligation_ref(installation.binding)}:"
        labels = {pin.service_ref: f"{prefix}{role}" for role, pin in role_pins(installation.binding)}
        services = {}
        for ref, service in installation.services.items():
            hooks = {"grant": after_grant} if after_grant is not None and labels[ref] == "coordinator" else {}
            services[ref] = replace(
                service, implementation=_RecordedRole(service.implementation, labels[ref], log, hooks)
            )
        rebuilt[key] = replace(installation, services=services)
    counters: dict[str, _CallCounter] = {}
    components = {}
    for component_id, component in binding.components.items():
        runtime = component.target.participant_runtime
        if runtime is not None:
            counters[component_id] = _CallCounter(inner=runtime)
            component = replace(component, target=replace(component.target, participant_runtime=counters[component_id]))
        components[component_id] = component
    return Instrumented(replace(binding, backend_installations=rebuilt, components=components), log, counters)


def open_plane(configuration: MixedCompositionProbeConfiguration, binding: object, **extra: object) -> object:
    """Open the shared runtime over the selected store; the runner closes it."""

    options: dict[str, object] = {
        "mixed_runtime": binding,
        "crossing_policy_resolver": configuration.crossing_policy_resolver,
        "run_scope": f"run:{binding.entry.run_id}",
        "store": configuration.store,
        **extra,
    }
    if configuration.supervision is not None:
        options["supervision"] = configuration.supervision
    return RuntimeControlPlane(configuration.target, **options)


def close_plane(plane: object | None, failures: list[str]) -> bool:
    """Close a probe runtime; an unresolved close stays visible as unverified cleanup."""

    if plane is None:
        return True
    try:
        plane.close()
    except Exception as exc:
        failures.append(f"cleanup: {sanitized_failure_message(exc)}")
        return False
    return True


@dataclass(frozen=True)
class OperationRead:
    """What the runtime retained for one governed operation."""

    operation_id: str | None = None
    accepted: bool | None = None
    state: str | None = None
    diagnostic_codes: tuple[str, ...] = ()
    reports: tuple[MixedBackendStageReportModel, ...] = ()
    responses: tuple[str, ...] = ()
    reserved: bool | None = None
    post_time: bool = False
    residual: bool = False
    invocation_id: str | None = None
    request_command: str | None = None
    request_backend: str | None = None
    refusal: str | None = None
    refusal_type: type[BaseException] | None = None

    def stages(self) -> tuple[str, ...]:
        return tuple(report.stage.stage for report in self.reports)

    def stage(self, kind: str) -> object | None:
        return next((report.stage for report in self.reports if report.stage.stage == kind), None)


def submit(call: Callable[[], object], plane: object, store: object) -> OperationRead:
    """Run one governed call and read back its retained operation, or its refusal."""

    try:
        receipt = call()
    except Exception as exc:
        return OperationRead(refusal=sanitized_failure_message(exc), refusal_type=type(exc))
    return read_operation(plane, store, receipt)


def read_operation(plane: object, store: object, receipt: object) -> OperationRead:
    operation_id = getattr(receipt, "operation_id", None)
    accepted = bool(getattr(receipt, "accepted", False))
    record = store.load_records().get(operation_id) if isinstance(operation_id, str) else None
    if record is None:
        codes = tuple(item.code for item in getattr(receipt, "diagnostics", ()))
        return OperationRead(operation_id=operation_id, accepted=accepted, diagnostic_codes=codes)
    status = plane.get_operation(operation_id)
    ledger = record.invocation
    responses = () if ledger is None else tuple(_response_label(item.message) for item in ledger.responses)
    outcome = (
        None
        if ledger is None
        else next((item.message for item in reversed(ledger.responses) if item.message.kind == "outcome"), None)
    )
    return OperationRead(
        operation_id=operation_id,
        accepted=accepted,
        state=status.state.value,
        diagnostic_codes=tuple(item.code for item in status.diagnostics),
        reports=() if ledger is None else tuple(ledger.mixed_reports),
        responses=responses,
        reserved=None if ledger is None else ledger.reserved,
        post_time=ledger is not None and ledger.mixed_post_time_state is not None,
        residual=outcome is not None and outcome.effects.residual_state is not None,
        invocation_id=None if ledger is None else ledger.request.binding.invocation_id,
        request_command=None if ledger is None else ledger.request.command.digest,
        request_backend=None if ledger is None else ledger.request.binding.backend_id,
    )


def _response_label(message: object) -> str:
    detail = getattr(message, "disposition", None) or getattr(message, "proposed_state", None)
    return message.kind if detail is None else f"{message.kind}:{getattr(detail, 'value', detail)}"


def composition_history(plane: object, run_id: str) -> tuple[Mapping[str, object], ...]:
    return tuple(plane.snapshot.mixed_composition_history.get(run_id, ()))


def composition_cut(plane: object, run_id: str) -> Mapping[str, object]:
    return dict(plane.snapshot.mixed_composition_states.get(run_id, {}))


def evidence_records(read: OperationRead) -> tuple[MixedEvidenceRecord, ...]:
    """Attribute each retained stage report to the producer the runtime accepted."""

    records = []
    for report in read.reports:
        stage = report.stage
        refs = (
            *getattr(stage, "evidence_refs", ()),
            *getattr(stage, "mapping_evidence_refs", ()),
            *getattr(stage, "timing_evidence_refs", ()),
        )
        records.append(
            MixedEvidenceRecord(
                position=report.sequence,
                kind=stage.stage,
                producer_ref=stage.producer.service_ref,
                digest=canonical_json_digest(report.model_dump(mode="json")),
                status=getattr(stage, "status", None) or getattr(stage, "comparison", None),
                evidence_refs=tuple(dict.fromkeys(refs)),
            )
        )
    return tuple(records)


def component_coordinates(binding: object) -> tuple[MixedComponentCoordinate, ...]:
    coordinates = []
    for component_id in sorted(binding.components):
        component = binding.components[component_id]
        envelope = component.envelope
        coordinates.append(
            MixedComponentCoordinate(
                component_id=component_id,
                target_name=component.target.name,
                backend_name=component.manifest.identity.name,
                backend_version=component.manifest.identity.version,
                manifest_digest=canonical_json_digest(component.manifest.model_dump(mode="json")),
                envelope_id=envelope.id,
                envelope_digest=envelope.digest,
                configuration_digest=canonical_json_digest(envelope.configuration.model_dump(mode="json")),
            )
        )
    return tuple(coordinates)


def service_coordinates(declaration: MixedBackendExecutionBindingModel) -> tuple[MixedServiceCoordinate, ...]:
    return tuple(
        MixedServiceCoordinate(role=role, service_ref=pin.service_ref, version=pin.version, digest=pin.digest)
        for role, pin in role_pins(declaration)
    )


def binding_digest(declaration: MixedBackendExecutionBindingModel) -> str:
    return mixed_backend_binding_reference(declaration).digest


def configuration_digest(binding: object, declaration: MixedBackendExecutionBindingModel, supervision: object) -> str:
    """Digest the runtime, binding, components, service implementations and bounds that executed.

    ``binding`` is the embedder's binding before instrumentation, so the
    digest names the installed implementations rather than the recording wrappers.
    """

    return canonical_json_digest(
        {
            "runtime": {"implementation": _qualified_name_of(RuntimeControlPlane), "raes_version": _raes_version()},
            "profile": [binding.profile.profile_id, binding.profile.profile_revision, binding.profile.profile_digest],
            "plan": [binding.plan.plan_id, binding.plan_entry_id],
            "binding": binding_digest(declaration),
            "components": [vars(item) for item in component_coordinates(binding)],
            "services": [
                {**vars(item), "implementation": _qualified_name_of(type(service.implementation))}
                for item, service in _installed_services(binding, declaration)
            ],
            "supervision": None if supervision is None else repr(supervision),
        }
    )


def _installed_services(binding: object, declaration: MixedBackendExecutionBindingModel) -> list[tuple[object, object]]:
    installation = binding.backend_installations[declaration.binding_id]
    return [(item, installation.services[item.service_ref]) for item in service_coordinates(declaration)]


def tool_digest() -> str:
    """Digest the probe-family revision and the RAES distribution that ran it."""

    return canonical_json_digest({"tool": _TOOL_REVISION, "raes_version": _raes_version()})


__all__ = [
    "EFFECT_METHODS",
    "CallLog",
    "Instrumented",
    "OperationRead",
    "binding_digest",
    "close_plane",
    "component_coordinates",
    "composition_cut",
    "composition_history",
    "configuration_digest",
    "evidence_records",
    "instrument",
    "obligation_ref",
    "open_plane",
    "probed_installation",
    "read_operation",
    "role_pins",
    "service_coordinates",
    "submit",
    "tool_digest",
]
