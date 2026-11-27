"""ADR-117 bridge to grimp and import-linter.

This is the only module that imports them. They come from the locked tooling
environment. grimp parses the package source; nothing imports or runs it. The
graph is built without a cache, so no earlier run can change the result.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from raes_contracts.errors import InvalidInputError, OperationalError

ANALYZER_DISTRIBUTIONS = ("grimp", "import-linter")
CONTRACT_KEPT = "kept"
CONTRACT_BROKEN = "broken"
CONTRACT_UNMATCHED_IGNORES = "unmatched-ignores"
_DETAIL_LINE_LIMIT = 20
_CONTRACT_TYPES = {
    "layers": ("importlinter.contracts.layers", "LayersContract"),
    "acyclic_siblings": ("importlinter.contracts.acyclic_siblings", "AcyclicSiblingsContract"),
}


@dataclass(frozen=True)
class ContractResult:
    contract_id: str
    status: str
    details: tuple[str, ...]


@dataclass(frozen=True)
class ImportAnalysis:
    modules: frozenset[str]
    imports: frozenset[tuple[str, str]]
    contracts: tuple[ContractResult, ...]
    versions: Mapping[str, str]


def analyze_imports(
    packages_roots: Sequence[Path],
    config_path: Path,
    *,
    root_packages: Sequence[str],
    exclude_type_checking_imports: bool,
) -> ImportAnalysis:
    """Build the import graph of ``root_packages`` and check each contract in ``config_path``.

    Raise ``OperationalError`` when the analyzers are not installed or a root
    package resolves outside ``packages_roots``, and ``InvalidInputError`` for
    source that grimp cannot parse or an invalid contract.
    """

    grimp = _load("grimp")
    configuration = _load("importlinter.configuration")
    use_cases = _load("importlinter.application.use_cases")
    contract_module = _load("importlinter.domain.contract")
    helpers = _load("importlinter.domain.helpers")
    console = _load("importlinter.application.output").console
    _ensure_import_roots(packages_roots, root_packages)
    configuration.configure()
    try:
        graph = grimp.build_graph(
            *root_packages,
            include_external_packages=False,
            exclude_type_checking_imports=exclude_type_checking_imports,
            cache_dir=None,
        )
    except grimp.exceptions.GrimpException as exc:
        raise InvalidInputError(f"grimp could not build the import graph: {type(exc).__name__}") from exc
    user_options = use_cases.read_user_options(config_filename=str(config_path))
    results: list[ContractResult] = []
    for options in user_options.contracts_options:
        contract_type = options.get("type")
        if contract_type not in _CONTRACT_TYPES:
            raise InvalidInputError(f"{config_path.name}: contract type {contract_type!r} is not used by ADR-117")
        module_name, class_name = _CONTRACT_TYPES[contract_type]
        contract_class = getattr(_load(module_name), class_name)
        try:
            contract = contract_class(
                name=options["name"],
                session_options=user_options.session_options,
                contract_options=options,
            )
        except contract_module.InvalidContractOptions as exc:
            raise InvalidInputError(f"{config_path.name}: contract {options.get('id')!r} has invalid options") from exc
        results.append(_check(contract, options.get("id", options["name"]), graph, helpers, console))
    imports = frozenset(
        (importer, imported)
        for importer in graph.modules
        for imported in graph.find_modules_directly_imported_by(importer)
    )
    return ImportAnalysis(
        modules=frozenset(graph.modules),
        imports=imports,
        contracts=tuple(results),
        versions={name: importlib.metadata.version(name) for name in ANALYZER_DISTRIBUTIONS},
    )


def _check(contract: object, contract_id: str, graph: object, helpers: ModuleType, console: object) -> ContractResult:
    try:
        # A contract removes its ignored imports from the graph, so it gets a copy.
        check = contract.check(deepcopy(graph), verbose=False)
    except helpers.MissingImport as exc:
        return ContractResult(contract_id, CONTRACT_UNMATCHED_IGNORES, _bounded_lines(str(exc)))
    if check.kept:
        return ContractResult(contract_id, CONTRACT_KEPT, ())
    with console.capture() as capture:
        contract.render_broken_contract(check)
    return ContractResult(contract_id, CONTRACT_BROKEN, _bounded_lines(_plain(capture.get())))


def _load(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise OperationalError(
            "the structural checks need grimp and import-linter from the locked tooling environment"
        ) from exc


def _ensure_import_roots(packages_roots: Sequence[Path], root_packages: Sequence[str]) -> None:
    """Put the package roots on the import path and verify where each root package resolves."""

    resolved_roots = [root.resolve() for root in packages_roots]
    for root in reversed(resolved_roots):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    expected = {root / name for root in resolved_roots for name in root_packages}
    for name in root_packages:
        spec = importlib.util.find_spec(name)
        locations = list(spec.submodule_search_locations or ()) if spec is not None else []
        if len(locations) != 1 or Path(locations[0]).resolve() not in expected:
            raise OperationalError(f"package {name!r} does not resolve to the analyzed source root")


def _plain(text: str) -> str:
    rich_text = _load("rich.text")
    return rich_text.Text.from_ansi(text).plain


def _bounded_lines(text: str) -> tuple[str, ...]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) > _DETAIL_LINE_LIMIT:
        omitted = len(lines) - _DETAIL_LINE_LIMIT
        lines = [*lines[:_DETAIL_LINE_LIMIT], f"({omitted} more lines)"]
    return tuple(lines)
