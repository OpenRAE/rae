"""Facade-parity contract for the ``raes_conformance.conformance`` package (issue #46).

The module was split into subdomain modules behind an API-stable re-export
facade. These tests pin the public export surface, the four private hooks that
external code imports directly, and singular object identity through the
re-export so a future internal reshuffle cannot silently drop, fork, or
over-export a name.
"""

from __future__ import annotations

import raes_conformance.conformance as facade
from raes_conformance.conformance import (
    fixture_suite,
    observability,
    participant_episode_structure,
    profiles,
    report,
    semantics,
    target,
    validators,
)

_PUBLIC_EXPORTS = {
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
}

# Each re-exported public name mapped to the subdomain module that defines it.
_PUBLIC_ORIGINS = {
    "BackendCapabilityProfile": profiles,
    "BackendProfileSelector": profiles,
    "fixtures_root": profiles,
    "profiles_root": profiles,
    "required_contracts": profiles,
    "BackendConformanceReport": report,
    "ConformanceCaseResult": report,
    "backend_conformance_report_payload": report,
    "observability_evidence_conformance_diagnostics": observability,
    "participant_episode_structure_conformance_diagnostics": participant_episode_structure,
    "run_fixture_suite": fixture_suite,
    "profile_for_manifest": target,
    "run_target_conformance": target,
    "contract_payload_root": validators,
    "contract_validation_strength": validators,
    "supported_contract_ids": validators,
    "validate_contract_payload": validators,
}

# Private hooks that external callers import directly from the facade; they are
# contractual for issue #46 but must stay out of the star-export surface.
_PRIVATE_HOOKS = {
    "_MODEL_VALIDATORS": validators,
    "_validate_payload": validators,
    "_semantic_diagnostics": semantics,
    "_fixture_case_diagnostics": semantics,
}


def test_public_all_matches_expected_surface():
    assert set(facade.__all__) == _PUBLIC_EXPORTS


def test_public_names_are_singular_objects():
    for name, module in _PUBLIC_ORIGINS.items():
        assert getattr(facade, name) is getattr(module, name), name


def test_private_hooks_are_importable_and_singular():
    for name, module in _PRIVATE_HOOKS.items():
        assert hasattr(facade, name), name
        assert getattr(facade, name) is getattr(module, name), name


def test_private_hooks_excluded_from_star_exports():
    assert not (set(_PRIVATE_HOOKS) & set(facade.__all__))
