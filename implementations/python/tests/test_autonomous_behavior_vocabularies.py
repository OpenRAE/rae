"""Pinned autonomous-service and autonomous-agent vocabulary source tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_conformance.conformance import validate_contract_payload
from raes_contracts.contracts import (
    ActivityStreamsActivityTypesSourceModel,
    FipaCommunicativeActsSourceModel,
    schema_bundle,
)
from raes_contracts.external_concept_bindings import (
    adapt_activitystreams_activity_types_snapshot,
    adapt_fipa_communicative_acts_snapshot,
)
from raes_contracts.vocabulary_sources import (
    load_activitystreams_activity_types_source,
    load_fipa_communicative_acts_source,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPO_ROOT / "contracts" / "schemas" / "concept-authority"
CHECKER_PATH = REPO_ROOT / "tools" / "check_autonomous_behavior_vocabularies.py"

ACTIVITYSTREAMS_TYPES = (
    "Accept",
    "Add",
    "Announce",
    "Arrive",
    "Block",
    "Create",
    "Delete",
    "Dislike",
    "Flag",
    "Follow",
    "Ignore",
    "Invite",
    "Join",
    "Leave",
    "Like",
    "Listen",
    "Move",
    "Offer",
    "Question",
    "Reject",
    "Read",
    "Remove",
    "TentativeReject",
    "TentativeAccept",
    "Travel",
    "Undo",
    "Update",
    "View",
)
FIPA_ACTS = (
    "accept-proposal",
    "agree",
    "cancel",
    "cfp",
    "confirm",
    "disconfirm",
    "failure",
    "inform",
    "inform-if",
    "inform-ref",
    "not-understood",
    "propagate",
    "propose",
    "proxy",
    "query-if",
    "query-ref",
    "refuse",
    "reject-proposal",
    "request",
    "request-when",
    "request-whenever",
    "subscribe",
)


def test_activitystreams_source_pins_dated_recommendation_and_normative_activity_types() -> None:
    source = load_activitystreams_activity_types_source()

    assert source.source_authority == "World Wide Web Consortium"
    assert source.source_version == "REC-activitystreams-vocabulary-20170523"
    assert source.source_status == "W3C Recommendation"
    assert source.source_url == "https://www.w3.org/TR/2017/REC-activitystreams-vocabulary-20170523/"
    assert source.source_digest == "sha256:1418443392160f4bb23dffb5727f5216d1f56d3430377dc67d364016521401db"
    assert [term.position for term in source.activity_types] == list(range(1, 29))
    assert [term.type_name for term in source.activity_types] == list(ACTIVITYSTREAMS_TYPES)
    assert [term.concept_id for term in source.activity_types] == [
        f"https://www.w3.org/ns/activitystreams#{name}" for name in ACTIVITYSTREAMS_TYPES
    ]
    assert all(term.type_name not in {"Application", "Service"} for term in source.activity_types)


def test_fipa_source_pins_standard_and_exact_communicative_act_symbols() -> None:
    source = load_fipa_communicative_acts_source()

    assert source.source_authority == "Foundation for Intelligent Physical Agents"
    assert source.source_version == "SC00037J-2002-12-03"
    assert source.source_status == "Standard"
    assert source.source_url == "https://www.fipa.org/specs/fipa00037/SC00037J.html"
    assert source.source_artifact_url == "https://www.fipa.org/specs/fipa00037/SC00037J.pdf"
    assert source.source_digest == "sha256:90b3277247ef7e7f614ba4c0d58fb2b86aa53ff69036d27a731c09a26c605227"
    assert [act.position for act in source.communicative_acts] == list(range(1, 23))
    assert [act.concept_id for act in source.communicative_acts] == list(FIPA_ACTS)


@pytest.mark.parametrize(
    ("loader", "field"),
    [
        (load_activitystreams_activity_types_source, "activity_types"),
        (load_fipa_communicative_acts_source, "communicative_acts"),
    ],
)
def test_source_contracts_reject_duplicate_positions_and_identifiers(loader, field: str) -> None:
    source = loader()
    payload = source.model_dump(mode="json")
    payload[field].append(dict(payload[field][0]))

    model_type = (
        ActivityStreamsActivityTypesSourceModel if field == "activity_types" else FipaCommunicativeActsSourceModel
    )
    with pytest.raises(ValidationError):
        model_type.model_validate(payload)


def test_source_adapters_emit_unrelated_neutral_snapshots_without_rewriting_identifiers() -> None:
    activitystreams = adapt_activitystreams_activity_types_snapshot(load_activitystreams_activity_types_source())
    fipa = adapt_fipa_communicative_acts_snapshot(load_fipa_communicative_acts_source())

    assert activitystreams.scheme_id == "w3c-activitystreams-activity-types"
    assert activitystreams.authority == "World Wide Web Consortium"
    assert activitystreams.revision == "REC-activitystreams-vocabulary-20170523"
    assert [term.concept_id for term in activitystreams.concepts] == [
        f"https://www.w3.org/ns/activitystreams#{name}" for name in ACTIVITYSTREAMS_TYPES
    ]

    assert fipa.scheme_id == "fipa-communicative-act-library"
    assert fipa.authority == "Foundation for Intelligent Physical Agents"
    assert fipa.revision == "SC00037J-2002-12-03"
    assert [term.concept_id for term in fipa.concepts] == list(FIPA_ACTS)


@pytest.mark.parametrize(
    ("loader", "adapter", "field"),
    [
        (load_activitystreams_activity_types_source, adapt_activitystreams_activity_types_snapshot, "activity_types"),
        (load_fipa_communicative_acts_source, adapt_fipa_communicative_acts_snapshot, "communicative_acts"),
    ],
)
def test_source_adapters_preserve_duplicate_concept_candidates(loader, adapter, field: str) -> None:
    source = loader()
    terms = getattr(source, field)
    duplicate_source = source.model_copy(update={field: [*terms, terms[0]]})

    snapshot = adapter(duplicate_source)

    assert sum(term.concept_id == snapshot.concepts[0].concept_id for term in snapshot.concepts) == 2


@pytest.mark.parametrize(
    "contract_id",
    [
        "w3c-activitystreams-activity-types-source-v1",
        "fipa-communicative-acts-source-v1",
    ],
)
def test_autonomous_vocabulary_source_schemas_are_published_and_generated_in_parity(contract_id: str) -> None:
    path = SCHEMA_ROOT / f"{contract_id}.json"
    published = json.loads(path.read_text(encoding="utf-8"))
    source = (
        load_activitystreams_activity_types_source()
        if contract_id.startswith("w3c-")
        else load_fipa_communicative_acts_source()
    )

    Draft202012Validator(published).validate(source.model_dump(mode="json"))
    assert schema_bundle()[contract_id] == published


@pytest.mark.parametrize(
    ("contract_id", "loader", "term_field"),
    [
        (
            "w3c-activitystreams-activity-types-source-v1",
            load_activitystreams_activity_types_source,
            "activity_types",
        ),
        ("fipa-communicative-acts-source-v1", load_fipa_communicative_acts_source, "communicative_acts"),
    ],
)
def test_source_contracts_use_canonical_structural_conformance(
    contract_id: str,
    loader,
    term_field: str,
) -> None:
    payload = loader().model_dump(mode="json")

    assert validate_contract_payload(contract_id, payload) == ()

    payload[term_field].append(dict(payload[term_field][0]))
    diagnostics = validate_contract_payload(contract_id, payload)

    assert {diagnostic.code for diagnostic in diagnostics} == {"conformance.schema-invalid"}
    assert payload[term_field][0]["concept_id"] not in diagnostics[0].message


def _load_source_checker():
    spec = importlib.util.spec_from_file_location("check_autonomous_behavior_vocabularies", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
def test_autonomous_behavior_source_integrity_checker_passes_offline() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_source_integrity_checker_rejects_metadata_drift() -> None:
    checker = _load_source_checker()
    activitystreams = load_activitystreams_activity_types_source().model_copy(
        update={"source_digest": f"sha256:{'0' * 64}"}
    )
    fipa = load_fipa_communicative_acts_source().model_copy(update={"source_version": "moving-latest"})

    activitystreams_failures = checker._check_activitystreams_source(activitystreams)
    fipa_failures = checker._check_fipa_source(fipa)

    assert any("source_digest" in failure for failure in activitystreams_failures)
    assert any("source_version" in failure for failure in fipa_failures)


def test_remote_verification_rejects_off_host_url_before_transport(monkeypatch) -> None:
    checker = _load_source_checker()
    failure = checker._remote_host_failure(
        "https://example.test/source",
        allowed_host="www.w3.org",
        relative_path=checker.ACTIVITYSTREAMS_RELATIVE_PATH,
    )

    assert failure is not None
    assert "allowlisted official HTTPS host" in failure
    assert (
        checker._remote_host_failure(
            "https://www.w3.org/TR/2017/REC-activitystreams-vocabulary-20170523/",
            allowed_host="www.w3.org",
            relative_path=checker.ACTIVITYSTREAMS_RELATIVE_PATH,
        )
        is None
    )
