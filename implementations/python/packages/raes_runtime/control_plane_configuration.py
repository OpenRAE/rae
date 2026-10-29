"""Typed keyword configuration for the runtime control plane."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, TypedDict

from raes_backend_protocols.inject_execution import InjectExecutionResolver, require_inject_resolver
from raes_contracts.contracts import ExperimentStochasticControlModel, ParticipantInformationStateContextResolver
from raes_contracts.contracts.backend_operation import OperationGuarantee
from raes_contracts.contracts.trial_controls import OperationSupervisionCapabilitiesModel
from raes_contracts.materialization import MaterializationArchive
from raes_contracts.planning import PlanScope
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ParticipantBehaviorSpecificationRuntime, RuntimeModel

from .control_plane_profiles import ControlPlaneProfile
from .control_plane_store import ControlPlaneStore
from .mixed_control_admission import refuse_unsupported_mixed_control
from .mixed_runtime import MixedRuntimeBinding
from .operation_supervision_configuration import OperationEvidenceResolver, OperationSupervisionConfiguration
from .participant_control_binding import ParticipantControlRuntimeBinding
from .participant_control_runtime import MixedControlRuntimeBinding
from .participant_crossing_mediation import ParticipantCrossingPolicyResolver
from .participant_inject_delivery import ParticipantInjectRuntimeBinding


class OperationDispatcher(Protocol):
    worker_identity: str

    def submit(self, request: object) -> str: ...
    def binding(self, request: object) -> object: ...
    def deliver_control(self, request: object, control: object) -> None: ...
    def close(self) -> None: ...


class ControlPlaneOptions(TypedDict, total=False):
    """Preserve the public constructor's optional, keyword-only configuration."""

    initial_snapshot: RuntimeSnapshot | None
    participant_outcome_model: RuntimeModel | None
    store: ControlPlaneStore | None
    behavior_specifications: Mapping[str, ParticipantBehaviorSpecificationRuntime] | None
    crossing_policy_resolver: ParticipantCrossingPolicyResolver | None
    information_state_context_resolver: ParticipantInformationStateContextResolver | None
    participant_control: ParticipantControlRuntimeBinding | None
    enforce_final_sink_flow_control: bool
    materialization_archive: MaterializationArchive | None
    run_scope: str
    mixed_runtime: MixedRuntimeBinding | None
    profile: ControlPlaneProfile | None
    supervision: OperationSupervisionConfiguration
    operation_evidence: OperationEvidenceResolver | None
    distributed_execution: OperationDispatcher | None
    inject_execution: InjectExecutionResolver | None
    mixed_control: MixedControlRuntimeBinding | None
    inject_delivery: ParticipantInjectRuntimeBinding | None
    stochastic_controls: Iterable[ExperimentStochasticControlModel]
    required_operation_guarantees: tuple[OperationGuarantee, ...]


