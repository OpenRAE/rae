"""ADR-117 check 6: a dynamic first-party import must name its target.

``importlib.import_module``, ``importlib.__import__``, ``builtins.__import__`` and
``importlib.util.find_spec`` load modules that the static import graph does not
see. The check resolves each name through the imports and simple assignments of
its scope, also across first-party modules. A name can have more than one value,
for example after a conditional assignment, a deletion or two star imports. The
check keeps each possible value, so a call is an import when any value of its
callable is an import function. Thus an alias such as
``from importlib import import_module as load`` is seen, and an unrelated
``obj.import_module`` is not. A call is resolved when:

- its target is a string literal. A relative ``import_module`` or ``find_spec``
  target needs a literal ``package``, ``__package__`` or ``__name__``. A relative
  ``__import__`` target needs a literal ``level`` and ``globals()``. A
  ``fromlist`` must be a literal list or tuple of strings; or
- inside a module-level ``__getattr__`` (PEP 562), its argument is the first
  target of a ``for`` loop over a literal ``_LAZY_EXPORTS`` dict, its ``keys()`` or
  its ``items()``. Each key of the dict is then a target. The module must only
  read the dict, and no other module may reach it.

Each target becomes an edge of the import graph, so the layer, boundary and
cycle checks see it. ``structural_checks.dynamic_import_allowlist`` names each
other call, with its reason. Any other call fails closed, and so does any other
use that passes on one of these callables or the ``importlib``,
``importlib.util`` or ``builtins`` module.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Hashable, Iterator, Sequence
from dataclasses import dataclass, field
from importlib.util import resolve_name

from raes_contracts.errors import InvalidInputError

from .source_index import SourceIndex, SourceModule

LAZY_EXPORTS_NAME = "_LAZY_EXPORTS"
_LAZY_GETATTR = "__getattr__"
_MODULE_LEVEL = "<module>"

# The values that a name or an attribute can have. A first-party module is "fp:<name>".
_IMPORTLIB = "std:importlib"
_IMPORTLIB_UTIL = "std:importlib.util"
_BUILTINS = "std:builtins"
_IMPORT_MODULE = "call:import_module"
_DUNDER_IMPORT = "call:__import__"
_FIND_SPEC = "call:find_spec"
_UNKNOWN = "unknown"
_FIRST_PARTY = "fp:"
_CALLS = frozenset({_IMPORT_MODULE, _DUNDER_IMPORT, _FIND_SPEC})
_TRACKED = _CALLS | {_IMPORTLIB, _IMPORTLIB_UTIL, _BUILTINS}

Values = frozenset[str]
_NO_VALUES: Values = frozenset()
_UNKNOWN_VALUES: Values = frozenset({_UNKNOWN})
_BUILTIN_VALUES = {"__import__": _DUNDER_IMPORT, "__builtins__": _BUILTINS}
_LAZY_READS = frozenset({"keys", "items", "values", "get"})

_STANDARD_MODULES = {"importlib": _IMPORTLIB, "importlib.util": _IMPORTLIB_UTIL, "builtins": _BUILTINS}
_ATTRIBUTES = {
    (_IMPORTLIB, "import_module"): _IMPORT_MODULE,
    (_IMPORTLIB, "__import__"): _DUNDER_IMPORT,
    (_IMPORTLIB, "util"): _IMPORTLIB_UTIL,
    (_IMPORTLIB_UTIL, "find_spec"): _FIND_SPEC,
    (_BUILTINS, "__import__"): _DUNDER_IMPORT,
}
_STAR_EXPORTS = {
    _IMPORTLIB: ("import_module", "__import__"),
    _IMPORTLIB_UTIL: ("find_spec",),
    _BUILTINS: ("__import__",),
}
_SCOPE_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ClassDef,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)
# In these scopes a bound name is local everywhere, so it never falls back to a builtin.
_LOCAL_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


@dataclass(frozen=True)
class DynamicImportAllowance:
    module: str
    function: str
    reason: str


@dataclass(frozen=True, order=True)
class HiddenImport:
    module: str
    function: str
    line: int


@dataclass(frozen=True)
class HiddenImportAnalysis:
    edges: frozenset[tuple[str, str]]
    unresolved: tuple[HiddenImport, ...]
    unused_allowances: tuple[DynamicImportAllowance, ...]


def parse_dynamic_import_allowlist(value: object) -> tuple[DynamicImportAllowance, ...]:
    """Read ``structural_checks.dynamic_import_allowlist``: entries of module, function and reason."""

    if value is None:
        return ()
    if not isinstance(value, list):
        raise InvalidInputError("structural_checks.dynamic_import_allowlist must be a list")
    allowances: list[DynamicImportAllowance] = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"module", "function", "reason"}:
            raise InvalidInputError(
                "each dynamic_import_allowlist entry must have exactly the keys module, function and reason"
            )
        if not all(isinstance(entry[key], str) and entry[key].strip() for key in ("module", "function", "reason")):
            raise InvalidInputError("dynamic_import_allowlist module, function and reason must be non-empty strings")
        allowances.append(DynamicImportAllowance(entry["module"], entry["function"], entry["reason"]))
    if len({(item.module, item.function) for item in allowances}) != len(allowances):
        raise InvalidInputError("dynamic_import_allowlist must not repeat a module and function")
    return tuple(allowances)


def analyze_hidden_imports(
    index: SourceIndex, allowances: Sequence[DynamicImportAllowance] = ()
) -> HiddenImportAnalysis:
    """Find each dynamic first-party import; return its graph edges and each use that names no target."""

    program = _Program(index)
    while True:
        inspected = {name: program.module(name).inspect() for name in sorted(index.modules)}
        if not program.next_pass():
            break
    allowed = {(item.module, item.function): item for item in allowances}
    used: set[tuple[str, str]] = set()
    edges: set[tuple[str, str]] = set()
    unresolved: set[HiddenImport] = set()
    for name, (targets, findings) in inspected.items():
        edges.update((name, target) for target in targets if index.is_first_party(target))
        for owner, line in findings:
            if (name, owner) in allowed:
                used.add((name, owner))
            else:
                unresolved.add(HiddenImport(name, owner, line))
    unused = tuple(item for key, item in allowed.items() if key not in used)
    return HiddenImportAnalysis(frozenset(edges), tuple(sorted(unresolved)), unused)


class _Program:
    """The scope analyses of all modules, so that a name can resolve through another first-party module.

    The values of names and module attributes grow to a fixpoint. A lookup that meets itself in a
    cycle reads the value of the previous pass, and the analysis repeats until no value grows.
    """

    def __init__(self, index: SourceIndex) -> None:
        self.index = index
        self._modules: dict[str, _ModuleAnalysis] = {}
        self._memo: dict[Hashable, Values] = {}
        self._previous: dict[Hashable, Values] = {}
        self._active: set[Hashable] = set()
        self._approximated = False
        self.lazy_tables_escape = _lazy_tables_escape(index)

    def module(self, name: str) -> _ModuleAnalysis:
        if name not in self._modules:
            self._modules[name] = _ModuleAnalysis(self, self.index.modules[name])
        return self._modules[name]

    def lookup(self, key: Hashable, compute: Callable[[], Values]) -> Values:
        if key in self._memo:
            return self._memo[key]
        if key in self._active:
            self._approximated = True
            return self._previous.get(key, _NO_VALUES)
        self._active.add(key)
        try:
            value = compute()
        finally:
            self._active.discard(key)
        self._memo[key] = value
        return value

    def next_pass(self) -> bool:
        """Report whether a cyclic lookup read a value that grew in this pass, and reset for the next pass."""

        again = self._approximated and self._memo != self._previous
        self._previous, self._memo, self._approximated = self._memo, {}, False
        return again

    def module_attribute(self, module: str, name: str) -> Values:
        """Resolve ``name`` at module level of a first-party module and as its submodule."""

        return self.lookup(("attribute", module, name), lambda: self._module_attribute(module, name))

    def _module_attribute(self, module: str, name: str) -> Values:
        if module not in self.index.modules:
            return _UNKNOWN_VALUES
        analysis = self.module(module)
        values: set[str] = set()
        if name in analysis.root.bindings or analysis.root.star_sources:
            values |= analysis.resolve_name(name, analysis.root)
        submodule = f"{module}.{name}"
        if submodule in self.index.modules:
            values.add(_FIRST_PARTY + submodule)
        return frozenset(values) if values else _UNKNOWN_VALUES

    def star_attribute(self, source: str, name: str) -> Values | None:
        """Resolve a name that ``from <source> import *`` may bind; ``None`` when the source cannot bind it.

        A private name counts when the source mentions ``__all__``, because ``__all__`` can list it.
        """

        module = source.removeprefix(_FIRST_PARTY)
        if module not in self.index.modules:
            return _UNKNOWN_VALUES
        analysis = self.module(module)
        exported = (analysis.declares_all or not name.startswith("_")) and (
            name in analysis.root.bindings or bool(analysis.root.star_sources)
        )
        return self.module_attribute(module, name) if exported else None


@dataclass(frozen=True)
class _Pending:
    """The right side of a simple assignment, resolved on use."""

    node: ast.AST


@dataclass(frozen=True)
class _ImportedName:
    """A name bound by ``from <source> import <name>``, resolved on use."""

    source: str
    name: str


@dataclass
class _Scope:
    owner: str
    parent: _Scope | None
    node: ast.AST | None = None
    bindings: dict[str, list[str | _Pending | _ImportedName]] = field(default_factory=dict)
    global_names: set[str] = field(default_factory=set)
    nonlocal_names: set[str] = field(default_factory=set)
    star_sources: list[str] = field(default_factory=list)
    visible_to_nested: bool = True

    def bind(self, name: str, value: str | _Pending | _ImportedName) -> None:
        self.bindings.setdefault(name, []).append(value)


class _ModuleAnalysis:
    def __init__(self, program: _Program, module: SourceModule) -> None:
        self._program = program
        self._module = module
        self._package = module.name if module.is_package else module.name.rpartition(".")[0]
        self._parents: dict[ast.AST, ast.AST] = {}
        self._node_scope: dict[ast.AST, _Scope] = {}
        self.root = _Scope(_MODULE_LEVEL, None, module.tree)
        for node in ast.walk(module.tree):
            for child in ast.iter_child_nodes(node):
                self._parents[child] = node
        self._collect_body(module.tree.body, self.root)
        self.declares_all = any(isinstance(node, ast.Name) and node.id == "__all__" for node in ast.walk(module.tree))
        self._lazy_targets = () if program.lazy_tables_escape else _lazy_export_targets(module, self._parents)

    # Scopes and bindings

    def _collect_body(self, statements: Sequence[ast.AST], scope: _Scope) -> None:
        for statement in statements:
            self._collect(statement, scope)

    def _collect(self, node: ast.AST, scope: _Scope) -> None:
        self._node_scope[node] = scope
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            scope.bind(node.name, _UNKNOWN)
            self._open(node, scope)
            return
        if isinstance(node, ast.Lambda):
            self._open(node, scope)
            return
        if isinstance(node, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp):
            self._open_comprehension(node, scope)
            return
        self._bind(node, scope)
        for child in ast.iter_child_nodes(node):
            self._collect(child, scope)

    def _open(self, node: ast.AST, scope: _Scope) -> None:
        inner = _Scope(self._qualified(scope, node), scope, node, visible_to_nested=not isinstance(node, ast.ClassDef))
        arguments = getattr(node, "args", None)
        if isinstance(arguments, ast.arguments):
            for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]:
                inner.bind(argument.arg, _UNKNOWN)
            for argument in (arguments.vararg, arguments.kwarg):
                if argument is not None:
                    inner.bind(argument.arg, _UNKNOWN)
        body = node.body if isinstance(node.body, list) else [node.body]
        for child in ast.iter_child_nodes(node):
            if child in body:
                continue
            self._collect(child, scope)
        self._collect_body(body, inner)

    def _open_comprehension(self, node: ast.AST, scope: _Scope) -> None:
        inner = _Scope(scope.owner, scope, node)
        first_iter = node.generators[0].iter
        self._collect(first_iter, scope)
        for generator in node.generators:
            for name in _names(generator.target):
                inner.bind(name, _UNKNOWN)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.comprehension):
                self._node_scope[child] = inner
                for part in ast.iter_child_nodes(child):
                    if part is not first_iter:
                        self._collect(part, inner)
            else:
                self._collect(child, inner)

    def _bind(self, node: ast.AST, scope: _Scope) -> None:
        if isinstance(node, ast.Global):
            scope.global_names.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            scope.nonlocal_names.update(node.names)
        elif isinstance(node, ast.Import):
            self._bind_import(node, scope)
        elif isinstance(node, ast.ImportFrom):
            self._bind_from_import(node, scope)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            for name, value in _assignment_bindings(node):
                scope.bind(name, value)
        else:
            for name in _untracked_binding_names(node):
                scope.bind(name, _UNKNOWN)

    def _bind_import(self, node: ast.Import, scope: _Scope) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.partition(".")[0]
            scope.bind(bound, self._module_value(alias.name if alias.asname else bound))

    def _bind_from_import(self, node: ast.ImportFrom, scope: _Scope) -> None:
        source = self._absolute(("." * node.level) + (node.module or ""), self._package) if node.level else node.module
        source_value = self._module_value(source) if source else _UNKNOWN
        for alias in node.names:
            if alias.name == "*":
                for name in _STAR_EXPORTS.get(source_value, ()):
                    scope.bind(name, _ATTRIBUTES[(source_value, name)])
                if source_value.startswith(_FIRST_PARTY):
                    scope.star_sources.append(source_value)
                continue
            scope.bind(alias.asname or alias.name, _ImportedName(source_value, alias.name))

    def _module_value(self, name: str) -> str:
        if name in _STANDARD_MODULES:
            return _STANDARD_MODULES[name]
        if name in self._program.index.modules:
            return _FIRST_PARTY + name
        return _UNKNOWN

    @staticmethod
    def _qualified(scope: _Scope, node: ast.AST) -> str:
        name = getattr(node, "name", "<lambda>")
        return name if scope.owner == _MODULE_LEVEL else f"{scope.owner}.{name}"

    # Resolution

    def resolve_name(self, name: str, scope: _Scope) -> Values:
        return self._program.lookup(
            ("name", self._module.name, id(scope), name), lambda: self._resolve_name(name, scope)
        )

    def _resolve_name(self, name: str, scope: _Scope) -> Values:
        current: _Scope | None = scope
        while current is not None:
            if name in current.global_names:
                current = self.root
                continue
            if name in current.nonlocal_names:
                current = current.parent
                continue
            values = self._scope_values(name, current) if current is scope or current.visible_to_nested else None
            if values is not None:
                # Module and class code can run before a binding or after a deletion and then see the builtin.
                if name in _BUILTIN_VALUES and not isinstance(current.node, _LOCAL_SCOPES):
                    values |= {_BUILTIN_VALUES[name]}
                return values
            current = current.parent
        return frozenset({_BUILTIN_VALUES.get(name, _UNKNOWN)})

    def _scope_values(self, name: str, scope: _Scope) -> Values | None:
        """Return each value that a binding or a star import of ``scope`` can give ``name``, else ``None``."""

        found = False
        values: set[str] = set()
        for value in scope.bindings.get(name, ()):
            found = True
            values |= self._value(value, scope)
        for source in scope.star_sources:
            star = self._program.star_attribute(source, name)
            if star is not None:
                found = True
                values |= star
        return frozenset(values) if found else None

    def _value(self, value: str | _Pending | _ImportedName, scope: _Scope) -> Values:
        if isinstance(value, _ImportedName):
            return self._attribute(value.source, value.name)
        if isinstance(value, _Pending):
            return self.resolve(value.node, scope)
        return frozenset({value})

    def resolve(self, node: ast.AST, scope: _Scope) -> Values:
        if isinstance(node, ast.Name):
            return self.resolve_name(node.id, scope)
        if isinstance(node, ast.Attribute):
            values: set[str] = set()
            for owner in self.resolve(node.value, scope):
                values |= self._attribute(owner, node.attr)
            return frozenset(values)
        return _UNKNOWN_VALUES

    def _attribute(self, owner: str, name: str) -> Values:
        if owner.startswith(_FIRST_PARTY):
            return self._program.module_attribute(owner.removeprefix(_FIRST_PARTY), name)
        return frozenset({_ATTRIBUTES.get((owner, name), _UNKNOWN)})

    # Inspection

    def inspect(self) -> tuple[set[str], list[tuple[str, int]]]:
        targets: set[str] = set()
        findings: list[tuple[str, int]] = []
        for node in ast.walk(self._module.tree):
            scope = self._node_scope.get(node, self.root)
            if isinstance(node, ast.Call):
                self._inspect_call(node, scope, targets, findings)
            elif self._passes_on_tracked_value(node, scope):
                findings.append((scope.owner, node.lineno))
        return targets, findings

    def _inspect_call(self, call: ast.Call, scope: _Scope, targets: set[str], findings: list[tuple[str, int]]) -> None:
        kinds = self.resolve(call.func, scope) & _CALLS
        if not kinds:
            return
        resolved = self._all_call_targets(call, kinds, scope)
        if resolved is None:
            findings.append((scope.owner, call.lineno))
        else:
            targets.update(resolved)

    def _passes_on_tracked_value(self, node: ast.AST, scope: _Scope) -> bool:
        """Report whether a load of a tracked callable or module leaves the uses that the check can follow."""

        if not isinstance(node, ast.Name | ast.Attribute) or not isinstance(node.ctx, ast.Load):
            return False
        return bool(self.resolve(node, scope) & _TRACKED) and not self._passes_through(node)

    def _all_call_targets(self, call: ast.Call, kinds: Values, scope: _Scope) -> set[str] | None:
        """Return the targets of a call for each import function that its callable can be, else ``None``."""

        resolved: set[str] = set()
        for kind in sorted(kinds):
            targets = self._call_targets(call, kind, scope)
            if targets is None:
                return None
            resolved |= targets
        return resolved

    def _passes_through(self, node: ast.AST) -> bool:
        """Report whether a use of a tracked value stays visible: a call, an attribute or a simple alias."""

        parent = self._parents.get(node)
        if isinstance(parent, ast.Attribute):
            scope = self._node_scope.get(node, self.root)
            return parent.value is node and not any(value.startswith("call:") for value in self.resolve(node, scope))
        return _is_callable_or_alias_value(parent, node)

    def _call_targets(self, call: ast.Call, kind: str, scope: _Scope) -> set[str] | None:
        if kind == _DUNDER_IMPORT:
            return self._dunder_import_targets(call)
        name = _argument(call, 0, "name")
        literal = _string(name)
        if literal is None:
            lazy = kind == _IMPORT_MODULE and self._from_lazy_table(name, call, scope)
            return set(self._lazy_targets) if lazy else None
        return _loaded_modules(kind, self._relative(literal, _argument(call, 1, "package")))

    def _relative(self, name: str, package: ast.AST | None) -> str | None:
        if not name.startswith("."):
            return name or None
        anchor = _string(package)
        if anchor is None and isinstance(package, ast.Name):
            anchor = {"__package__": self._package, "__name__": self._module.name}.get(package.id)
        return self._absolute(name, anchor) if anchor else None

    @staticmethod
    def _absolute(name: str, package: str | None) -> str | None:
        if not package:
            return None
        try:
            return resolve_name(name, package)
        except ImportError, ValueError:
            return None

    def _dunder_import_targets(self, call: ast.Call) -> set[str] | None:
        base = self._dunder_import_base(call)
        items = _fromlist(_argument(call, 3, "fromlist"))
        if base is None or items is None:
            return None
        modules = self._program.index.modules
        return {base, *(f"{base}.{item}" for item in items if f"{base}.{item}" in modules)}

    def _dunder_import_base(self, call: ast.Call) -> str | None:
        """Return the absolute module that ``__import__`` loads first, or ``None`` when no literal names it."""

        name = _string(_argument(call, 0, "name"))
        level_node = _argument(call, 4, "level")
        level = 0 if level_node is None else _integer(level_node)
        if name is None or level is None or level < 0:
            return None
        if not level:
            return name or None
        globals_given = _is_globals_call(_argument(call, 1, "globals"))
        return self._absolute("." * level + name, self._package) if globals_given else None

    def _from_lazy_table(self, argument: ast.AST | None, call: ast.Call, scope: _Scope) -> bool:
        if not self._is_lazy_getattr(scope) or not isinstance(argument, ast.Name):
            return False
        if len(scope.bindings.get(argument.id, ())) != 1 or argument.id in scope.global_names | scope.nonlocal_names:
            return False
        loops = (node for node in self._ancestors(call, scope.node) if isinstance(node, ast.For))
        return any(_loop_binds(loop, argument.id) for loop in loops)

    def _is_lazy_getattr(self, scope: _Scope) -> bool:
        """Report whether ``scope`` is the module-level ``__getattr__`` of a module with a lazy table."""

        return (
            bool(self._lazy_targets)
            and scope.owner == _LAZY_GETATTR
            and isinstance(scope.node, ast.FunctionDef)
            and self._parents.get(scope.node) is self._module.tree
        )

    def _ancestors(self, node: ast.AST, stop: ast.AST | None) -> Iterator[ast.AST]:
        current = self._parents.get(node)
        while current is not None and current is not stop:
            yield current
            current = self._parents.get(current)


def _names(target: ast.AST) -> list[str]:
    return [node.id for node in ast.walk(target) if isinstance(node, ast.Name)]


# Statements that bind a target expression, and nodes that bind one name, to values the check does not track.
_TARGET_FIELDS = {ast.AugAssign: "target", ast.NamedExpr: "target", ast.For: "target", ast.AsyncFor: "target"}
_NAME_FIELDS = {ast.ExceptHandler: "name", ast.MatchAs: "name", ast.MatchStar: "name", ast.MatchMapping: "rest"}


def _assignment_bindings(node: ast.Assign | ast.AnnAssign) -> list[tuple[str, str | _Pending]]:
    """Return each name that an assignment binds: a simple one to its value, any other to an untracked value."""

    if isinstance(node, ast.Assign):
        simple = len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        value: str | _Pending = _Pending(node.value) if simple else _UNKNOWN
        return [(name, value) for target in node.targets for name in _names(target)]
    pending = node.value is not None and isinstance(node.target, ast.Name)
    value = _Pending(node.value) if pending else _UNKNOWN
    return [(name, value) for name in _names(node.target)]


def _untracked_binding_names(node: ast.AST) -> list[str]:
    """Return the names that a node binds to a value the check does not track."""

    targets: list[ast.AST] = []
    if type(node) in _TARGET_FIELDS:
        targets = [getattr(node, _TARGET_FIELDS[type(node)])]
    elif isinstance(node, ast.withitem) and node.optional_vars is not None:
        targets = [node.optional_vars]
    elif isinstance(node, ast.Delete):
        targets = list(node.targets)
    names = [name for target in targets for name in _names(target)]
    single = getattr(node, _NAME_FIELDS[type(node)], None) if type(node) in _NAME_FIELDS else None
    return [*names, single] if single else names


def _is_callable_or_alias_value(parent: ast.AST | None, node: ast.AST) -> bool:
    """Report whether ``node`` is the callable of a call or the whole value of a simple assignment."""

    if isinstance(parent, ast.Call):
        return parent.func is node
    if isinstance(parent, ast.Assign):
        return parent.value is node and len(parent.targets) == 1 and isinstance(parent.targets[0], ast.Name)
    return isinstance(parent, ast.AnnAssign) and parent.value is node and isinstance(parent.target, ast.Name)


def _loaded_modules(kind: str, resolved: str | None) -> set[str] | None:
    """Return the modules that ``import_module`` or ``find_spec`` loads for a resolved target."""

    if resolved is None:
        return None
    if kind == _FIND_SPEC:
        parent = resolved.rpartition(".")[0]
        return {parent} if parent else set()
    return {resolved}


def _fromlist(node: ast.AST | None) -> tuple[str, ...] | None:
    return () if node is None or _is_empty(node) else _strings(node)


class _Unresolvable(ast.AST):
    """A position filled by ``*args`` or ``**kwargs``; it never resolves."""


def _argument(call: ast.Call, position: int, keyword: str) -> ast.AST | None:
    named = next((item.value for item in call.keywords if item.arg == keyword), None)
    if named is not None:
        return named
    starred = any(isinstance(item, ast.Starred) for item in call.args[: position + 1])
    if starred or (position >= len(call.args) and any(item.arg is None for item in call.keywords)):
        return _Unresolvable()
    return call.args[position] if position < len(call.args) else None


def _string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _integer(node: ast.AST) -> int | None:
    return node.value if isinstance(node, ast.Constant) and type(node.value) is int else None


def _is_empty(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _strings(node: ast.AST) -> tuple[str, ...] | None:
    if not isinstance(node, ast.List | ast.Tuple):
        return None
    values = [_string(item) for item in node.elts]
    return None if any(value is None for value in values) else tuple(value for value in values if value is not None)


def _is_globals_call(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "globals"
        and not node.args
        and not node.keywords
    )


def _loop_binds(loop: ast.For, name: str) -> bool:
    """Report whether a loop binds ``name`` to each key of the lazy table."""

    iterated = loop.iter
    target = loop.target
    if _is_lazy_table(iterated) or _is_lazy_call(iterated, "keys"):
        return isinstance(target, ast.Name) and target.id == name
    return (
        _is_lazy_call(iterated, "items")
        and isinstance(target, ast.Tuple)
        and len(target.elts) == 2
        and isinstance(target.elts[0], ast.Name)
        and target.elts[0].id == name
    )


def _is_lazy_table(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == LAZY_EXPORTS_NAME


def _is_lazy_call(node: ast.AST, method: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and not node.args
        and not node.keywords
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and _is_lazy_table(node.func.value)
    )


def _lazy_tables_escape(index: SourceIndex) -> bool:
    """Report whether any module reaches a lazy-export table as an attribute or imports it by name."""

    for module in index.modules.values():
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Attribute) and node.attr == LAZY_EXPORTS_NAME:
                return True
            if isinstance(node, ast.alias) and node.name == LAZY_EXPORTS_NAME:
                return True
    return False


def _lazy_export_targets(module: SourceModule, parents: dict[ast.AST, ast.AST]) -> tuple[str, ...]:
    """Return the keys of the module's literal ``_LAZY_EXPORTS`` dict, made absolute.

    The dict must be the only binding of the name in the module. Each other use must be a read that
    the check models, and no string may name the table. Otherwise the module has no lazy targets.
    """

    table = _lazy_exports_table(module, parents)
    if table is None:
        return ()
    keys = [key.value for key in table.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)]
    if len(keys) != len(table.keys):
        raise InvalidInputError(f"{module.rel_path}: {LAZY_EXPORTS_NAME} keys must be string literals")
    package = module.name if module.is_package else module.name.rpartition(".")[0]
    return tuple(key if not key.startswith(".") else resolve_name(key, package) for key in keys)


def _lazy_exports_table(module: SourceModule, parents: dict[ast.AST, ast.AST]) -> ast.Dict | None:
    """Return the module's literal lazy table when it is bound once, only read and never named by a string."""

    values = [value for statement in module.tree.body if (value := _lazy_exports_value(statement)) is not None]
    stores = [
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Name) and node.id == LAZY_EXPORTS_NAME and not isinstance(node.ctx, ast.Load)
    ]
    if len(values) != 1 or len(stores) != 1 or not values[0].keys:
        return None
    return values[0] if all(_leaves_table_unchanged(node, parents) for node in ast.walk(module.tree)) else None


