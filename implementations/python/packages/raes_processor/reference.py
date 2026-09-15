"""Repository-owned reference processor (RUN-313).

The reference processor realizes the normative processing model: it carries SDL
authoring input through instantiation, compilation, and planning to a portable
:class:`~raes_processor.models.ExecutionPlan`, and exposes the published
processor manifest. Per ADR-008 the processor is the semantics-bearing layer
between SDL authoring and backend realization, so its responsibility ends at the
execution plan; live backend realization (apply) is the runtime's job. End-to-end
execution is realized by composing this plan with the reference runtime
(``raes_runtime``) and is proven by ``raes_conformance`` and the RUN-313 tests.

Import layering (ADR-036 / ``tools/policy/adr_policy.yaml``): this module imports
only the lower SDL/processor/contract layers. It must not import ``raes_runtime``;
that one-directional boundary is why the reference processor stops at the plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from raes.parser import parse_sdl, parse_sdl_file
from raes.scenario import ExpandedScenario, InstantiatedScenario, Scenario
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import PlanScope

from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.manifest import (
    REFERENCE_PROCESSOR_NAME,
    REFERENCE_SUPPORTED_CONTRACT_VERSIONS_V2,
    reference_processor_manifest_payload,
)
from raes_processor.models import ExecutionPlan, RuntimeModel, RuntimeSnapshot
from raes_processor.planner import plan as _plan

__all__ = [
    "ReferenceProcessor",
    "ReferenceProcessorResult",
    "ScenarioInput",
    "run_reference_processor",
]

# SDL authoring input the reference processor accepts: raw SDL text, a path to an
# SDL file, or an already-parsed scenario (parameterized or instantiated).
ScenarioInput = str | Path | Scenario | ExpandedScenario | InstantiatedScenario


@dataclass(frozen=True)
class ReferenceProcessorResult:
    """Portable outcome of a reference-processor realization run."""

    scenario_name: str
    runtime_model: RuntimeModel
    execution_plan: ExecutionPlan
    diagnostics: tuple[Diagnostic, ...]

    @property
    def is_valid(self) -> bool:
        """True when neither compilation nor planning produced an error."""

        return not any(diag.is_error for diag in self.diagnostics)


def _resolve_scenario(scenario: ScenarioInput) -> Scenario | ExpandedScenario | InstantiatedScenario:
    if isinstance(scenario, (Scenario, ExpandedScenario, InstantiatedScenario)):
        return scenario
    if isinstance(scenario, Path):
        return parse_sdl_file(scenario)
    if isinstance(scenario, str):
        return parse_sdl(scenario)
    raise TypeError(
        "scenario must be SDL text (str), a file path (Path), or a parsed "
        f"Scenario/ExpandedScenario/InstantiatedScenario; got {type(scenario).__name__}"
    )


class ReferenceProcessor:
    """Repository-owned reference processor over the SDL -> ExecutionPlan path."""

    name: str = REFERENCE_PROCESSOR_NAME
    supported_contract_versions: tuple[str, ...] = REFERENCE_SUPPORTED_CONTRACT_VERSIONS_V2

    @staticmethod
    def manifest_payload(*, version: str | None = None) -> dict[str, Any]:
        """Return the published reference processor manifest as JSON-ready data."""

        return reference_processor_manifest_payload(version=version)

    @staticmethod
    def realize(
        scenario: ScenarioInput,
        backend_manifest: BackendManifest,
        *,
        parameters: Mapping[str, object] | None = None,
        profile: str | None = None,
        base_snapshot: RuntimeSnapshot | None = None,
        scope: PlanScope | None = None,
    ) -> ReferenceProcessorResult:
        """Realize an SDL scenario into a portable execution plan.

        Drives the canonical processing path: parse (when needed) ->
        instantiate -> compile -> plan, against ``backend_manifest`` (the
        backend the plan targets). Compilation and planning diagnostics are
        surfaced on the result rather than raised, so capability gaps and
        ordering conflicts are reported as data.
        """

        raw = _resolve_scenario(scenario)
        model = compile_scenario_runtime_model(raw, parameters=parameters, profile=profile)
        execution_plan = _plan(
            model,
            backend_manifest,
            base_snapshot,
            scope=scope,
        )
        diagnostics = (*model.diagnostics, *execution_plan.diagnostics)
        return ReferenceProcessorResult(
            scenario_name=model.scenario_name,
            runtime_model=model,
            execution_plan=execution_plan,
            diagnostics=diagnostics,
        )


def run_reference_processor(
    scenario: ScenarioInput,
    backend_manifest: BackendManifest,
    *,
    parameters: Mapping[str, object] | None = None,
    profile: str | None = None,
    base_snapshot: RuntimeSnapshot | None = None,
    scope: PlanScope | None = None,
) -> ReferenceProcessorResult:
    """Convenience wrapper around :meth:`ReferenceProcessor.realize`."""

    return ReferenceProcessor.realize(
        scenario,
        backend_manifest,
        parameters=parameters,
        profile=profile,
        base_snapshot=base_snapshot,
        scope=scope,
    )
