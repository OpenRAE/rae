"""Typed SDL declarations, their alias index, and canonical-address collision checks."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from ._declaration_sources import DeclarationSource
from ._errors import SDLValidationError
from ._reference_targetability import (
    ReferencePurpose,
    canonical_purposes,
    declaration_eligible,
    is_eligible,
    require_eligibility_decision,
    resolution_domain,
)

Purposes = ReferencePurpose | tuple[ReferencePurpose, ...]


@dataclass(frozen=True)
class Declaration:
    """One declared SDL identity before alias projection."""

    kind: str
    address: str
    model_path: str
    source: str | None = field(default=None, compare=False)
    model_tokens: tuple[str, ...] = ()
    source_location: DeclarationSource | None = field(default=None, compare=False)

    @property
    def referenceable(self) -> bool:
        """Whether any declared-reference field may name this declaration."""

        return is_eligible(self.kind, ReferencePurpose.DECLARED)

    @property
    def targetable(self) -> bool:
        """Whether the explicit general target purpose admits this declaration."""

        return is_eligible(self.kind, ReferencePurpose.TARGETABLE)


class DeclarationIndex:
    """Collision-preserving declarations plus non-authoritative lookup aliases."""

    def __init__(self) -> None:
        self._declarations: dict[str, Declaration] = {}
        self._aliases: dict[str, set[str]] = defaultdict(set)
        self._collisions: list[str] = []

    @property
    def addresses(self) -> frozenset[str]:
        return frozenset(self._declarations)

    @property
    def declarations(self) -> tuple[Declaration, ...]:
        return tuple(self._declarations[address] for address in sorted(self._declarations))

    @property
    def collision_errors(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self._collisions))

    def declaration_for(self, address: str) -> Declaration | None:
        """Return the typed declaration at an exact canonical address."""

        return self._declarations.get(address)

    def resolve(self, reference: str) -> set[str]:
        return set(self._aliases.get(reference, ()))

    def reference_aliases(self, purpose: Purposes = ReferencePurpose.DECLARED) -> dict[str, set[str]]:
        """Return aliases naming a declaration eligible for *purpose* (every member of a purpose tuple).

        Candidates come from the purpose's resolution domain, so a bare name
        shared with another declaration in that domain stays ambiguous.
        """

        return {alias: candidates for alias in self._aliases if (candidates := self.resolve_for(alias, purpose))}

    def resolve_for(self, reference: str, purpose: Purposes) -> set[str]:
        """Return *reference*'s resolution-domain candidates, or none when none is eligible for *purpose*."""

        purposes = canonical_purposes(purpose)
        domain = resolution_domain(purposes[0])
        candidates = self.eligible(self._aliases.get(reference, set()), domain)
        return candidates if purposes == (domain,) or self.eligible(candidates, purposes) else set()

    def eligible(self, addresses: set[str], purpose: Purposes) -> set[str]:
        purposes = canonical_purposes(purpose)
        return {
            address
            for address in addresses
            if (declaration := self._declarations.get(address)) is not None
            and declaration_eligible(declaration, purposes)
        }

    def reference_completions(
        self, purpose: Purposes = ReferencePurpose.DECLARED
    ) -> tuple[tuple[str, Declaration], ...]:
        """Return one unambiguous preferred spelling per declaration eligible for *purpose*."""

        purposes = canonical_purposes(purpose)
        aliases = self.reference_aliases(purposes)
        return tuple(
            (preferred_spelling(aliases, declaration.address), declaration)
            for declaration in self.declarations
            if declaration_eligible(declaration, purposes)
        )

    def spellings_for(self, reference: str) -> frozenset[str]:
        """Return aliases denoting the same declarations as *reference*."""

        targets = self.resolve(reference)
        if not targets:
            return frozenset({reference})
        return frozenset(alias for alias, candidates in self._aliases.items() if candidates.intersection(targets))

    def add(self, declaration: Declaration, *, aliases: Iterable[str] = ()) -> None:
        require_eligibility_decision(declaration.kind)
        previous = self._declarations.get(declaration.address)
        if previous is not None and (previous != declaration or previous.source != declaration.source):
            self._collisions.append(
                f"Canonical address '{declaration.address}' collides between "
                f"{previous.kind} declaration at {previous.model_path} and "
                f"{declaration.kind} declaration at {declaration.model_path}"
            )
            return
        self._declarations[declaration.address] = declaration
        self._aliases[declaration.address].add(declaration.address)
        for alias in aliases:
            if alias:
                self._aliases[alias].add(declaration.address)

    def raise_for_collisions(self) -> None:
        if self._collisions:
            raise SDLValidationError(list(dict.fromkeys(self._collisions)))

    def attach_sources(self, sources: Mapping[str, DeclarationSource]) -> None:
        for address, location in sources.items():
            declaration = self._declarations.get(address)
            if declaration is not None:
                self._declarations[address] = replace(declaration, source=location.source, source_location=location)


def preferred_spelling(aliases: dict[str, set[str]], address: str) -> str:
    """Return the shortest alias that names only *address* (its canonical address at worst)."""

    spellings = [alias for alias, candidates in aliases.items() if candidates == {address}]
    return min(spellings, key=lambda value: (value.count("."), len(value), value))


__all__ = [
    "Declaration",
    "DeclarationIndex",
    "Purposes",
    "preferred_spelling",
]
