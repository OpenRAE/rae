"""Schema parts that the processor owns: its analysis evidence contracts (ADR-121)."""

from __future__ import annotations

from typing import Any

from .exploit_path.evidence import ExploitPathAnalysisEvidenceModel
from .satisfiability.evidence import ScenarioSatisfiabilityEvidenceModel, ScenarioSatisfiabilityEvidenceV2Model


def processor_contract_schemas() -> dict[str, dict[str, Any]]:
    """Return the raw schemas of the processor analysis evidence contracts."""

    return {
        "exploit-path-analysis-evidence-v1": ExploitPathAnalysisEvidenceModel.model_json_schema(),
        "scenario-satisfiability-evidence-v1": ScenarioSatisfiabilityEvidenceModel.model_json_schema(),
        "scenario-satisfiability-evidence-v2": ScenarioSatisfiabilityEvidenceV2Model.model_json_schema(),
    }


__all__ = ["processor_contract_schemas"]
