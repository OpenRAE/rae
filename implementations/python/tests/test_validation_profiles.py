"""ASR-511 governed validation-profile catalog tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_conformance.conformance import _fixture_case_diagnostics
from raes_contracts.validation_profiles import (
    ValidationProfileCatalogModel,
    load_validation_profile_catalog,
    select_validation_profile,
)
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "contracts/profiles/validation/validation-profile-catalog-v1.json"


def _catalog_payload() -> dict[str, object]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_canonical_catalog_defines_the_ordered_validation_strengths() -> None:
    catalog = load_validation_profile_catalog()

    assert catalog.profile_family == "raes-validation"
    assert {strength.strength_id: strength.rank for strength in catalog.strengths} == {
        "structural": 1,
        "semantic": 2,
        "behavioral": 3,
        "evidence_backed": 4,
        "falsification_backed": 5,
    }
    assert {subject.subject_kind for subject in catalog.subject_kinds} == {
        "scenario",
        "scenario_snapshot",
        "experiment_task",
        "experiment_run",
        "experiment_study",
        "backend_conformance_claim",
        "participant_conformance_claim",
        "published_claim",
    }


def test_profiles_reference_governed_terms_without_implying_gate_execution() -> None:
    catalog = load_validation_profile_catalog()
    evidence_profile = select_validation_profile(
        "raes-evidence-backed-validation",
        "v1",
        subject_kind="experiment_run",
    )

    assert evidence_profile.minimum_strength == "evidence_backed"
    assert "behavioral_execution" not in evidence_profile.required_gate_kinds
    assert "behavioral_execution" in evidence_profile.optional_gate_kinds
    assert {profile.minimum_strength for profile in catalog.profiles} == {
        "structural",
        "semantic",
        "behavioral",
        "evidence_backed",
        "falsification_backed",
    }


def test_profile_selection_fails_closed_for_unknown_identity_or_subject() -> None:
    with pytest.raises(ValueError, match="unknown validation profile"):
        select_validation_profile(
            "raes-missing-validation",
            "v1",
            subject_kind="scenario",
        )

    with pytest.raises(ValueError, match="does not declare subject kind"):
        select_validation_profile(
            "raes-behavioral-validation",
            "v1",
            subject_kind="published_claim",
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["profiles"][0]["required_gate_kinds"].append("missing_gate"),
            "unknown gate kinds",
        ),
        (
            lambda payload: payload["profiles"][0]["optional_gate_kinds"].append(
                payload["profiles"][0]["required_gate_kinds"][0]
            ),
            "required and optional gate kinds must be disjoint",
        ),
        (
            lambda payload: payload["profiles"].append(deepcopy(payload["profiles"][0])),
            "profile identities must be unique",
        ),
        (
            lambda payload: payload["strengths"].__setitem__(
                1,
                {
                    **payload["strengths"][1],
                    "rank": payload["strengths"][0]["rank"],
                },
            ),
            "strength ranks must be unique",
        ),
        (
            lambda payload: payload["limitation_categories"][0].__setitem__(
                "limitation_category",
                "x-invalid-extension",
            ),
            "String should match pattern",
        ),
    ],
)
def test_catalog_rejects_invalid_identity_and_reference_shapes(mutate, message: str) -> None:
    payload = _catalog_payload()
    mutate(payload)

    with pytest.raises(ValidationError, match=message):
        ValidationProfileCatalogModel.model_validate(payload)


def test_catalog_schema_is_published_with_reference_integrity_invariant() -> None:
    schema = schema_bundle()["validation-profile-catalog-v1"]

    assert {item["id"] for item in schema["x-raes-invariants"]} == {"validation-profile-catalog-reference-integrity"}
    published = json.loads(
        (REPO_ROOT / "contracts/schemas/profiles/validation-profile-catalog-v1.json").read_text(encoding="utf-8")
    )
    assert published == schema


@pytest.mark.parametrize(
    ("fixture", "valid"),
    [
        ("valid/minimal.json", True),
        ("invalid/dangling-reference.json", False),
    ],
)
def test_published_catalog_fixtures_use_conformance_validation(fixture: str, valid: bool) -> None:
    path = REPO_ROOT / "contracts/fixtures/profiles/validation-profile-catalog-v1" / fixture
    diagnostics = _fixture_case_diagnostics(
        "validation-profile-catalog-v1",
        json.loads(path.read_text(encoding="utf-8")),
    )

    assert (not diagnostics) is valid
