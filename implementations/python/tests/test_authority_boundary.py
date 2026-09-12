from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_authority_boundary import (  # noqa: E402
    _REQUIRED_ARTIFACT_FAMILY_FIELDS,
    _REQUIRED_AUTHORITY_ROOT_FIELDS,
    _REQUIRED_NON_NORMATIVE_ROOT_FIELDS,
    _REQUIRED_SCHEMA_AUTHORITY_FIELDS,
    ADR_AUTHORITY_RELATIVE_PATH,
    ADR_REFS,
    ADR_SEAM_REF,
    ADR_SOURCE_REF,
    AUTHORITY_BOUNDARY_RELATIVE_PATH,
    CANONICAL_ARTIFACT_FAMILY_BINDING,
    CANONICAL_AUTHORITY_ROOT_IDS,
    CANONICAL_LEGACY_TOP_LEVEL_DIRS,
    CANONICAL_NON_NORMATIVE_ROOT_IDS,
    CONTRACTS_README_RELATIVE_PATH,
    POLICY_VALUE,
    REQUIREMENT_REF,
    SPECS_README_RELATIVE_PATH,
    evaluate_authority_boundary,
)


def _policy_without_entry_field(section: str, index: int, field: str) -> str:
    """Return `_GOOD_POLICY` with one field deleted from a list entry.

    Parses the canonical YAML, drops `section[index][field]`, and re-dumps.
    Used to exercise every field of a `_REQUIRED_*_FIELDS` tuple (rather than a
    single hand-picked field) so dropping a field from the tuple in production
    leaves a failing test.
    """
    data = yaml.safe_load(_GOOD_POLICY)
    del data[section][index][field]
    return yaml.safe_dump(data, sort_keys=False)


def _policy_without_schema_authority_field(field: str) -> str:
    data = yaml.safe_load(_GOOD_POLICY)
    del data["schema_authority"][field]
    return yaml.safe_dump(data, sort_keys=False)


# --------------------------------------------------------------------------- #
# Canonical, well-formed authority-boundary YAML used as the positive case    #
# and as the starting point for every mutation test. Mirrors the real         #
# specs/authority/authority-boundary.yaml shape; descriptive prose is trimmed #
# so the test fixture stays auditable.                                        #
# --------------------------------------------------------------------------- #
_GOOD_POLICY = """policy: normative-artifact-authority
requirement_refs:
  - ASR-517
adr_refs:
  - ADR-009
  - ADR-019
authority_roots:
  - id: normative_prose
    root: specs/
    authority: normative prose specifications
    family: prose
  - id: normative_schemas
    root: contracts/schemas/
    authority: published JSON Schemas
    family: schemas
  - id: normative_fixtures
    root: contracts/fixtures/
    authority: conformance fixtures
    family: fixtures
  - id: normative_profiles
    root: contracts/profiles/
    authority: capability profile declarations
    family: profiles
  - id: normative_realization_envelopes
    root: contracts/realization-envelopes/
    authority: configuration-bound backend realization envelope declarations
    family: realization-envelopes
  - id: normative_concept_authority
    root: contracts/concept-authority/
    authority: concept-family and controlled-vocabulary authority artifacts
    family: concept-authority
  - id: normative_provenance
    root: contracts/provenance/
    authority: revision-pinned lineage and derivation records
    family: provenance
non_normative_roots:
  - id: reference_implementations
    root: implementations/
    note: reference code only
  - id: explanatory_docs
    root: docs/
    note: explanatory material
  - id: worked_examples
    root: examples/
    note: non-normative worked examples
  - id: research_notes
    root: research/
    note: non-normative research material
  - id: process_notes
    root: notes/
    note: non-normative process notes
  - id: tooling
    root: tools/
    note: tooling
legacy_top_level_dirs:
  - schemas
  - conformance
  - src
schema_authority:
  normative_root: contracts/schemas/
  publication_manifest: contracts/schema-publication-manifest.json
  forbidden_authority_roots:
    - implementations/
  forbidden_schema_filename_suffixes:
    - .schema.json
normative_artifact_families:
  - id: agent_guidance_profile
    artifact: specs/agent-guidance/agent-guidance.yaml
    authority: agent-usable governance-guidance profile
    family: governance-guidance
    requirement_refs:
      - AUT-811
  - id: deprecation_records
    artifact: specs/evolution/deprecation-records.yaml
    authority: ecosystem deprecation and lifecycle records
    family: deprecation-records
    requirement_refs:
      - GOV-902
"""

# ADR-009 is immutable; the drift guard requires every authority-root token
# (specs/, contracts/schemas/, contracts/fixtures/, contracts/profiles/,
# contracts/realization-envelopes/, contracts/concept-authority/,
# contracts/provenance/) to appear
# across the immutable ADR pair. ADR-019 is the
# canonical-seam decision — required by adr_refs and by the drift guard.
_GOOD_ADR_AUTHORITY = """# ADR-009: Normative Artifact Authority and Repository Structure

## Status
accepted

## Decision

The authoritative ecosystem artifacts are normative prose under specs/,
published JSON Schemas under contracts/schemas/, conformance fixtures under
contracts/fixtures/, capability profiles under contracts/profiles/, and
concept-authority artifacts under contracts/concept-authority/.
Reference implementations consume them; they do not define them.
"""

_GOOD_CONTRACTS_README = """# Contracts

Machine-readable contracts. See
[specs/authority/authority-boundary.yaml](../specs/authority/authority-boundary.yaml)
for the canonical authority manifest, governed by
[ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md).
"""

_GOOD_SPECS_README = """# Specs

Normative prose lives here. See
[authority/authority-boundary.yaml](authority/authority-boundary.yaml) for the
canonical authority manifest, governed by
[ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md).
"""

# Every declared root in `_GOOD_POLICY` — both authority and non-normative
# — must exist on disk with a real artifact, or `evaluate_authority_boundary`
# fires `authority-boundary-root-missing` / `authority-boundary-root-empty`.
# The seed materialises this canonical set.
_GOOD_AUTHORITY_ROOTS: tuple[str, ...] = (
    "specs",
    "contracts/schemas",
    "contracts/fixtures",
    "contracts/profiles",
    "contracts/realization-envelopes",
    "contracts/concept-authority",
    "contracts/provenance",
)
_GOOD_NON_NORMATIVE_ROOTS: tuple[str, ...] = (
    "implementations",
    "docs",
    "examples",
    "research",
    "notes",
    "tools",
)


def _materialise_root(tmp_path: Path, relative: str) -> Path:
    """Create ``relative`` under ``tmp_path`` with a real placeholder file.

    A `.keep` file alone does not satisfy `_dir_has_content` — the gate
    treats `.keep` as a placeholder marker — so the seed writes a real
    `placeholder.md` artifact next to it.
    """
    directory = tmp_path / relative
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "placeholder.md").write_text("seed placeholder", encoding="utf-8")
    return directory


