from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from tools.check_semantic_coverage import (
    ADR_RELATIVE_PATH,
    CANONICAL_PHASES,
    COVERAGE_NOTE_RELATIVE_PATH,
    VALID_STATUSES,
    CoverageParseError,
    evaluate_semantic_coverage,
    main,
    parse_coverage_rows,
)

# A stub ADR-016 that references the coverage note by its repo-relative path, so
# the ADR↔note linkage check passes in the seeded temp repo.
_GOOD_ADR = """# ADR-016: Semantic Layer Scope and Coverage Model

## Status
accepted

## Decision
The live coverage table lives in `docs/explain/reference/shared-semantic-integrity.md`,
which this ADR governs.
"""

# A minimal but well-formed coverage note: prose, then a Coverage Model section
# with a table whose paths exist under the (temp) repo root.
_GOOD_NOTE = """# Shared Semantic Integrity

Guardrails note for SEM-200. The scope and coverage model are governed by
ADR-016 (../../decisions/adrs/adr-016-semantic-layer-scope-and-coverage-model.md).

## Coverage Model

Lifecycle phases (canonical, fixed): authoring, validation, instantiation,
compilation, planning, execution, observation.

| Construct family | Owning requirement(s) | Phases covered | Realizing artifacts | Status |
| --- | --- | --- | --- | --- |
| Objective windows | SEM-202 | validation, compilation, planning | `specs/formal/objectives/README.md`, `implementations/python/tests/test_semantics_objectives.py` | active |
| Assessment semantics | SEM-206, DSL-110 | — | — | planned |

## Non-Goals
Nothing else here.
"""

_ACTIVE_ROW = (
    "| Objective windows | SEM-202 | validation, compilation, planning | "
    "`specs/formal/objectives/README.md`, `implementations/python/tests/test_semantics_objectives.py` | active |"
)
_ARTIFACTS = "`specs/formal/objectives/README.md`, `implementations/python/tests/test_semantics_objectives.py`"
_PLANNED_ROW = "| Assessment semantics | SEM-206, DSL-110 | — | — | planned |"

_ARTIFACTS_IN_GOOD_NOTE = (
    "specs/formal/objectives/README.md",
    "implementations/python/tests/test_semantics_objectives.py",
)


def _seed_repo(tmp_path: Path, note_body: str = _GOOD_NOTE, adr_body: str | None = _GOOD_ADR) -> Path:
    """Create a temp repo skeleton: the coverage note, its governing ADR, and the artifacts named in the note."""
    note_path = tmp_path / COVERAGE_NOTE_RELATIVE_PATH
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(note_body, encoding="utf-8")
    if adr_body is not None:
        adr_path = tmp_path / ADR_RELATIVE_PATH
        adr_path.parent.mkdir(parents=True, exist_ok=True)
        adr_path.write_text(adr_body, encoding="utf-8")
    for rel in _ARTIFACTS_IN_GOOD_NOTE:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("placeholder\n", encoding="utf-8")
    return tmp_path


def _flagged(failures, marker: str) -> bool:
    """True if some failure matches ``marker`` by rule id or by a substring of its rendered text."""
    needle = marker.lower()
    return any(f.rule_id == marker or needle in f.render().lower() for f in failures)


# (case id, mutated coverage note, markers the checker must flag)
_NOTE_DEFECT_CASES = [
    ("section-missing", _GOOD_NOTE.replace("## Coverage Model", "## Something Else"), "coverage model"),
    ("status-unknown", _GOOD_NOTE.replace("| active |", "| done |"), ("done", "coverage-status")),
    (
        "phase-unknown",
        _GOOD_NOTE.replace("validation, compilation, planning", "validation, deployment"),
        ("deployment", "coverage-phase"),
    ),
    ("owner-bad-uid", _GOOD_NOTE.replace("| SEM-202 |", "| sem-202 |"), "sem-202"),
    (
        "artifact-missing",
        _GOOD_NOTE.replace("`specs/formal/objectives/README.md`", "`specs/formal/objectives/nope.md`"),
        ("nope.md", "coverage-artifact-missing"),
    ),
    (
        "artifact-unsupported",
        _GOOD_NOTE.replace("`specs/formal/objectives/README.md`", "`pyproject.toml`"),
        "coverage-artifact-unsupported",
    ),
    (
        "artifact-escapes-root",
        _GOOD_NOTE.replace("`specs/formal/objectives/README.md`", "`specs/../../escape.md`"),
        "coverage-artifact-escape",
    ),
    (
        "active-no-artifacts",
        _GOOD_NOTE.replace(_ACTIVE_ROW, "| Objective windows | SEM-202 | validation | — | active |"),
        "coverage-incomplete",
    ),
    (
        "active-only-prose-artifact",
        _GOOD_NOTE.replace(_ARTIFACTS, "objective window semantics live in the validator"),
        "coverage-incomplete",
    ),
    (
        "active-no-test-artifact",
        _GOOD_NOTE.replace(_ARTIFACTS, "`specs/formal/objectives/README.md`"),
        "coverage-untested",
    ),
    (
        "active-only-test-artifact",
        _GOOD_NOTE.replace(_ARTIFACTS, "`implementations/python/tests/test_semantics_objectives.py`"),
        "coverage-incomplete",
    ),
    (
        "planned-has-artifacts",
        _GOOD_NOTE.replace(
            _PLANNED_ROW,
            "| Assessment semantics | SEM-206 | validation | `specs/formal/objectives/README.md` | planned |",
        ),
        "coverage-planned",
    ),
    (
        "planned-has-phases",
        _GOOD_NOTE.replace(_PLANNED_ROW, "| Assessment semantics | SEM-206 | validation | — | planned |"),
        "coverage-planned",
    ),
]


