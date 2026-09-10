"""Registry for runtime targets."""

from collections.abc import Callable
from dataclasses import dataclass
from inspect import Signature, signature
from typing import Any

from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.protocols import (
    Evaluator,
    Orchestrator,
    ParticipantRuntime,
    Provisioner,
    TimeRuntime,
)
from raes_contracts.observation_demand import ObservationBasis, ObservationLifecycleStage
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest

from . import time_coordinator as _time_coordinator
from .observation_execution import ObservationRuntime
from .observation_native import backend_selection_observation_runtime as backend_selection_observation_runtime
from .registry_probes import sample_participant_action_admission_request

ReferenceTimeRuntime = _time_coordinator.ReferenceTimeRuntime
_TIME_CLOCK_PROBE = "time.clock.probe"


@dataclass(frozen=True)
class _ParticipantRuntimeMethodRequirements:
    autonomous_binding: bool
    coordinated_reset: bool
    execution_control: bool
    bounded_concurrency: bool


def _participant_runtime_method_requirements(manifest: BackendManifest) -> _ParticipantRuntimeMethodRequirements:
    capability = manifest.participant_runtime
    return _ParticipantRuntimeMethodRequirements(
        autonomous_binding=bool(capability and capability.supports_autonomous_execution),
        coordinated_reset=bool(manifest.time and manifest.time.supports_coordinated_participant_reset),
        execution_control=bool(capability and capability.supports_execution_control),
        bounded_concurrency=bool(capability and capability.supports_bounded_concurrency),
    )


def _require_invokable_method(
    component: object | None,
    *,
    label: str,
    method_name: str,
    invocation_args: tuple[object, ...],
) -> None:
    if component is None:
        return
    method = getattr(component, method_name, None)
    if not callable(method):
        raise ValueError(f"registry.target-contract-mismatch: {label} is missing callable method '{method_name}'.")
    try:
        method_signature = signature(method)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"registry.target-contract-mismatch: {label}.{method_name} has a non-inspectable signature."
        ) from exc
    try:
        method_signature.bind(*invocation_args)
    except TypeError as exc:
        rendered_signature = _render_signature(method_signature)
        raise ValueError(
            "registry.target-contract-mismatch: "
            f"{label}.{method_name}{rendered_signature} is incompatible with "
            f"the runtime call shape for {label}.{method_name}."
        ) from exc


def _render_signature(method_signature: Signature) -> str:
    return str(method_signature)


def _validate_runtime_target_shape(
    *,
    manifest: BackendManifest | None,
    provisioner: Provisioner | None,
    orchestrator: Orchestrator | None,
    evaluator: Evaluator | None,
    participant_runtime: ParticipantRuntime | None,
    time_runtime: TimeRuntime | None,
    observation_runtime: ObservationRuntime | None,
) -> None:
    if manifest is None:
        raise ValueError("RuntimeTarget requires an explicit manifest.")
    if provisioner is None:
        raise ValueError("RuntimeTarget requires a provisioner.")
    _validate_optional_component_presence(
        manifest,
        orchestrator=orchestrator,
        evaluator=evaluator,
        participant_runtime=participant_runtime,
        time_runtime=time_runtime,
    )
    if (
        observation_runtime is not None
        and manifest.observation is None
        and any(
            capability.bases != frozenset({ObservationBasis.BACKEND_SELECTED})
            or not capability.stages.issubset({ObservationLifecycleStage.RETENTION})
            for capability in observation_runtime.capabilities
        )
    ):
        raise ValueError("registry.target-shape-mismatch: observation runtime requires manifest capabilities.")
    sample_plan = object()
    sample_snapshot = object()
    sample_request = object()
    sample_admission_request = sample_participant_action_admission_request()
    _validate_provisioner_methods(provisioner, sample_plan, sample_snapshot)
    _validate_orchestrator_methods(orchestrator, sample_plan, sample_snapshot)
    _validate_evaluator_methods(evaluator, sample_plan, sample_snapshot)
    _validate_participant_runtime_methods(
        participant_runtime,
        sample_request,
        sample_admission_request,
        sample_snapshot,
        requirements=_participant_runtime_method_requirements(manifest),
    )
    _validate_time_runtime_methods(
        time_runtime,
        sample_plan,
        sample_snapshot,
        require_coordinated_participant_reset=bool(
            manifest.time and manifest.time.supports_coordinated_participant_reset
        ),
    )


def _validate_optional_component_presence(
    manifest: BackendManifest,
    *,
    orchestrator: Orchestrator | None,
    evaluator: Evaluator | None,
    participant_runtime: ParticipantRuntime | None,
    time_runtime: TimeRuntime | None,
) -> None:
    if manifest.has_orchestrator != (orchestrator is not None):
        raise ValueError("registry.target-shape-mismatch: orchestrator presence does not match the manifest.")
    if manifest.has_evaluator != (evaluator is not None):
        raise ValueError("registry.target-shape-mismatch: evaluator presence does not match the manifest.")
    if manifest.has_participant_runtime != (participant_runtime is not None):
        raise ValueError("registry.target-shape-mismatch: participant_runtime presence does not match the manifest.")
    if manifest.has_time != (time_runtime is not None):
        raise ValueError("registry.target-shape-mismatch: time_runtime presence does not match the manifest.")
    if manifest.time and manifest.time.supports_coordinated_participant_reset and participant_runtime is None:
        raise ValueError(
            "registry.target-shape-mismatch: coordinated participant reset requires a participant_runtime."
        )


