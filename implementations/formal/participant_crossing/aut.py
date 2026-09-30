"""Strict deterministic AUT codec; contains no transition semantics."""

import re

from raes_contracts.behavioral_relation_profiles import HIDDEN, VISIBLE

from .graph import Graph
from .ingress import MAX_BYTES


def parse_aut(content: bytes) -> tuple[int, int, tuple[tuple[int, str, int], ...]]:
    if len(content) > MAX_BYTES:
        raise ValueError("AUT exceeds byte limit")
    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeDecodeError:
        raise ValueError("invalid AUT encoding") from None
    header = (
        re.fullmatch(r"des \((\d{1,5}), (\d{1,6}), (\d{1,5})\)", lines[0])
        if lines
        else None
    )
    if header is None:
        raise ValueError("invalid AUT header")
    initial, edge_count, state_count = map(int, header.groups())
    if not 0 <= initial < state_count <= 4096 or edge_count != len(lines) - 1:
        raise ValueError("invalid AUT counts")
    edges = []
    for line in lines[1:]:
        edge = re.fullmatch(r'\((\d{1,5}),"([a-z.-]{1,48})",(\d{1,5})\)', line)
        if edge is None:
            raise ValueError("invalid AUT edge")
        left, label, right = edge.groups()
        if (
            label not in (*VISIBLE, "internal")
            or max(int(left), int(right)) >= state_count
        ):
            raise ValueError("invalid AUT label or endpoint")
        edges.append((int(left), label, int(right)))
    if len(set(edges)) != len(edges):
        raise ValueError("duplicate AUT edge")
    return initial, state_count, tuple(edges)


def render_aut(graph: Graph) -> bytes:
    projected = []
    for source, label, target in graph.edges:
        if label not in (*VISIBLE, *HIDDEN):
            raise ValueError("undeclared semantic label")
        projected.append((source, "internal" if label in HIDDEN else label, target))
    projected.sort()
    content = (
        f"des ({graph.initial}, {len(projected)}, {len(graph.states)})\n"
        + "".join(
            f'({source},"{label}",{target})\n' for source, label, target in projected
        )
    ).encode("ascii")
    initial, count, edges = parse_aut(content)
    if (initial, count, edges) != (graph.initial, len(graph.states), tuple(projected)):
        raise ValueError("AUT readback mismatch")
    return content
