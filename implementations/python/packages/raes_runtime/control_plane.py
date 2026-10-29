"""Shared runtime engine with a compatible fixed default run context."""

from __future__ import annotations

from dataclasses import replace
from typing import Unpack

from .control_plane_configuration import ControlPlaneConfiguration, ControlPlaneOptions
from .control_plane_lifecycle import runtime_owned
from .control_plane_operation_context import operation_actor_scope
from .control_plane_security import ControlPlaneIdentity as ControlPlaneIdentity
from .control_plane_store import ControlPlaneOperationRecord
from .control_plane_store import LocalControlPlaneStore as LocalControlPlaneStore
from .participant_control_binding import (
    ParticipantControlResolution,
    ParticipantControlRuntimeBinding,
    ParticipantControlRuntimeResolver,
)
from .participant_control_effects import ParticipantControlEffectRealization
from .registry import RuntimeTarget
from .runtime_engine import RuntimeEngineResources
from .runtime_run_context import RuntimeRunContext

__all__ = (
    "ControlPlaneIdentity",
    "ControlPlaneOperationRecord",
    "ControlPlaneOptions",
    "LocalControlPlaneStore",
    "ParticipantControlEffectRealization",
    "ParticipantControlResolution",
    "ParticipantControlRuntimeBinding",
    "ParticipantControlRuntimeResolver",
    "RuntimeControlPlane",
    "operation_actor_scope",
)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from raes_contracts.contracts import ExperimentStudyModel
    from raes_contracts.trial_unit import TrialUnitResult
    from raes_processor.trial_realization import TrialRealizationInputs

    from .control_plane_store import ControlPlaneStore
    from .experiment_records import (
        ExperimentEvidenceReader,
        ExperimentRecordArchive,
        ExperimentRecordBundle,
        ExperimentRunMetadata,
    )
    from .runtime_experiment import ExperimentProgress
    from .runtime_experiment_replacement import ExperimentReplacementBinding
    from .runtime_sequence_authority import RuntimeSequenceOptions
    from .runtime_sequence_reference import RuntimeSequenceReference
    from .runtime_trial_services import TrialRuntimeServices


class RuntimeControlPlane(RuntimeRunContext):
    """One engine for all workloads; legacy calls use its fixed default run."""

    def __init__(self, target: RuntimeTarget, **options: Unpack[ControlPlaneOptions]) -> None:
        config = ControlPlaneConfiguration(**options)
        engine = RuntimeEngineResources(self, target, config)
        super().__init__(target, config=config, engine=engine)
        self._experiments = {}
        self._sequence_bindings = {}

    @runtime_owned
    def bind_workflow(self, **options: Unpack[RuntimeSequenceOptions]) -> RuntimeSequenceReference:
        """Bind exact owned artifacts before submitting reference-only delivery."""
        self._assert_runtime_owner()
        from .runtime_sequence_authority import bind_sequence

        return bind_sequence(self, options)

    @runtime_owned
    def advance_workflow(self, reference: RuntimeSequenceReference, *, identity: object | None) -> str:
        self._assert_runtime_owner()
        from .runtime_sequence_authority import advance_sequence

        return advance_sequence(self, reference, identity)

    @runtime_owned
    def admit_experiment(
        self,
        inputs: TrialRealizationInputs,
        *,
        services: TrialRuntimeServices,
        store_factory: Callable[[str], ControlPlaneStore] | None = None,
        identity: object | None = None,
        replacement: ExperimentReplacementBinding | None = None,
    ) -> str:
        self._assert_runtime_owner()
        from .runtime_experiment import RuntimeExperiment

        experiment = RuntimeExperiment(
            self, inputs, services=services, store_factory=store_factory, identity=identity, replacement=replacement
        )
        self._experiments.setdefault(experiment.experiment_id, experiment)
        return experiment.experiment_id

    @runtime_owned
    def advance_experiment(self, experiment_id: str, *, identity: object | None = None) -> ExperimentProgress:
        self._assert_runtime_owner()
        return self._experiments[experiment_id].advance(identity)

    @runtime_owned
    def cancel_experiment(self, experiment_id: str, *, identity: object | None = None) -> None:
        self._assert_runtime_owner()
        self._experiments[experiment_id].cancel(identity)

    @runtime_owned
    def experiment_results(self, experiment_id: str, *, identity: object | None = None) -> tuple[TrialUnitResult, ...]:
        self._assert_runtime_owner()
        return self._experiments[experiment_id].results(identity)

    @runtime_owned
    def experiment_records(
        self,
        experiment_id: str,
        *,
        identity: object | None = None,
        metadata: Mapping[str, ExperimentRunMetadata] | None = None,
        study: ExperimentStudyModel | None = None,
        evidence_reader: ExperimentEvidenceReader | None = None,
        archive: ExperimentRecordArchive | None = None,
    ) -> ExperimentRecordBundle:
        """Build records for every started run, including unresolved and failed work."""
        self._assert_runtime_owner()
        from .runtime_experiment_records import experiment_records

        return experiment_records(
            self._experiments[experiment_id],
            identity=identity,
            metadata=metadata,
            study=study,
            evidence_reader=evidence_reader,
            archive=archive,
        )

    @runtime_owned
    def open_run(self, **options: Unpack[ControlPlaneOptions]) -> RuntimeRunContext:
        """Open a fixed run scope without constructing another engine."""
        self._assert_runtime_owner()
        if "run_scope" not in options:
            raise ValueError("a new run requires an explicit run scope")
        for name in ("supervision", "distributed_execution", "profile"):
            if name in options and options[name] != getattr(self._engine.configuration, name):
                raise ValueError("a run cannot replace engine execution configuration")
        config = replace(self._engine.configuration, **{"store": None, "initial_snapshot": None, **options})
        return self._engine.open_run(config)

    @runtime_owned
    def get_run(self, run_scope: str) -> RuntimeRunContext:
        """Select a retained context without changing the default run."""
        return self._engine.get_run(run_scope)

    @runtime_owned
    def retire_run(self, run_scope: str) -> None:
        """Retain completed run state and release its verified resource use."""
        self._assert_runtime_owner()
        self._engine.retire(self._engine.get_run(run_scope))
