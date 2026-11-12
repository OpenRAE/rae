"""Contract fixtures store no derived values; readers fill them (issue #1929)."""

from __future__ import annotations

import importlib
import json
import pkgutil
from functools import cache
from pathlib import Path

import pytest
import raes_contracts
from contract_fixtures import load_contract_fixture
from paths import REPO_ROOT
from pydantic import BaseModel
from raes_contracts.contract_seals import (
    SEALED_FIXTURE_KINDS,
    contract_seal_model,
    derivable_seal_paths,
    seal_contract_fixture,
    seal_payload,
    sealed_contract_ids,
    strip_derivable_seals,
)
from raes_contracts.contracts import AdmittedTrialPlanModel

FIXTURES = REPO_ROOT / "contracts" / "fixtures"


@cache
def _schema_models() -> dict[str, type[BaseModel]]:
    """Map each published contract id to the model that its schema names."""
    classes: dict[str, type[BaseModel]] = {}
    for module in pkgutil.walk_packages(raes_contracts.__path__, "raes_contracts."):
        for name, value in vars(importlib.import_module(module.name)).items():
            if isinstance(value, type) and issubclass(value, BaseModel):
                classes.setdefault(name, value)
    models = {}
    for schema in (REPO_ROOT / "contracts" / "schemas").rglob("*.json"):
        title = json.loads(schema.read_text(encoding="utf-8")).get("title")
        if title in classes:
            models[schema.stem] = classes[title]
    return models


def _sealed_kind_fixtures() -> list[Path]:
    return sorted(path for kind in SEALED_FIXTURE_KINDS for path in FIXTURES.rglob(f"{kind}/*.json"))


def test_no_fixture_stores_a_derived_value_that_its_contract_computes():
    stored = {}
    unregistered = set()
    for path in _sealed_kind_fixtures():
        contract_id = path.parent.parent.name
        model = _schema_models().get(contract_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if model is None or not isinstance(payload, dict):
            continue
        paths = derivable_seal_paths(model, payload)
        if paths:
            stored[path.relative_to(FIXTURES).as_posix()] = paths
        if seal_payload(model, payload) != payload and contract_id not in sealed_contract_ids():
            unregistered.add(contract_id)

    assert stored == {}, "remove these derived values; readers fill them with load_contract_fixture"
    assert unregistered == set(), "register these contracts in raes_contracts.contract_seals._CONTRACT_MODELS"


@pytest.mark.parametrize("contract_id", sorted(sealed_contract_ids()))
def test_registered_contract_resolves_to_its_published_model(contract_id):
    assert contract_seal_model(contract_id) is _schema_models()[contract_id]


def test_sealed_fixture_validates_and_its_seals_are_the_verified_values():
    path = FIXTURES / "plans" / "admitted-trial-plan-v1" / "valid" / "minimal.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "plan_digest" not in raw

    sealed = load_contract_fixture(path)
    plan = AdmittedTrialPlanModel.model_validate(sealed)

    assert sealed["plan_digest"] == plan.plan_digest
    assert strip_derivable_seals(AdmittedTrialPlanModel, sealed) == raw


def test_present_derived_value_is_kept_so_a_wrong_value_still_fails():
    path = FIXTURES / "plans" / "admitted-trial-plan-v1" / "valid" / "minimal.json"
    payload = {**json.loads(path.read_text(encoding="utf-8")), "plan_digest": "sha256:" + "1" * 64}

    sealed = seal_contract_fixture("admitted-trial-plan-v1", payload)

    assert sealed["plan_digest"] == "sha256:" + "1" * 64
    with pytest.raises(ValueError, match="plan_digest does not match"):
        AdmittedTrialPlanModel.model_validate(sealed)


def test_invalid_fixtures_stay_as_written():
    path = FIXTURES / "plans" / "admitted-trial-plan-v1" / "invalid" / "missing-plan-digest.json"
    assert load_contract_fixture(path) == json.loads(path.read_text(encoding="utf-8"))
