from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_concept_authority_governance import (  # noqa: E402
    ADR_DIR_RELATIVE_PATH,
    CONCEPT_FAMILIES_RELATIVE_PATH,
    CONTROLLED_VOCABULARIES_RELATIVE_PATH,
    EXTENSION_DISCIPLINE_ADR_REF,
    GOVERNANCE_ADR_REF,
    REQUIREMENT_REFS,
    evaluate_concept_authority_governance,
    main,
)

# --------------------------------------------------------------------------- #
# Canonical, well-formed concept-authority catalogs used as the positive case #
# and the starting point for every mutation test. The families catalog mirrors #
# the real contracts/concept-authority/concept-families-v1.json shape (one     #
# adopted + one native family); the native family's relation_rules use the     #
# inline-code (backtick) token convention to reference a known family and a    #
# known controlled vocabulary, so the positive case exercises both resolution  #
# paths.                                                                       #
# --------------------------------------------------------------------------- #
_GOOD_FAMILIES: dict = {
    "schema_version": "concept-families/v1",
    "families": {
        "assets": {
            "title": "Assets",
            "description": "Nodes, infrastructure, networks, and deployable resources.",
            "provenance": "adopted",
            "authority": "UCO",
            "authority_reference": "https://github.com/ucoProject/UCO",
        },
        "episodes": {
            "title": "Episodes",
            "description": "Participant runtime episode identity and lifecycle state.",
            "provenance": "native",
            "extension_scope": "RAES participant runtime episode identity and lifecycle state.",
            "relation_rules": [
                "May relate to `assets` as the asset-bearing scenario node an episode runs on.",
                "May bind enumerated terms through the `sample-vocab` controlled vocabulary.",
            ],
            "non_ambiguity_constraints": [
                "Must not be used as a synonym for tasks, runs, or studies.",
            ],
        },
    },
}

_GOOD_VOCABULARIES: dict = {
    "schema_version": "controlled-vocabularies/v1",
    "vocabularies": {
        "sample-vocab": {
            "title": "Sample Vocabulary",
            "description": "A closed enumeration used only by the test fixture.",
            "kind": "enumeration",
            "governed_scopes": [],
            "extension_policy": "closed",
            "terms": {
                "alpha": {"title": "Alpha", "description": "The alpha term."},
            },
        },
    },
}

# A single ADR that mentions every fixture family id as a whole token. ADR
# linkage is governance proof: the gate is satisfied when a family id appears
# word-boundary in at least one ADR under docs/decisions/adrs/.
_GOOD_ADR = """# ADR-001: Concept Families

## Status
accepted

## Decision

The catalog governs the `assets` family and the `episodes` family.
"""