def _validate_provisioner_methods(
    provisioner: Provisioner,
    sample_plan: object,
    sample_snapshot: object,
) -> None:
    _require_invokable_method(
        provisioner,
        label="provisioner",
        method_name="validate",
        invocation_args=(sample_plan,),
    )
    _require_invokable_method(
        provisioner,
        label="provisioner",
        method_name="apply",
        invocation_args=(sample_plan, sample_snapshot),
    )


def _validate_orchestrator_methods(
    orchestrator: Orchestrator | None,
    sample_plan: object,
    sample_snapshot: object,
) -> None:
    _require_invokable_method(
        orchestrator,
        label="orchestrator",
        method_name="start",
        invocation_args=(sample_plan, sample_snapshot),
    )
    _require_invokable_method(
        orchestrator,
        label="orchestrator",
        method_name="status",
        invocation_args=(),
    )
    _require_invokable_method(
        orchestrator,
        label="orchestrator",
        method_name="results",
        invocation_args=(),
    )
    _require_invokable_method(
        orchestrator,
        label="orchestrator",
        method_name="history",
        invocation_args=(),
    )
    _require_invokable_method(
        orchestrator,
        label="orchestrator",
        method_name="stop",
        invocation_args=(sample_snapshot,),
    )


def _validate_evaluator_methods(
    evaluator: Evaluator | None,
    sample_plan: object,
    sample_snapshot: object,
) -> None:
    _require_invokable_method(
        evaluator,
        label="evaluator",
        method_name="start",
        invocation_args=(sample_plan, sample_snapshot),
    )
    _require_invokable_method(
        evaluator,
        label="evaluator",
        method_name="status",
        invocation_args=(),
    )
    _require_invokable_method(
        evaluator,
        label="evaluator",
        method_name="results",
        invocation_args=(),
    )
    _require_invokable_method(
        evaluator,
        label="evaluator",
        method_name="history",
        invocation_args=(),
    )
    _require_invokable_method(
        evaluator,
        label="evaluator",
        method_name="stop",
        invocation_args=(sample_snapshot,),
    )


def _validate_participant_runtime_methods(
    participant_runtime: ParticipantRuntime | None,
    sample_request: object,
    sample_admission_request: ParticipantActionAdmissionRequest,
    sample_snapshot: object,
    *,
    requirements: _ParticipantRuntimeMethodRequirements,
) -> None:
    _require_invokable_method(
        participant_runtime,
        label="participant_runtime",
        method_name="initialize",
        invocation_args=(sample_request, sample_snapshot),
    )
    _require_invokable_method(
        participant_runtime,
        label="participant_runtime",
        method_name="reset",
        invocation_args=(sample_request, sample_snapshot),
    )
    _require_invokable_method(
        participant_runtime,
        label="participant_runtime",
        method_name="restart",
        invocation_args=(sample_request, sample_snapshot),
    )
    _require_invokable_method(
        participant_runtime,
        label="participant_runtime",
        method_name="terminate",
        invocation_args=(sample_request, sample_snapshot),
    )
    _require_invokable_method(
        participant_runtime,
        label="participant_runtime",
        method_name="admit_action",
        invocation_args=(sample_admission_request, sample_snapshot),
    )
    _require_invokable_method(
        participant_runtime,
        label="participant_runtime",
        method_name="status",
        invocation_args=(),
    )
    _require_invokable_method(
        participant_runtime,
        label="participant_runtime",
        method_name="results",
        invocation_args=(),
    )
    _require_invokable_method(
        participant_runtime,
        label="participant_runtime",
        method_name="history",
        invocation_args=(),
    )
    if requirements.autonomous_binding:
        _require_invokable_method(
            participant_runtime,
            label="participant_runtime",
            method_name="bind_autonomous_action",
            invocation_args=(
                "participant.behavior.registry-probe",
                "participant.action-contract.registry-probe",
                "participant.observation-boundary.registry-probe",
                "participant-implementation-manifests.registry-probe.v1",
                "participant.autonomous-execution.registry-probe:0",
                (),
                sample_snapshot,
            ),
        )
    if requirements.coordinated_reset:
        _require_invokable_method(
            participant_runtime,
            label="participant_runtime",
            method_name="reset_many",
            invocation_args=((sample_request,), sample_snapshot),
        )
    if requirements.execution_control:
        _require_invokable_method(
            participant_runtime,
            label="participant_runtime",
            method_name="control_execution",
            invocation_args=(sample_request, sample_snapshot),
        )
        _require_invokable_method(
            participant_runtime,
            label="participant_runtime",
            method_name="execution_state",
            invocation_args=(
                "participant.autonomous-execution.registry-probe",
                sample_snapshot,
            ),
        )
    if requirements.bounded_concurrency:
        _require_invokable_method(
            participant_runtime,
            label="participant_runtime",
            method_name="admit_actions_concurrently",
            invocation_args=(
                (sample_admission_request, sample_admission_request),
                sample_snapshot,
                2,
            ),
        )


