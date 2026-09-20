"""Typed keyword configuration for the runtime control plane."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypedDict

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.materialization import MaterializationArchive
from raes_contracts.planning import PlanScope
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ParticipantBehaviorSpecificationRuntime

from .control_plane_store import ControlPlaneStore
from .mixed_runtime import MixedRuntimeBinding
from .participant_crossing_mediation import ParticipantCrossingPolicyResolver


class ControlPlaneOptions(TypedDict, total=False):
    """Preserve the public constructor's optional, keyword-only configuration."""

    initial_snapshot: RuntimeSnapshot | None
    store: ControlPlaneStore | None
    behavior_specifications: Mapping[str, ParticipantBehaviorSpecificationRuntime] | None
    crossing_policy_resolver: ParticipantCrossingPolicyResolver | None
    information_state_context_resolver: ParticipantInformationStateContextResolver | None
    enforce_final_sink_flow_control: bool
    materialization_archive: MaterializationArchive | None
    run_scope: str
    mixed_runtime: MixedRuntimeBinding | None


@dataclass(frozen=True, kw_only=True)
class ControlPlaneConfiguration:
    """Resolve defaults and reject unknown options before runtime initialization."""

    initial_snapshot: RuntimeSnapshot | None = None
    store: ControlPlaneStore | None = None
    behavior_specifications: Mapping[str, ParticipantBehaviorSpecificationRuntime] | None = None
    crossing_policy_resolver: ParticipantCrossingPolicyResolver | None = None
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None
    enforce_final_sink_flow_control: bool = True
    materialization_archive: MaterializationArchive | None = None
    run_scope: str = "run:default"
    mixed_runtime: MixedRuntimeBinding | None = None

    def __post_init__(self) -> None:
        if not self.run_scope.startswith("run:"):
            raise ValueError("control-plane run_scope must use the normalized run:<id> form")
        PlanScope(run_id=self.run_scope.removeprefix("run:"))
        if self.mixed_runtime is not None:
            admitted_run_scope = f"run:{self.mixed_runtime.entry.run_id}"
            if self.run_scope != admitted_run_scope:
                raise ValueError("mixed runtime run_scope must match the admitted trial entry")
            if self.crossing_policy_resolver is None:
                raise ValueError("mixed runtime requires a crossing policy resolver")
