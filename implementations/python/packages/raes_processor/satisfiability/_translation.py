"""Total translation of the governed SDL v1 satisfiability fragment."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import partial
from typing import cast

import rfc8785
from raes.architectures import normalize_architecture
from raes.canonical import canonical_sdl_digest
from raes.infrastructure import ACLAction
from raes.nodes import OSFamily
from raes.runtime_values import parse_runtime_enum_identity
from raes.scenario import ExpandedScenario, Scenario
from raes.value_parsing import extract_variable_name, normalize_enum_value, variable_names_in_value
from raes.variables import Variable, VariableType
from raes_contracts.diagnostics import DiagnosticModel
from raes_contracts.satisfiability import (
    ConstraintClauseKind,
    ConstraintClauseModel,
    ConstraintSort,
    ConstraintSymbolModel,
    NormalizedConstraintModel,
)

_MAX_SYMBOLS = 128
_MAX_CLAUSES = 512
_MAX_DOMAIN_MEMBERS = 256
_MAX_DIAGNOSTICS = 64
_DOMAIN_CODE = "scenario-satisfiability.unsupported-domain"
_TARGET_CODE = "scenario-satisfiability.unsupported-target"
_RESOURCE_CODE = "scenario-satisfiability.resource-limit"
VariableOccurrence = tuple[str, str, bool]


@dataclass(frozen=True)
class TranslationResult:
    """Normalized model plus any fail-closed coverage diagnostics."""

    model: NormalizedConstraintModel
    diagnostics: tuple[DiagnosticModel, ...]


class _DiagnosticAccumulator:
    """Keep unsupported evidence within its closed contract at every boundary."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], DiagnosticModel] = {}
        self._overflowed = False

    def add(self, diagnostic: DiagnosticModel) -> None:
        key = (diagnostic.address, diagnostic.code)
        if key in self._items or self._overflowed:
            return
        if len(self._items) < _MAX_DIAGNOSTICS:
            self._items[key] = diagnostic
            return

        # Replace the last deterministically visited detail with one stable
        # overflow record. The traversal order is canonical, so the retained
        # evidence is reproducible without ever exceeding the contract bound.
        self._items.pop(next(reversed(self._items)))
        overflow = _diagnostic(
            _RESOURCE_CODE,
            "",
            "The analysis produced more unsupported diagnostics than the evidence profile permits.",
        )
        self._items[(overflow.address, overflow.code)] = overflow
        self._overflowed = True

    def as_tuple(self) -> tuple[DiagnosticModel, ...]:
        return tuple(sorted(self._items.values(), key=lambda item: (item.address, item.code)))


def translate_scenario(
    scenario: Scenario | ExpandedScenario,
    *,
    source_digest: str,
) -> TranslationResult:
    """Translate every remaining variable occurrence or reject it explicitly."""

    payload = scenario.model_dump(
        mode="python",
        by_alias=True,
        exclude={"variables", "imports", "module", "expansion_provenance"},
    )
    occurrences = tuple(_variable_occurrences(payload))
    diagnostics = _DiagnosticAccumulator()
    symbols = _select_symbols(scenario, occurrences, diagnostics)
    clauses = _translate_clauses(symbols, occurrences, diagnostics)

    model = NormalizedConstraintModel(
        profile="raes-finite-domain-constraints/v1",
        theory_profile="raes-finite-domain-theory/v1",
        translation_profile="raes-sdl-authoring-translation/v1",
        source_digest=source_digest,
        authored_digest=canonical_sdl_digest(scenario).as_dict(),
        symbols=tuple(sorted(symbols.values(), key=lambda item: item.symbol_id)),
        clauses=tuple(sorted(clauses, key=lambda item: item.clause_id)),
    )
    return TranslationResult(
        model=model,
        diagnostics=diagnostics.as_tuple(),
    )


