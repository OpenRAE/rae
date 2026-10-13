"""Guard the participant semantic coverage matrix against drift (issue #219, ASR-506).

The matrix in ``specs/formal/participant-semantics/semantic-coverage.md`` maps every
participant-semantics clause to contracts, implementation, tests, an evidence class,
coverage, and an open owner. These checks read the clause sources from the tree and
require agreement in both directions; whether a cited test exercises the whole clause
stays a review judgment.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from functools import cache
from pathlib import Path

import pytest
import yaml
from raes.participant_behavior_specification import ParticipantBehaviorSpecification
from raes_runtime.participant_control import ParticipantControlMixin

REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTICS_DIR = REPO_ROOT / "specs/formal/participant-semantics"
README = SEMANTICS_DIR / "README.md"
MATRIX = SEMANTICS_DIR / "semantic-coverage.md"
BEHAVIOR_README = REPO_ROOT / "specs/formal/participant-behavior-model/README.md"
RUNTIME_README = REPO_ROOT / "specs/formal/participant-runtime/README.md"
TESTS_DIR = REPO_ROOT / "implementations/python/tests"
PACKAGES_DIR = REPO_ROOT / "implementations/python/packages"
ORACLE = TESTS_DIR / "test_participant_semantics_invariant_oracle.py"
CATALOG = REPO_ROOT / "contracts/concept-authority/behavioral-relations-v1.json"
FULFILLMENT = REPO_ROOT / "specs/formal/assurance-fulfillment.yaml"

HEADER = (
    "| Facet | Clause | Requirement(s) | Excerpt | Normative location | Contract | Implementation | Tests "
    "| Evidence class | Coverage | Owner | Acceptance test |"
)
COLUMNS = (
    "facet", "clause", "requirements", "excerpt", "location", "contract",
    "implementation", "tests", "classes", "coverage", "owner", "acceptance",
)  # fmt: skip
FACETS = frozenset({"behavior", "interaction", "visibility", "timing", "causality", "outcomes"})
CLASSES = frozenset({"executable-invariant", "bounded-model-check", "runtime-test", "proof"})
COVERAGE = frozenset({"covered", "partial", "uncovered"})
CLAUSE_SECTIONS = ("SEM-208", "SEM-209", "SEM-210", "SEM-212", "SEM-213", "SEM-215")
SEM_211_GROUPS = ("Precondition classes:", "Effect classes:", "Failure classes:")
WAIVER_SUBSYSTEMS = ("participant-semantics", "participant-behavior-model", "participant-runtime")
DASH = "—"
UID = re.compile(r"\b[A-Z]{3}-\d{3}\b")
CODE = re.compile(r"`([^`]+)`")
RELATION = re.compile(r"relation `([a-z0-9-]+)`")
TEST_REF = re.compile(r"^test_\w+\.py::test_\w+$")
PATH_TOKEN = re.compile(r"^[\w./-]+(?:\.[a-z]+|/)$")


def _normalize(text: str) -> str:
    return " ".join(text.replace("`", "").split())


def _matrix_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_table = False
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if line == HEADER:
            in_table = True
        elif in_table and line.startswith("| ---"):
            continue
        elif in_table and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(dict(zip(COLUMNS, cells, strict=True)))
        else:
            in_table = False
    return rows


ROWS = _matrix_rows()
BY_CLAUSE = {row["clause"].strip("`"): row for row in ROWS}
OPEN_ROWS = [row for row in ROWS if row["coverage"] != "covered"]


def _readme_sections() -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in README.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            match = re.match(r"## (SEM-\d{3}.*?) - ", line)
            current = match.group(1) if match else None
            if current:
                sections[current] = []
        elif current:
            sections[current].append(line)
    return sections


def _list_after(lines: list[str], label: str) -> list[str]:
    items: list[str] = []
    for line in lines[lines.index(label) + 1 :]:
        if line.startswith("- "):
            items.append(line[2:])
        elif line.startswith("  ") and items:
            items[-1] += " " + line.strip()
        elif line.strip() or items:
            break
    return [_normalize(item) for item in items]


def _pbm_table() -> dict[str, tuple[str, str]]:
    rows = re.findall(r"^\| (PBM-\d+) \| (.+?) \| (.+?) \|$", BEHAVIOR_README.read_text(encoding="utf-8"), re.M)
    return {pbm: (_normalize(text), clauses) for pbm, text, clauses in rows}


@cache
def _expected_clauses() -> dict[str, str]:
    sections = _readme_sections()
    expected = {
        f"{uid}.C{index}": text
        for uid in CLAUSE_SECTIONS
        for index, text in enumerate(_list_after(sections[uid], "Design commitments:"), 1)
    }
    for index, label in enumerate(SEM_211_GROUPS, 1):
        assert _list_after(sections["SEM-211"], label), label
        expected[f"SEM-211.C{index}"] = label.rstrip(":")
    for invariant, paragraph in re.findall(r"^### (I\d+) - .+?\n\n(.+?)\n\n", README.read_text("utf-8"), re.M | re.S):
        expected[invariant] = _normalize(paragraph)
    expected.update({pbm: text for pbm, (text, _clauses) in _pbm_table().items()})
    return expected


def _source_group(clause: str) -> str | None:
    if clause.endswith(".F") or clause.startswith("PRT-"):
        return None
    if clause.startswith("PBM-"):
        return "PBM"
    return "I" if re.fullmatch(r"I\d+", clause) else clause.split(".")[0]


def _evidence(row: dict[str, str]) -> dict[str, list[str]]:
    if row["tests"] == DASH:
        return {}
    return {cls: CODE.findall(refs) for cls, _, refs in (part.partition(": ") for part in row["tests"].split("; "))}


def _owners(row: dict[str, str]) -> set[str]:
    return set(re.findall(r"#(\d+)", row["owner"].split("(", 1)[0]))


@cache
def _test_module(file_name: str) -> ast.Module:
    return ast.parse((TESTS_DIR / file_name).read_text(encoding="utf-8"))


def _resolves(reference: str) -> bool:
    file_name, *names = reference.split("::")
    body = _test_module(file_name).body
    for name in names[:-1]:
        body = next((node.body for node in body if isinstance(node, ast.ClassDef) and node.name == name), [])
    return any(isinstance(node, ast.FunctionDef) and node.name == names[-1] for node in body)


def _imports_shipped_package(file_name: str) -> bool:
    packages = {path.name for path in PACKAGES_DIR.iterdir() if (path / "__init__.py").exists()}
    modules = {
        alias.name.split(".")[0] for node in ast.walk(_test_module(file_name)) if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0] for node in ast.walk(_test_module(file_name))
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0
    }  # fmt: skip
    return bool(modules & packages)


def _paths(cell: str) -> list[str]:
    return [token for token in CODE.findall(cell) if "/" in token and PATH_TOKEN.match(token)]


@pytest.mark.parametrize("group", (*CLAUSE_SECTIONS, "SEM-211", "I", "PBM"))
def test_clause_rows_match_their_source_in_both_directions(group: str) -> None:
    expected = {clause: text for clause, text in _expected_clauses().items() if _source_group(clause) == group}
    actual = {clause: row for clause, row in BY_CLAUSE.items() if _source_group(clause) == group}

    assert expected
    assert sorted(actual) == sorted(expected)
    for clause, row in actual.items():
        assert expected[clause].startswith(_normalize(row["excerpt"])), clause


def test_every_readme_sem_section_has_a_row() -> None:
    locations = " ".join(row["location"] for row in ROWS)
    missing = [label for label in _readme_sections() if not re.search(rf"§ {re.escape(label)}(?![\w-])", locations)]
    assert not missing, f"README sections without a matrix row: {missing}"


def test_every_focused_specification_is_named_by_a_family_row() -> None:
    family = " ".join(row["location"] for clause, row in BY_CLAUSE.items() if clause.endswith(".F"))
    specs = sorted(path.name for path in SEMANTICS_DIR.glob("*.md") if path.name not in {README.name, MATRIX.name})
    missing = [name for name in specs if f"specs/formal/participant-semantics/{name}`" not in family]
    assert specs
    assert not missing, f"focused specifications without a family row: {missing}"


def test_every_declared_scope_uid_has_a_row() -> None:
    lines = README.read_text(encoding="utf-8").splitlines()
    declared = [
        UID.search(item).group(0)
        for item in _list_after(lines, "This document is the issue #71 formal design artifact for:")
    ]
    mapped = {uid for row in ROWS for uid in UID.findall(row["requirements"])}
    assert declared
    assert not [uid for uid in declared if uid not in mapped]


def test_rows_use_closed_vocabularies_and_list_their_evidence_classes() -> None:
    for row in ROWS:
        classes = set(_evidence(row))
        assert row["facet"] in FACETS, row["clause"]
        assert row["coverage"] in COVERAGE, row["clause"]
        assert classes <= CLASSES, row["clause"]
        assert row["classes"] == (", ".join(_evidence(row)) or DASH), row["clause"]
    assert {row["facet"] for row in ROWS} == FACETS


def test_cited_paths_and_test_functions_resolve() -> None:
    for row in ROWS:
        repository_paths = _paths(row["location"]) + _paths(row["contract"]) + _evidence(row).get("proof", [])
        assert all((REPO_ROOT / path).exists() for path in repository_paths), row["clause"]
        assert all((PACKAGES_DIR / path).exists() for path in _paths(row["implementation"])), row["clause"]
        tests = [ref for cls, refs in _evidence(row).items() if cls != "proof" for ref in refs]
        assert [ref for ref in tests if not _resolves(ref)] == [], row["clause"]


def test_runtime_tests_drive_shipped_packages() -> None:
    runtime_files = {ref.split("::")[0] for row in ROWS for ref in _evidence(row).get("runtime-test", [])}
    assert runtime_files
    assert sorted(name for name in runtime_files if not _imports_shipped_package(name)) == []


def test_coverage_follows_the_cited_evidence() -> None:
    for row in ROWS:
        cited = [row[column] != DASH for column in ("contract", "implementation", "tests")]
        if row["coverage"] == "covered":
            assert cited[:2] == [True, True], row["clause"]
            assert _evidence(row).get("runtime-test"), row["clause"]
        else:
            assert any(cited) == (row["coverage"] == "partial"), row["clause"]


def test_open_rows_name_an_owner_and_an_acceptance_test() -> None:
    for row in OPEN_ROWS:
        owners = _owners(row)
        acceptance = CODE.findall(row["acceptance"])
        assert owners, row["clause"]
        assert "219" not in owners, row["clause"]
        assert acceptance, row["clause"]
        assert TEST_REF.match(acceptance[0]), row["clause"]
    assert all(row["owner"] == row["acceptance"] == DASH for row in ROWS if row["coverage"] == "covered")


def test_relation_bound_rows_name_catalog_relations() -> None:
    relations = json.loads(CATALOG.read_text(encoding="utf-8"))["relations"]
    named = {relation for row in ROWS for relation in RELATION.findall(row["location"])}
    assert named
    assert named <= set(relations)


def test_requirement_cells_come_from_their_sources() -> None:
    oracle_refs = {
        call.args[0].value: {element.value for element in call.args[2].elts}
        for call in ast.walk(ast.parse(ORACLE.read_text(encoding="utf-8")))
        if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "Invariant"
    }
    runtime_scope = set(
        _list_after(
            RUNTIME_README.read_text(encoding="utf-8").splitlines(),
            "This document is the issue #74 formal design artifact for:",
        )
    )
    runtime_uids = {UID.search(item).group(0) for item in runtime_scope}
    for clause, row in BY_CLAUSE.items():
        if re.fullmatch(r"I\d+", clause):
            assert set(UID.findall(row["requirements"])) == oracle_refs[clause], clause
        elif clause.startswith("PBM-"):
            assert row["requirements"] == _pbm_table()[clause][1], clause
        elif clause.startswith("PRT-"):
            assert set(UID.findall(row["requirements"])) == runtime_uids, clause


def test_act606_aggregate_matches_the_behavior_specification_model() -> None:
    block = BEHAVIOR_README.read_text(encoding="utf-8").split("BehaviorSpecification =\n", 1)[1].split("```", 1)[0]
    entries = [line.strip() for line in block.splitlines() if line.strip()]
    plural = {
        entry: entry[:-2] + "ies" if entry.endswith("y*") else entry[:-1] + "s"
        for entry in entries
        if entry.endswith("*")
    }
    documented = {plural.get(entry, entry.rstrip("?")) for entry in entries}

    # spec_id is the behavior_specifications mapping key, not a model field.
    assert documented - {"spec_id"} == set(ParticipantBehaviorSpecification.model_fields)


@pytest.mark.parametrize("document", (README, BEHAVIOR_README), ids=lambda path: path.parent.name)
def test_backticked_repository_paths_exist(document: Path) -> None:
    # Code spans without whitespace, so code fences cannot shift the backtick pairing.
    candidates = re.findall(r"`([^`\s]+)`", document.read_text(encoding="utf-8"))
    paths = [token for token in candidates if "/" in token and PATH_TOKEN.match(token)]
    bases = (REPO_ROOT, PACKAGES_DIR, document.parent)
    assert paths
    assert sorted({path for path in paths if not any((base / path).exists() for base in bases)}) == []


def test_v1_decision_surface_admission_entries_are_mapped() -> None:
    v1_entries = [
        name for name, member in inspect.getmembers(ParticipantControlMixin, inspect.isfunction)
        if any(str(parameter.annotation) == "ParticipantDecisionSurfaceModel"
               for parameter in inspect.signature(member).parameters.values())
    ]  # fmt: skip
    row = next(row for row in ROWS if "SEM-220" in UID.findall(row["requirements"]))
    named = set(CODE.findall(row["implementation"]))
    assert v1_entries
    assert [name for name in v1_entries if f"ParticipantControlMixin.{name}" not in named] == []


def test_participant_waivers_are_tracked_by_matrix_owners() -> None:
    entries = yaml.safe_load(FULFILLMENT.read_text(encoding="utf-8"))["entries"]
    tracking = {
        ref.lstrip("#")
        for entry in entries if entry["subsystem"] in WAIVER_SUBSYSTEMS
        for waiver in entry.get("waived_artifacts") or [] for ref in waiver["tracking"]
    }  # fmt: skip
    owners = {owner for row in OPEN_ROWS for owner in _owners(row)}
    assert sorted(tracking - owners) == []
