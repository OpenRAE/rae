"""Typed keyword configuration for the runtime control plane."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, TypedDict

from raes_contracts.contracts import ParticipantInformationStateContextResolver
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
from .participant_crossing_mediation import ParticipantCrossingPolicyResolver


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

    def __post_init__(self) -> None:
        _require_dispatcher_shape(self.distributed_execution)
        if not isinstance(self.supervision, OperationSupervisionConfiguration):
            raise TypeError("supervision requires typed apparatus configuration")
        if self.operation_evidence is not None and not all(
            callable(getattr(self.operation_evidence, name, None)) for name in ("validate_effects", "resolve_result")
        ):
            raise TypeError("operation evidence requires installed scoped validation and resolution")
        self._require_state_configuration()

    def _require_state_configuration(self) -> None:
        if self.participant_outcome_model is not None and not isinstance(self.participant_outcome_model, RuntimeModel):
            raise TypeError("participant_outcome_model must be a compiled RuntimeModel")
        if self.profile is not None and not isinstance(self.profile, ControlPlaneProfile):
            raise TypeError("control-plane profile must be a ControlPlaneProfile value")
        if not self.run_scope.startswith("run:"):
            raise ValueError("control-plane run_scope must use the normalized run:<id> form")
        PlanScope(run_id=self.run_scope.removeprefix("run:"))
        refuse_unsupported_mixed_control(self.behavior_specifications)
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
