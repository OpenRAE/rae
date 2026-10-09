"""Published-contract requirement tracing gate (issue #712).

Every published schema must trace to a live governing requirement: an
``IMPLEMENTS → SPEC`` link to its exact path from a requirement record whose
status is ACTIVE or DRAFT. These tests drive the rule through temporary
repositories, then assert that the live tree satisfies it and that the
inventory the gate reads agrees with ``schema_bundle()`` and the publication
catalog.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from raes_contracts.contracts import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_contract_requirement_tracing import (  # noqa: E402
    MISSING_RULE_ID,
    UNREADABLE_RULE_ID,
    evaluate_contract_tracing,
    main,
    published_schema_paths,
)
from tools.check_schema_publication import load_schema_publication_catalog  # noqa: E402

_STAGE = "policy / published contract requirement tracing"
_SCRIPT = "tools/check_contract_requirement_tracing.py"
_SCHEMA = "contracts/schemas/control-plane/operation-status-v1.json"
_RECORD = "docs/requirements/API-403/requirement.md"


def _publish(repo_root: Path, schema_path: str = _SCHEMA) -> str:
    target = repo_root / schema_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}\n", encoding="utf-8")
    return schema_path


def _link(identifier: str, link_type: str = "IMPLEMENTS", artifact_type: str = "SPEC") -> str:
    return f"- {link_type} → {artifact_type} `{identifier}` (fixture link)"


def _requirement(repo_root: Path, uid: str, *links: str, status: str = "ACTIVE") -> Path:
    record = repo_root / "docs" / "requirements" / uid / "requirement.md"
    record.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"id: {uid}", f"status: {status}", "---", "", f"# {uid}", "", "## Traceability", "", *links]
    record.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return record


def _paths(failures: list, rule_id: str) -> set[str | None]:
    return {failure.path for failure in failures if failure.rule_id == rule_id}


# --- the rule ----------------------------------------------------------------


@pytest.mark.parametrize("status", ["ACTIVE", "DRAFT"])
def test_a_live_implements_spec_link_traces_the_contract(tmp_path: Path, status: str) -> None:
    _publish(tmp_path)
    _requirement(tmp_path, "API-403", _link(_SCHEMA), status=status)

    assert evaluate_contract_tracing(tmp_path) == []


@pytest.mark.parametrize("status", ["DEPRECATED", "ARCHIVED"])
def test_a_retired_owner_never_traces_the_contract(tmp_path: Path, status: str) -> None:
    _publish(tmp_path)
    _requirement(tmp_path, "API-403", _link(_SCHEMA), status=status)

    assert _paths(evaluate_contract_tracing(tmp_path), MISSING_RULE_ID) == {_SCHEMA}


def test_one_live_owner_is_enough_beside_a_retired_one(tmp_path: Path) -> None:
    _publish(tmp_path)
    _requirement(tmp_path, "API-402", _link(_SCHEMA), status="DEPRECATED")
    _requirement(tmp_path, "API-403", _link(_SCHEMA))

    assert evaluate_contract_tracing(tmp_path) == []


@pytest.mark.parametrize(
    "link",
    [
        pytest.param(_link(_SCHEMA, artifact_type="CODE_FILE"), id="implements-typed-as-code-file"),
        pytest.param(_link(_SCHEMA, artifact_type="CONFIG"), id="implements-typed-as-config"),
        pytest.param(_link(_SCHEMA, link_type="CONSTRAINS"), id="constrains-spec"),
        pytest.param(_link(_SCHEMA, link_type="DOCUMENTS"), id="documents-spec"),
        pytest.param(_link(_SCHEMA, link_type="VERIFIES"), id="verifies-spec"),
        pytest.param(
            _link("contracts/control-plane/operation-status-v1.json"),
            id="implements-spec-on-a-sibling-document",
        ),
    ],
)
def test_only_an_exact_implements_spec_link_traces_the_contract(tmp_path: Path, link: str) -> None:
    _publish(tmp_path)
    _requirement(tmp_path, "API-403", link)

    assert _paths(evaluate_contract_tracing(tmp_path), MISSING_RULE_ID) == {_SCHEMA}


def test_an_untraced_contract_is_reported_by_id_at_its_exact_path(tmp_path: Path) -> None:
    _publish(tmp_path)

    [failure] = evaluate_contract_tracing(tmp_path)

    assert (failure.rule_id, failure.path) == (MISSING_RULE_ID, _SCHEMA)
    assert "operation-status-v1" in failure.message


def _malformed_link(repo_root: Path) -> str:
    _requirement(repo_root, "API-403", f"- IMPLEMENTS → SPEC {_SCHEMA}")
    return _RECORD


def _symlinked_record(repo_root: Path) -> str:
    real = _requirement(repo_root / "elsewhere", "API-403", _link(_SCHEMA))
    record = repo_root / _RECORD
    record.parent.mkdir(parents=True)
    record.symlink_to(real)
    return _RECORD


def _non_canonical_directory(repo_root: Path) -> str:
    _requirement(repo_root, "notes", _link(_SCHEMA))
    return "docs/requirements/notes/requirement.md"


@pytest.mark.parametrize("make_record", [_malformed_link, _symlinked_record, _non_canonical_directory])
def test_an_unreadable_requirement_record_fails_closed_and_owns_nothing(tmp_path: Path, make_record) -> None:
    _publish(tmp_path)
    record = make_record(tmp_path)

    failures = evaluate_contract_tracing(tmp_path)

    assert _paths(failures, UNREADABLE_RULE_ID) == {record}
    assert _paths(failures, MISSING_RULE_ID) == {_SCHEMA}


# --- CLI and reporting -------------------------------------------------------


def test_cli_emits_json_naming_each_untraced_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _publish(tmp_path)

    assert main(["--repo-root", str(tmp_path), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert [(item["rule_id"], item["path"]) for item in payload] == [(MISSING_RULE_ID, _SCHEMA)]


def test_cli_text_mode_reports_on_stderr_and_passes_a_traced_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish(tmp_path)

    assert main(["--repo-root", str(tmp_path)]) == 1
    assert f"[{MISSING_RULE_ID}] {_SCHEMA}:" in capsys.readouterr().err

    _requirement(tmp_path, "API-403", _link(_SCHEMA))
    assert main(["--repo-root", str(tmp_path)]) == 0


def test_a_shared_policy_waiver_suppresses_only_the_named_finding(tmp_path: Path) -> None:
    _publish(tmp_path)
    other = _publish(tmp_path, "contracts/schemas/control-plane/operation-receipt-v1.json")
    waivers = tmp_path / "tools" / "policy" / "exceptions.yaml"
    waivers.parent.mkdir(parents=True)
    waivers.write_text(f"exceptions:\n  - rule_id: {MISSING_RULE_ID}\n    paths: [{_SCHEMA}]\n", encoding="utf-8")

    assert main(["--repo-root", str(tmp_path)]) == 1
    _requirement(tmp_path, "API-403", _link(other))
    assert main(["--repo-root", str(tmp_path)]) == 0


def test_report_names_owners_untraced_contracts_and_unreadable_records_without_gating(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    traced = _publish(tmp_path)
    untraced = _publish(tmp_path, "contracts/schemas/control-plane/operation-receipt-v1.json")
    _requirement(tmp_path, "API-403", _link(traced))
    _requirement(tmp_path, "API-404", _link(traced), status="DRAFT")
    _requirement(tmp_path, "API-402", "- not a link record")

    assert main(["--repo-root", str(tmp_path), "--report"]) == 0
    report = capsys.readouterr().out
    assert f"{traced}: API-403, API-404" in report
    assert f"{untraced}: UNTRACED" in report
    assert f"[{UNREADABLE_RULE_ID}] docs/requirements/API-402/requirement.md" in report


# --- policy-lane wiring ------------------------------------------------------


class _Reporter:
    def __init__(self) -> None:
        self.runs: list[str] = []
        self.skips: list[str] = []

    def run(self, name: str, func: object, *, detail: str = "") -> None:
        del detail
        self.runs.append(name)
        assert callable(func)
        func()

    def skip(self, name: str, reason: str) -> None:
        del reason
        self.skips.append(name)


@pytest.fixture
def policy_lanes(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the lane module against a stand-in ``nox``; the project env has none."""

    monkeypatch.setitem(sys.modules, "nox", SimpleNamespace(Session=object))
    for name in [name for name in sys.modules if name.startswith("tools.nox_support")]:
        monkeypatch.delitem(sys.modules, name)
    return importlib.import_module("tools.nox_support.policy_lanes")


