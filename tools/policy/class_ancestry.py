"""ADR-117 class-ancestry check: count the distinct package-defined ancestors of each class.

The resolver reads source statically. It follows relative imports, aliases,
re-exports, star imports, nested classes and subscripted bases. It does not
count external or builtin classes. A base that it cannot resolve to a class,
or to an external name, is reported instead of being counted as zero.
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Mapping
from dataclasses import dataclass, field

from raes_contracts.errors import InvalidInputError

from .private_imports import resolve_import_source
from .source_index import SourceIndex, SourceModule

_BASE_TEXT_LIMIT = 120


@dataclass(frozen=True)
class UnresolvedBase:
    class_id: str
    base: str
    reason: str
    rel_path: str


@dataclass(frozen=True)
class AncestryResult:
    counts: Mapping[str, int]
    unresolved: tuple[UnresolvedBase, ...]


@dataclass(frozen=True)
class _ClassRef:
    module: str
    qualname: str

    @property
    def class_id(self) -> str:
        return f"{self.module}:{self.qualname}"


@dataclass(frozen=True)
class _ModuleRef:
    name: str


@dataclass(frozen=True)
class _ValueRef:
    """A binding that is not a class or a module, such as a function."""


@dataclass(frozen=True)
class _FromBinding:
    source: str
    name: str


@dataclass(frozen=True)
class _AliasBinding:
    expression: ast.expr
    scopes: _Scopes
    lineno: int


_EXTERNAL = object()
# The scopes that a name lookup searches, innermost first. The flag marks a scope
# that is still executing when the definition runs, so only its earlier bindings apply.
_Scopes = tuple[tuple["_Table", bool], ...]


@dataclass(eq=False)
class _Table:
    """The names that one scope binds, in source order."""

    bindings: dict[str, list[tuple[int, object]]] = field(default_factory=dict)

    def bind(self, name: str, lineno: int, binding: object) -> None:
        self.bindings.setdefault(name, []).append((lineno, binding))

    def lookup(self, name: str, before: int | None) -> object | None:
        found = None
        for lineno, binding in self.bindings.get(name, ()):
            if before is None or lineno < before:
                found = binding
        return found


@dataclass(frozen=True)
class _ClassInfo:
    ref: _ClassRef
    node: ast.ClassDef
    scopes: _Scopes
    rel_path: str


class _Unresolved(InvalidInputError):
    """A base expression that does not resolve to a class or an external name."""


def analyze_class_ancestry(index: SourceIndex) -> AncestryResult:
    resolver = _Resolver(index)
    counts = {info.ref.class_id: len(resolver.ancestors(info.ref)) for info in resolver.classes.values()}
    return AncestryResult(counts=counts, unresolved=resolver.unresolved_bases())


class _Resolver:
    def __init__(self, index: SourceIndex) -> None:
        self._index = index
        self.classes: dict[_ClassRef, _ClassInfo] = {}
        self._module_tables: dict[str, _Table] = {}
        self._stars: dict[str, list[str]] = {}
        self._memo: dict[_ClassRef, frozenset[_ClassRef]] = {}
        self._unresolved: dict[tuple[str, str], UnresolvedBase] = {}
        for module in index.modules.values():
            table = _Table()
            self._module_tables[module.name] = table
            self._stars[module.name] = []
            self._walk(module, module.tree.body, table, (), "", table)

    # Scope construction -------------------------------------------------

    def _walk(
        self,
        module: SourceModule,
        body: list[ast.stmt],
        local: _Table,
        functions: tuple[_Table, ...],
        prefix: str,
        module_table: _Table,
    ) -> None:
        scopes = _scopes(local, functions, module_table)
        for statement in body:
            if isinstance(statement, ast.ClassDef):
                ref = _ClassRef(module.name, f"{prefix}{statement.name}")
                local.bind(statement.name, statement.lineno, ref)
                self.classes[ref] = _ClassInfo(ref, statement, scopes, module.rel_path)
                self._walk(module, statement.body, _Table(), functions, f"{ref.qualname}.", module_table)
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local.bind(statement.name, statement.lineno, _ValueRef())
                function_table = _Table()
                self._walk(
                    module,
                    statement.body,
                    function_table,
                    (*functions, function_table),
                    f"{prefix}{statement.name}.<locals>.",
                    module_table,
                )
            elif bodies := _nested_bodies(statement):
                # Definitions inside a compound statement belong to the enclosing scope.
                for nested in bodies:
                    self._walk(module, nested, local, functions, prefix, module_table)
            else:
                self._bind_simple(module, statement, local, scopes)

    def _bind_simple(self, module: SourceModule, statement: ast.stmt, local: _Table, scopes: _Scopes) -> None:
        lineno = statement.lineno
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.asname:
                    local.bind(alias.asname, lineno, _ModuleRef(alias.name))
                else:
                    top = alias.name.split(".", 1)[0]
                    local.bind(top, lineno, _ModuleRef(top))
        elif isinstance(statement, ast.ImportFrom):
            source = resolve_import_source(module, statement.level, statement.module)
            for alias in statement.names:
                if alias.name == "*":
                    self._stars[module.name].append(source)
                else:
                    local.bind(alias.asname or alias.name, lineno, _FromBinding(source, alias.name))
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    local.bind(target.id, lineno, _AliasBinding(statement.value, scopes, lineno))
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name) and statement.value is not None:
                local.bind(statement.target.id, lineno, _AliasBinding(statement.value, scopes, lineno))
        elif isinstance(statement, ast.TypeAlias):
            local.bind(statement.name.id, lineno, _AliasBinding(statement.value, scopes, lineno))

    # Resolution ---------------------------------------------------------

    def ancestors(self, ref: _ClassRef, stack: tuple[_ClassRef, ...] = ()) -> frozenset[_ClassRef]:
        if ref in self._memo:
            return self._memo[ref]
        info = self.classes[ref]
        result: set[_ClassRef] = set()
        for base in info.node.bases:
            try:
                value = self._resolve(ref.module, base, info.scopes, info.node.lineno, frozenset())
            except _Unresolved as exc:
                self._record(info, base, str(exc))
                continue
            if value is _EXTERNAL:
                continue
            if not isinstance(value, _ClassRef):
                self._record(info, base, "the base is not a class")
                continue
            if value == ref or value in stack:
                cycle = (*stack[stack.index(value) :], ref) if value in stack else (ref,)
                for member in cycle:
                    self._record(self.classes[member], base, "the inheritance is cyclic")
                continue
            result.add(value)
            result.update(self.ancestors(value, (*stack, ref)))
        frozen = frozenset(result)
        self._memo[ref] = frozen
        return frozen

    def unresolved_bases(self) -> tuple[UnresolvedBase, ...]:
        return tuple(sorted(self._unresolved.values(), key=lambda item: (item.class_id, item.base)))

    def _record(self, info: _ClassInfo, base: ast.expr, reason: str) -> None:
        text = ast.unparse(base)[:_BASE_TEXT_LIMIT]
        key = (info.ref.class_id, text)
        self._unresolved.setdefault(key, UnresolvedBase(info.ref.class_id, text, reason, info.rel_path))

    def _resolve(
        self,
        module: str,
        expression: ast.expr,
        scopes: _Scopes,
        before: int | None,
        seen: frozenset[object],
    ) -> object:
        if isinstance(expression, ast.Name):
            return self._lookup_name(module, scopes, expression.id, before, seen)
        if isinstance(expression, ast.Attribute):
            owner = self._resolve(module, expression.value, scopes, before, seen)
            return self._attribute(owner, expression.attr, seen)
        if isinstance(expression, ast.Subscript):
            return self._resolve(module, expression.value, scopes, before, seen)
        if isinstance(expression, ast.Call):
            if self._resolve(module, expression.func, scopes, before, seen) is _EXTERNAL:
                return _EXTERNAL
            raise _Unresolved("the base is the result of a package call")
        raise _Unresolved("the base expression is not supported")

    def _lookup_name(
        self, module: str, scopes: _Scopes, name: str, before: int | None, seen: frozenset[object]
    ) -> object:
        for table, executing in scopes:
            binding = table.lookup(name, before if executing else None)
            if binding is not None:
                return self._binding_value(module, binding, seen)
        star = self._star_lookup(module, name, seen)
        if star is not None:
            return star
        if hasattr(builtins, name):
            return _EXTERNAL
        raise _Unresolved(f"the name {name!r} is not defined")

    def _attribute(self, owner: object, name: str, seen: frozenset[object]) -> object:
        if owner is _EXTERNAL:
            return _EXTERNAL
        if isinstance(owner, _ModuleRef):
            return self._module_attribute(owner.name, name, seen)
        if isinstance(owner, _ClassRef):
            nested = _ClassRef(owner.module, f"{owner.qualname}.{name}")
            if nested in self.classes:
                return nested
            raise _Unresolved(f"{owner.class_id} defines no class {name!r}")
        raise _Unresolved("an attribute of a value that is not a module or a class")

    def _binding_value(self, module: str, binding: object, seen: frozenset[object]) -> object:
        if isinstance(binding, (_ClassRef, _ValueRef)):
            return binding
        if isinstance(binding, _ModuleRef):
            return binding if self._index.is_first_party(binding.name) else _EXTERNAL
        if isinstance(binding, _FromBinding):
            if not self._index.is_first_party(binding.source):
                return _EXTERNAL
            submodule = f"{binding.source}.{binding.name}"
            if submodule in self._index.modules:
                return _ModuleRef(submodule)
            return self._module_attribute(binding.source, binding.name, seen)
        if isinstance(binding, _AliasBinding):
            if binding in seen:
                raise _Unresolved("the alias is cyclic")
            return self._resolve(module, binding.expression, binding.scopes, binding.lineno, seen | {binding})
        raise _Unresolved("the binding is not supported")

    def _module_attribute(self, module: str, name: str, seen: frozenset[object]) -> object:
        key = (module, name)
        if key in seen:
            raise _Unresolved("the re-export is cyclic")
        table = self._module_tables.get(module)
        if table is None:
            raise _Unresolved(f"the package module {module!r} does not exist")
        binding = table.lookup(name, None)
        if binding is not None:
            return self._binding_value(module, binding, seen | {key})
        submodule = f"{module}.{name}"
        if submodule in self._index.modules:
            return _ModuleRef(submodule)
        star = self._star_lookup(module, name, seen | {key})
        if star is not None:
            return star
        raise _Unresolved(f"the package module {module!r} has no name {name!r}")

    def _star_lookup(self, module: str, name: str, seen: frozenset[object]) -> object | None:
        external_star = False
        for source in self._stars.get(module, ()):
            if not self._index.is_first_party(source):
                external_star = True
                continue
            try:
                return self._module_attribute(source, name, seen)
            except _Unresolved:
                continue
        return _EXTERNAL if external_star else None


def _scopes(local: _Table, functions: tuple[_Table, ...], module_table: _Table) -> _Scopes:
    """Return the lookup scopes of a definition in ``local``.

    Python resolves a name in a class body through that body, the enclosing
    functions and the module; enclosing class bodies are not visible. The local
    scope and the innermost function are executing at definition time; the
    module is executing too when no function encloses the definition.
    """

    ordered: dict[_Table, bool] = {local: True}
    for depth, function in enumerate(reversed(functions)):
        ordered.setdefault(function, depth == 0)
    ordered.setdefault(module_table, not functions)
    return tuple(ordered.items())


def _nested_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    bodies: list[list[ast.stmt]] = []
    for attribute in ("body", "orelse", "finalbody"):
        value = getattr(statement, attribute, None)
        if isinstance(value, list):
            bodies.append(value)
    for handler in getattr(statement, "handlers", ()) or ():
        bodies.append(handler.body)
    for case in getattr(statement, "cases", ()) or ():
        bodies.append(case.body)
    return bodies