@pytest.mark.parametrize(
    ("note_body", "markers"), [(n, m) for _, n, m in _NOTE_DEFECT_CASES], ids=[c for c, _, _ in _NOTE_DEFECT_CASES]
)
def test_note_defect_is_flagged(tmp_path: Path, note_body: str, markers: str | tuple[str, ...]) -> None:
    failures = evaluate_semantic_coverage(_seed_repo(tmp_path, note_body))
    for marker in (markers,) if isinstance(markers, str) else markers:
        assert _flagged(failures, marker), marker


# (case id, ADR-016 body — or None to omit the file entirely, expected rule id)
_ADR_LINKAGE_CASES = [
    ("adr-absent", None, "coverage-adr-missing"),
    ("adr-no-reference", "# ADR-016: Something\n\n## Status\naccepted\n", "coverage-adr-unlinked"),
    (
        "adr-basename-only",
        "# ADR-016: X\n\n## Status\naccepted\n\nSee shared-semantic-integrity.md.\n",
        "coverage-adr-unlinked",
    ),
]


@pytest.mark.parametrize(
    ("adr_body", "rule_id"), [(b, r) for _, b, r in _ADR_LINKAGE_CASES], ids=[c for c, _, _ in _ADR_LINKAGE_CASES]
)
def test_adr_linkage_defect_is_flagged(tmp_path: Path, adr_body: str | None, rule_id: str) -> None:
    failures = evaluate_semantic_coverage(_seed_repo(tmp_path, adr_body=adr_body))
    assert any(f.rule_id == rule_id for f in failures)


def test_well_formed_note_passes(tmp_path: Path) -> None:
    assert evaluate_semantic_coverage(_seed_repo(tmp_path)) == []


def test_missing_note_fails(tmp_path: Path) -> None:
    failures = evaluate_semantic_coverage(tmp_path)
    assert any(f.rule_id == "coverage-note-missing" for f in failures)


def test_malformed_row_column_count_fails(tmp_path: Path) -> None:
    repo = _seed_repo(
        tmp_path, _GOOD_NOTE.replace(_PLANNED_ROW, "| Assessment semantics | SEM-206, DSL-110 | — | planned |")
    )
    failures = evaluate_semantic_coverage(repo)
    assert any(f.rule_id == "coverage-model-parse" for f in failures)


def test_no_table_raises_parse_error() -> None:
    with pytest.raises(CoverageParseError):
        parse_coverage_rows("# Note\n\n## Coverage Model\n\nNo table here.\n\n## Next\nDone.\n")


def test_missing_section_raises_parse_error() -> None:
    with pytest.raises(CoverageParseError):
        parse_coverage_rows("# Note\n\nNothing relevant.\n")


def test_parse_rows_returns_expected_count() -> None:
    rows = parse_coverage_rows(_GOOD_NOTE)
    assert len(rows) == 2
    assert rows[0].family == "Objective windows"
    assert rows[0].owners == ["SEM-202"]
    assert rows[0].phases == ["validation", "compilation", "planning"]
    assert rows[0].status == "active"
    assert rows[1].owners == ["SEM-206", "DSL-110"]
    assert rows[1].phases == []
    assert rows[1].status == "planned"