def _seed_repo(
    tmp_path: Path,
    *,
    families: dict | str | None = None,
    vocabularies: dict | str | None = None,
    adrs: dict[str, str] | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Seed a temp repo with concept-authority catalogs and ADR files.

    ``families`` / ``vocabularies`` accept a dict (serialized to JSON) or a raw
    string (to plant malformed JSON). ``adrs`` maps ADR file names to bodies;
    when omitted the canonical single ADR is written.
    """
    if families is None:
        families = _GOOD_FAMILIES
    if vocabularies is None:
        vocabularies = _GOOD_VOCABULARIES
    if adrs is None:
        adrs = {"adr-001-concept-families.md": _GOOD_ADR}

    if families is not None:
        families_path = tmp_path / CONCEPT_FAMILIES_RELATIVE_PATH
        families_path.parent.mkdir(parents=True, exist_ok=True)
        families_path.write_text(
            families if isinstance(families, str) else json.dumps(families, indent=2),
            encoding="utf-8",
        )

    if vocabularies is not None:
        vocab_path = tmp_path / CONTROLLED_VOCABULARIES_RELATIVE_PATH
        vocab_path.parent.mkdir(parents=True, exist_ok=True)
        vocab_path.write_text(
            vocabularies if isinstance(vocabularies, str) else json.dumps(vocabularies, indent=2),
            encoding="utf-8",
        )

    adr_dir = tmp_path / ADR_DIR_RELATIVE_PATH
    adr_dir.mkdir(parents=True, exist_ok=True)
    for name, body in adrs.items():
        (adr_dir / name).write_text(body, encoding="utf-8")

    if extra_files:
        for rel, body in extra_files.items():
            extra_path = tmp_path / rel
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_text(body, encoding="utf-8")

    return tmp_path


def _flagged(failures, marker: str) -> bool:
    needle = marker.lower()
    return any(f.rule_id == marker or needle in f.render().lower() for f in failures)


# --------------------------------------------------------------------------- #
# Module-level invariants.                                                     #
# --------------------------------------------------------------------------- #


def test_requirement_refs_include_gov_918() -> None:
    assert "GOV-918" in REQUIREMENT_REFS


def test_governance_adr_ref_is_adr_062() -> None:
    assert GOVERNANCE_ADR_REF == "ADR-062"


def test_extension_discipline_adr_ref_is_adr_012() -> None:
    assert EXTENSION_DISCIPLINE_ADR_REF == "ADR-012"


# --------------------------------------------------------------------------- #
# Positive case.                                                              #
# --------------------------------------------------------------------------- #


def test_good_catalog_has_no_failures(tmp_path: Path) -> None:
    assert evaluate_concept_authority_governance(_seed_repo(tmp_path)) == []


# --------------------------------------------------------------------------- #
# Check 1 -- family ADR linkage.                                              #
# --------------------------------------------------------------------------- #


def test_family_absent_from_all_adrs_is_flagged(tmp_path: Path) -> None:
    # The ADR mentions only `assets`; `episodes` is unlinked.
    adr = "# ADR-001\n\n## Decision\n\nThe catalog governs the `assets` family.\n"
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, adrs={"adr-001.md": adr}))
    assert _flagged(failures, "concept-authority-family-adr-missing")
    assert any("episodes" in f.message for f in failures)


def test_substring_adr_mention_does_not_satisfy_linkage(tmp_path: Path) -> None:
    # `subepisodes` must not satisfy the `episodes` family id (word-boundary).
    adr = "# ADR-001\n\n## Decision\n\nGoverns `assets` and subepisodes handling.\n"
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, adrs={"adr-001.md": adr}))
    assert _flagged(failures, "concept-authority-family-adr-missing")
    assert any("episodes" in f.message for f in failures)


def test_hyphen_delimited_superset_does_not_satisfy_linkage(tmp_path: Path) -> None:
    # A hyphen-delimited superset like `pre-episodes-handling` must not satisfy
    # the `episodes` family id: concept ids use `-` as an identifier character,
    # so the boundary excludes `-` and the id matches only as a complete token.
    adr = "# ADR-001\n\n## Decision\n\nGoverns `assets` and pre-episodes-handling.\n"
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, adrs={"adr-001.md": adr}))
    assert _flagged(failures, "concept-authority-family-adr-missing")
    assert any("episodes" in f.message for f in failures)


def test_readme_in_adr_dir_does_not_count_as_adr(tmp_path: Path) -> None:
    # A README under the ADR dir is not an ADR file; it must not satisfy linkage.
    seeded = _seed_repo(
        tmp_path,
        adrs={"adr-001.md": "# ADR-001\n\n## Decision\n\nGoverns `assets`.\n"},
        extra_files={f"{ADR_DIR_RELATIVE_PATH}/README.md": "Mentions `episodes` here.\n"},
    )
    failures = evaluate_concept_authority_governance(seeded)
    assert _flagged(failures, "concept-authority-family-adr-missing")
    assert any("episodes" in f.message for f in failures)


def test_missing_adr_dir_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path)
    for child in (seeded / ADR_DIR_RELATIVE_PATH).iterdir():
        child.unlink()
    (seeded / ADR_DIR_RELATIVE_PATH).rmdir()
    failures = evaluate_concept_authority_governance(seeded)
    assert _flagged(failures, "concept-authority-adr-dir-missing")


# --------------------------------------------------------------------------- #
# Check 2 -- relation/vocabulary reference resolution (explicit-token only).  #
# --------------------------------------------------------------------------- #


def test_relation_rule_unknown_family_reference_is_flagged(tmp_path: Path) -> None:
    families = json.loads(json.dumps(_GOOD_FAMILIES))
    families["families"]["episodes"]["relation_rules"][0] = "May relate to `ghost-family` nodes."
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, families=families))
    assert _flagged(failures, "concept-authority-dangling-reference")
    assert any("ghost-family" in f.message for f in failures)


def test_relation_rule_unknown_vocabulary_like_reference_is_flagged(tmp_path: Path) -> None:
    families = json.loads(json.dumps(_GOOD_FAMILIES))
    families["families"]["episodes"]["relation_rules"][1] = "Bind through the `made-up-vocab` vocabulary."
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, families=families))
    assert _flagged(failures, "concept-authority-dangling-reference")
    assert any("made-up-vocab" in f.message for f in failures)


def test_known_vocabulary_reference_resolves(tmp_path: Path) -> None:
    # `sample-vocab` is a known controlled vocabulary id -> no dangling failure.
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path))
    assert not _flagged(failures, "concept-authority-dangling-reference")


def test_non_id_inline_code_token_is_ignored(tmp_path: Path) -> None:
    # Backtick tokens that are not concept-family-id shaped (caps, underscores,
    # dotted paths) are not references and must not be validated.
    families = json.loads(json.dumps(_GOOD_FAMILIES))
    families["families"]["episodes"]["relation_rules"][0] = (
        "Bound via `concept_bindings` on `RuntimeConfiguration` at `nodes.*.runtime`."
    )
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, families=families))
    assert not _flagged(failures, "concept-authority-dangling-reference")


def test_bare_prose_family_like_word_is_not_validated(tmp_path: Path) -> None:
    # Without inline-code delimiters, a family-id-shaped word is prose, not a
    # reference: no natural-language inference.
    families = json.loads(json.dumps(_GOOD_FAMILIES))
    families["families"]["episodes"]["relation_rules"][0] = "May relate to ghost-family nodes."
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, families=families))
    assert not _flagged(failures, "concept-authority-dangling-reference")


# --------------------------------------------------------------------------- #
# Catalog load failures.                                                      #
# --------------------------------------------------------------------------- #


def test_missing_families_catalog_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path)
    (seeded / CONCEPT_FAMILIES_RELATIVE_PATH).unlink()
    failures = evaluate_concept_authority_governance(seeded)
    assert _flagged(failures, "concept-authority-families-catalog-missing")


def test_invalid_families_catalog_is_flagged(tmp_path: Path) -> None:
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, families="{ not valid json"))
    assert _flagged(failures, "concept-authority-families-catalog-invalid")


def test_schema_invalid_families_catalog_is_flagged(tmp_path: Path) -> None:
    # A native family missing its required relation_rules fails model validation.
    families = json.loads(json.dumps(_GOOD_FAMILIES))
    del families["families"]["episodes"]["relation_rules"]
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, families=families))
    assert _flagged(failures, "concept-authority-families-catalog-invalid")


def test_missing_vocabularies_catalog_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path)
    (seeded / CONTROLLED_VOCABULARIES_RELATIVE_PATH).unlink()
    failures = evaluate_concept_authority_governance(seeded)
    assert _flagged(failures, "concept-authority-vocabularies-catalog-missing")


def test_invalid_vocabularies_catalog_is_flagged(tmp_path: Path) -> None:
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, vocabularies="{ not valid json"))
    assert _flagged(failures, "concept-authority-vocabularies-catalog-invalid")


def test_schema_invalid_vocabularies_catalog_is_flagged(tmp_path: Path) -> None:
    # A vocabulary missing its required `kind` field fails model validation.
    vocabularies = json.loads(json.dumps(_GOOD_VOCABULARIES))
    del vocabularies["vocabularies"]["sample-vocab"]["kind"]
    failures = evaluate_concept_authority_governance(_seed_repo(tmp_path, vocabularies=vocabularies))
    assert _flagged(failures, "concept-authority-vocabularies-catalog-invalid")


# --------------------------------------------------------------------------- #
# CLI surface -- --json output and exception waiver.                          #
# --------------------------------------------------------------------------- #


def test_main_json_output_lists_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded = _seed_repo(tmp_path, adrs={"adr-001.md": "Governs `assets` only.\n"})
    exit_code = main(["--repo-root", str(seeded), "--json"])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert any(item["rule_id"] == "concept-authority-family-adr-missing" for item in payload)


def test_exception_waiver_suppresses_failure(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path, adrs={"adr-001.md": "Governs `assets` only.\n"})
    exceptions = 'exceptions:\n  - rule_id: concept-authority-family-adr-missing\n    reason: "test waiver"\n'
    (seeded / "tools" / "policy").mkdir(parents=True, exist_ok=True)
    (seeded / "tools" / "policy" / "exceptions.yaml").write_text(exceptions, encoding="utf-8")
    assert main(["--repo-root", str(seeded)]) == 0


def test_main_passes_on_good_catalog(tmp_path: Path) -> None:
    assert main(["--repo-root", str(_seed_repo(tmp_path))]) == 0


def test_main_reports_a_malformed_waiver_date_as_a_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded = _seed_repo(tmp_path, adrs={"adr-001.md": "Governs `assets` only.\n"})
    exceptions = "exceptions:\n  - rule_id: concept-authority-family-adr-missing\n    expires_at: not-a-date\n"
    (seeded / "tools" / "policy").mkdir(parents=True, exist_ok=True)
    (seeded / "tools" / "policy" / "exceptions.yaml").write_text(exceptions, encoding="utf-8")

    assert main(["--repo-root", str(seeded)]) == 1
    assert "concept-authority-governance: policy exception expires_at must be an ISO date" in capsys.readouterr().err
