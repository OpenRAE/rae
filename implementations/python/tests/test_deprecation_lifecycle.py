from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_deprecation_lifecycle import (  # noqa: E402
    _REQUIRED_RECORD_FIELDS,
    _REQUIRED_TOP_LEVEL_FIELDS,
    ADR_REF,
    CANONICAL_DEPRECATION_RECORD_IDS,
    DEPRECATION_RECORDS_RELATIVE_PATH,
    POLICY_VALUE,
    REQUIREMENT_REF,
    SCHEMA_PUBLICATION_MANIFEST,
    SPEC_RELATIVE_PATH,
    STATUSES,
    SURFACE_CLASSES,
    evaluate_deprecation_records,
)

# --------------------------------------------------------------------------- #
# A minimal, well-formed deprecation-records ledger used as the positive case  #
# and as the starting point for every mutation test. It mirrors the real      #
# specs/evolution/deprecation-records.yaml shape.                             #
# --------------------------------------------------------------------------- #


def _good_ledger() -> dict:
    # Includes all canonical (retention-floor) records so the positive case and
    # every mutation starting point satisfies CANONICAL_DEPRECATION_RECORD_IDS.
    # records[0] is a canonical record; mutation tests operate on it.
    return {
        "policy": POLICY_VALUE,
        "requirement_refs": [REQUIREMENT_REF],
        "adr_refs": [ADR_REF],
        "spec": SPEC_RELATIVE_PATH,
        "records": [
            {
                "id": "obsolete-example-surface",
                "surface_class": "python-distribution",
                "identifier": "example package alias",
                "status": "removed",
                "first_notice": "ADR-010 (example)",
                "replacement": "the canonical example package",
                "migration_reference": "docs/migration/raes-rename.md",
                "notice_window": "removed after the documented test window",
                "verification_evidence": "the test fixture models a completed removal",
                "removal_record": "The example alias is no longer published.",
            },
            {
                "id": "sdl-import-path-field",
                "surface_class": "sdl-scenario-module",
                "identifier": "ImportDecl.path (module import 'path:' field)",
                "status": "deprecated",
                "first_notice": "ADR-053 (example)",
                "replacement": "the 'source:' field",
                "migration_reference": "docs/explain/sdl/parser.md",
                "notice_window": "supported indefinitely as a backward-compatible alias",
                "verification_evidence": "parser normalises the legacy field; tests exercise both forms",
            },
            {
                "id": "legacy-python-distribution",
                "surface_class": "python-distribution",
                "identifier": "the legacy PyPI distribution",
                "status": "deprecated",
                "first_notice": "ADR-093 and issue #907",
                "replacement": "the raes PyPI distribution",
                "migration_reference": "docs/migration/raes-rename.md",
                "notice_window": "publish the final pointer release, verify it, then archive the project",
                "verification_evidence": "the current release path publishes only raes",
            },
            {
                "id": "sdl-domain-classification-fields",
                "surface_class": "sdl-scenario-module",
                "identifier": "legacy classification fields",
                "status": "removed",
                "first_notice": "Issue #989",
                "replacement": "standalone external concept bindings",
                "migration_reference": "docs/migration/external-classifications.md",
                "notice_window": "generic contract and atomic migrator available",
                "verification_evidence": "canonical exclusion and migration tests",
                "removal_record": "Draft SDL schemas no longer carry classification fields.",
            },
        ],
    }


def _write_repo(
    tmp_path: Path,
    ledger: object,
    *,
    write_spec: bool = True,
    manifest: dict | None = None,
) -> Path:
    """Materialise a minimal repo layout under ``tmp_path`` and return it.

    ``ledger`` is dumped to the canonical records path. The spec file the ledger
    points at is written unless ``write_spec`` is False, and a schema
    publication manifest is written when ``manifest`` is provided.
    """
    records_path = tmp_path / DEPRECATION_RECORDS_RELATIVE_PATH
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")

    if write_spec:
        spec_path = tmp_path / SPEC_RELATIVE_PATH
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text("# evolution policy (test stub)\n", encoding="utf-8")

    if manifest is not None:
        manifest_path = tmp_path / SCHEMA_PUBLICATION_MANIFEST
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    return tmp_path


def _rule_ids(tmp_path: Path) -> set[str]:
    return {failure.rule_id for failure in evaluate_deprecation_records(tmp_path)}