def _select_symbols(
    scenario: Scenario | ExpandedScenario,
    occurrences: tuple[VariableOccurrence, ...],
    diagnostics: _DiagnosticAccumulator,
) -> dict[str, ConstraintSymbolModel]:
    referenced = {name for _, name, _ in occurrences}
    selected = {
        name: variable for name, variable in scenario.variables.items() if name in referenced or variable.required
    }
    selected_items = sorted(selected.items())
    if len(selected_items) > _MAX_SYMBOLS:
        diagnostics.add(_diagnostic(_RESOURCE_CODE, "/variables", "The analysis exceeds the symbol limit."))
        selected_items = selected_items[:_MAX_SYMBOLS]

    symbols: dict[str, ConstraintSymbolModel] = {}
    for name, variable in selected_items:
        symbol = _symbol(name, variable, diagnostics)
        if symbol is not None:
            symbols[name] = symbol
    return symbols


def _translate_clauses(
    symbols: dict[str, ConstraintSymbolModel],
    occurrences: tuple[VariableOccurrence, ...],
    diagnostics: _DiagnosticAccumulator,
) -> list[ConstraintClauseModel]:
    clauses: list[ConstraintClauseModel] = []
    for name, symbol in symbols.items():
        _append_clause(
            clauses,
            ConstraintClauseModel(
                clause_id=_stable_id("domain", name),
                kind=ConstraintClauseKind.DECLARED_DOMAIN,
                symbol_id=symbol.symbol_id,
                source_address=f"/variables/{_pointer(name)}",
                allowed_values=symbol.domain,
            ),
            diagnostics,
        )
    for occurrence in occurrences:
        clause = _target_clause(occurrence, symbols, diagnostics)
        if clause is not None:
            _append_clause(clauses, clause, diagnostics)
    return clauses


def _append_clause(
    clauses: list[ConstraintClauseModel],
    clause: ConstraintClauseModel,
    diagnostics: _DiagnosticAccumulator,
) -> None:
    if len(clauses) < _MAX_CLAUSES:
        clauses.append(clause)
    else:
        diagnostics.add(_diagnostic(_RESOURCE_CODE, "", "The analysis exceeds the clause limit."))


def _target_clause(
    occurrence: VariableOccurrence,
    symbols: dict[str, ConstraintSymbolModel],
    diagnostics: _DiagnosticAccumulator,
) -> ConstraintClauseModel | None:
    address, name, embedded = occurrence
    symbol = symbols.get(name)
    allowed = None if embedded or symbol is None else _target_domain(address, symbol)
    if symbol is None or allowed is None:
        diagnostics.add(
            _diagnostic(
                _TARGET_CODE,
                address,
                "The variable occurrence is outside the selected translation profile.",
            )
        )
        return None
    return ConstraintClauseModel(
        clause_id="target:" + hashlib.sha256(address.encode("utf-8")).hexdigest(),
        kind=ConstraintClauseKind.TARGET_DOMAIN,
        symbol_id=symbol.symbol_id,
        source_address=address,
        allowed_values=allowed,
    )


def _symbol(
    name: str,
    variable: Variable,
    diagnostics: _DiagnosticAccumulator,
) -> ConstraintSymbolModel | None:
    address = f"/variables/{_pointer(name)}"
    values = _finite_domain_values(variable, address, diagnostics)
    if values is None:
        return None
    sort = {
        VariableType.STRING: ConstraintSort.STRING,
        VariableType.INTEGER: ConstraintSort.INTEGER,
        VariableType.BOOLEAN: ConstraintSort.BOOLEAN,
    }[variable.type]
    canonical = tuple(sorted(values, key=rfc8785.dumps))
    if len(canonical) > _MAX_DOMAIN_MEMBERS or len({rfc8785.dumps(item) for item in canonical}) != len(canonical):
        diagnostics.add(_diagnostic(_DOMAIN_CODE, address, "The variable domain is invalid or exceeds its limit."))
        return None
    return ConstraintSymbolModel(
        symbol_id=_stable_id("symbol", name),
        variable=name,
        sort=sort,
        domain=canonical,
    )