def test_policy_lane_runs_the_gate_on_the_working_tree_and_skips_it_when_staged(
    monkeypatch: pytest.MonkeyPatch, policy_lanes: ModuleType
) -> None:
    scripts: list[str] = []
    monkeypatch.setattr(policy_lanes, "_run_project_python", lambda _session, script, *_args: scripts.append(script))

    working_tree = _Reporter()
    policy_lanes._run_working_tree_policies(SimpleNamespace(), working_tree, staged=False, adr_pin_args=[])
    staged = _Reporter()
    policy_lanes._run_working_tree_policies(SimpleNamespace(), staged, staged=True, adr_pin_args=[])

    assert _STAGE in working_tree.runs
    assert _SCRIPT in scripts
    assert _STAGE in staged.skips
    assert _STAGE not in staged.runs


# --- the live tree -----------------------------------------------------------


def test_checked_in_repository_traces_every_published_contract() -> None:
    assert evaluate_contract_tracing(REPO_ROOT) == []


def test_the_gate_inventory_agrees_with_schema_bundle_and_the_publication_catalog() -> None:
    inventory = published_schema_paths(REPO_ROOT)
    catalog = sorted(entry["schema_path"] for entry in load_schema_publication_catalog(REPO_ROOT)["schemas"])

    assert inventory == catalog
    assert sorted(Path(schema_path).stem for schema_path in inventory) == sorted(schema_bundle())