# --------------------------------------------------------------------------- #
# Positive cases.                                                             #
# --------------------------------------------------------------------------- #


def test_good_ledger_passes(tmp_path: Path) -> None:
    _write_repo(tmp_path, _good_ledger())
    assert evaluate_deprecation_records(tmp_path) == []


def test_no_replacement_rationale_is_accepted(tmp_path: Path) -> None:
    ledger = _good_ledger()
    record = ledger["records"][0]
    del record["replacement"]
    record["no_replacement_rationale"] = "the surface is withdrawn with no successor by design"
    _write_repo(tmp_path, ledger)
    assert evaluate_deprecation_records(tmp_path) == []


def test_complete_security_exception_is_accepted(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0]["security_exception"] = {
        "affected_versions": "0.1.0 through 0.19.1",
        "impact": "example impact",
        "mitigation": "example mitigation",
        "migration": "example migration path",
        "review_authority": "maintainers",
    }
    _write_repo(tmp_path, ledger)
    assert evaluate_deprecation_records(tmp_path) == []


def test_removed_schema_with_tombstone_is_accepted(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0].update(
        {
            "surface_class": "published-json-schema",
            "status": "removed",
            "removal_record": "release note X; ADR-061 tombstone",
            "removal_tombstone": "contracts/schemas/old/legacy-v1.json",
        }
    )
    manifest = {
        "schema_version": "schema-publication-manifest/v1",
        "hash_algorithm": "sha256",
        "schemas": [],
        "removed_schemas": [{"schema_path": "contracts/schemas/old/legacy-v1.json", "summary": "removed"}],
    }
    _write_repo(tmp_path, ledger, manifest=manifest)
    assert evaluate_deprecation_records(tmp_path) == []


# --------------------------------------------------------------------------- #
# Negative cases — one per rule_id.                                           #
# --------------------------------------------------------------------------- #


def test_missing_file(tmp_path: Path) -> None:
    assert "deprecation-records-missing" in _rule_ids(tmp_path)


def test_parse_error(tmp_path: Path) -> None:
    records_path = tmp_path / DEPRECATION_RECORDS_RELATIVE_PATH
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_text("policy: [unterminated\n", encoding="utf-8")
    assert "deprecation-records-parse" in _rule_ids(tmp_path)


def test_top_level_not_mapping(tmp_path: Path) -> None:
    _write_repo(tmp_path, ["not", "a", "mapping"])
    assert "deprecation-records-shape" in _rule_ids(tmp_path)


@pytest.mark.parametrize("field", _REQUIRED_TOP_LEVEL_FIELDS)
def test_missing_top_level_field(tmp_path: Path, field: str) -> None:
    # Parametrised over the FULL required-tuple so dropping any field from the
    # tuple leaves a failing test, not a silent no-op.
    ledger = _good_ledger()
    del ledger[field]
    _write_repo(tmp_path, ledger)
    failures = evaluate_deprecation_records(tmp_path)
    assert any(f.rule_id == "deprecation-records-field" and field in f.message for f in failures), (
        f"expected a missing-field failure naming {field!r}; got: {[f.render() for f in failures]}"
    )


