from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_sdl_catalog_parity import (  # noqa: E402
    CatalogParseError,
    evaluate_sdl_catalog_parity,
    main,
    parse_reference_catalog,
    parse_top_level_catalog,
)

_CATALOG_PATHS = (
    "specs/sdl/sections.md",
    "specs/sdl/references.md",
    "specs/sdl/runtime-inventory.md",
    "specs/sdl/document-model.md",
    "specs/sdl/variables-and-instantiation.md",
    "specs/sdl/diagnostics.md",
    "specs/formal/sdl-phases/README.md",
    "contracts/schemas/sdl/sdl-authoring-input-v1.json",
)


def _seed_repo(tmp_path: Path) -> Path:
    for relative in _CATALOG_PATHS:
        source = REPO_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return tmp_path


def _replace(tmp_path: Path, relative: str, old: str, new: str) -> None:
    path = tmp_path / relative
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _rule_ids(tmp_path: Path) -> set[str]:
    return {failure.rule_id for failure in evaluate_sdl_catalog_parity(tmp_path)}


@pytest.mark.parametrize(
    ("old", "new", "rule_id"),
    [
        ("| `behavior_specifications` |", "| `behavior_profiles` |", "sdl-catalog-field-set"),
        ("| `nodes` | section | map |", "| `nodes` | section | list |", "sdl-catalog-field-shape"),
        ("| `version` | metadata | scalar |", "| `version` | metadata | map |", "sdl-catalog-field-shape"),
        ("optional; default `*`", "required", "sdl-catalog-field-default"),
    ],
)
def test_top_level_catalog_drift_is_flagged(tmp_path: Path, old: str, new: str, rule_id: str) -> None:
    repo = _seed_repo(tmp_path)
    _replace(repo, "specs/sdl/sections.md", old, new)
    assert rule_id in _rule_ids(repo)


def test_checked_summary_drift_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(repo, "specs/sdl/sections.md", "sections=37", "sections=36")
    assert "sdl-catalog-summary" in _rule_ids(repo)


def test_phase_lifecycle_membership_drift_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/sections.md",
        "| `realization` | composition | mapping | normalized |",
        "| `realization` | composition | mapping | normalized, expanded |",
    )
    assert "sdl-catalog-lifecycle" in _rule_ids(repo)


def test_phase_member_catalog_drift_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/formal/sdl-phases/README.md",
        "| `realization` | optional | forbidden | forbidden |",
        "| `realization` | optional | optional | forbidden |",
    )
    assert "sdl-catalog-phase-membership" in _rule_ids(repo)


def test_realization_transfer_prose_drift_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/formal/sdl-phases/README.md",
        "`expansion_provenance.realization_designations` and later `instantiation_provenance.realization_designations`",
        "`expansion_provenance.realization_designations`",
    )
    assert "sdl-catalog-phase-transfer" in _rule_ids(repo)


def test_identity_classification_drift_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(repo, "specs/sdl/sections.md", "| `map_key` | catalogued |", "| `node_id` | catalogued |")
    assert "sdl-catalog-field-identity" in _rule_ids(repo)


def test_reference_domain_drift_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/references.md",
        "| `behavior_specifications.*.authority_scope_refs[]` | `targetable` |",
        "| `behavior_specifications.*.authority_scope_refs[]` | `any` |",
    )
    assert "sdl-catalog-reference-domain" in _rule_ids(repo)


def test_non_completion_reference_domain_drift_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/references.md",
        "| `action_contracts.*.interactions.*.related_actions[]` | `action_contracts` |",
        "| `action_contracts.*.interactions.*.related_actions[]` | `any` |",
    )
    assert "sdl-catalog-reference-row" in _rule_ids(repo)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("| `features` | semantic validation |", "| `features` | |"),
        (
            "| fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | "
            "[node validator]",
            "| | [reference rules](#5-cross-section-reference-edge-catalog) | [node validator]",
        ),
        ("[node validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py)", ""),
    ],
)
def test_reference_row_classification_drift_is_flagged(tmp_path: Path, old: str, new: str) -> None:
    repo = _seed_repo(tmp_path)
    _replace(repo, "specs/sdl/references.md", old, new)
    assert "sdl-catalog-reference-row" in _rule_ids(repo)


def test_missing_behavior_reference_edge_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/references.md",
        "| `behavior_specifications.*.participant_refs[]` |",
        "| `behavior_profiles.*.participant_refs[]` |",
    )
    assert "sdl-catalog-behavior-edge" in _rule_ids(repo)


