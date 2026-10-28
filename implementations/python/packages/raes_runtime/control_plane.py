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


class RuntimeControlPlane(RuntimeRunContext):
    """One engine for all workloads; legacy calls use its fixed default run."""

    def __init__(self, target: RuntimeTarget, **options: Unpack[ControlPlaneOptions]) -> None:
        config = ControlPlaneConfiguration(**options)
        engine = RuntimeEngineResources(self, target, config)
        super().__init__(target, config=config, engine=engine)
        self._experiments = {}
        self._sequence_bindings = {}

    @runtime_owned
    def bind_workflow(self, **options):
        """Bind exact owned artifacts before submitting reference-only delivery."""
        self._assert_runtime_owner()
        from .runtime_sequence_authority import bind_sequence

        return bind_sequence(self, **options)

    @runtime_owned
    def advance_workflow(self, reference, *, identity):
        self._assert_runtime_owner()
        from .runtime_sequence_authority import advance_sequence

        return advance_sequence(self, reference, identity)

    @runtime_owned
    def admit_experiment(self, inputs, *, services, store_factory=None, identity=None, replacement=None):
        self._assert_runtime_owner()
        from .runtime_experiment import RuntimeExperiment

        experiment = RuntimeExperiment(
            self, inputs, services=services, store_factory=store_factory, identity=identity, replacement=replacement
        )
        self._experiments.setdefault(experiment.experiment_id, experiment)
        return experiment.experiment_id

    @runtime_owned
    def advance_experiment(self, experiment_id, *, identity=None):
        self._assert_runtime_owner()
        return self._experiments[experiment_id].advance(identity)

    @runtime_owned
    def cancel_experiment(self, experiment_id, *, identity=None):
        self._assert_runtime_owner()
        self._experiments[experiment_id].cancel(identity)

    @runtime_owned
    def experiment_results(self, experiment_id, *, identity=None):
        self._assert_runtime_owner()
        return self._experiments[experiment_id].results(identity)

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
