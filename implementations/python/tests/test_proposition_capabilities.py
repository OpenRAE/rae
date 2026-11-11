"""Backend capability declarations for proposition realization."""

from __future__ import annotations

import pytest
from raes_backend_protocols.capabilities import EvaluatorCapabilities


def test_evaluator_declares_finite_truth_and_predicate_capabilities() -> None:
    evaluator = EvaluatorCapabilities(
        name="portable-evaluator",
        supported_sections=frozenset({"propositions", "assertions", "objectives"}),
        supported_predicate_families=frozenset({"presence", "boolean", "string", "number"}),
        supported_quantifiers=frozenset({"all", "any", "at_least"}),
        supported_truth_outcomes=frozenset({"true", "false", "unknown", "unsupported"}),
        supported_evidence_channels=frozenset({"log", "api_response"}),
        supported_time_domains=frozenset({"scenario_time"}),
        preserves_binding_provenance=True,
    )

    assert evaluator.supported_truth_outcomes == frozenset({"true", "false", "unknown", "unsupported"})
    assert evaluator.preserves_binding_provenance is True


def test_evaluator_cannot_claim_proposition_support_without_full_outcome_domain() -> None:
    with pytest.raises(ValueError, match="all portable truth outcomes"):
        EvaluatorCapabilities(
            name="boolean-only",
            supported_sections=frozenset({"propositions", "assertions", "objectives"}),
            supported_predicate_families=frozenset({"boolean"}),
            supported_quantifiers=frozenset({"all"}),
            supported_truth_outcomes=frozenset({"true", "false"}),
            supported_evidence_channels=frozenset({"log"}),
            supported_time_domains=frozenset({"scenario_time"}),
            preserves_binding_provenance=True,
        )


def test_evaluator_cannot_claim_observed_truth_without_provenance() -> None:
    with pytest.raises(ValueError, match="binding provenance"):
        EvaluatorCapabilities(
            name="opaque-evaluator",
            supported_sections=frozenset({"propositions", "assertions", "objectives"}),
            supported_predicate_families=frozenset({"string"}),
            supported_quantifiers=frozenset({"all"}),
            supported_truth_outcomes=frozenset({"true", "false", "unknown", "unsupported"}),
            supported_evidence_channels=frozenset({"log"}),
            supported_time_domains=frozenset({"scenario_time"}),
            preserves_binding_provenance=False,
        )
