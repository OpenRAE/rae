"""Issue #1734 / ADR-117: the grimp and import-linter bridge, with stand-in analyzer modules.

test_issue_1734_structural_integration.py runs the same bridge with the real
analyzers from the locked tooling environment.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from raes_contracts.errors import InvalidInputError, OperationalError
from rich.console import Console
from tools.policy import import_graph
from tools.policy.import_graph import CONTRACT_BROKEN, CONTRACT_KEPT, CONTRACT_UNMATCHED_IGNORES


class _GrimpError(Exception):
    pass


class _MissingImport(Exception):
    pass


class _InvalidOptions(Exception):
    pass


class _Graph:
    modules = {"fixa1734", "fixa1734.one", "fixa1734.two"}

    def find_modules_directly_imported_by(self, module: str) -> set[str]:
        return {"fixa1734.two"} if module == "fixa1734.one" else set()


class _Check:
    def __init__(self, kept: bool) -> None:
        self.kept = kept


class _Contract:
    outcome = "kept"

    def __init__(self, *, name: str, session_options: dict, contract_options: dict) -> None:
        if contract_options.get("invalid"):
            raise _InvalidOptions(name)
        self.name = name

    def check(self, graph: _Graph, verbose: bool) -> _Check:
        if self.outcome == "missing":
            raise _MissingImport("No matches for ignored import fixa1734.x -> fixa1734.y.")
        return _Check(self.outcome == "kept")

    def render_broken_contract(self, check: _Check) -> None:
        _CONSOLE.print("[red]fixa1734.two is not allowed to import fixa1734.one[/red]")


_CONSOLE = Console(force_terminal=True, color_system="standard")


def _modules(contracts: list[dict], *, graph_error: bool = False) -> dict[str, types.ModuleType]:
    def build_graph(*_packages: str, **_options: object) -> _Graph:
        if graph_error:
            raise _GrimpError("bad source")
        return _Graph()

    options = types.SimpleNamespace(session_options={}, contracts_options=contracts)
    return {
        "grimp": types.SimpleNamespace(
            build_graph=build_graph, exceptions=types.SimpleNamespace(GrimpException=_GrimpError)
        ),
        "importlinter.configuration": types.SimpleNamespace(configure=lambda: None),
        "importlinter.application.use_cases": types.SimpleNamespace(read_user_options=lambda config_filename: options),
        "importlinter.domain.contract": types.SimpleNamespace(InvalidContractOptions=_InvalidOptions),
        "importlinter.domain.helpers": types.SimpleNamespace(MissingImport=_MissingImport),
        "importlinter.application.output": types.SimpleNamespace(console=_CONSOLE),
        "importlinter.contracts.layers": types.SimpleNamespace(LayersContract=_Contract),
        "importlinter.contracts.acyclic_siblings": types.SimpleNamespace(AcyclicSiblingsContract=_Contract),
        "rich.text": __import__("rich.text", fromlist=["Text"]),
    }


@pytest.fixture
def package_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "src"
    (root / "fixa1734").mkdir(parents=True)
    (root / "fixa1734" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "path", list(sys.path))
    return root


def _analyze(monkeypatch: pytest.MonkeyPatch, root: Path, contracts: list[dict], **kwargs: bool):
    modules = _modules(contracts, **kwargs)
    monkeypatch.setattr(import_graph, "_load", lambda name: modules[name])
    monkeypatch.setattr(import_graph.importlib.metadata, "version", lambda name: {"grimp": "3.18"}.get(name, "2.15"))
    return import_graph.analyze_imports(
        [root], root / "contracts.toml", root_packages=["fixa1734"], exclude_type_checking_imports=True
    )


def test_the_bridge_returns_the_graph_imports_and_each_contract_result(
    monkeypatch: pytest.MonkeyPatch, package_root: Path
) -> None:
    contracts = [{"id": "raes-package-layers", "name": "layers", "type": "layers"}]
    monkeypatch.setattr(_Contract, "outcome", "kept")

    analysis = _analyze(monkeypatch, package_root, contracts)

    assert analysis.imports == frozenset({("fixa1734.one", "fixa1734.two")})
    assert analysis.modules == frozenset(_Graph.modules)
    assert [(result.contract_id, result.status) for result in analysis.contracts] == [
        ("raes-package-layers", CONTRACT_KEPT)
    ]
    assert analysis.versions == {"grimp": "3.18", "import-linter": "2.15"}


def test_broken_contracts_carry_plain_bounded_details_and_unmatched_ignores_are_distinct(
    monkeypatch: pytest.MonkeyPatch, package_root: Path
) -> None:
    contracts = [{"id": "raes-sibling-cycles", "name": "cycles", "type": "acyclic_siblings"}]

    monkeypatch.setattr(_Contract, "outcome", "broken")
    broken = _analyze(monkeypatch, package_root, contracts).contracts[0]
    monkeypatch.setattr(_Contract, "outcome", "missing")
    missing = _analyze(monkeypatch, package_root, contracts).contracts[0]

    assert broken.status == CONTRACT_BROKEN
    assert broken.details == ("fixa1734.two is not allowed to import fixa1734.one",)
    assert missing.status == CONTRACT_UNMATCHED_IGNORES
    assert "fixa1734.x -> fixa1734.y" in missing.details[0]


@pytest.mark.parametrize(
    ("contracts", "graph_error", "message"),
    [
        ([{"id": "x", "name": "x", "type": "forbidden"}], False, "not used by ADR-117"),
        ([{"id": "x", "name": "x", "type": "layers", "invalid": True}], False, "invalid options"),
        ([], True, "could not build the import graph"),
    ],
)
def test_unsupported_or_invalid_contracts_and_unparseable_source_are_refused(
    monkeypatch: pytest.MonkeyPatch, package_root: Path, contracts: list[dict], graph_error: bool, message: str
) -> None:
    with pytest.raises(InvalidInputError, match=message):
        _analyze(monkeypatch, package_root, contracts, graph_error=graph_error)


def test_a_root_package_must_resolve_inside_the_analyzed_source_root(
    monkeypatch: pytest.MonkeyPatch, package_root: Path, tmp_path: Path
) -> None:
    other_root = tmp_path / "other"
    other_root.mkdir()
    monkeypatch.setattr(import_graph, "_load", lambda name: _modules([])[name])

    import_graph._ensure_import_roots([package_root], ["fixa1734"])

    with pytest.raises(OperationalError, match="does not resolve to the analyzed source root"):
        import_graph._ensure_import_roots([other_root], ["fixa1734"])
    with pytest.raises(OperationalError, match="does not resolve to the analyzed source root"):
        import_graph._ensure_import_roots([package_root], ["fixmissing1734"])


def test_detail_lines_are_bounded() -> None:
    lines = import_graph._bounded_lines("\n".join(f"line {index}" for index in range(30)))

    assert len(lines) == 21
    assert lines[-1] == "(10 more lines)"
