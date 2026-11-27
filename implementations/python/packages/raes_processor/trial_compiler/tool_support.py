"""Check each selected apparatus before admitting tool-bearing trial entries."""

from collections.abc import Iterable

from raes.scenario import InstantiatedScenario
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.contracts import ProcessorManifestV2Model
from raes_contracts.experiment_bindings import ApparatusManifest

from ..compiler import compile_scenario_runtime_model
from ..participant_tool_support import participant_tool_support_diagnostics
from .models import CompilationFailure


def require_selected_tool_support(
    selected: InstantiatedScenario,
    manifests: Iterable[ApparatusManifest],
    backends: tuple[BackendManifest, ...],
) -> None:
    if not any(spec.tool_affordances for spec in selected.behavior_specifications.values()):
        return
    model = compile_scenario_runtime_model(selected)
    processors = tuple(manifest for manifest in manifests if isinstance(manifest, ProcessorManifestV2Model))
    if not processors or not backends:
        raise CompilationFailure(
            "tool-support-apparatus-missing",
            "/apparatus/manifest_refs",
            "Tool profiles require selected processor and backend declarations.",
        )
    for processor in processors:
        for backend in backends:
            if participant_tool_support_diagnostics(model, backend, processor):
                raise CompilationFailure(
                    "tool-support-insufficient",
                    "/apparatus/manifest_refs",
                    "A selected apparatus lacks required tool-profile support or capacity.",
                )
