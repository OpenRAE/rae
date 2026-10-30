"""ADR-117 private-import check: private names and private modules imported from another module.

A name that starts with ``_`` is private, except a special name of the form
``__name__`` (PEP 8). A private module is private to its parent package, so a
module inside that package can import it. A private name is private to the
module that defines it.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass

from raes_contracts.errors import InvalidInputError

from .source_index import SourceIndex, SourceModule


@dataclass(frozen=True, order=True)
class PrivateImport:
    importer: str
    target: str


def is_private_name(name: str) -> bool:
    special = len(name) > 4 and name.startswith("__") and name.endswith("__")
    return name.startswith("_") and not special


def collect_private_imports(index: SourceIndex) -> Counter[PrivateImport]:
    """Count each private import of each module, including imports in functions and type-checking blocks."""

    findings: Counter[PrivateImport] = Counter()
    for module in index.modules.values():
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _private_module_path(module.name, alias.name):
                        findings[PrivateImport(module.name, alias.name)] += 1
            elif isinstance(node, ast.ImportFrom):
                source = resolve_import_source(module, node.level, node.module)
                for target in _from_import_findings(index, module, source, node):
                    findings[PrivateImport(module.name, target)] += 1
    return findings


def resolve_import_source(module: SourceModule, level: int, name: str | None) -> str:
    """Return the absolute module name of a ``from`` import, following its relative level."""

    if level == 0:
        return name or ""
    package = module.name.split(".") if module.is_package else module.name.split(".")[:-1]
    if level - 1 >= len(package):
        raise InvalidInputError(f"{module.rel_path}: a relative import goes above the top-level package")
    base = package[: len(package) - (level - 1)]
    return ".".join([*base, name] if name else base)


def _from_import_findings(index: SourceIndex, module: SourceModule, source: str, node: ast.ImportFrom) -> list[str]:
    findings: list[str] = []
    for alias in node.names:
        if alias.name == "*":
            if _private_module_path(module.name, source):
                findings.append(source)
            findings.extend(
                f"{source}.{name}"
                for name in _star_exports(index, module, source)
                if is_private_name(name) and source != module.name
            )
            continue
        target = f"{source}.{alias.name}"
        if target in index.modules:
            # The name is a submodule, so the module rule decides.
            private = _private_module_path(module.name, target)
        else:
            private = _private_module_path(module.name, source) or (
                is_private_name(alias.name) and source != module.name
            )
        if private:
            findings.append(target)
    return findings


def _private_module_path(importer: str, module_path: str) -> bool:
    """Tell whether ``module_path`` has a private part that is outside the importer's reach."""

    parts = module_path.split(".")
    for position, part in enumerate(parts):
        if not is_private_name(part):
            continue
        if position == 0:
            return True
        owner = ".".join(parts[:position])
        if importer != owner and not importer.startswith(f"{owner}."):
            return True
    return False


def _star_exports(index: SourceIndex, importer: SourceModule, source: str) -> tuple[str, ...]:
    """Return the names that ``from source import *`` binds explicitly through ``__all__``.

    Without ``__all__`` a star import binds only public names. The module-level
    statements that update ``__all__``, directly or through a name bound to the
    same list, are applied in order: an assignment of a literal sequence, ``+=``
    with one, and ``extend`` or ``append`` with literals. Any other use cannot be
    read statically, so the check fails closed.
    """

    exporter = index.modules.get(source)
    if exporter is None:
        return ()
    context = f"{importer.rel_path}: star import from {source}"
    names: list[str] | None = None
    aliases = frozenset({"__all__"})
    for statement in exporter.tree.body:
        if any(isinstance(node, ast.Name) and node.id in aliases for node in ast.walk(statement)):
            names, aliases = _updated_all(statement, names, aliases, context)
    return tuple(names or ())


def _updated_all(
    statement: ast.stmt, names: list[str] | None, aliases: frozenset[str], context: str
) -> tuple[list[str] | None, frozenset[str]]:
    """Apply one module-level statement that uses ``__all__`` or a name bound to the same list."""

    def mentions(node: ast.AST) -> bool:
        return any(isinstance(item, ast.Name) and item.id in aliases for item in ast.walk(node))

    if isinstance(statement, (ast.Assign, ast.AnnAssign)):
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        target = targets[0].id if len(targets) == 1 and isinstance(targets[0], ast.Name) else None
        value = statement.value
        if target is not None and value is not None:
            if isinstance(value, ast.Name) and value.id in aliases:
                # Another name for the same list; the list itself does not change.
                return names, aliases | {target}
            if not mentions(value):
                if target == "__all__":
                    return _literal_names(value, context), aliases
                if target in aliases:
                    # The name now refers to another object, so it no longer aliases the list.
                    return names, aliases - {target}
    elif isinstance(statement, ast.AugAssign):
        target = statement.target
        if names is not None and isinstance(target, ast.Name) and target.id in aliases:
            if isinstance(statement.op, ast.Add) and not mentions(statement.value):
                return [*names, *_literal_names(statement.value, context)], aliases
    elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        call = statement.value
        receiver = call.func.value if isinstance(call.func, ast.Attribute) else None
        method = call.func.attr if isinstance(receiver, ast.Name) and receiver.id in aliases else None
        if names is not None and method in {"extend", "append"} and len(call.args) == 1 and not call.keywords:
            argument = call.args[0]
            if method == "append":
                argument = ast.List(elts=[argument], ctx=ast.Load())
            if not mentions(argument):
                return [*names, *_literal_names(argument, context)], aliases
    raise InvalidInputError(f"{context}, whose __all__ changes in a way the check cannot read statically")


def _literal_names(value: ast.expr, context: str) -> list[str]:
    try:
        names = ast.literal_eval(value)
    except (ValueError, TypeError) as exc:
        raise InvalidInputError(f"{context}, whose __all__ is not a literal list of names") from exc
    if not isinstance(names, (list, tuple)) or not all(isinstance(name, str) for name in names):
        raise InvalidInputError(f"{context}, whose __all__ is not a literal list of names")
    return list(names)
