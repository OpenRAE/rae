"""Strict deterministic AUT codec; contains no transition semantics."""

import re

from raes_contracts.behavioral_relation_profiles import HIDDEN, VISIBLE
from raes_contracts.errors import InvalidInputError

from .graph import Graph
from .ingress import MAX_BYTES


def parse_aut(
    content: bytes, *, visible_labels=VISIBLE, max_states=4096, max_bytes=MAX_BYTES
) -> tuple[int, int, tuple[tuple[int, str, int], ...]]:
    if len(content) > max_bytes:
        raise InvalidInputError("AUT exceeds byte limit")
    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeDecodeError:
        raise InvalidInputError("invalid AUT encoding") from None
    header = re.fullmatch(r"des \((\d{1,6}), (\d{1,7}), (\d{1,6})\)", lines[0]) if lines else None
    if header is None:
        raise InvalidInputError("invalid AUT header")
    initial, edge_count, state_count = map(int, header.groups())
    if not 0 <= initial < state_count <= max_states or edge_count != len(lines) - 1:
        raise InvalidInputError("invalid AUT counts")
    edges = []
    for line in lines[1:]:
        edge = re.fullmatch(r'\((\d{1,6}),"([a-z.-]{1,48})",(\d{1,6})\)', line)
        if edge is None:
            raise InvalidInputError("invalid AUT edge")
        left, label, right = edge.groups()
        if label not in (*visible_labels, "internal") or max(int(left), int(right)) >= state_count:
            raise InvalidInputError("invalid AUT label or endpoint")
        edges.append((int(left), label, int(right)))
    if len(set(edges)) != len(edges):
        raise InvalidInputError("duplicate AUT edge")
    return initial, state_count, tuple(edges)


def render_aut(
    graph: Graph, *, visible_labels=VISIBLE, hidden_labels=HIDDEN, max_states=4096, max_bytes=MAX_BYTES
) -> bytes:
    projected = []
    for source, label, target in graph.edges:
        if label not in (*visible_labels, *hidden_labels):
            raise InvalidInputError("undeclared semantic label")
        projected.append((source, "internal" if label in hidden_labels else label, target))
    projected = sorted(set(projected))
    content = (
        f"des ({graph.initial}, {len(projected)}, {len(graph.states)})\n"
        + "".join(f'({source},"{label}",{target})\n' for source, label, target in projected)
    ).encode("ascii")
    initial, count, edges = parse_aut(
        content, visible_labels=visible_labels, max_states=max_states, max_bytes=max_bytes
    )
    if (initial, count, edges) != (graph.initial, len(graph.states), tuple(projected)):
        raise InvalidInputError("AUT readback mismatch")
    return content
