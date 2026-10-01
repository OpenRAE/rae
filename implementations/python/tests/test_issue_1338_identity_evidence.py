"""Participant relation changes preserve decision and historical evidence authority."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from raes import parse_sdl_file
from tools.check_adr_immutability import amendment_refs, canonical_content
from tools.formal_semantic_validation._releases import _retained_historical_cases

ROOT = Path(__file__).resolve().parents[3]
CORPUS = "docs/research/formal-semantic-validation/corpus"


@pytest.mark.parametrize("number", ["002", "020", "109"])
def test_relation_decisions_are_accepted_and_recorded(number):
    index = yaml.safe_load((ROOT / "docs/decisions/adrs/adr-index.yaml").read_text())
    record = next(entry for entry in index["adrs"] if entry["id"] == f"ADR-{number}")
    source = (ROOT / record["path"]).read_text()
    assert "## Status\n\naccepted\n" in source
    assert record["pin"] == hashlib.sha256(canonical_content(source).encode()).hexdigest()
    if number != "109":
        assert "#1338" in amendment_refs(source)
        assert "#1338" in {entry["ref"] for entry in record["amendments"]}


@pytest.mark.parametrize("name", ["semantic-valid", "semantic-invalid-dangling-ref"])
def test_historical_fixture_bytes_are_preserved_with_explicit_successors(name):
    historical = ROOT / CORPUS / f"{name}.sdl.yaml"
    release = json.loads((ROOT / "docs/research/formal-semantic-validation/bundles/retest-v39.json").read_text())
    pin = next(item for item in release["artifacts"] if item["path"] == historical.relative_to(ROOT).as_posix())
    assert hashlib.sha256(historical.read_bytes()).hexdigest() == pin["sha256"]
    successor = ROOT / CORPUS / f"{name}-participant-identity-v2.sdl.yaml"
    payload = yaml.safe_load(successor.read_text())
    assert payload["objectives"]["goal"]["owner"] == "blue"
    assert "entity" not in payload["objectives"]["goal"]
    if name == "semantic-valid":
        assert payload["propositions"]["ready"]["predicate"]["semantic_ref"] == "urn:raes:declared-property:ready"
        assert parse_sdl_file(successor).objectives["goal"].assigned_participant is None


def test_corpus_migration_allows_only_named_successors_without_changing_case_meaning():
    path = f"{CORPUS}/manifest-v4.json"
    corpus = json.loads((ROOT / path).read_text())
    cases = {item["case_id"]: item for item in corpus["cases"]}
    failures = []
    _retained_historical_cases(ROOT, cases, failures, path, corpus["revision"])
    assert failures == []
    for field, value in (("fixture_path", f"{CORPUS}/schema-valid.sdl.yaml"), ("expected_outcome", "rejected")):
        changed = deepcopy(cases)
        changed["semantic-resolved-objective"][field] = value
        failures = []
        _retained_historical_cases(ROOT, changed, failures, path, corpus["revision"])
        assert {failure.rule_id for failure in failures} == {"formal-validation-historical-retention"}
