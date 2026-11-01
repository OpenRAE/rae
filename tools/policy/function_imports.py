"""ADR-117 check 5: first-party imports inside functions.

An import inside a function hides an edge from the import order of its module.
When it only defers a cycle, the cycle stays in place (ADR-121). An import inside
a module-level ``__getattr__`` (PEP 562) loads a lazy export and is not a
finding. Imports of modules outside the analyzed packages are not findings.

The identity of a finding is the importing module and the imported module.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

from .private_imports import resolve_import_source
from .source_index import SourceIndex, SourceModule

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


@dataclass(frozen=True, order=True)
class FunctionImport:
    importer: str
    imported: str


def collect_function_imports(index: SourceIndex) -> Counter[FunctionImport]:
    """Count each first-party import statement inside a function of each module."""

    return Counter(
        FunctionImport(module.name, imported)
        for module in index.modules.values()
        for node in _function_level_imports(module)
        for imported in _imported_modules(index, module, node)
    )


def _function_level_imports(module: SourceModule) -> Iterator[ast.Import | ast.ImportFrom]:
    for statement in module.tree.body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef) and statement.name == "__getattr__":
            continue
        yield from _imports_in_functions(statement, inside_function=isinstance(statement, _FUNCTION_NODES))


def _imports_in_functions(node: ast.AST, *, inside_function: bool) -> Iterator[ast.Import | ast.ImportFrom]:
    for child in ast.iter_child_nodes(node):
        if inside_function and isinstance(child, ast.Import | ast.ImportFrom):
            yield child
        yield from _imports_in_functions(child, inside_function=inside_function or isinstance(child, _FUNCTION_NODES))


def _imported_modules(index: SourceIndex, module: SourceModule, node: ast.Import | ast.ImportFrom) -> list[str]:
    """Return the first-party module that one import statement loads, as one identity per statement."""

    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names if index.is_first_party(alias.name)]
    source = resolve_import_source(module, node.level, node.module)
    if not index.is_first_party(source):
        return []
    submodules = [f"{source}.{alias.name}" for alias in node.names if f"{source}.{alias.name}" in index.modules]
    return submodules or [source]


__all__ = ["FunctionImport", "collect_function_imports"]
