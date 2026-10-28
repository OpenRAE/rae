"""Aggregate resource bounds for one SDL module-composition request."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from ._errors import SDLParseError
from ._identifiers import QualifiedName
from ._module_symbols import FORWARDING_AGENTS_SECTION, HASHMAP_SECTIONS
from ._source_profile import SDLParserLimits


@dataclass
class CompositionBudget:
    limits: SDLParserLimits
    imports: int = 0
    nodes: int = 0
    decoded_bytes: int = 0

    def add_document(self, value: object, *, path: Path) -> None:
        pending = [value]
        count = 0
        while pending:
            current = pending.pop()
            count += 1
            if isinstance(current, str):
                self.decoded_bytes += len(current.encode("utf-8"))
            if isinstance(current, Mapping):
                pending.extend(current.keys())
                pending.extend(current.values())
            elif isinstance(current, list | tuple):
                pending.extend(current)
        self.nodes += count
        if self.nodes > self.limits.max_composed_nodes:
            raise SDLParseError("SDL composition node budget exceeded", path=path)
        if self.decoded_bytes > self.limits.max_composed_bytes:
            raise SDLParseError("SDL composition decoded-byte budget exceeded", path=path)

    def add_import(self, *, path: Path) -> None:
        self.imports += 1
        if self.imports > self.limits.max_imports:
            raise SDLParseError("SDL composition import budget exceeded", path=path)

    def check_depth(self, depth: int, *, path: Path) -> None:
        if depth > self.limits.max_composition_depth:
            raise SDLParseError("SDL composition depth budget exceeded", path=path)

    def check_namespaces(self, payload: Mapping[str, Any], *, path: Path) -> None:
        identifiers: list[str] = []
        for section_name in HASHMAP_SECTIONS:
            section = payload.get(section_name)
            if isinstance(section, Mapping):
                identifiers.extend(str(name) for name in section)
        agents = payload.get(FORWARDING_AGENTS_SECTION)
        if isinstance(agents, list):
            identifiers.extend(
                str(agent.get("forwarding_agent_id"))
                for agent in agents
                if isinstance(agent, Mapping) and agent.get("forwarding_agent_id")
            )
        for identifier in identifiers:
            try:
                namespace_depth = len(QualifiedName.parse(identifier).parts) - 1
            except ValueError as exc:
                raise SDLParseError("SDL composition produced an invalid qualified identifier", path=path) from exc
            if namespace_depth > self.limits.max_namespace_depth:
                raise SDLParseError("SDL composition namespace-depth budget exceeded", path=path)


@dataclass(frozen=True)
class CompositionTraversal:
    """Immutable ancestry plus the request-scoped mutable resource budget.

    ``local_sources_only`` marks an editor path-mode composition: every level
    resolves local sources only and refuses registry imports before any request.
    """

    seen: frozenset[Path]
    budget: CompositionBudget
    depth: int
    local_sources_only: bool = False

    @classmethod
    def local_root(cls, limits: SDLParserLimits) -> CompositionTraversal:
        """Start a root composition that resolves local imports only and fetches nothing."""

        return cls(seen=frozenset(), budget=CompositionBudget(limits), depth=0, local_sources_only=True)

    def descend_from(self, path: Path) -> CompositionTraversal:
        return CompositionTraversal(
            seen=self.seen | {path},
            budget=self.budget,
            depth=self.depth + 1,
            local_sources_only=self.local_sources_only,
        )


class ParsePrivateOptions(TypedDict, total=False):
    """Private ``parse_sdl`` keywords; ``_traversal`` starts composition from a given traversal."""

    _traversal: CompositionTraversal | None