def test_row_line_number_accounts_for_prose_before_table() -> None:
    body = (
        "# Reference Note\n"  # line 1
        "\n"  # line 2
        "Intro paragraph.\n"  # line 3
        "\n"  # line 4
        "## Coverage Model\n"  # line 5
        "\n"  # line 6
        "Lifecycle phases: authoring, validation.\n"  # line 7
        "Some more prose before the table.\n"  # line 8
        "\n"  # line 9
        "| Construct family | Owning requirement(s) | Phases covered | Realizing artifacts | Status |\n"  # line 10
        "| --- | --- | --- | --- | --- |\n"  # line 11
        "| Objective windows | SEM-202 | validation | `specs/x.md` | active |\n"  # line 12
        "| Future thing | SEM-999 | — | — | planned |\n"  # line 13
        "\n"
        "## Next Section\nDone.\n"
    )
    rows = parse_coverage_rows(body)
    assert [row.line_no for row in rows] == [12, 13]


def test_cli_returns_nonzero_on_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo-root", str(tmp_path)]) == 1
    assert capsys.readouterr().err.strip()


def test_cli_returns_zero_when_clean(tmp_path: Path) -> None:
    assert main(["--repo-root", str(_seed_repo(tmp_path))]) == 0


@pytest.mark.integration
def test_repo_coverage_note_is_well_formed() -> None:
    """The real SEM-200 coverage note must pass the structural coverage gate."""
    assert evaluate_semantic_coverage(REPO_ROOT) == []


def test_constants_are_sane() -> None:
    assert "validation" in CANONICAL_PHASES
    assert set(VALID_STATUSES) == {"active", "partial", "planned"}
    assert COVERAGE_NOTE_RELATIVE_PATH.endswith("shared-semantic-integrity.md")
    assert ADR_RELATIVE_PATH.endswith("adr-016-semantic-layer-scope-and-coverage-model.md")


# --------------------------------------------------------------------------- #
# Integration check (#504): an active row's named test must import a realizing
# module, and the named test functions must contain assertions. The seeded repo
# below carries a real package tree, optional compat wrappers, and real test
# bodies so the AST resolver has something to resolve.
# --------------------------------------------------------------------------- #

_INTEGRATION_NOTE = """# Shared Semantic Integrity

Governed by ADR-016
(../../decisions/adrs/adr-016-semantic-layer-scope-and-coverage-model.md).

## Coverage Model

| Construct family | Owning requirement(s) | Phases covered | Realizing artifacts | Status |
| --- | --- | --- | --- | --- |
{rows}

## Non-Goals
Nothing else.
"""


def _seed_integration_repo(tmp_path: Path, *, rows: str, files: dict[str, str]) -> Path:
    """Seed a temp repo: coverage note + governing ADR + a real package/test tree."""
    note_path = tmp_path / COVERAGE_NOTE_RELATIVE_PATH
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(_INTEGRATION_NOTE.format(rows=rows), encoding="utf-8")
    adr_path = tmp_path / ADR_RELATIVE_PATH
    adr_path.parent.mkdir(parents=True, exist_ok=True)
    adr_path.write_text(_GOOD_ADR, encoding="utf-8")
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp_path


_WIDGET_ROW = (
    "| Widget | ABC-001 | validation | "
    "`implementations/python/packages/widget/core.py`, "
    "`implementations/python/tests/test_widget.py` | active |"
)
_WIDGET_CORE = "implementations/python/packages/widget/core.py"
_WIDGET_INIT = "implementations/python/packages/widget/__init__.py"
_WIDGET_TEST = "implementations/python/tests/test_widget.py"


def _rule_ids(failures) -> set[str]:
    return {f.rule_id for f in failures}


def test_active_row_named_test_not_importing_module_fails(tmp_path: Path) -> None:
    repo = _seed_integration_repo(
        tmp_path,
        rows=_WIDGET_ROW,
        files={
            _WIDGET_INIT: "",
            _WIDGET_CORE: "VALUE = 1\n",
            # imports nothing from widget.core — the hollow case
            _WIDGET_TEST: "def test_widget():\n    assert True\n",
        },
    )
    failures = evaluate_semantic_coverage(repo)
    assert "coverage-test-integration" in _rule_ids(failures)


def test_active_row_direct_import_passes(tmp_path: Path) -> None:
    repo = _seed_integration_repo(
        tmp_path,
        rows=_WIDGET_ROW,
        files={
            _WIDGET_INIT: "",
            _WIDGET_CORE: "VALUE = 1\n",
            _WIDGET_TEST: "from widget.core import VALUE\n\ndef test_widget():\n    assert VALUE == 1\n",
        },
    )
    assert evaluate_semantic_coverage(repo) == []