@dataclass(frozen=True, kw_only=True)
class ControlPlaneConfiguration:
    """Resolve defaults and reject unknown options before runtime initialization."""

    initial_snapshot: RuntimeSnapshot | None = None
    participant_outcome_model: RuntimeModel | None = None
    store: ControlPlaneStore | None = None
    behavior_specifications: Mapping[str, ParticipantBehaviorSpecificationRuntime] | None = None
    crossing_policy_resolver: ParticipantCrossingPolicyResolver | None = None
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None
    participant_control: ParticipantControlRuntimeBinding | None = None
    enforce_final_sink_flow_control: bool = True
    materialization_archive: MaterializationArchive | None = None
    run_scope: str = "run:default"
    mixed_runtime: MixedRuntimeBinding | None = None
    profile: ControlPlaneProfile | None = None
    supervision: OperationSupervisionConfiguration = field(default_factory=OperationSupervisionConfiguration)
    operation_evidence: OperationEvidenceResolver | None = None
    distributed_execution: OperationDispatcher | None = None
    inject_execution: InjectExecutionResolver | None = None
    mixed_control: MixedControlRuntimeBinding | None = None
    inject_delivery: ParticipantInjectRuntimeBinding | None = None
    stochastic_controls: Iterable[ExperimentStochasticControlModel] = ()
    required_operation_guarantees: tuple[OperationGuarantee, ...] = ()

    def __post_init__(self) -> None:
        guarantees = OperationSupervisionCapabilitiesModel(
            name="runtime-run", guarantees=self.required_operation_guarantees
        )
        object.__setattr__(self, "required_operation_guarantees", guarantees.guarantees)
        if (
            self.distributed_execution is not None
            and self.mixed_runtime is not None
            and self.mixed_runtime.backend_installations
        ):
            raise ValueError(
                "portable mixed execution requires local pinned services; "
                "remote mixed worker authority is not installed"
            )
        require_inject_resolver(self.inject_execution)
        _require_dispatcher_shape(self.distributed_execution)
        if not isinstance(self.supervision, OperationSupervisionConfiguration):
            raise TypeError("supervision requires typed apparatus configuration")
        if self.operation_evidence is not None and not all(
            callable(getattr(self.operation_evidence, name, None)) for name in ("validate_effects", "resolve_result")
        ):
            raise TypeError("operation evidence requires installed scoped validation and resolution")
        if self.inject_delivery is not None and not isinstance(self.inject_delivery, ParticipantInjectRuntimeBinding):
            raise TypeError("inject delivery requires a typed runtime binding")
        self._require_state_configuration()
        self._require_inject_projection_configuration()

    def _require_inject_projection_configuration(self) -> None:
        if self.inject_delivery is not None:
            if self.crossing_policy_resolver is None:
                raise ValueError("inject delivery requires its crossing policy owner")
            if any(
                self.inject_delivery.model.behavior_specifications.get(ref) != specification
                for ref, specification in (self.behavior_specifications or {}).items()
            ):
                raise ValueError("inject delivery must match installed behavior specifications")

    def _require_state_configuration(self) -> None:
        if self.participant_outcome_model is not None and not isinstance(self.participant_outcome_model, RuntimeModel):
            raise TypeError("participant_outcome_model must be a compiled RuntimeModel")
        if self.profile is not None and not isinstance(self.profile, ControlPlaneProfile):
            raise TypeError("control-plane profile must be a ControlPlaneProfile value")
        if not self.run_scope.startswith("run:"):
            raise ValueError("control-plane run_scope must use the normalized run:<id> form")
        PlanScope(run_id=self.run_scope.removeprefix("run:"))
        self._require_mixed_control_configuration()
        self._require_mixed_runtime_configuration()

    def _require_mixed_control_configuration(self) -> None:
        if self.mixed_control is None:
            refuse_unsupported_mixed_control(self.behavior_specifications)
        elif not isinstance(self.mixed_control, MixedControlRuntimeBinding):
            raise TypeError("mixed control requires an installed runtime binding")
        elif any(
            self.mixed_control.model.behavior_specifications.get(ref) != spec
            for ref, spec in (self.behavior_specifications or {}).items()
        ):
            raise ValueError("mixed-control binding must match installed compiler context")
        elif self.mixed_runtime is not None:
            raise ValueError("reusable control cannot install an unsupported mixed-runtime participant path")
        elif self._has_controlled_delivery() and (
            self.inject_delivery is None
            or self.inject_delivery.model != self.mixed_control.model
            or self.crossing_policy_resolver is None
            or not callable(getattr(self.mixed_control.resolver, "resolve_delivery_cut", None))
        ):
            raise ValueError("reusable control cannot install an unsupported directed delivery path")

    def _has_controlled_delivery(self) -> bool:
        return any(
            self.mixed_control.model.participant_inject_deliveries[address].control is not None
            for spec in (self.behavior_specifications or {}).values()
            for address in spec.participant_inject_delivery_addresses
        )

    def _require_mixed_runtime_configuration(self) -> None:
        if self.mixed_runtime is not None:
            admitted_run_scope = f"run:{self.mixed_runtime.entry.run_id}"
            if self.run_scope != admitted_run_scope:
                raise ValueError("mixed runtime run_scope must match the admitted trial entry")
            if self.crossing_policy_resolver is None:
                raise ValueError("mixed runtime requires a crossing policy resolver")


def _require_dispatcher_shape(dispatcher: OperationDispatcher | None) -> None:
    if dispatcher is None:
        return
    if (
        not isinstance(getattr(dispatcher, "worker_identity", None), str)
        or not dispatcher.worker_identity
        or not all(
            callable(getattr(dispatcher, name, None)) for name in ("submit", "close", "binding", "deliver_control")
        )
    ):
        raise TypeError("distributed execution requires a scoped configured adapter")
