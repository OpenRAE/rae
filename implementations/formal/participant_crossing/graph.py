"""Nonsemantic graph storage shared by the independent model exporters."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Graph:
    states: tuple
    edges: tuple[tuple[int, str, int], ...]
    initial: int = 0
