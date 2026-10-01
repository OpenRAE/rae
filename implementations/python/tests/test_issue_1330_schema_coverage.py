"""Published-schema coverage gate (ASR-501, issue #1330).

Every published contract must carry concrete coverage evidence: a routed corpus
artifact, a delivered formal assurance artifact, or an explicitly declared and
validated alternate association. These tests drive the rule through temporary
repositories in the style of ``test_repo_policy_tools.py`` and
``test_assurance_policy.py``, then assert the live tree satisfies it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.contracts.backend_preparation import BackendPreparationResponseModel
from raes_contracts.contracts.candidate_synthesis import CandidateSynthesisRecordModel
from raes_contracts.contracts.execution_state import (
    InstantiationRequestModel,
    WorkflowCancellationRequestModel,
)
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionBindingModel,
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.contracts.semantic_projection import SemanticProjectionReportModel
from raes_contracts.realization_profiles import PlanProfileAuthority

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_json_artifacts import (  # noqa: E402
    _frozen_historical_records,
    collect_validation_targets,
    covered_schema_paths,
)
from tools.check_schema_coverage import (  # noqa: E402
    COVERAGE_KEY,
    DECLARATION_RULE_ID,
    MAX_SOURCES,
    MISSING_RULE_ID,
    build_coverage_report,
    evaluate_schema_coverage,
    main,
)
from tools.check_schema_publication import load_schema_publication_catalog  # noqa: E402

_SCHEMA = json.dumps(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {"schema_version": {"type": "string"}},
        "type": "object",
    },
    indent=2,
    sort_keys=True,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _publish(
    repo_root: Path,
    contract_id: str,
    family: str,
    *,
    coverage: dict[str, Any] | None = None,
    sharded: bool = True,
) -> str:
    """Publish one schema and its catalog record; return the schema path."""

    schema_path = f"contracts/schemas/{family}/{contract_id}.json"
    _write(repo_root / schema_path, _SCHEMA + "\n")
    entry: dict[str, Any] = {
        "content_hash": "0" * 64,
        "contract_id": contract_id,
        "schema_path": schema_path,
        "stability": "draft",
    }
    if coverage is not None:
        entry[COVERAGE_KEY] = coverage
    if sharded:
        _write_json(repo_root / "contracts/schema-publication/entries" / f"{contract_id}.json", entry)
        _seal_sharded(repo_root)
    else:
        _append_legacy(repo_root, entry)
    return schema_path


def _seal_sharded(repo_root: Path) -> None:
    (repo_root / "contracts/schema-publication/tombstones").mkdir(parents=True, exist_ok=True)
    _write_json(
        repo_root / "contracts/schema-publication-manifest.json",
        {
            "entries_directory": "contracts/schema-publication/entries",
            "hash_algorithm": "sha256",
            "schema_version": "schema-publication-manifest/v2",
            "tombstones_directory": "contracts/schema-publication/tombstones",
        },
    )


def _append_legacy(repo_root: Path, entry: dict[str, Any]) -> None:
    manifest = repo_root / "contracts/schema-publication-manifest.json"
    document: dict[str, Any] = {
        "hash_algorithm": "sha256",
        "schema_version": "schema-publication-manifest/v1",
        "schemas": [],
    }
    if manifest.is_file():
        document = json.loads(manifest.read_text(encoding="utf-8"))
    document["schemas"] = sorted(
        [*(e for e in document["schemas"] if e["contract_id"] != entry["contract_id"]), entry],
        key=lambda item: item["contract_id"],
    )
    _write_json(manifest, document)


def _tombstone(repo_root: Path, schema_path: str) -> None:
    _write_json(
        repo_root / "contracts/schema-publication/tombstones" / f"{Path(schema_path).stem}.json",
        {"schema_path": schema_path, "summary": "Retired during the coverage fixture build."},
    )
    _seal_sharded(repo_root)


def _corpus_fixture(repo_root: Path, contract_id: str, family: str, *, name: str = "reference") -> str:
    relative = f"contracts/fixtures/{family}/{contract_id}/valid/{name}.json"
    _write_json(repo_root / relative, {"schema_version": contract_id})
    return relative


def _fulfillment(repo_root: Path, *, delivered: list[str] = (), waived: list[str] = ()) -> None:
    lines = [
        "fulfillment: classification-based-assurance-fulfillment",
        "policy_ref: specs/formal/assurance-policy.yaml",
        "subsystems:",
        "  - id: coverage-subsystem",
        "    path: specs/formal/coverage-subsystem",
        "    fm_level: FM2",
        "entries:",
        "  - subsystem: coverage-subsystem",
        "    delivered_artifacts:",
    ]
    lines.extend(f"      - kind: typed_ir_or_contract_coverage\n        path: {path}" for path in delivered)
    if not delivered:
        lines.append("      []")
    lines.append("    waived_artifacts:")
    for path in waived:
        lines.append(
            f"      - kind: typed_ir_or_contract_coverage\n        path: {path}\n"
            "        date: 2026-09-20\n        tracking:\n          - '#1330'\n"
            "        rationale: Tracked gap retained as a waiver."
        )
    if not waived:
        lines.append("      []")
    _write(repo_root / "specs/formal/assurance-fulfillment.yaml", "\n".join(lines) + "\n")


def _rule_ids(failures: list[Any]) -> list[str]:
    return [failure.rule_id for failure in failures]


def _paths_for(failures: list[Any], rule_id: str) -> set[str]:
    return {failure.path for failure in failures if failure.rule_id == rule_id}


def _declaration(*sources: dict[str, str], rationale: str | None = None) -> dict[str, Any]:
    return {
        "rationale": rationale if rationale is not None else "No conventional corpus route reaches this contract.",
        "sources": list(sources),
    }


def _source(kind: str, path: str, supports: str = "Publication shape at the validation phase.") -> dict[str, str]:
    return {"kind": kind, "path": path, "supports": supports}


# --- leg 1: derived corpus coverage -----------------------------------------


def test_routed_corpus_artifact_covers_published_schema(tmp_path: Path) -> None:
    _publish(tmp_path, "operation-status-v1", "control-plane")
    _corpus_fixture(tmp_path, "operation-status-v1", "control-plane")

    assert evaluate_schema_coverage(tmp_path) == []


def test_uncovered_schema_reports_its_exact_path(tmp_path: Path) -> None:
    schema_path = _publish(tmp_path, "operation-status-v1", "control-plane")

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def test_empty_valid_directory_is_not_coverage(tmp_path: Path) -> None:
    schema_path = _publish(tmp_path, "operation-status-v1", "control-plane")
    (tmp_path / "contracts/fixtures/control-plane/operation-status-v1/valid").mkdir(parents=True)
    (tmp_path / "contracts/fixtures/control-plane/operation-status-v1/invalid").mkdir(parents=True)

    assert _paths_for(evaluate_schema_coverage(tmp_path), MISSING_RULE_ID) == {schema_path}


def test_invalid_only_corpus_is_not_coverage(tmp_path: Path) -> None:
    schema_path = _publish(tmp_path, "operation-status-v1", "control-plane")
    _write_json(
        tmp_path / "contracts/fixtures/control-plane/operation-status-v1/invalid/broken.json",
        {"schema_version": "operation-status-v1"},
    )

    assert _paths_for(evaluate_schema_coverage(tmp_path), MISSING_RULE_ID) == {schema_path}


def test_covered_schema_paths_exposes_the_router_join(tmp_path: Path) -> None:
    _publish(tmp_path, "operation-status-v1", "control-plane")
    _corpus_fixture(tmp_path, "operation-status-v1", "control-plane")

    assert "contracts/schemas/control-plane/operation-status-v1.json" in covered_schema_paths(tmp_path)


def test_migration_corpus_documents_route_to_their_contract(tmp_path: Path) -> None:
    _publish(tmp_path, "runtime-snapshot-v1", "snapshots")
    _write_json(
        tmp_path / "contracts/fixtures/snapshots/runtime-snapshot-v1/migration/legacy-before.json",
        {"schema_version": "runtime-snapshot-v1"},
    )

    assert evaluate_schema_coverage(tmp_path) == []


def test_frozen_historical_records_are_not_routed_as_live_documents(tmp_path: Path) -> None:
    """A content-hash-pinned pre-cutover record is not a claim about the contract now.

    ``tools/check_identity_cutover.py`` pins these documents, so they keep the
    shape their contract had when they were written. Routing one would demand an
    edit that the pin forbids and that would destroy the dated fact.
    """

    schema_path = _publish(tmp_path, "sdl-lineage-ledger-v1", "provenance")
    _write_json(
        tmp_path / "contracts/provenance/sdl-lineage-ledger-v1.json",
        {"schema_version": "sdl-lineage-ledger/v1"},
    )
    _write_json(
        tmp_path / "tools/policy/historical_identity_records.json",
        {
            "schema_version": "historical-identity-records/v3",
            "records": [
                {
                    "path": "contracts/provenance/sdl-lineage-ledger-v1.json",
                    "record_class": "provenance-record",
                    "rationale": "Pre-cutover lineage observations.",
                }
            ],
        },
    )

    assert "contracts/provenance/sdl-lineage-ledger-v1.json" not in {
        target.path for target in collect_validation_targets(tmp_path)
    }
    assert _paths_for(evaluate_schema_coverage(tmp_path), MISSING_RULE_ID) == {schema_path}


def test_a_live_document_still_covers_a_contract_whose_history_is_frozen(tmp_path: Path) -> None:
    schema_path = _publish(tmp_path, "sdl-lineage-ledger-v1", "provenance")
    _write_json(
        tmp_path / "contracts/provenance/sdl-lineage-ledger-v1.json",
        {"schema_version": "sdl-lineage-ledger/v1"},
    )
    _write_json(
        tmp_path / "contracts/provenance/sdl-lineage-ledger-v2.json",
        {"schema_version": "sdl-lineage-ledger/v1"},
    )
    _write_json(
        tmp_path / "tools/policy/historical_identity_records.json",
        {"records": [{"path": "contracts/provenance/sdl-lineage-ledger-v1.json", "record_class": "provenance-record"}]},
    )

    routed = {target.path for target in collect_validation_targets(tmp_path)}
    assert "contracts/provenance/sdl-lineage-ledger-v2.json" in routed
    assert "contracts/provenance/sdl-lineage-ledger-v1.json" not in routed
    assert schema_path in covered_schema_paths(tmp_path)


def test_every_checked_in_contract_payload_is_routed_or_frozen() -> None:
    """No positive payload of a published contract sits outside the validation lane.

    A document that names a published contract but that nothing validates is the
    silent hole this gate exists to close: the contract reads as covered while
    the document is free to drift.
    """

    routed = {target.path for target in collect_validation_targets(REPO_ROOT)}
    frozen = _frozen_historical_records(REPO_ROOT)
    published = {entry["contract_id"] for entry in load_schema_publication_catalog(REPO_ROOT)["schemas"]}

    unrouted = []
    for path in sorted((REPO_ROOT / "contracts").rglob("*.json")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative.startswith(("contracts/schemas/", "contracts/schema-publication")):
            continue
        if "/invalid/" in relative or relative in routed or relative in frozen:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
        if isinstance(schema_version, str) and schema_version.replace("/", "-") in published:
            unrouted.append(relative)

    assert unrouted == []


def test_a_symlinked_exclusion_manifest_excludes_nothing(tmp_path: Path) -> None:
    """The exclusion manifest decides what routing skips, so it cannot be a link.

    Following one would let a contributed symlink redirect the skip set at a file
    outside the checkout and silently suppress validation. Irregular means
    "exclude nothing", never "exclude whatever the link resolves to".
    """

    outside = tmp_path / "outside-records.json"
    _write_json(
        outside,
        {"records": [{"path": "contracts/provenance/operation-status-v1.json", "record_class": "provenance-record"}]},
    )
    _publish(tmp_path, "operation-status-v1", "control-plane")
    _write_json(
        tmp_path / "contracts/provenance/operation-status-v1.json",
        {"schema_version": "operation-status-v1"},
    )
    manifest = tmp_path / "tools/policy/historical_identity_records.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.symlink_to(outside)

    assert _frozen_historical_records(tmp_path) == frozenset()
    assert "contracts/provenance/operation-status-v1.json" in {
        target.path for target in collect_validation_targets(tmp_path)
    }


def test_symlinked_corpus_artifacts_are_never_dereferenced(tmp_path: Path) -> None:
    """Corpus discovery must not follow a tracked symlink out of the checkout.

    Corpus trees are PR-controlled. ``Path.is_file()`` follows a symlink, so
    without the regular-file boundary a contributed link would have its target
    read for a schema version and handed to the validator, putting host-resident
    content into policy diagnostics.
    """

    outside = tmp_path / "outside.json"
    _write_json(outside, {"schema_version": "operation-status-v1", "secret": "host-resident"})

    _publish(tmp_path, "operation-status-v1", "control-plane")
    linked = tmp_path / "contracts/provenance/operation-status-v1.json"
    linked.parent.mkdir(parents=True, exist_ok=True)
    linked.symlink_to(outside)

    routed = {target.path for target in collect_validation_targets(tmp_path)}

    assert "contracts/provenance/operation-status-v1.json" not in routed
    assert _paths_for(evaluate_schema_coverage(tmp_path), MISSING_RULE_ID) == {
        "contracts/schemas/control-plane/operation-status-v1.json"
    }


def test_symlinked_fixture_and_schema_artifacts_are_excluded_from_every_scan(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    _write_json(outside, {"schema_version": "operation-status-v1"})
    _publish(tmp_path, "operation-status-v1", "control-plane")

    for relative in (
        "contracts/fixtures/control-plane/operation-status-v1/valid/linked.json",
        "contracts/concept-authority/linked.json",
        "contracts/schemas/control-plane/linked.json",
    ):
        link = tmp_path / relative
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside)

    full = {target.path for target in collect_validation_targets(tmp_path)}
    named = {
        target.path
        for target in collect_validation_targets(
            tmp_path,
            paths=["contracts/fixtures/control-plane/operation-status-v1/valid/linked.json"],
        )
    }

    assert not any("linked.json" in path for path in full)
    assert named == set()


# --- leg 2: canonical formal coverage ---------------------------------------


def test_delivered_formal_artifact_covers_published_schema(tmp_path: Path) -> None:
    schema_path = _publish(tmp_path, "operation-status-v1", "control-plane")
    _fulfillment(tmp_path, delivered=[schema_path])

    assert evaluate_schema_coverage(tmp_path) == []


def test_waived_formal_artifact_is_not_coverage(tmp_path: Path) -> None:
    schema_path = _publish(tmp_path, "operation-status-v1", "control-plane")
    _fulfillment(tmp_path, waived=[schema_path])

    assert _paths_for(evaluate_schema_coverage(tmp_path), MISSING_RULE_ID) == {schema_path}


def test_structural_contract_passes_without_any_formal_model(tmp_path: Path) -> None:
    _publish(tmp_path, "operation-status-v1", "control-plane")
    _corpus_fixture(tmp_path, "operation-status-v1", "control-plane")

    # No assurance-fulfillment file exists at all: the gate never demands a
    # formal model and never reports a missing formal association.
    assert not (tmp_path / "specs/formal/assurance-fulfillment.yaml").exists()
    assert evaluate_schema_coverage(tmp_path) == []


# --- leg 3: declared alternate coverage -------------------------------------
#
# A declaration is a claim, and the gate proves every claim it accepts. Naming a
# contract, or naming a file that mentions one, is identity, not evidence: the
# named artifact must actually conform to the published schema, so removing the
# validation cannot leave the gate green.


def _conforming(contract_id: str) -> dict[str, Any]:
    return {"schema_version": contract_id}


def test_declared_fixture_source_covers_published_schema(tmp_path: Path) -> None:
    _write_json(tmp_path / "contracts/profiles/control-plane/reference-status.json", _conforming("operation-status-v1"))
    _publish(
        tmp_path,
        "operation-status-v1",
        "control-plane",
        coverage=_declaration(_source("fixture", "contracts/profiles/control-plane/reference-status.json")),
    )

    assert evaluate_schema_coverage(tmp_path) == []


def test_declared_fixture_source_must_conform_to_the_published_schema(tmp_path: Path) -> None:
    """A document that claims the contract but violates it is not evidence.

    This is the hole a name-matching gate leaves open: a deliberately invalid
    corpus case carries the contract id, so identity alone would accept it as
    proof that the contract is exercised.
    """

    _write_json(
        tmp_path / "contracts/profiles/control-plane/rejected-status.json",
        {"schema_version": "operation-status-v1", "force": True},
    )
    schema_path = _publish(
        tmp_path,
        "operation-status-v1",
        "control-plane",
        coverage=_declaration(_source("fixture", "contracts/profiles/control-plane/rejected-status.json")),
    )

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def test_a_carrier_is_not_whole_document_evidence_for_a_contract_it_embeds(tmp_path: Path) -> None:
    """A carrier is not a payload of what it carries.

    Validating the carrier against the embedded contract's schema would be a
    category error, so a nested payload has to name its node instead.
    """

    _write_json(
        tmp_path / "contracts/profiles/control-plane/carrier.json",
        {"schema_version": "backend-manifest-v2", "members": [{"schema_version": "operation-status-v1"}]},
    )
    schema_path = _publish(
        tmp_path,
        "operation-status-v1",
        "control-plane",
        coverage=_declaration(_source("fixture", "contracts/profiles/control-plane/carrier.json")),
    )

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def test_contract_id_inside_a_string_list_is_not_coverage(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "contracts/profiles/control-plane/manifest.json",
        {"schema_version": "backend-manifest-v2", "declared_contracts": ["operation-status-v1"]},
    )
    schema_path = _publish(
        tmp_path,
        "operation-status-v1",
        "control-plane",
        coverage=_declaration(_source("fixture", "contracts/profiles/control-plane/manifest.json")),
    )

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def test_a_python_test_file_is_no_longer_an_accepted_source_kind(tmp_path: Path) -> None:
    """Naming a test cannot be evidence, because the gate cannot falsify it.

    A file containing nothing but the contract name would satisfy any reference
    check, so the kind is gone rather than weakened.
    """

    _write(
        tmp_path / "implementations/python/tests/test_operation_status.py",
        'CONTRACT = "operation-status-v1"\n',
    )
    schema_path = _publish(
        tmp_path,
        "operation-status-v1",
        "control-plane",
        coverage=_declaration(_source("test", "implementations/python/tests/test_operation_status.py")),
    )

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def _carrier_repo(tmp_path: Path, node: Any) -> str:
    """Publish a contract realized only as a node inside another artifact."""

    _write_json(
        tmp_path / "contracts/schemas/profiles/annotation-entry-v1.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": {
                "Entry": {
                    "additionalProperties": False,
                    "properties": {"id": {"minLength": 1, "type": "string"}},
                    "required": ["id"],
                    "type": "object",
                }
            },
            "additionalProperties": False,
            "properties": {"schema_version": {"type": "string"}},
            "type": "object",
        },
    )
    _write_json(tmp_path / "contracts/profiles/carriers/host.json", {"schema_version": "host-v1", "annotations": node})
    entry = {
        "content_hash": "0" * 64,
        "contract_id": "annotation-entry-v1",
        "schema_path": "contracts/schemas/profiles/annotation-entry-v1.json",
        "stability": "draft",
        COVERAGE_KEY: _declaration(
            {
                "kind": "embedded",
                "path": "contracts/profiles/carriers/host.json",
                "pointer": "/annotations/0",
                "schema_pointer": "#/$defs/Entry",
                "supports": "A published annotation entry, validated at the publication phase.",
            }
        ),
    }
    _write_json(tmp_path / "contracts/schema-publication/entries/annotation-entry-v1.json", entry)
    _seal_sharded(tmp_path)
    return "contracts/schemas/profiles/annotation-entry-v1.json"


def test_embedded_source_covers_when_the_pointed_node_validates(tmp_path: Path) -> None:
    _carrier_repo(tmp_path, [{"id": "entry-one"}])

    assert evaluate_schema_coverage(tmp_path) == []


def test_embedded_source_stops_covering_when_the_node_is_removed(tmp_path: Path) -> None:
    """Deleting the annotation must turn the gate red, not leave it green."""

    schema_path = _carrier_repo(tmp_path, [])

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def test_embedded_source_stops_covering_when_the_node_stops_conforming(tmp_path: Path) -> None:
    schema_path = _carrier_repo(tmp_path, [{"id": "entry-one", "unexpected": True}])

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def test_embedded_schema_pointer_must_name_a_published_definition(tmp_path: Path) -> None:
    _carrier_repo(tmp_path, [{"id": "entry-one"}])
    entry_path = tmp_path / "contracts/schema-publication/entries/annotation-entry-v1.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry[COVERAGE_KEY]["sources"][0]["schema_pointer"] = "#/$defs/DoesNotExist"
    _write_json(entry_path, entry)

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {"contracts/schemas/profiles/annotation-entry-v1.json"}


def test_one_schema_may_cite_several_nodes_of_one_carrier(tmp_path: Path) -> None:
    _carrier_repo(tmp_path, [{"id": "entry-one"}, {"id": "entry-two"}])
    entry_path = tmp_path / "contracts/schema-publication/entries/annotation-entry-v1.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    second = dict(entry[COVERAGE_KEY]["sources"][0])
    second["pointer"] = "/annotations/1"
    entry[COVERAGE_KEY]["sources"].append(second)
    _write_json(entry_path, entry)

    assert evaluate_schema_coverage(tmp_path) == []


def test_several_schemas_may_share_one_carrier(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "contracts/profiles/shared.json",
        {"status": {"schema_version": "operation-status-v1"}, "receipt": {"schema_version": "operation-receipt-v1"}},
    )
    for contract_id, pointer in (("operation-receipt-v1", "/receipt"), ("operation-status-v1", "/status")):
        _publish(
            tmp_path,
            contract_id,
            "control-plane",
            coverage=_declaration(
                {
                    "kind": "embedded",
                    "path": "contracts/profiles/shared.json",
                    "pointer": pointer,
                    "supports": "A published payload carried by the shared artifact, at the publication phase.",
                }
            ),
        )

    assert evaluate_schema_coverage(tmp_path) == []


def test_checked_in_declaration_is_falsifiable_against_its_real_carrier() -> None:
    """The live declaration must fail if its carrier annotation is broken.

    A declaration nothing can falsify is decoration. This drives the checked-in
    association through the gate with the real carrier mutated.
    """

    from tools.schema_coverage._evidence import check_embedded_source

    carrier = "contracts/schemas/experiment-core/experiment-run-v1.json"
    schema = "contracts/schemas/profiles/raes-semantic-invariants-v1.json"
    pointer = "/x-raes-invariants/0"
    definition = "#/$defs/RaesSemanticInvariantEntryModel"

    assert check_embedded_source(REPO_ROOT, carrier, schema, pointer, definition) is None
    assert check_embedded_source(REPO_ROOT, carrier, schema, "/x-raes-invariants/99999", definition) is not None
    assert check_embedded_source(REPO_ROOT, carrier, schema, pointer, "#/$defs/DoesNotExist") is not None


# --- declaration hygiene -----------------------------------------------------


@pytest.mark.parametrize(
    "coverage",
    [
        pytest.param({"sources": [_source("fixture", "contracts/profiles/a.json")]}, id="missing-rationale"),
        pytest.param(_declaration(rationale="too short"), id="short-rationale"),
        pytest.param({**_declaration(_source("fixture", "contracts/profiles/a.json")), "extra": 1}, id="unknown-key"),
        pytest.param(_declaration(), id="empty-sources"),
        pytest.param(_declaration({"kind": "fixture", "path": "contracts/profiles/a.json"}), id="missing-supports"),
        pytest.param(_declaration(_source("fixture", "contracts/profiles/a.json", "tiny")), id="short-supports"),
        pytest.param(_declaration(_source("proof", "contracts/profiles/a.json")), id="unknown-kind"),
        pytest.param(_declaration(_source("fixture", "../outside.json")), id="escaping-path"),
        pytest.param(_declaration(_source("fixture", "/etc/passwd")), id="absolute-path"),
        pytest.param(_declaration(_source("fixture", "contracts/profiles/missing.json")), id="missing-file"),
        pytest.param(_declaration(_source("fixture", "tools/check_repo_policy.py")), id="fixture-outside-contracts"),
        pytest.param(_declaration(_source("embedded", "contracts/profiles/a.json")), id="embedded-without-pointer"),
        pytest.param(
            _declaration(
                _source("fixture", "contracts/profiles/a.json"),
                _source("fixture", "contracts/profiles/a.json"),
            ),
            id="duplicate-sources",
        ),
        pytest.param(
            _declaration(
                *[_source("fixture", f"contracts/profiles/a{index}.json") for index in range(MAX_SOURCES + 1)]
            ),
            id="oversized-source-list",
        ),
        pytest.param([], id="not-an-object"),
    ],
)
def test_malformed_declarations_are_reported_and_never_count(tmp_path: Path, coverage: Any) -> None:
    _write_json(tmp_path / "contracts/profiles/a.json", {"schema_version": "operation-status-v1"})
    schema_path = _publish(tmp_path, "operation-status-v1", "control-plane", coverage=coverage)

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def test_symlinked_declaration_source_is_rejected(tmp_path: Path) -> None:
    _write_json(tmp_path / "contracts/profiles/real.json", {"schema_version": "operation-status-v1"})
    link = tmp_path / "contracts/profiles/link.json"
    link.symlink_to(tmp_path / "contracts/profiles/real.json")
    schema_path = _publish(
        tmp_path,
        "operation-status-v1",
        "control-plane",
        coverage=_declaration(_source("fixture", "contracts/profiles/link.json")),
    )

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


def test_a_stale_reference_does_not_ride_on_a_resolving_sibling(tmp_path: Path) -> None:
    _write_json(tmp_path / "contracts/profiles/a.json", {"schema_version": "operation-status-v1"})
    schema_path = _publish(
        tmp_path,
        "operation-status-v1",
        "control-plane",
        coverage=_declaration(
            _source("fixture", "contracts/profiles/missing.json"),
            _source("fixture", "contracts/profiles/a.json"),
        ),
    )

    failures = evaluate_schema_coverage(tmp_path)

    assert _paths_for(failures, DECLARATION_RULE_ID) == {schema_path}
    assert _paths_for(failures, MISSING_RULE_ID) == {schema_path}


# --- denominator -------------------------------------------------------------


def test_legacy_v1_manifest_storage_reads_the_same_declaration(tmp_path: Path) -> None:
    _write_json(tmp_path / "contracts/profiles/a.json", {"schema_version": "operation-status-v1"})
    _publish(
        tmp_path,
        "operation-status-v1",
        "control-plane",
        coverage=_declaration(_source("fixture", "contracts/profiles/a.json")),
        sharded=False,
    )

    assert evaluate_schema_coverage(tmp_path) == []


def test_tombstoned_schema_is_outside_the_denominator(tmp_path: Path) -> None:
    _publish(tmp_path, "operation-status-v1", "control-plane")
    _corpus_fixture(tmp_path, "operation-status-v1", "control-plane")
    _tombstone(tmp_path, "contracts/schemas/control-plane/retired-v1.json")

    assert evaluate_schema_coverage(tmp_path) == []


def test_unreadable_catalog_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path / "contracts/schema-publication-manifest.json", "{ not json\n")

    failures = evaluate_schema_coverage(tmp_path)

    assert failures
    assert MISSING_RULE_ID not in _rule_ids(failures)


# --- reporting and CLI -------------------------------------------------------


def test_report_names_each_schema_and_its_covering_leg(tmp_path: Path) -> None:
    covered = _publish(tmp_path, "operation-status-v1", "control-plane")
    _corpus_fixture(tmp_path, "operation-status-v1", "control-plane")
    uncovered = _publish(tmp_path, "operation-receipt-v1", "control-plane")

    report = build_coverage_report(tmp_path)

    assert covered in report
    assert uncovered in report
    assert "corpus" in report
    assert "uncovered" in report


def test_cli_emits_json_failures_and_exits_non_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    schema_path = _publish(tmp_path, "operation-status-v1", "control-plane")

    exit_code = main(["--repo-root", str(tmp_path), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert {item["path"] for item in payload if item["rule_id"] == MISSING_RULE_ID} == {schema_path}


def test_cli_report_mode_never_gates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _publish(tmp_path, "operation-status-v1", "control-plane")

    assert main(["--repo-root", str(tmp_path), "--report"]) == 0
    assert "operation-status-v1" in capsys.readouterr().out


# --- the live tree -----------------------------------------------------------


def test_checked_in_repository_has_full_published_schema_coverage() -> None:
    assert evaluate_schema_coverage(REPO_ROOT) == []


# --- the corpora backfilled for the contracts that had none -----------------
#
# The gate reports a contract with no evidence; the repair is a real document,
# not a placeholder. These cases keep the backfilled corpora executable: every
# positive document validates against the checked-in published schema *and* its
# reference model, and every negative document is rejected by a named layer.
# A corpus nothing exercises would be exactly the vacuous coverage the gate
# exists to reject.

_BACKFILLED_CORPORA = {
    "participant-execution-binding-v1": (
        "participant-runtime",
        ParticipantExecutionBindingModel,
    ),
    "participant-execution-control-v1": (
        "participant-runtime",
        ParticipantExecutionControlRequestModel,
    ),
    "participant-execution-service-state-v1": (
        "participant-runtime",
        ParticipantExecutionServiceStateModel,
    ),
    "workflow-cancellation-request-v1": ("control-plane", WorkflowCancellationRequestModel),
    "scenario-instantiation-request-v1": ("sdl", InstantiationRequestModel),
    "semantic-projection-report-v1": ("concept-authority", SemanticProjectionReportModel),
    "sdl-candidate-synthesis-record-v1": ("candidate-synthesis", CandidateSynthesisRecordModel),
    "backend-realization-preparation-v1": ("plans", BackendPreparationResponseModel),
    "plan-realization-profiles-v1": ("plans", PlanProfileAuthority),
}

# Contracts whose repair is a positive document only: no negative case belongs
# to this issue because the contract already has one, or because its rejection
# layer is a runtime exchange rather than a standalone document.
_POSITIVE_ONLY = frozenset({"sdl-candidate-synthesis-record-v1"})


def _corpus_case_paths(contract_id: str, family: str, bucket: str) -> list[Path]:
    return sorted((REPO_ROOT / "contracts/fixtures" / family / contract_id / bucket).glob("*.json"))


def _published_validator(contract_id: str, family: str) -> Draft202012Validator:
    schema = json.loads((REPO_ROOT / "contracts/schemas" / family / f"{contract_id}.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


@pytest.mark.parametrize("contract_id", sorted(_BACKFILLED_CORPORA))
def test_backfilled_corpus_carries_positive_and_negative_cases(contract_id: str) -> None:
    family, _ = _BACKFILLED_CORPORA[contract_id]

    assert _corpus_case_paths(contract_id, family, "valid"), contract_id
    if contract_id not in _POSITIVE_ONLY:
        assert _corpus_case_paths(contract_id, family, "invalid"), contract_id


@pytest.mark.parametrize("contract_id", sorted(_BACKFILLED_CORPORA))
def test_backfilled_positive_cases_satisfy_the_published_schema_and_model(contract_id: str) -> None:
    family, model = _BACKFILLED_CORPORA[contract_id]
    validator = _published_validator(contract_id, family)

    for path in _corpus_case_paths(contract_id, family, "valid"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert not list(validator.iter_errors(payload)), f"{path.name} violates the published schema"
        model.model_validate(payload)


@pytest.mark.parametrize("contract_id", sorted(_BACKFILLED_CORPORA))
def test_backfilled_negative_cases_are_rejected_by_a_named_layer(contract_id: str) -> None:
    family, model = _BACKFILLED_CORPORA[contract_id]
    validator = _published_validator(contract_id, family)

    for path in _corpus_case_paths(contract_id, family, "invalid"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rejected_by_schema = bool(list(validator.iter_errors(payload)))
        try:
            model.model_validate(payload)
            rejected_by_model = False
        except ValueError:
            rejected_by_model = True
        assert rejected_by_schema or rejected_by_model, f"{path.name} is not rejected by schema or model"