def test_records_wrong_type(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"] = "not-a-list"
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-field-type" in _rule_ids(tmp_path)


def test_wrong_policy_value(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["policy"] = "something-else"
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-policy-value" in _rule_ids(tmp_path)


def test_missing_requirement_ref(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["requirement_refs"] = ["OTHER-001"]
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-requirement-ref" in _rule_ids(tmp_path)


def test_missing_adr_ref(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["adr_refs"] = ["ADR-999"]
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-adr-ref" in _rule_ids(tmp_path)


def test_spec_missing_on_disk(tmp_path: Path) -> None:
    _write_repo(tmp_path, _good_ledger(), write_spec=False)
    assert "deprecation-records-spec-missing" in _rule_ids(tmp_path)


@pytest.mark.parametrize("field", _REQUIRED_RECORD_FIELDS)
def test_record_missing_required_field(tmp_path: Path, field: str) -> None:
    # Full-tuple coverage: every required record field is exercised, and the
    # failure must name the dropped field (not merely fire the generic rule).
    ledger = _good_ledger()
    del ledger["records"][0][field]
    _write_repo(tmp_path, ledger)
    failures = evaluate_deprecation_records(tmp_path)
    assert any(f.rule_id == "deprecation-records-entry-field" and field in f.message for f in failures), (
        f"expected a missing-field failure naming {field!r}; got: {[f.render() for f in failures]}"
    )


def test_record_empty_field(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0]["identifier"] = "   "
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-entry-field" in _rule_ids(tmp_path)


def test_duplicate_record_id(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"].append(copy.deepcopy(ledger["records"][0]))
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-entry-duplicate" in _rule_ids(tmp_path)


def test_unknown_surface_class(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0]["surface_class"] = "not-a-real-surface"
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-surface-class" in _rule_ids(tmp_path)


def test_bad_status(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0]["status"] = "sunset"
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-status" in _rule_ids(tmp_path)


def test_both_replacement_and_no_replacement(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0]["no_replacement_rationale"] = "conflicting"
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-replacement" in _rule_ids(tmp_path)


def test_neither_replacement_nor_rationale(tmp_path: Path) -> None:
    ledger = _good_ledger()
    del ledger["records"][0]["replacement"]
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-replacement" in _rule_ids(tmp_path)


def test_incomplete_security_exception(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0]["security_exception"] = {"impact": "only one field"}
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-security-exception" in _rule_ids(tmp_path)


def test_removed_without_removal_record(tmp_path: Path) -> None:
    ledger = _good_ledger()
    del ledger["records"][0]["removal_record"]
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-removal-record" in _rule_ids(tmp_path)


def test_removed_schema_without_tombstone(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0].update(
        {
            "surface_class": "published-json-schema",
            "status": "removed",
            "removal_record": "release note",
        }
    )
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-removal-tombstone" in _rule_ids(tmp_path)


def test_removed_schema_tombstone_not_in_manifest(tmp_path: Path) -> None:
    ledger = _good_ledger()
    ledger["records"][0].update(
        {
            "surface_class": "published-json-schema",
            "status": "removed",
            "removal_record": "release note",
            "removal_tombstone": "contracts/schemas/absent.json",
        }
    )
    manifest = {
        "schema_version": "schema-publication-manifest/v1",
        "hash_algorithm": "sha256",
        "schemas": [],
        "removed_schemas": [],
    }
    _write_repo(tmp_path, ledger, manifest=manifest)
    assert "deprecation-records-removal-tombstone" in _rule_ids(tmp_path)


# --------------------------------------------------------------------------- #
# Retention floor — lifecycle history may not silently disappear.             #
# --------------------------------------------------------------------------- #


def test_empty_ledger_is_rejected(tmp_path: Path) -> None:
    # An authoritative record surface that permits `records: []` would let all
    # lifecycle history be erased while the gate stays green.
    ledger = _good_ledger()
    ledger["records"] = []
    _write_repo(tmp_path, ledger)
    assert "deprecation-records-canonical-record-missing" in _rule_ids(tmp_path)


def test_dropping_a_canonical_record_is_rejected(tmp_path: Path) -> None:
    # Deleting an established record (leaving the others) must fail: an existing
    # deprecation is permanent lifecycle history, not something a later diff can
    # silently remove.
    ledger = _good_ledger()
    dropped = ledger["records"].pop()  # remove a canonical retention-floor record
    _write_repo(tmp_path, ledger)
    failures = evaluate_deprecation_records(tmp_path)
    assert any(f.rule_id == "deprecation-records-canonical-record-missing" for f in failures)
    assert any(dropped["id"] in f.message for f in failures), (
        f"expected the dropped record id to be named; got: {[f.render() for f in failures]}"
    )


# --------------------------------------------------------------------------- #
# Guard the pinned constants so a rename surfaces here.                       #
# --------------------------------------------------------------------------- #


def test_canonical_record_ids_are_pinned() -> None:
    expected = {
        "legacy-python-distribution",
        "sdl-import-path-field",
        "sdl-domain-classification-fields",
    }
    actual = CANONICAL_DEPRECATION_RECORD_IDS
    assert actual == expected


def test_surface_classes_cover_known_matrix_rows() -> None:
    assert {"python-distribution", "sdl-scenario-module", "published-json-schema"} <= SURFACE_CLASSES


def test_statuses_are_deprecated_and_removed() -> None:
    assert {"deprecated", "removed"} == STATUSES