def test_active_row_import_via_package_reexport_passes(tmp_path: Path) -> None:
    repo = _seed_integration_repo(
        tmp_path,
        rows=_WIDGET_ROW,
        files={
            _WIDGET_INIT: "from widget.core import VALUE\n",
            _WIDGET_CORE: "VALUE = 1\n",
            # imports the symbol from the package, not the submodule
            _WIDGET_TEST: "from widget import VALUE\n\ndef test_widget():\n    assert VALUE == 1\n",
        },
    )
    assert "coverage-test-integration" not in _rule_ids(evaluate_semantic_coverage(repo))


def test_active_row_import_via_relative_package_reexport_passes(tmp_path: Path) -> None:
    # The idiomatic package-API form: ``__init__`` re-exports the symbol with a
    # relative import (#504 review IMP-2 F1). The resolver must map the package
    # symbol back to ``widget.core`` just as it does for the absolute form.
    repo = _seed_integration_repo(
        tmp_path,
        rows=_WIDGET_ROW,
        files={
            _WIDGET_INIT: "from .core import VALUE\n",
            _WIDGET_CORE: "VALUE = 1\n",
            _WIDGET_TEST: "from widget import VALUE\n\ndef test_widget():\n    assert VALUE == 1\n",
        },
    )
    assert "coverage-test-integration" not in _rule_ids(evaluate_semantic_coverage(repo))


def test_active_row_import_via_relative_submodule_reexport_passes(tmp_path: Path) -> None:
    # The ``from . import core`` submodule re-export form: the test reaches the
    # submodule through the package namespace (``widget.core``).
    repo = _seed_integration_repo(
        tmp_path,
        rows=_WIDGET_ROW,
        files={
            _WIDGET_INIT: "from . import core\n",
            _WIDGET_CORE: "VALUE = 1\n",
            _WIDGET_TEST: "from widget import core\n\ndef test_widget():\n    assert core.VALUE == 1\n",
        },
    )
    assert "coverage-test-integration" not in _rule_ids(evaluate_semantic_coverage(repo))


def test_stub_test_function_fails(tmp_path: Path) -> None:
    repo = _seed_integration_repo(
        tmp_path,
        rows=_WIDGET_ROW,
        files={
            _WIDGET_INIT: "",
            _WIDGET_CORE: "VALUE = 1\n",
            # imports the module (integration ok) but asserts nothing
            _WIDGET_TEST: "from widget.core import VALUE\n\ndef test_widget():\n    VALUE\n",
        },
    )
    assert "coverage-stub-test" in _rule_ids(evaluate_semantic_coverage(repo))


def test_pytest_raises_counts_as_assertion(tmp_path: Path) -> None:
    repo = _seed_integration_repo(
        tmp_path,
        rows=_WIDGET_ROW,
        files={
            _WIDGET_INIT: "",
            _WIDGET_CORE: "def boom():\n    raise ValueError\n",
            _WIDGET_TEST: (
                "import pytest\n"
                "from widget.core import boom\n\n"
                "def test_widget():\n"
                "    with pytest.raises(ValueError):\n"
                "        boom()\n"
            ),
        },
    )
    assert "coverage-stub-test" not in _rule_ids(evaluate_semantic_coverage(repo))


def test_active_row_with_no_module_artifact_skips_integration(tmp_path: Path) -> None:
    row = "| Doc only | ABC-001 | validation | `specs/doc.md`, `implementations/python/tests/test_doc.py` | active |"
    repo = _seed_integration_repo(
        tmp_path,
        rows=row,
        files={
            "specs/doc.md": "doc\n",
            "implementations/python/tests/test_doc.py": "def test_doc():\n    assert True\n",
        },
    )
    failures = evaluate_semantic_coverage(repo)
    assert "coverage-test-integration" not in _rule_ids(failures)
    assert failures == []


def test_report_mode_groups_families_by_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = _WIDGET_ROW + "\n| Future thing | ABC-002 | — | — | planned |"
    repo = _seed_integration_repo(
        tmp_path,
        rows=rows,
        files={
            _WIDGET_INIT: "",
            _WIDGET_CORE: "VALUE = 1\n",
            _WIDGET_TEST: "from widget.core import VALUE\n\ndef test_widget():\n    assert VALUE == 1\n",
        },
    )
    assert main(["--report", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "active" in out
    assert "planned" in out
    assert "Widget" in out
    assert "1/1" in out  # module coverage count surfaced