def _validate_time_runtime_methods(
    time_runtime: TimeRuntime | None,
    sample_declaration: object,
    sample_snapshot: object,
    *,
    require_coordinated_participant_reset: bool,
) -> None:
    for method_name, invocation_args in (
        ("initialize", (sample_declaration, sample_snapshot)),
        ("advance", (_TIME_CLOCK_PROBE, 1, 0, sample_snapshot)),
        ("pause", (_TIME_CLOCK_PROBE, sample_snapshot)),
        ("resume", (_TIME_CLOCK_PROBE, sample_snapshot)),
        ("jump", (_TIME_CLOCK_PROBE, 1, 0, sample_snapshot)),
        ("reset", (_TIME_CLOCK_PROBE, False, sample_snapshot)),
        ("state", (sample_snapshot,)),
    ):
        _require_invokable_method(
            time_runtime,
            label="time_runtime",
            method_name=method_name,
            invocation_args=invocation_args,
        )
    if require_coordinated_participant_reset:
        _require_invokable_method(
            time_runtime,
            label="time_runtime",
            method_name="reset_with_participants",
            invocation_args=("time.clock.probe", False, object(), (), sample_snapshot),
        )


@dataclass(frozen=True)
class RuntimeTarget:
    """A fully configured runtime target."""

    name: str
    manifest: BackendManifest
    provisioner: Provisioner
    orchestrator: Orchestrator | None = None
    evaluator: Evaluator | None = None
    participant_runtime: ParticipantRuntime | None = None
    time_runtime: TimeRuntime | None = None
    observation_runtime: ObservationRuntime | None = None

    def __post_init__(self) -> None:
        _validate_runtime_target_shape(
            manifest=self.manifest,
            provisioner=self.provisioner,
            orchestrator=self.orchestrator,
            evaluator=self.evaluator,
            participant_runtime=self.participant_runtime,
            time_runtime=self.time_runtime,
            observation_runtime=self.observation_runtime,
        )


@dataclass(frozen=True)
class RuntimeTargetComponents:
    """Instantiated runtime target components without a manifest."""

    provisioner: Provisioner
    orchestrator: Orchestrator | None = None
    evaluator: Evaluator | None = None
    participant_runtime: ParticipantRuntime | None = None
    time_runtime: TimeRuntime | None = None
    observation_runtime: ObservationRuntime | None = None


@dataclass(frozen=True)
class RuntimeTargetDescriptor:
    """Factories for manifest introspection and target creation."""

    name: str
    manifest_factory: Callable[..., BackendManifest]
    components_factory: Callable[..., RuntimeTargetComponents]


class BackendRegistry:
    """Registry of runtime target descriptors."""

    def __init__(self) -> None:
        self._descriptors: dict[str, RuntimeTargetDescriptor] = {}

    def register(
        self,
        name: str,
        manifest_factory: Callable[..., BackendManifest],
        components_factory: Callable[..., RuntimeTargetComponents],
    ) -> None:
        if name in self._descriptors:
            raise ValueError(f"Backend '{name}' is already registered and cannot be replaced.")
        self._descriptors[name] = RuntimeTargetDescriptor(
            name=name,
            manifest_factory=manifest_factory,
            components_factory=components_factory,
        )

    def describe(self, name: str) -> RuntimeTargetDescriptor:
        if name not in self._descriptors:
            registered = sorted(self._descriptors)
            raise KeyError(f"Unknown backend '{name}'. Registered backends: {registered}")
        return self._descriptors[name]

    def manifest(self, name: str, **config: Any) -> BackendManifest:
        return self.describe(name).manifest_factory(**config)

    def create(self, name: str, **config: Any) -> RuntimeTarget:
        descriptor = self.describe(name)
        manifest = descriptor.manifest_factory(**config)
        components = descriptor.components_factory(manifest=manifest, **config)

        if hasattr(components, "evaluators"):
            raise ValueError("registry.target-shape-mismatch: legacy evaluator collections are not supported.")

        _validate_runtime_target_shape(
            manifest=manifest,
            provisioner=components.provisioner,
            orchestrator=components.orchestrator,
            evaluator=components.evaluator,
            participant_runtime=components.participant_runtime,
            time_runtime=components.time_runtime,
            observation_runtime=components.observation_runtime,
        )

        return RuntimeTarget(
            name=name,
            manifest=manifest,
            provisioner=components.provisioner,
            orchestrator=components.orchestrator,
            evaluator=components.evaluator,
            participant_runtime=components.participant_runtime,
            time_runtime=components.time_runtime,
            observation_runtime=components.observation_runtime,
        )

    def list_backends(self) -> list[str]:
        return sorted(self._descriptors)

    def is_registered(self, name: str) -> bool:
        return name in self._descriptors
