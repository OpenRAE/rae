"""ASR-526 clause map checks (#222, first done-when item).

``docs/research/conformance-reporting/clause-map.md`` splits the ASR-526
statement into clauses. It maps each clause to the backend reporting that
meets it and names the processor reporting that is missing. These checks keep
the map tied to the statement and to the code, tests and pages it cites.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLAUSE_MAP = ROOT / "docs/research/conformance-reporting/clause-map.md"
REQUIREMENT = ROOT / "docs/requirements/ASR-526/requirement.md"
CODE_ROOT = ROOT / "implementations/python/packages"
TEST_ROOT = Path(__file__).resolve().parent

# Written independently of the map: the statement words each clause covers.
CLAUSE_WORDS = {
    "C1": "machine-readable",
    "C2": "human-readable",
    "C3": "achieved conformance profile or level",
    "C4": "passed and failed checks",
    "C5": "declared and observed unsupported or partially supported capabilities",
    "C6": "applicable validation basis",
    "C7": "diagnostics sufficient to explain gaps or limitations",
}
# Statement words that frame the clauses rather than add one.
FRAME_WORDS = (
    "The ecosystem shall provide",
    "conformance and support reports",
    "for processors and backends",
    "that expose",
)
STATUSES = {"covered", "partial", "gap"}

_ROW = re.compile(r'^\| (C\d+) \| "([^"]+)" \| (\w+) \| (\w+) \|$', re.MULTILINE)
_SECTION_HEADING = re.compile(r"### (C\d+) ")
_LEAD = re.compile(r"\*\*(Backends|Processors): (\w+)\.\*\*")
# `path::symbol`, where a quoted symbol names a string constant in that file.
_CODE_CITATION = re.compile(r"`(?!test_)([\w/.-]+\.(?:py|json))::([^`]+)`")
_QUOTED = re.compile(r'"([^"]+)"')
_DEFINITIONS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_TEST_CITATION = re.compile(r"`(test_\w+\.py)(?:::(\w+))?`")
_LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")


def _page() -> str:
    return CLAUSE_MAP.read_text(encoding="utf-8")


def _statement() -> str:
    record = REQUIREMENT.read_text(encoding="utf-8")
    return record.split("\n## Statement\n", 1)[1].split("\n## ", 1)[0].strip()


def _sections() -> dict[str, str]:
    """Each clause's evidence section, keyed by its label, in page order."""

    parts = re.split(r"^(?=#{2,3} )", _page(), flags=re.MULTILINE)
    labelled = [(match.group(1), part) for part in parts if (match := _SECTION_HEADING.match(part))]
    assert len(labelled) == len(dict(labelled)), "a clause has more than one section"
    return dict(labelled)


def test_clauses_and_frame_words_cover_the_whole_statement() -> None:
    statement = _statement()
    phrases = (*CLAUSE_WORDS.values(), *FRAME_WORDS)
    remainder = statement
    for phrase in phrases:
        remainder = remainder.replace(phrase, " ", 1)

    assert [phrase for phrase in phrases if phrase not in statement] == []
    # Only the joining "and" and punctuation may be left once every phrase is gone.
    assert set(re.findall(r"[A-Za-z-]+", remainder)) <= {"and"}, remainder


def test_every_clause_has_one_row_and_one_section_that_agree() -> None:
    rows = _ROW.findall(_page())
    sections = _sections()

    assert [label for label, *_ in rows] == list(CLAUSE_WORDS)
    assert {label: words for label, words, *_ in rows} == CLAUSE_WORDS
    assert list(sections) == list(CLAUSE_WORDS)
    for label, _words, backends, processors in rows:
        table = {"Backends": backends.lower(), "Processors": processors.lower()}
        assert set(table.values()) <= STATUSES, label
        assert dict(_LEAD.findall(sections[label])) == table, label


def _scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """The nodes of ``scope``, without the bodies of the definitions nested in it."""

    for child in ast.iter_child_nodes(scope):
        yield child
        if not isinstance(child, _DEFINITIONS):
            yield from _scope_nodes(child)


def _binds(node: ast.AST, name: str) -> bool:
    """Whether ``node`` defines or assigns ``name``, or passes it as a call keyword."""

    if isinstance(node, _DEFINITIONS):
        return node.name == name
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Store) and node.id == name
    return isinstance(node, ast.keyword) and node.arg == name


def _defines(tree: ast.Module, symbol: str) -> bool:
    """Whether each part of a dotted ``symbol`` is bound in the scope that the part before it names."""

    scopes: list[ast.AST] = [tree]
    for name in symbol.split("."):
        scopes = [node for scope in scopes for node in _scope_nodes(scope) if _binds(node, name)]
    return bool(scopes)


def _cites_existing_code(path: str, symbol: str) -> bool:
    source = (ROOT if path.startswith("contracts/") else CODE_ROOT) / path
    if not source.is_file():
        return False
    text = source.read_text(encoding="utf-8")
    quoted = _QUOTED.fullmatch(symbol)
    if source.suffix == ".json":
        # A JSON citation names a string that the document holds.
        return quoted is not None and json.dumps(quoted.group(1)) in text
    tree = ast.parse(text)
    if quoted:
        return any(isinstance(node, ast.Constant) and node.value == quoted.group(1) for node in ast.walk(tree))
    return _defines(tree, symbol)


def test_cited_code_symbols_exist() -> None:
    citations = list(_CODE_CITATION.finditer(_page()))

    assert citations
    assert [match.group(0) for match in citations if not _cites_existing_code(*match.groups())] == []


def _test_exists(module: str, function: str) -> bool:
    source = TEST_ROOT / module
    if not source.is_file():
        return False
    tree = ast.parse(source.read_text(encoding="utf-8"))
    return not function or function in {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def test_cited_tests_exist() -> None:
    citations = _TEST_CITATION.findall(_page())

    assert citations
    assert [f"{module}::{function}" for module, function in citations if not _test_exists(module, function)] == []


def test_links_open_existing_pages() -> None:
    targets = [
        target.split("#", 1)[0]
        for target in _LINK_TARGET.findall(_page())
        if not target.startswith(("http://", "https://"))
    ]

    assert targets
    assert [target for target in targets if not (CLAUSE_MAP.parent / target).is_file()] == []