def _finite_domain_values(
    variable: Variable,
    address: str,
    diagnostics: _DiagnosticAccumulator,
) -> tuple[str | int | bool, ...] | None:
    values: tuple[str | int | bool, ...] | None = None
    if variable.type is VariableType.NUMBER:
        diagnostics.add(_diagnostic(_DOMAIN_CODE, address, "The variable sort is not supported by this profile."))
    elif variable.allowed_values:
        values = cast(tuple[str | int | bool, ...], tuple(variable.allowed_values))
    elif variable.type is VariableType.BOOLEAN:
        values = (False, True)
    else:
        diagnostics.add(
            _diagnostic(_DOMAIN_CODE, address, "The variable requires an explicit finite allowed-values domain.")
        )
    return values


def _variable_occurrences(value: object, address: str = "") -> Iterator[VariableOccurrence]:
    if isinstance(value, dict):
        yield from _mapping_variable_occurrences(cast(dict[object, object], value), address)
    elif isinstance(value, list):
        yield from _sequence_variable_occurrences(cast(list[object], value), address)
    elif isinstance(value, str):
        yield from _string_variable_occurrences(value, address)


def _mapping_variable_occurrences(
    value: dict[object, object],
    address: str,
) -> Iterator[VariableOccurrence]:
    for key in sorted(value, key=str):
        yield from _variable_occurrences(value[key], f"{address}/{_pointer(str(key))}")


def _sequence_variable_occurrences(
    value: list[object],
    address: str,
) -> Iterator[VariableOccurrence]:
    for index, item in enumerate(value):
        yield from _variable_occurrences(item, f"{address}/{index}")


def _string_variable_occurrences(value: str, address: str) -> Iterator[VariableOccurrence]:
    whole = extract_variable_name(value)
    if whole is not None:
        yield address, whole, False
    else:
        for name in variable_names_in_value(value):
            yield address, name, True


def _target_domain(
    address: str,
    symbol: ConstraintSymbolModel,
) -> tuple[str | int | bool, ...] | None:
    parts = address.split("/")[1:]
    result: tuple[str | int | bool, ...] | None = None
    match parts:
        case ["nodes", _, "os"] if symbol.sort is ConstraintSort.STRING:
            result = _identity_domain(symbol, partial(parse_runtime_enum_identity, enum_cls=OSFamily, field_name="os"))
        case ["nodes", _, "architecture"] if symbol.sort is ConstraintSort.STRING:
            result = _identity_domain(symbol, normalize_architecture)
        case ["infrastructure", _, "acls", _, "action"] if symbol.sort is ConstraintSort.STRING:
            result = _string_vocabulary_domain(symbol, {item.value for item in ACLAction})
        case ["infrastructure", _, "count"] if symbol.sort is ConstraintSort.INTEGER:
            integer_domain = cast(tuple[int, ...], symbol.domain)
            result = tuple(value for value in integer_domain if value >= 1)
        case ["infrastructure", _, "properties", "internal"] if symbol.sort is ConstraintSort.BOOLEAN:
            result = symbol.domain
    return result


def _identity_domain(symbol: ConstraintSymbolModel, normalizer: Callable[[object], object]) -> tuple[str, ...]:
    values = []
    for value in cast(tuple[str, ...], symbol.domain):
        try:
            parsed = normalizer(value)
        except ValueError:
            continue
        if isinstance(parsed, str) and extract_variable_name(parsed) is None:
            values.append(value)
    return tuple(values)


def _string_vocabulary_domain(
    symbol: ConstraintSymbolModel,
    vocabulary: set[str],
) -> tuple[str, ...]:
    string_domain = cast(tuple[str, ...], symbol.domain)
    return tuple(value for value in string_domain if normalize_enum_value(value) in vocabulary)


def _diagnostic(code: str, address: str, message: str) -> DiagnosticModel:
    return DiagnosticModel(
        code=code,
        domain="scenario-satisfiability",
        address=address,
        message=message,
        severity="error",
    )


def _pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _stable_id(prefix: str, value: str) -> str:
    """Keep ids closed and collision-resistant for every legal SDL identifier."""

    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
