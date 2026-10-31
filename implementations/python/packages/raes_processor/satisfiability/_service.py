"""Production orchestration and replay for scenario satisfiability evidence."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import z3
from pydantic import ValidationError
from raes import SDLMigrationPolicy
from raes.canonical import (
    INSTANTIATED_SNAPSHOT_PROFILE,
    InstantiatedScenarioSnapshot,
    canonical_instantiated_sdl_digest,
)
from raes.instantiate import instantiate_scenario
from raes.parser import parse_sdl, read_sdl_source
from raes.scenario import ExpandedScenario
from raes_contracts.digests import sha256_digest
from raes_contracts.errors import EvidenceIntegrityError, OperationalError
from raes_contracts.satisfiability import (
    SatisfiabilityOutcome,
    SatisfiableWitnessModel,
    ScenarioSatisfiabilityEvidenceModel,
    SolverConfigurationModel,
    SourceArtifactIdentityModel,
    UnsatisfiableCoreModel,
    UnsupportedAnalysisModel,
    canonical_contract_digest,
)

from ._solver import SOLVER_TIMEOUT_MS, SolverOperationalError, solve_model
from ._translation import translate_scenario

ANALYSIS_PROFILE = "raes-finite-domain-satisfiability-v1"


class SatisfiabilityEvidenceError(EvidenceIntegrityError):
    """Stored evidence does not replay against its governed inputs."""


class SatisfiabilityOperationalError(OperationalError):
    """The production analyzer failed outside the typed outcome domain."""

    def __init__(
        self,
        message: str,
        *,
        solver_phase: str | None = None,
        solver_check_count: int | None = None,
        solver_check_budget: int | None = None,
        solver_timeout_ms: int | None = None,
        solver_reason: str | None = None,
    ) -> None:
        self.solver_phase = solver_phase
        self.solver_check_count = solver_check_count
        self.solver_check_budget = solver_check_budget
        self.solver_timeout_ms = solver_timeout_ms
        self.solver_reason = solver_reason
        details = []
        if solver_phase is not None:
            details.append(f"phase={solver_phase}")
        if solver_check_count is not None and solver_check_budget is not None:
            details.append(f"check={solver_check_count}/{solver_check_budget}")
        if solver_timeout_ms is not None:
            details.append(f"timeout_ms={solver_timeout_ms}")
        if solver_reason is not None:
            details.append(f"reason={solver_reason}")
        rendered = f"{message} ({', '.join(details)})" if details else message
        super().__init__(rendered)


def analyze_scenario_file(
    path: Path,
    *,
    profile: str = ANALYSIS_PROFILE,
) -> ScenarioSatisfiabilityEvidenceModel:
    """Analyze a bounded SDL file through the governed production boundary."""

    if profile != ANALYSIS_PROFILE:
        raise SatisfiabilityOperationalError("unknown satisfiability analysis profile")
    document = read_sdl_source(path)
    # The frozen formal-validation corpus predates canonical ``compute``.  This
    # analysis boundary opts into the diagnosed migration so replay preserves
    # the legacy declaration's exact virtual-machine intent.
    scenario = parse_sdl(
        document.text,
        path=path,
        migration_policy=SDLMigrationPolicy.ACCEPT,
    )
    source_digest = sha256_digest(document.raw_bytes)
    translation = translate_scenario(scenario, source_digest=source_digest)
    solver_configuration = _solver_configuration()
    common = {
        "profile": "scenario-satisfiability-evidence/v1",
        "analysis_profile": ANALYSIS_PROFILE,
        "source": SourceArtifactIdentityModel(source_id=path.name, byte_digest=source_digest),
        "authored_digest": translation.model.authored_digest,
        "imports": scenario.expansion_provenance.imports if isinstance(scenario, ExpandedScenario) else (),
        "normalized_model": translation.model,
        "normalized_model_digest": canonical_contract_digest(translation.model),
        "solver_configuration": solver_configuration,
        "solver_configuration_digest": canonical_contract_digest(solver_configuration),
    }
    if translation.diagnostics:
        return ScenarioSatisfiabilityEvidenceModel(
            **common,
            outcome=SatisfiabilityOutcome.UNSUPPORTED,
            diagnostics=translation.diagnostics,
            unsupported=UnsupportedAnalysisModel(
                profile="raes-satisfiability-unsupported/v1",
                reason_codes=tuple(sorted({item.code for item in translation.diagnostics})),
            ),
        )
    try:
        result = solve_model(translation.model)
    except SolverOperationalError as exc:
        raise SatisfiabilityOperationalError(
            "the pinned solver did not complete",
            solver_phase=exc.phase,
            solver_check_count=exc.check_count,
            solver_check_budget=exc.check_budget,
            solver_timeout_ms=exc.timeout_ms,
            solver_reason=exc.reason,
        ) from exc
    if result.outcome is SatisfiabilityOutcome.SATISFIABLE:
        assert result.assignment is not None
        instantiated = instantiate_scenario(
            scenario,
            parameters=result.assignment,
            profile=ANALYSIS_PROFILE,
        )
        snapshot = InstantiatedScenarioSnapshot(
            profile=INSTANTIATED_SNAPSHOT_PROFILE,
            scenario=instantiated,
        )
        return ScenarioSatisfiabilityEvidenceModel(
            **common,
            outcome=result.outcome,
            diagnostics=(),
            witness=SatisfiableWitnessModel(
                profile="raes-satisfiability-witness/v1",
                snapshot=snapshot,
                snapshot_digest=canonical_instantiated_sdl_digest(instantiated).value,
            ),
        )
    assert result.core is not None
    return ScenarioSatisfiabilityEvidenceModel(
        **common,
        outcome=result.outcome,
        diagnostics=(),
        unsat_core=UnsatisfiableCoreModel(
            profile="raes-unsatisfiable-core/v1",
            clause_ids=result.core,
            minimality="subset-minimal",
        ),
    )


def replay_satisfiability_evidence(
    path: Path,
    evidence: ScenarioSatisfiabilityEvidenceModel,
) -> ScenarioSatisfiabilityEvidenceModel:
    """Recompute and compare every source/model/solver/result evidence join."""

    document = read_sdl_source(path)
    actual_source_digest = sha256_digest(document.raw_bytes)
    if actual_source_digest != evidence.source.byte_digest:
        raise SatisfiabilityEvidenceError("source digest does not match the evidence")
    replayed = analyze_scenario_file(path, profile=evidence.analysis_profile)
    if canonical_contract_digest(replayed) != canonical_contract_digest(evidence):
        raise SatisfiabilityEvidenceError("satisfiability evidence replay did not reproduce")
    return replayed


def _solver_configuration() -> SolverConfigurationModel:
    package_version = version("z3-solver")
    engine_version = z3.get_version_string()
    try:
        return SolverConfigurationModel(
            profile="raes-z3-finite-domain/v1",
            engine="z3",
            package="z3-solver",
            package_version=package_version,
            engine_version=engine_version,
            logic="QF_LIA",
            random_seed=0,
            timeout_ms=SOLVER_TIMEOUT_MS,
            threads=1,
            auto_config=False,
            model=True,
            unsat_core=True,
            witness_selection="canonical-lexicographic/v1",
            core_reduction="sorted-deletion-subset-minimal/v1",
        )
    except ValidationError as exc:
        raise SatisfiabilityOperationalError("the installed solver does not match the governed profile") from exc
