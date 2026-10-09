"""Backend conformance runner for schema-first runtime contracts.

This package is an API-stable facade over the conformance subdomain modules.
It re-exports the public surface plus the four private hooks that existing code
imports directly; internal modules never import this facade.
"""

from __future__ import annotations

from raes_conformance.conformance.fixture_suite import run_fixture_suite
from raes_conformance.conformance.observability import (
    observability_evidence_conformance_diagnostics,
)
from raes_conformance.conformance.participant_episode_structure import (
    participant_episode_structure_conformance_diagnostics,
)
from raes_conformance.conformance.profiles import (
    BackendCapabilityProfile,
    BackendProfileSelector,
    fixtures_root,
    profiles_root,
    required_contracts,
)
from raes_conformance.conformance.report import (
    BackendConformanceReport,
    ConformanceCaseResult,
    backend_conformance_report_payload,
)
from raes_conformance.conformance.semantics import (
    _fixture_case_diagnostics as _fixture_case_diagnostics,
)
from raes_conformance.conformance.semantics import (
    _semantic_diagnostics as _semantic_diagnostics,
)
from raes_conformance.conformance.target import profile_for_manifest, run_target_conformance
from raes_conformance.conformance.validators import (
    _MODEL_VALIDATORS as _MODEL_VALIDATORS,
)
from raes_conformance.conformance.validators import (
    _validate_payload as _validate_payload,
)
from raes_conformance.conformance.validators import (
    contract_payload_root,
    contract_validation_strength,
    supported_contract_ids,
    validate_contract_payload,
)

__all__ = [
    "BackendCapabilityProfile",
    "BackendConformanceReport",
    "BackendProfileSelector",
    "ConformanceCaseResult",
    "backend_conformance_report_payload",
    "contract_payload_root",
    "contract_validation_strength",
    "fixtures_root",
    "observability_evidence_conformance_diagnostics",
    "participant_episode_structure_conformance_diagnostics",
    "profile_for_manifest",
    "profiles_root",
    "required_contracts",
    "run_fixture_suite",
    "run_target_conformance",
    "supported_contract_ids",
    "validate_contract_payload",
]