def _seed_repo(
    tmp_path: Path,
    *,
    policy_body: str | None = _GOOD_POLICY,
    adr_body: str | None = _GOOD_ADR_AUTHORITY,
    seam_body: str | None = "ADR-019 stub mentioning concept-authority, realization-envelopes, and provenance.\n",
    contracts_readme: str | None = _GOOD_CONTRACTS_README,
    specs_readme: str | None = _GOOD_SPECS_README,
    authority_roots: tuple[str, ...] = _GOOD_AUTHORITY_ROOTS,
    non_normative_roots: tuple[str, ...] = _GOOD_NON_NORMATIVE_ROOTS,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Seed a temp repo with the canonical authority artifacts.

    ``extra_files`` lets a defect test plant an additional file (e.g. a
    published schema in the wrong root) without rewriting the seed.
    """
    if policy_body is not None:
        policy_path = tmp_path / AUTHORITY_BOUNDARY_RELATIVE_PATH
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(policy_body, encoding="utf-8")

    if adr_body is not None:
        adr_path = tmp_path / ADR_AUTHORITY_RELATIVE_PATH
        adr_path.parent.mkdir(parents=True, exist_ok=True)
        adr_path.write_text(adr_body, encoding="utf-8")

    if seam_body is not None:
        # ADR-019 governs the manifest YAML; the drift guard unions it with
        # ADR-009. The seed writes a stub that mentions `concept-authority`
        # and `realization-envelopes` so the canonical positive case clears
        # the drift check.
        seam_relative = "docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md"
        seam_path = tmp_path / seam_relative
        seam_path.parent.mkdir(parents=True, exist_ok=True)
        seam_path.write_text(seam_body, encoding="utf-8")

    if contracts_readme is not None:
        contracts_path = tmp_path / CONTRACTS_README_RELATIVE_PATH
        contracts_path.parent.mkdir(parents=True, exist_ok=True)
        contracts_path.write_text(contracts_readme, encoding="utf-8")

    if specs_readme is not None:
        specs_path = tmp_path / SPECS_README_RELATIVE_PATH
        specs_path.parent.mkdir(parents=True, exist_ok=True)
        specs_path.write_text(specs_readme, encoding="utf-8")

    # The canonical `normative_artifact_families` entry in `_GOOD_POLICY`
    # classifies specs/agent-guidance/agent-guidance.yaml, and the gate
    # requires that artifact to exist on disk. Seed a minimal real file so the
    # positive case clears the artifact-family existence check.
    guidance_path = tmp_path / "specs" / "agent-guidance" / "agent-guidance.yaml"
    guidance_path.parent.mkdir(parents=True, exist_ok=True)
    if not guidance_path.exists():
        guidance_path.write_text("profile: raes-agent-guidance\n", encoding="utf-8")

    # The canonical deprecation-records ledger (GOV-902) is likewise classified
    # in _GOOD_POLICY and must exist on disk for the positive case.
    deprecation_path = tmp_path / "specs" / "evolution" / "deprecation-records.yaml"
    deprecation_path.parent.mkdir(parents=True, exist_ok=True)
    if not deprecation_path.exists():
        deprecation_path.write_text("policy: ecosystem-deprecation-records\n", encoding="utf-8")

    for root in authority_roots:
        _materialise_root(tmp_path, root)
    for root in non_normative_roots:
        _materialise_root(tmp_path, root)

    # Seed the canonical schema-publication-manifest path so the
    # schema_authority block reads a real file.
    manifest_path = tmp_path / "contracts" / "schema-publication-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if not manifest_path.exists():
        manifest_path.write_text("{}\n", encoding="utf-8")

    if extra_files:
        for rel, body in extra_files.items():
            extra_path = tmp_path / rel
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_text(body, encoding="utf-8")

    return tmp_path


def _flagged(failures, marker: str) -> bool:
    """Return True if some failure matches ``marker`` by rule id or rendered substring."""
    needle = marker.lower()
    return any(f.rule_id == marker or needle in f.render().lower() for f in failures)


# --------------------------------------------------------------------------- #
# Positive case -- the canonical YAML against canonical docs is clean.        #
# --------------------------------------------------------------------------- #


def test_good_policy_has_no_failures(tmp_path: Path) -> None:
    failures = evaluate_authority_boundary(_seed_repo(tmp_path))
    assert failures == []


# --------------------------------------------------------------------------- #
# Module-level invariants -- the validator pins ASR-517, ADR-009, ADR-019,    #
# the policy literal, and the canonical root-id set against drift in the      #
# Python module itself.                                                       #
# --------------------------------------------------------------------------- #


def test_requirement_ref_is_asr_517() -> None:
    assert REQUIREMENT_REF == "ASR-517"


def test_adr_source_ref_is_adr_009() -> None:
    assert ADR_SOURCE_REF == "ADR-009"


def test_adr_seam_ref_is_adr_019() -> None:
    assert ADR_SEAM_REF == "ADR-019"


def test_adr_refs_include_both_adr_009_and_adr_019() -> None:
    assert "ADR-009" in ADR_REFS
    assert "ADR-019" in ADR_REFS


def test_policy_value_is_normative_artifact_authority() -> None:
    assert POLICY_VALUE == "normative-artifact-authority"


def test_canonical_authority_root_ids_cover_every_family() -> None:
    # ADR-009 and ADR-019 name these authority families. A YAML that drops any
    # of them fails the gate.
    assert set(CANONICAL_AUTHORITY_ROOT_IDS) == {
        "normative_prose",
        "normative_schemas",
        "normative_fixtures",
        "normative_profiles",
        "normative_realization_envelopes",
        "normative_concept_authority",
        "normative_provenance",
    }


def test_canonical_legacy_top_level_dirs_match_adr_009() -> None:
    # ADR-009 names schemas/, conformance/, src/ as transitional. The gate
    # fails if any reappears at the repo root.
    assert set(CANONICAL_LEGACY_TOP_LEVEL_DIRS) == {"schemas", "conformance", "src"}


def test_canonical_non_normative_root_ids_include_implementations(tmp_path: Path) -> None:
    # The whole point of the boundary is that implementations/ is non-normative.
    assert "reference_implementations" in CANONICAL_NON_NORMATIVE_ROOT_IDS


# --------------------------------------------------------------------------- #
# YAML missing, unparseable, wrong root shape.                                #
# --------------------------------------------------------------------------- #


def test_missing_policy_file_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path)
    (seeded / AUTHORITY_BOUNDARY_RELATIVE_PATH).unlink()
    failures = evaluate_authority_boundary(seeded)
    assert _flagged(failures, "authority-boundary-missing")


def test_unparseable_policy_file_is_flagged(tmp_path: Path) -> None:
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body="this: is: : invalid"))
    assert _flagged(failures, "authority-boundary-parse")


def test_policy_root_must_be_mapping(tmp_path: Path) -> None:
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body="- just\n- a\n- list\n"))
    assert _flagged(failures, "authority-boundary-shape")


# --------------------------------------------------------------------------- #
# Required top-level fields + the policy literal.                             #
# --------------------------------------------------------------------------- #


_SCHEMA_AUTHORITY_BLOCK = (
    "schema_authority:\n"
    "  normative_root: contracts/schemas/\n"
    "  publication_manifest: contracts/schema-publication-manifest.json\n"
    "  forbidden_authority_roots:\n"
    "    - implementations/\n"
    "  forbidden_schema_filename_suffixes:\n"
    "    - .schema.json\n"
)

_TOP_LEVEL_FIELD_CASES = [
    ("policy", "policy: normative-artifact-authority\n"),
    ("requirement_refs", "requirement_refs:\n  - ASR-517\n"),
    ("adr_refs", "adr_refs:\n  - ADR-009\n  - ADR-019\n"),
    ("authority_roots", "authority_roots:\n"),
    ("non_normative_roots", "non_normative_roots:\n"),
    ("legacy_top_level_dirs", "legacy_top_level_dirs:\n"),
    # schema_authority's value spans multiple indented lines; the test must
    # remove the entire block, not just the heading, to avoid an orphaned
    # mapping that fails YAML parsing instead of the field-missing check.
    ("schema_authority", _SCHEMA_AUTHORITY_BLOCK),
    (
        "normative_artifact_families",
        (
            "normative_artifact_families:\n"
            "  - id: agent_guidance_profile\n"
            "    artifact: specs/agent-guidance/agent-guidance.yaml\n"
            "    authority: agent-usable governance-guidance profile\n"
            "    family: governance-guidance\n"
            "    requirement_refs:\n"
            "      - AUT-811\n"
            "  - id: deprecation_records\n"
            "    artifact: specs/evolution/deprecation-records.yaml\n"
            "    authority: ecosystem deprecation and lifecycle records\n"
            "    family: deprecation-records\n"
            "    requirement_refs:\n"
            "      - GOV-902\n"
        ),
    ),
]


@pytest.mark.parametrize(
    ("field", "needle"),
    _TOP_LEVEL_FIELD_CASES,
    ids=[case[0] for case in _TOP_LEVEL_FIELD_CASES],
)
def test_missing_top_level_field_is_flagged(tmp_path: Path, field: str, needle: str) -> None:
    body = _GOOD_POLICY.replace(needle, "", 1)
    assert body != _GOOD_POLICY, f"setup error for field {field}: needle not found in _GOOD_POLICY"
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    # Exact rule_id match — the loose substring helper would let
    # `authority-boundary-field-type` masquerade as `authority-boundary-field`
    # because the former contains the latter as a literal substring.
    assert any(f.rule_id == "authority-boundary-field" for f in failures), (
        f"expected an exact 'authority-boundary-field' rule id; got: {[(f.rule_id, f.message) for f in failures]}"
    )
    assert any(field in failure.message for failure in failures), (
        f"expected a failure naming field {field!r}; got: {[failure.render() for failure in failures]}"
    )


def test_policy_value_must_match_canonical(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "policy: normative-artifact-authority\n",
        "policy: something-else\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-value")


def test_requirement_refs_missing_asr_517_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "requirement_refs:\n  - ASR-517\n",
        "requirement_refs:\n  - ASR-999\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-requirement-ref")


def test_adr_refs_missing_adr_009_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "adr_refs:\n  - ADR-009\n  - ADR-019\n",
        "adr_refs:\n  - ADR-019\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-adr-ref")
    assert any("ADR-009" in failure.message for failure in failures), (
        f"expected a failure naming ADR-009; got: {[failure.render() for failure in failures]}"
    )


def test_adr_refs_missing_adr_019_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "adr_refs:\n  - ADR-009\n  - ADR-019\n",
        "adr_refs:\n  - ADR-009\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-adr-ref")
    assert any("ADR-019" in failure.message for failure in failures), (
        f"expected a failure naming ADR-019; got: {[failure.render() for failure in failures]}"
    )


# --------------------------------------------------------------------------- #
# Sequence-field type strictness -- non-list values are rejected, not coerced.#
# --------------------------------------------------------------------------- #


def test_authority_roots_non_list_value_is_rejected(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace("authority_roots:\n", "authority_roots: oops\n", 1)
    # Strip the original block contents so the YAML still parses cleanly.
    lines = body.splitlines(keepends=True)
    kept: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("authority_roots:"):
            kept.append(line)
            skipping = True
            continue
        if skipping and (line.startswith(" ") or line.startswith("\t") or line.startswith("-")):
            continue
        skipping = False
        kept.append(line)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body="".join(kept)))
    assert _flagged(failures, "authority-boundary-field-type")


def test_legacy_top_level_dirs_non_list_value_is_rejected(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "legacy_top_level_dirs:\n  - schemas\n  - conformance\n  - src\n",
        "legacy_top_level_dirs: schemas\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-field-type")


@pytest.mark.parametrize("field", _REQUIRED_AUTHORITY_ROOT_FIELDS)
def test_authority_root_required_fields_are_rejected(tmp_path: Path, field: str) -> None:
    # An authority_roots entry missing ANY required field is a malformation, not
    # a default. Parametrised over the full tuple so dropping a field from
    # _REQUIRED_AUTHORITY_ROOT_FIELDS in production leaves a failing test.
    body = _policy_without_entry_field("authority_roots", 0, field)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert any(
        f.rule_id == "authority-boundary-entry-field" and f"required field: {field}" in f.message for f in failures
    ), f"expected an entry-field failure naming {field!r}; got: {[f.render() for f in failures]}"


def test_authority_root_must_end_with_slash(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "    root: contracts/schemas/\n",
        "    root: contracts/schemas\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-root-shape")


def test_authority_root_must_be_repo_relative(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "    root: contracts/schemas/\n",
        "    root: /abs/contracts/schemas/\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-root-shape")


def test_authority_root_must_not_traverse_parent(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "    root: contracts/schemas/\n",
        "    root: ../escape/\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-root-shape")


# --------------------------------------------------------------------------- #
# Canonical family coverage -- every governed family MUST have an entry.      #
# entry. Reordering or renaming an id is a drift.                             #
# --------------------------------------------------------------------------- #


def test_missing_canonical_authority_root_is_flagged(tmp_path: Path) -> None:
    # Drop the entire `normative_fixtures` entry.
    body = _GOOD_POLICY.replace(
        "  - id: normative_fixtures\n"
        "    root: contracts/fixtures/\n"
        "    authority: conformance fixtures\n"
        "    family: fixtures\n",
        "",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-canonical-root-missing")
    assert any("normative_fixtures" in failure.message for failure in failures), (
        f"expected normative_fixtures to be named; got: {[failure.render() for failure in failures]}"
    )


def test_duplicate_authority_root_id_is_flagged(tmp_path: Path) -> None:
    # Duplicate the `normative_prose` id under a different root.
    body = _GOOD_POLICY.replace(
        "  - id: normative_schemas\n"
        "    root: contracts/schemas/\n"
        "    authority: published JSON Schemas\n"
        "    family: schemas\n",
        "  - id: normative_prose\n    root: contracts/schemas/\n    authority: duplicate id\n    family: schemas\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-entry-duplicate")


def test_duplicate_authority_root_path_is_flagged(tmp_path: Path) -> None:
    # Reuse contracts/schemas/ under a different id.
    body = _GOOD_POLICY.replace(
        "  - id: normative_profiles\n"
        "    root: contracts/profiles/\n"
        "    authority: capability profile declarations\n"
        "    family: profiles\n",
        "  - id: shadow_profiles\n    root: contracts/schemas/\n    authority: shadow\n    family: profiles\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-entry-duplicate")


# --------------------------------------------------------------------------- #
# Filesystem invariants.                                                      #
# --------------------------------------------------------------------------- #


def _rmtree(path: Path) -> None:
    """Recursively remove ``path`` (handles non-empty directories)."""
    if path.is_file() or path.is_symlink():
        path.unlink()
        return
    for child in path.iterdir():
        _rmtree(child)
    path.rmdir()


def test_authority_root_missing_on_disk_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path)
    _rmtree(seeded / "contracts" / "profiles")
    failures = evaluate_authority_boundary(seeded)
    assert _flagged(failures, "authority-boundary-root-missing")
    assert any("contracts/profiles" in failure.render() for failure in failures), (
        f"expected the missing path to be named; got: {[failure.render() for failure in failures]}"
    )


def test_non_normative_root_missing_on_disk_is_allowed(tmp_path: Path) -> None:
    # Non-normative roots are classified but not required to exist on disk.
    # `research/` and `notes/` are gitignored in this repo, so requiring
    # existence would fail CI (where they aren't checked out) while passing
    # local dev. Deleting one must NOT fire `authority-boundary-root-missing`.
    seeded = _seed_repo(tmp_path)
    _rmtree(seeded / "research")
    failures = evaluate_authority_boundary(seeded)
    assert not _flagged(failures, "authority-boundary-root-missing"), (
        f"non-normative roots must be allowed to be absent; got: {[f.render() for f in failures]}"
    )


def test_authority_root_with_only_keep_marker_is_flagged_as_empty(tmp_path: Path) -> None:
    # _dir_has_content treats `.keep` as a placeholder marker, not real
    # content. A root that contains only `.keep` should fire
    # `authority-boundary-root-empty`. Without this test, the .keep-exclusion
    # branch is dead code from the suite's perspective and removing/inverting
    # it would silently accept placeholder roots that contain no real
    # normative artifacts.
    seeded = _seed_repo(tmp_path)
    fixtures_dir = seeded / "contracts" / "fixtures"
    (fixtures_dir / "placeholder.md").unlink()
    (fixtures_dir / ".keep").write_text("", encoding="utf-8")
    failures = evaluate_authority_boundary(seeded)
    assert _flagged(failures, "authority-boundary-root-empty")
    assert any("contracts/fixtures" in failure.render() for failure in failures), (
        f"expected the empty root path to be named; got: {[failure.render() for failure in failures]}"
    )


@pytest.mark.parametrize("field", _REQUIRED_NON_NORMATIVE_ROOT_FIELDS)
def test_non_normative_root_required_fields_are_rejected(tmp_path: Path, field: str) -> None:
    # Symmetric full-tuple coverage for _check_non_normative_roots: every
    # required field of a non_normative_roots entry must be enforced.
    body = _policy_without_entry_field("non_normative_roots", 0, field)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert any(
        f.rule_id == "authority-boundary-entry-field" and f"required field: {field}" in f.message for f in failures
    ), f"expected an entry-field failure naming {field!r}; got: {[f.render() for f in failures]}"


def test_legacy_dir_present_at_root_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path)
    legacy = seeded / "schemas"
    legacy.mkdir()
    (legacy / "should-not-exist.json").write_text("{}", encoding="utf-8")
    failures = evaluate_authority_boundary(seeded)
    assert _flagged(failures, "authority-boundary-legacy-dir-present")
    assert any("schemas" in failure.render() for failure in failures), (
        f"expected 'schemas' to be named; got: {[failure.render() for failure in failures]}"
    )


def test_unclassified_top_level_dir_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path)
    rogue = seeded / "rogue_top_level"
    rogue.mkdir()
    (rogue / "data.txt").write_text("data", encoding="utf-8")
    failures = evaluate_authority_boundary(seeded)
    assert _flagged(failures, "authority-boundary-unclassified-top-level")
    assert any("rogue_top_level" in failure.render() for failure in failures), (
        f"expected 'rogue_top_level' to be named; got: {[failure.render() for failure in failures]}"
    )


def test_dotfiles_and_hidden_dirs_are_not_unclassified(tmp_path: Path) -> None:
    # Hidden directories (.codex, .github, .vscode, etc.) and dotfiles are
    # operational infrastructure, not authority artifacts; the gate must not
    # require them to be classified.
    seeded = _seed_repo(tmp_path)
    (seeded / ".github").mkdir()
    (seeded / ".github" / "workflows").mkdir()
    (seeded / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (seeded / ".codex").mkdir()
    failures = evaluate_authority_boundary(seeded)
    assert not _flagged(failures, "authority-boundary-unclassified-top-level"), (
        f"hidden dirs must not be flagged; got: {[failure.render() for failure in failures]}"
    )


def test_build_artifacts_are_not_unclassified(tmp_path: Path) -> None:
    # Operational build/cache artifacts (build/, dist/, node_modules/, venv/)
    # are git-ignored and never authority-bearing. They must not trip the gate
    # when they linger in a developer's checkout; CI's clean checkout never
    # sees them.
    seeded = _seed_repo(tmp_path)
    for artifact in ("build", "dist", "node_modules", "venv"):
        (seeded / artifact).mkdir()
        (seeded / artifact / "artifact.txt").write_text("x", encoding="utf-8")
    measurement = seeded / "build" / "gc-measurement"
    measurement.mkdir()
    (measurement / "attempt.marker").write_text("", encoding="utf-8")
    failures = evaluate_authority_boundary(seeded)
    assert not _flagged(failures, "authority-boundary-unclassified-top-level"), (
        f"build artifacts must not be flagged; got: {[failure.render() for failure in failures]}"
    )


def test_schema_outside_normative_root_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(
        tmp_path,
        extra_files={"implementations/python/packages/raes_processor/leaked.schema.json": "{}"},
    )
    failures = evaluate_authority_boundary(seeded)
    assert _flagged(failures, "authority-boundary-schema-misplaced")
    assert any("leaked.schema.json" in failure.render() for failure in failures), (
        f"expected the misplaced schema path to be named; got: {[failure.render() for failure in failures]}"
    )


def test_internal_tooling_schema_is_not_treated_as_published_contract(tmp_path: Path) -> None:
    seeded = _seed_repo(
        tmp_path,
        extra_files={"implementations/tooling/schemas/tool.schema.json": "{}"},
    )
    failures = evaluate_authority_boundary(seeded)
    assert not _flagged(failures, "authority-boundary-schema-misplaced"), (
        "internal tooling schemas must remain non-normative implementation data; "
        f"got: {[failure.render() for failure in failures]}"
    )


def test_schema_inside_normative_root_is_clean(tmp_path: Path) -> None:
    seeded = _seed_repo(
        tmp_path,
        extra_files={"contracts/schemas/example/v1/example.schema.json": "{}"},
    )
    failures = evaluate_authority_boundary(seeded)
    assert not _flagged(failures, "authority-boundary-schema-misplaced"), (
        f"published schemas inside contracts/schemas/ must pass; got: {[failure.render() for failure in failures]}"
    )


def test_schema_publication_manifest_missing_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path)
    (seeded / "contracts" / "schema-publication-manifest.json").unlink()
    failures = evaluate_authority_boundary(seeded)
    assert _flagged(failures, "authority-boundary-publication-manifest-missing")


# --------------------------------------------------------------------------- #
# Drift guards -- ADR-009 + contracts/README.md + specs/README.md.            #
# --------------------------------------------------------------------------- #


def test_adr_009_missing_family_token_is_flagged(tmp_path: Path) -> None:
    # The drift guard requires every authority family's token to appear in
    # the UNION of ADR-009 and ADR-019. A family stripped from both ADRs
    # fires `authority-boundary-adr-drift`.
    adr_body = _GOOD_ADR_AUTHORITY.replace("profiles", "REDACTED")
    failures = evaluate_authority_boundary(
        _seed_repo(tmp_path, adr_body=adr_body, seam_body="seam stub without the family token\n")
    )
    assert _flagged(failures, "authority-boundary-adr-drift")
    assert any("profiles" in failure.render() for failure in failures), (
        f"expected the missing 'profiles' family to be named; got: {[failure.render() for failure in failures]}"
    )


_ADR_009_WITHOUT_CONCEPT_AUTHORITY = """# ADR-009: Normative Artifact Authority and Repository Structure

## Status
accepted

## Decision

The authoritative ecosystem artifacts are normative prose under specs/,
published JSON Schemas under contracts/schemas/, conformance fixtures under
contracts/fixtures/, and capability profiles under contracts/profiles/.
Reference implementations consume them; they do not define them.
"""


def test_adr_drift_passes_when_only_one_of_two_adrs_mentions_family(tmp_path: Path) -> None:
    # The historic ADR-009 (immutable) names `prose`/`schemas`/`fixtures`/
    # `profiles` but does NOT mention `concept-authority` — that family was
    # introduced by ADR-012 and is named verbatim in ADR-019. The union
    # check must accept the family because ADR-019 covers it.
    adr_body = _ADR_009_WITHOUT_CONCEPT_AUTHORITY
    seam_body = "ADR-019: the canonical-seam decision mentions concept-authority explicitly.\n"
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, adr_body=adr_body, seam_body=seam_body))
    # `concept-authority` family must NOT trigger drift; other families MAY
    # still pass cleanly. Specifically: no drift failure for the
    # concept-authority family id should appear.
    drift_for_concept_authority = [
        f for f in failures if f.rule_id == "authority-boundary-adr-drift" and "concept-authority" in f.message
    ]
    assert drift_for_concept_authority == [], (
        f"expected concept-authority family to be covered by ADR-019; got: "
        f"{[f.render() for f in drift_for_concept_authority]}"
    )


def test_adr_drift_fires_when_only_adr_009_silences_a_family_and_seam_is_also_silent(tmp_path: Path) -> None:
    # Same ADR-009 body that omits `concept-authority`, but ADR-019 also
    # omits it. The union check then has no coverage for the family and
    # MUST fire `authority-boundary-adr-drift`.
    adr_body = _ADR_009_WITHOUT_CONCEPT_AUTHORITY
    seam_body = "ADR-019 stub that does not mention the concept family token.\n"
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, adr_body=adr_body, seam_body=seam_body))
    drift_for_concept_authority = [
        f for f in failures if f.rule_id == "authority-boundary-adr-drift" and "concept-authority" in f.message
    ]
    assert drift_for_concept_authority, (
        f"expected concept-authority drift when neither ADR covers it; got: {[f.render() for f in failures]}"
    )


def test_adr_009_missing_file_is_flagged(tmp_path: Path) -> None:
    seeded = _seed_repo(tmp_path, adr_body=None)
    failures = evaluate_authority_boundary(seeded)
    assert _flagged(failures, "authority-boundary-adr-missing")


def test_contracts_readme_missing_yaml_reference_is_flagged(tmp_path: Path) -> None:
    contracts_readme = "# Contracts\n\nMachine-readable contracts.\n"
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, contracts_readme=contracts_readme))
    assert _flagged(failures, "authority-boundary-contracts-readme-drift")


def test_specs_readme_missing_yaml_reference_is_flagged(tmp_path: Path) -> None:
    specs_readme = "# Specs\n\nNormative prose lives here.\n"
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, specs_readme=specs_readme))
    assert _flagged(failures, "authority-boundary-specs-readme-drift")


def test_contracts_readme_missing_file_is_flagged(tmp_path: Path) -> None:
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, contracts_readme=None))
    assert _flagged(failures, "authority-boundary-contracts-readme-missing")


def test_specs_readme_missing_file_is_flagged(tmp_path: Path) -> None:
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, specs_readme=None))
    assert _flagged(failures, "authority-boundary-specs-readme-missing")


def test_contracts_readme_missing_adr_019_reference_is_flagged(tmp_path: Path) -> None:
    contracts_readme = (
        "# Contracts\n\nSee [specs/authority/authority-boundary.yaml]"
        "(../specs/authority/authority-boundary.yaml) for the canonical manifest.\n"
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, contracts_readme=contracts_readme))
    assert _flagged(failures, "authority-boundary-contracts-readme-drift")
    assert any("ADR-019" in failure.message for failure in failures), (
        f"expected ADR-019 to be named; got: {[failure.render() for failure in failures]}"
    )


# --------------------------------------------------------------------------- #
# schema_authority block invariants.                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", _REQUIRED_SCHEMA_AUTHORITY_FIELDS)
def test_schema_authority_required_subfields_are_rejected(tmp_path: Path, field: str) -> None:
    # Dropping any required sub-field from an otherwise-present schema_authority
    # block must fail — the whole-block-absence case (_TOP_LEVEL_FIELD_CASES)
    # does not cover per-sub-field requiredness.
    body = _policy_without_schema_authority_field(field)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert any(
        f.rule_id == "authority-boundary-entry-field" and f"required field: {field}" in f.message for f in failures
    ), f"expected a schema_authority entry-field failure naming {field!r}; got: {[f.render() for f in failures]}"


def test_schema_authority_normative_root_must_match_authority_root(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  normative_root: contracts/schemas/\n",
        "  normative_root: implementations/python/schemas/\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-schema-authority-mismatch")


def test_schema_authority_forbidden_roots_must_include_implementations(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  forbidden_authority_roots:\n    - implementations/\n",
        "  forbidden_authority_roots:\n    - examples/\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-schema-authority-forbidden-roots")


def test_schema_authority_normative_root_non_string_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  normative_root: contracts/schemas/\n",
        "  normative_root:\n    - contracts/schemas/\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-field-type")


def test_schema_authority_publication_manifest_non_string_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  publication_manifest: contracts/schema-publication-manifest.json\n",
        "  publication_manifest: 42\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-field-type")


def test_schema_authority_forbidden_root_with_bad_path_shape_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  forbidden_authority_roots:\n    - implementations/\n",
        "  forbidden_authority_roots:\n    - implementations/\n    - /abs/escape\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-root-shape")


def test_schema_authority_suffix_must_start_with_dot(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  forbidden_schema_filename_suffixes:\n    - .schema.json\n",
        "  forbidden_schema_filename_suffixes:\n    - .schema.json\n    - schema.json\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-field-type")


def test_schema_authority_empty_suffix_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  forbidden_schema_filename_suffixes:\n    - .schema.json\n",
        "  forbidden_schema_filename_suffixes:\n    - .schema.json\n    - ''\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-field-type")


# --------------------------------------------------------------------------- #
# Canonical id/root/family/legacy binding (fix for finding #1).               #
# --------------------------------------------------------------------------- #


def test_canonical_authority_root_id_swap_is_flagged(tmp_path: Path) -> None:
    # Transposing `normative_schemas` and `normative_fixtures` onto each
    # other's roots leaves both ids present, both roots present, and both
    # roots non-empty — but the id-to-root binding is wrong. The gate must
    # fail.
    body = _GOOD_POLICY.replace(
        "  - id: normative_schemas\n"
        "    root: contracts/schemas/\n"
        "    authority: published JSON Schemas\n"
        "    family: schemas\n"
        "  - id: normative_fixtures\n"
        "    root: contracts/fixtures/\n"
        "    authority: conformance fixtures\n"
        "    family: fixtures\n",
        "  - id: normative_schemas\n"
        "    root: contracts/fixtures/\n"
        "    authority: published JSON Schemas\n"
        "    family: schemas\n"
        "  - id: normative_fixtures\n"
        "    root: contracts/schemas/\n"
        "    authority: conformance fixtures\n"
        "    family: fixtures\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-canonical-root-binding")


def test_canonical_authority_root_family_relabel_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  - id: normative_prose\n    root: specs/\n    authority: normative prose specifications\n    family: prose\n",
        "  - id: normative_prose\n    root: specs/\n    authority: normative prose specifications\n    family: documents\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-canonical-root-binding")


def test_canonical_non_normative_root_relabel_is_flagged(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "  - id: reference_implementations\n    root: implementations/\n    note: reference code only\n",
        "  - id: reference_implementations\n    root: tools/\n    note: reference code only\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-canonical-root-binding")


def test_legacy_floor_subset_is_enforced(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "legacy_top_level_dirs:\n  - schemas\n  - conformance\n  - src\n",
        "legacy_top_level_dirs:\n  - conformance\n  - src\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-legacy-floor")
    assert any("schemas" in f.message for f in failures), (
        f"expected the missing 'schemas' legacy floor entry to be named; got: {[f.render() for f in failures]}"
    )


# --------------------------------------------------------------------------- #
# Seam ADR (ADR-019) presence (fix for finding #2).                           #
# --------------------------------------------------------------------------- #


def test_seam_adr_missing_file_is_flagged(tmp_path: Path) -> None:
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, seam_body=None))
    assert _flagged(failures, "authority-boundary-seam-adr-missing")


# --------------------------------------------------------------------------- #
# Tightened README drift check (fix for finding #4) — partial substrings      #
# like `old/authority-boundary.yaml` must not satisfy the drift guard.        #
# --------------------------------------------------------------------------- #


def test_contracts_readme_stale_path_substring_is_flagged(tmp_path: Path) -> None:
    contracts_readme = (
        "# Contracts\n\nSee [old/authority-boundary.yaml](../old/authority-boundary.yaml) for the canonical "
        "manifest, governed by [ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md).\n"
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, contracts_readme=contracts_readme))
    assert _flagged(failures, "authority-boundary-contracts-readme-drift")


def test_specs_readme_stale_path_substring_is_flagged(tmp_path: Path) -> None:
    specs_readme = (
        "# Specs\n\nSee [old/authority-boundary.yaml](old/authority-boundary.yaml) for the canonical "
        "manifest, governed by [ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md).\n"
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, specs_readme=specs_readme))
    assert _flagged(failures, "authority-boundary-specs-readme-drift")


def test_contracts_readme_stale_path_with_canonical_suffix_is_flagged(tmp_path: Path) -> None:
    # `../old/specs/authority/authority-boundary.yaml` ends with the
    # canonical accepted path but the actual link target is different. The
    # tightened Markdown-link-aware check must reject this.
    contracts_readme = (
        "# Contracts\n\nSee [the manifest](../old/specs/authority/authority-boundary.yaml) for the canonical "
        "manifest, governed by [ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md).\n"
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, contracts_readme=contracts_readme))
    assert _flagged(failures, "authority-boundary-contracts-readme-drift")


def test_contracts_readme_inline_code_satisfies_drift(tmp_path: Path) -> None:
    # An inline code span like `specs/authority/authority-boundary.yaml`
    # counts as a reference; the drift guard accepts code-fenced tokens
    # because the prose may not need a clickable link.
    contracts_readme = (
        "# Contracts\n\nThe canonical manifest is `specs/authority/authority-boundary.yaml`, "
        "governed by [ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md).\n"
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, contracts_readme=contracts_readme))
    assert not _flagged(failures, "authority-boundary-contracts-readme-drift")


# --------------------------------------------------------------------------- #
# ADR drift uses word-boundary matching (codex cycle-2 finding).               #
# --------------------------------------------------------------------------- #


def test_adr_drift_short_family_token_does_not_match_unrelated_word(tmp_path: Path) -> None:
    # If the family token `prose` could match `prosecution` anywhere, the
    # drift guard would silently pass an ADR that never names the family.
    # The word-boundary regex must reject this substring match — both
    # ADR-009 and ADR-019 stubs here contain `prose` only as a substring of
    # `prosecution`.
    adr_body = "# ADR-009\n\nThe prosecution defines schemas, fixtures, profiles, and concept-authority.\n"
    seam_body = "ADR-019 stub mentioning prosecution only, with concept-authority noted.\n"
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, adr_body=adr_body, seam_body=seam_body))
    assert _flagged(failures, "authority-boundary-adr-drift")
    assert any("prose" in failure.message for failure in failures), (
        f"expected the missing prose family to be named; got: {[failure.render() for failure in failures]}"
    )


# --------------------------------------------------------------------------- #
# Cross-list categorisation overlap (codex cycle-2 finding).                  #
# --------------------------------------------------------------------------- #


def test_root_classified_as_both_authority_and_non_normative_is_flagged(tmp_path: Path) -> None:
    # Add an extra authority_roots entry that points at implementations/,
    # which is also a non_normative_roots entry. The cross-list overlap
    # check must reject this.
    body = _GOOD_POLICY.replace(
        "  - id: normative_concept_authority\n",
        "  - id: stowaway_impl_authority\n"
        "    root: implementations/\n"
        "    authority: shadow authority\n"
        "    family: prose\n"
        "  - id: normative_concept_authority\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-categorisation-overlap")


def test_classified_root_overlapping_legacy_segment_is_flagged(tmp_path: Path) -> None:
    # Declare an authority root whose top-level segment is `schemas` —
    # which is a legacy_top_level_dirs entry. The overlap check must reject
    # this even though the root is well-formed in isolation.
    body = _GOOD_POLICY.replace(
        "  - id: normative_concept_authority\n",
        "  - id: stowaway_schemas_authority\n"
        "    root: schemas/leaked/\n"
        "    authority: shadow authority\n"
        "    family: prose\n"
        "  - id: normative_concept_authority\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-categorisation-overlap")


def test_authority_root_ancestor_of_non_normative_root_is_flagged(tmp_path: Path) -> None:
    # An authority root that strictly contains a non-normative root would
    # force the non-normative dir to bear partial authority.
    body = _GOOD_POLICY.replace(
        "  - id: normative_concept_authority\n",
        "  - id: stowaway_subtree_authority\n"
        "    root: implementations/python/foo/\n"
        "    authority: shadow authority\n"
        "    family: prose\n"
        "  - id: normative_concept_authority\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-categorisation-overlap")


# --------------------------------------------------------------------------- #
# Schema scan ignores developer-local virtualenvs and build artifacts.        #
# --------------------------------------------------------------------------- #


def test_schema_scan_skips_dotvenv_and_pycache(tmp_path: Path) -> None:
    # A schema file under implementations/python/.venv/ or under a
    # __pycache__ tree must not flag the gate; those paths are operational
    # and not under the repo's authority boundary.
    seeded = _seed_repo(
        tmp_path,
        extra_files={
            "implementations/python/.venv/lib/site-packages/x.schema.json": "{}",
            "implementations/__pycache__/cached.schema.json": "{}",
        },
    )
    failures = evaluate_authority_boundary(seeded)
    assert not _flagged(failures, "authority-boundary-schema-misplaced"), (
        f"venv/pycache schemas must not flag the gate; got: {[f.render() for f in failures]}"
    )


# --------------------------------------------------------------------------- #
# Codex cycle-3 follow-ups.                                                   #
# --------------------------------------------------------------------------- #


def test_every_canonical_non_normative_root_binding_is_enforced(tmp_path: Path) -> None:
    # Each non-normative id MUST be pinned to its canonical root. The
    # previous binding only covered `reference_implementations`; the rest
    # are now part of the floor. Mutating `explanatory_docs` onto `notes/`
    # must fail the gate.
    body = _GOOD_POLICY.replace(
        "  - id: explanatory_docs\n    root: docs/\n    note: explanatory material\n",
        "  - id: explanatory_docs\n    root: notes/\n    note: explanatory material\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-canonical-root-binding")


def test_swapped_non_normative_pair_is_flagged(tmp_path: Path) -> None:
    # Swap `worked_examples` (canonically `examples/`) onto `tools/` —
    # both top-level dirs remain classified, but the id-to-root binding
    # is wrong. Without the binding floor this slipped past the gate.
    body = _GOOD_POLICY.replace(
        "  - id: worked_examples\n    root: examples/\n    note: non-normative worked examples\n"
        "  - id: research_notes\n    root: research/\n    note: non-normative research material\n",
        "  - id: worked_examples\n    root: tools/\n    note: non-normative worked examples\n"
        "  - id: research_notes\n    root: research/\n    note: non-normative research material\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-canonical-root-binding")


def test_invalid_forbidden_root_does_not_walk_unrelated_tree(tmp_path: Path) -> None:
    # A malformed forbidden_authority_roots entry must be skipped by the
    # schema-misplaced scan even though `_check_schema_authority_block`
    # already reports the shape failure. The scan must not crash or
    # attempt to walk outside the repo.
    body = _GOOD_POLICY.replace(
        "  forbidden_authority_roots:\n    - implementations/\n",
        "  forbidden_authority_roots:\n    - implementations/\n    - /abs/escape\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    # Two assertions: the shape failure fires for the malformed entry, and
    # the schema-misplaced rule never fires because the bad root was
    # skipped.
    assert _flagged(failures, "authority-boundary-root-shape")
    assert not _flagged(failures, "authority-boundary-schema-misplaced"), (
        f"malformed forbidden root must not trigger a misplaced-schema walk; got: {[f.render() for f in failures]}"
    )


# --------------------------------------------------------------------------- #
# normative_artifact_families -- CA-4: a non-prose artifact (agent-guidance    #
# AUT-811 profile) that lives inside the normative `specs/` root but carries a #
# distinct `governance-guidance` family. The classification is declared in the #
# manifest so the artifact's authority class is decidable from the manifest    #
# alone, and pinned (CANONICAL_ARTIFACT_FAMILY_BINDING) against silent drift.  #
# --------------------------------------------------------------------------- #


_NAF_BLOCK = (
    "normative_artifact_families:\n"
    "  - id: agent_guidance_profile\n"
    "    artifact: specs/agent-guidance/agent-guidance.yaml\n"
    "    authority: agent-usable governance-guidance profile\n"
    "    family: governance-guidance\n"
    "    requirement_refs:\n"
    "      - AUT-811\n"
    "  - id: deprecation_records\n"
    "    artifact: specs/evolution/deprecation-records.yaml\n"
    "    authority: ecosystem deprecation and lifecycle records\n"
    "    family: deprecation-records\n"
    "    requirement_refs:\n"
    "      - GOV-902\n"
)


def test_canonical_artifact_family_binding_pins_agent_guidance() -> None:
    # The agent-guidance AUT-811 profile and the GOV-902 deprecation-records
    # ledger are the pinned artifact families; a rename of either constant
    # surfaces in the suite rather than silently relaxing the gate.
    assert CANONICAL_ARTIFACT_FAMILY_BINDING == {
        "specs/agent-guidance/agent-guidance.yaml": "governance-guidance",
        "specs/evolution/deprecation-records.yaml": "deprecation-records",
    }


def test_missing_canonical_artifact_family_entry_is_flagged(tmp_path: Path) -> None:
    # Drop the agent-guidance entry (leaving an empty block) — its authority
    # class is no longer decidable from the manifest, which is exactly the
    # ambiguity CA-4 closes.
    body = _GOOD_POLICY.replace(_NAF_BLOCK, "normative_artifact_families: []\n", 1)
    assert body != _GOOD_POLICY, "setup error: NAF block not found in _GOOD_POLICY"
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-artifact-family-canonical-missing")
    assert any("agent-guidance.yaml" in failure.message for failure in failures), (
        f"expected the canonical artifact to be named; got: {[f.render() for f in failures]}"
    )


def test_artifact_family_relabel_is_flagged(tmp_path: Path) -> None:
    # Relabelling the pinned artifact's family (governance-guidance → prose)
    # must fail even though the entry is otherwise well-formed.
    body = _GOOD_POLICY.replace("    family: governance-guidance\n", "    family: prose\n", 1)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-artifact-family-canonical-binding")


@pytest.mark.parametrize("field", _REQUIRED_ARTIFACT_FAMILY_FIELDS)
def test_artifact_family_missing_required_field_is_flagged(tmp_path: Path, field: str) -> None:
    # An artifact-family entry missing ANY required field is a malformation, not
    # a default — full-tuple coverage over _REQUIRED_ARTIFACT_FAMILY_FIELDS.
    body = _policy_without_entry_field("normative_artifact_families", 0, field)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert any(
        f.rule_id == "authority-boundary-artifact-family-entry-field" and f"required field: {field}" in f.message
        for f in failures
    ), f"expected an artifact-family entry-field failure naming {field!r}; got: {[f.render() for f in failures]}"


def test_artifact_family_entry_must_be_mapping(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(_NAF_BLOCK, "normative_artifact_families:\n  - just-a-string\n", 1)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-artifact-family-entry-field")


def test_artifact_family_non_list_value_is_rejected(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(_NAF_BLOCK, "normative_artifact_families: oops\n", 1)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-field-type")


def test_artifact_family_duplicate_id_is_flagged(tmp_path: Path) -> None:
    # A second entry reusing `agent_guidance_profile` as its id.
    extra = (
        "  - id: agent_guidance_profile\n"
        "    artifact: specs/agent-guidance/agent-guidance.yaml\n"
        "    authority: duplicate id\n"
        "    family: governance-guidance\n"
    )
    body = _GOOD_POLICY.replace(_NAF_BLOCK, _NAF_BLOCK + extra, 1)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-artifact-family-duplicate")


def test_artifact_family_path_not_on_disk_is_flagged(tmp_path: Path) -> None:
    # A second, well-formed entry whose artifact does not exist on disk. The
    # canonical agent-guidance entry stays intact so only the missing-file
    # rule fires.
    extra = (
        "  - id: ghost_profile\n"
        "    artifact: specs/agent-guidance/does-not-exist.yaml\n"
        "    authority: ghost\n"
        "    family: governance-guidance\n"
    )
    body = _GOOD_POLICY.replace(_NAF_BLOCK, _NAF_BLOCK + extra, 1)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-artifact-family-missing")
    assert any("does-not-exist.yaml" in failure.render() for failure in failures), (
        f"expected the missing artifact path to be named; got: {[f.render() for f in failures]}"
    )


def test_artifact_family_under_non_normative_root_is_flagged(tmp_path: Path) -> None:
    # A classified artifact must live under a NORMATIVE authority root.
    # Pointing one at docs/ (non-normative) must fail even when the file
    # exists, because docs/ consumes authority and does not define it.
    extra = (
        "  - id: misplaced_profile\n"
        "    artifact: docs/misplaced-guidance.yaml\n"
        "    authority: misplaced\n"
        "    family: governance-guidance\n"
    )
    body = _GOOD_POLICY.replace(_NAF_BLOCK, _NAF_BLOCK + extra, 1)
    failures = evaluate_authority_boundary(
        _seed_repo(
            tmp_path,
            policy_body=body,
            extra_files={"docs/misplaced-guidance.yaml": "profile: x\n"},
        )
    )
    assert _flagged(failures, "authority-boundary-artifact-family-non-normative")


def test_artifact_family_absolute_path_is_flagged(tmp_path: Path) -> None:
    extra = (
        "  - id: abs_profile\n"
        "    artifact: /abs/specs/agent-guidance/agent-guidance.yaml\n"
        "    authority: abs\n"
        "    family: governance-guidance\n"
    )
    body = _GOOD_POLICY.replace(_NAF_BLOCK, _NAF_BLOCK + extra, 1)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-artifact-family-path-shape")


def test_artifact_family_traversal_path_is_flagged(tmp_path: Path) -> None:
    extra = (
        "  - id: escape_profile\n"
        "    artifact: specs/../../escape.yaml\n"
        "    authority: escape\n"
        "    family: governance-guidance\n"
    )
    body = _GOOD_POLICY.replace(_NAF_BLOCK, _NAF_BLOCK + extra, 1)
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-artifact-family-path-shape")


def test_artifact_family_requirement_refs_must_be_string_list(tmp_path: Path) -> None:
    body = _GOOD_POLICY.replace(
        "    requirement_refs:\n      - AUT-811\n",
        "    requirement_refs:\n      - 811\n",
        1,
    )
    failures = evaluate_authority_boundary(_seed_repo(tmp_path, policy_body=body))
    assert _flagged(failures, "authority-boundary-artifact-family-entry-field")


# --------------------------------------------------------------------------- #
# Real-repo positive case -- run the validator against the actual repo and    #
# confirm it reports no failures. This is the integration-style check that    #
# catches the "validator passes synthetic fixtures but the real repo is dirty"#
# failure mode.                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_evaluate_authority_boundary_real_repo_is_clean() -> None:
    failures = evaluate_authority_boundary(REPO_ROOT)
    assert failures == [], "\n".join(failure.render() for failure in failures)


# --------------------------------------------------------------------------- #
# SDL authoring spec registration (issue #498 / review CT-6).                 #
# The structural checker fires `root-empty`/`root-missing` only when an        #
# authority root is *registered* but absent; it does not, on its own, prove    #
# that the SDL authoring spec stays registered. Removing both the manifest     #
# entry and the directory would leave a valid manifest with the SDL authoring  #
# authority silently dropped. This test pins the registration directly.        #
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_specs_sdl_prose_root_is_registered_in_real_manifest() -> None:
    import yaml

    manifest = yaml.safe_load((REPO_ROOT / AUTHORITY_BOUNDARY_RELATIVE_PATH).read_text(encoding="utf-8"))
    sdl_entries = [entry for entry in manifest["authority_roots"] if entry.get("root") == "specs/sdl/"]
    assert sdl_entries, "specs/sdl/ must be registered as an authority root in the authority-boundary manifest"
    assert all(entry.get("family") == "prose" for entry in sdl_entries), (
        f"specs/sdl/ must be registered with family 'prose'; got {[entry.get('family') for entry in sdl_entries]}"
    )

    sdl_dir = REPO_ROOT / "specs" / "sdl"
    assert sdl_dir.is_dir(), "specs/sdl/ must exist on disk"
    real_artifacts = [path for path in sdl_dir.iterdir() if path.name != ".keep"]
    assert real_artifacts, "specs/sdl/ must contain at least one specification artifact"