def _leaves_table_unchanged(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Report whether a node does not name the lazy table, or only reads it in a way that the check models."""

    if isinstance(node, ast.Constant):
        return node.value != LAZY_EXPORTS_NAME
    if isinstance(node, ast.Name) and node.id == LAZY_EXPORTS_NAME and isinstance(node.ctx, ast.Load):
        return _is_modeled_read(node, parents)
    return True


def _is_modeled_read(node: ast.Name, parents: dict[ast.AST, ast.AST]) -> bool:
    """Report whether a use of the lazy table only reads it: a loop, a read method, a subscript or a membership test."""

    parent = parents.get(node)
    if isinstance(parent, ast.Attribute):
        call = parents.get(parent)
        is_read_call = isinstance(call, ast.Call) and call.func is parent
        return parent.value is node and parent.attr in _LAZY_READS and is_read_call
    return _is_read_position(parent, node)


def _is_read_position(parent: ast.AST | None, node: ast.AST) -> bool:
    """Report whether ``parent`` iterates ``node``, reads an item of it or tests membership in it."""

    if isinstance(parent, ast.For | ast.AsyncFor | ast.comprehension):
        return parent.iter is node
    if isinstance(parent, ast.Subscript):
        return parent.value is node and isinstance(parent.ctx, ast.Load)
    in_test = isinstance(parent, ast.Compare) and all(isinstance(op, ast.In | ast.NotIn) for op in parent.ops)
    return in_test and any(item is node for item in parent.comparators)


def _lazy_exports_value(statement: ast.stmt) -> ast.Dict | None:
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target, value = statement.targets[0], statement.value
    elif isinstance(statement, ast.AnnAssign):
        target, value = statement.target, statement.value
    else:
        return None
    if isinstance(target, ast.Name) and target.id == LAZY_EXPORTS_NAME and isinstance(value, ast.Dict):
        return value
    return None


__all__ = [
    "DynamicImportAllowance",
    "HiddenImport",
    "HiddenImportAnalysis",
    "analyze_hidden_imports",
    "parse_dynamic_import_allowlist",
]