def test_missing_live_reference_edges_are_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/references.md",
        "| `features.*.dependencies[]` |",
        "| `features.*.dependency_refs[]` |",
    )
    rule_ids = _rule_ids(repo)
    assert "sdl-catalog-reference-row" in rule_ids
    assert "sdl-catalog-reference-path" in rule_ids


def test_reference_catalog_uses_live_nested_model_paths() -> None:
    rows = parse_reference_catalog((REPO_ROOT / "specs/sdl/references.md").read_text(encoding="utf-8"))
    paths = {row.source_path for row in rows}
    assert {
        "nodes.*.features.*",
        "nodes.*.conditions.*",
        "nodes.*.injects.*",
        "action_contracts.*.temporal_contracts.*.backend_disclosure_refs[]",
        "action_contracts.*.backend_timing_disclosures.*.affected_temporal_ids[]",
        "action_contracts.*.interactions.*.related_actions[]",
        "behavior_specifications.*.tool_affordances.*.tool_ref",
        "behavior_specifications.*.tool_affordances.*.action_contract_refs[]",
        "behavior_specifications.*.tool_affordances.*.observation_boundary_refs[]",
        "behavior_specifications.*.participant_inject_deliveries.*.participant_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.inject_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.occurrence.event_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.occurrence.script_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.occurrence.story_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.source_item_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.result_item_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.observation_boundary_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.temporal_constraint_refs[]",
        "behavior_specifications.*.participant_inject_deliveries.*.evidence_requirement_refs[]",
        "behavior_specifications.*.participant_inject_deliveries.*.control_transition_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.controller_ref",
        "behavior_specifications.*.participant_inject_deliveries.*.control_authority_scope_refs[]",
        "behavior_specifications.*.participant_inject_deliveries.*.control_evidence_refs[]",
        "outcome_interpretation_rules.*.source_bindings.*.ref",
        "outcome_interpretation_rules.*.target_bindings.*.ref",
    } <= paths
    assert {
        "outcome_interpretation_rules.*.source_ref",
        "outcome_interpretation_rules.*.target_ref",
        "action_contracts.*.interactions.*.related_action_ref",
    }.isdisjoint(paths)


def test_implementation_evidence_cannot_be_normative_owner(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/references.md",
        "[reference rules](#5-cross-section-reference-edge-catalog)",
        "[implementation](../../implementations/python/packages/raes/scenario.py)",
    )
    assert "sdl-catalog-reference-owner" in _rule_ids(repo)


def test_normative_owner_resolution_is_independent_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _seed_repo(tmp_path / "repo")
    monkeypatch.chdir(tmp_path)
    assert "sdl-catalog-reference-owner" not in _rule_ids(repo)


def test_missing_internal_markdown_target_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/sections.md",
        "[README](README.md)",
        "[README](missing-authority.md)",
    )
    assert "sdl-catalog-link-target" in _rule_ids(repo)


def test_implementation_specific_diagnostic_term_must_be_marked_nonnormative(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/diagnostics.md",
        "> these as `SDLParseError`, `SDLValidationError`, and `SDLInstantiationError`;",
        "these as `SDLParseError`, `SDLValidationError`, and `SDLInstantiationError`;",
    )
    assert "sdl-catalog-normative-layer" in _rule_ids(repo)


def test_runtime_child_tree_drift_is_flagged(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _replace(
        repo,
        "specs/sdl/runtime-inventory.md",
        "zones:zone_id/rrsets:rrset_id",
        "zones:zone_id/records:record_id",
    )
    assert "sdl-catalog-runtime-family" in _rule_ids(repo)


def test_duplicate_top_level_row_is_rejected() -> None:
    body = """# Catalog

## Complete top-level field catalog

| Field | Kind | Shape | Lifecycle | Presence/default | Identity | References | Semantic owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `name` | metadata | scalar | normalized | required | scenario_name | none | `specs/sdl/document-model.md` |
| `name` | metadata | scalar | normalized | required | scenario_name | none | `specs/sdl/document-model.md` |
"""
    with pytest.raises(CatalogParseError, match="duplicate"):
        parse_top_level_catalog(body)


def test_catalog_parser_rejects_oversized_input() -> None:
    body = "x" * (512 * 1024 + 1)
    with pytest.raises(CatalogParseError, match="size limit"):
        parse_top_level_catalog(body)


def test_cli_reports_json_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _seed_repo(tmp_path)
    _replace(repo, "specs/sdl/sections.md", "sections=37", "sections=36")
    assert main(["--repo-root", str(repo), "--json"]) == 1
    assert '"rule_id": "sdl-catalog-summary"' in capsys.readouterr().out


@pytest.mark.integration
def test_live_sdl_catalogs_match_authorities() -> None:
    assert evaluate_sdl_catalog_parity(REPO_ROOT) == []
