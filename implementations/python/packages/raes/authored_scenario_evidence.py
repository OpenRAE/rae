"""Authored scenario facts for evidence-relation validation (ADR-121)."""

from __future__ import annotations

from collections.abc import Mapping

from raes_contracts.contracts.experiment_evidence_refinement import ScenarioIdentity
from raes_contracts.evidence_requirements import EvidenceRequirement

from .canonical import canonical_sdl_digest
from .scenario import Scenario


class AuthoredScenarioEvidenceView:
    """An authored scenario as ``AuthoredScenarioEvidence``.

    The view computes the SDL digest each time the identity is read, as the
    validators did before ADR-121, so a scenario error surfaces at the same point.
    """

    __slots__ = ("_scenario",)

    def __init__(self, scenario: Scenario) -> None:
        self._scenario = scenario

    @property
    def scenario_identity(self) -> ScenarioIdentity:
        return (
            "scenario-snapshot",
            self._scenario.name,
            self._scenario.version,
            canonical_sdl_digest(self._scenario).value,
            None,
        )

    @property
    def evidence_requirements(self) -> Mapping[str, EvidenceRequirement]:
        return self._scenario.evidence_requirements


__all__ = ["AuthoredScenarioEvidenceView"]
