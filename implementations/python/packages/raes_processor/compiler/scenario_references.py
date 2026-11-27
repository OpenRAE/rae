"""SDL facts that the runtime reads through the processor (ADR-036, ADR-121).

``raes_runtime`` imports no ``raes`` module. These functions give it the SDL
admission check and the authored scenario view that it needs.
"""

from __future__ import annotations

from raes.associated_artifacts import require_instantiated_scenario_reference
from raes.authored_scenario_evidence import AuthoredScenarioEvidenceView
from raes.scenario import Scenario
from raes_contracts.contracts import OperationArtifactReferenceModel
from raes_contracts.contracts.experiment_evidence_refinement import AuthoredScenarioEvidence

from ..models import RuntimeModel


def require_realization_reference(model: RuntimeModel, reference: OperationArtifactReferenceModel) -> None:
    """Refuse a scenario reference that does not bind the admitted realization instance of ``model``."""

    require_instantiated_scenario_reference(model.realization_instance, reference)


def authored_scenario_evidence(scenario: Scenario) -> AuthoredScenarioEvidence:
    """Return the evidence-relation view of one authored scenario."""

    return AuthoredScenarioEvidenceView(scenario)


__all__ = ["authored_scenario_evidence", "require_realization_reference"]
