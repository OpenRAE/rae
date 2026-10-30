"""Small independent admission of finite HML and rev2 divergence witnesses."""

import re
from collections import defaultdict, deque

from raes_contracts.behavioral_relation_profiles import VISIBLE
from raes_contracts.errors import EvidenceIntegrityError

from .aut import parse_aut

MAX_FORMULA_BYTES = 65536
MAX_NODES = 512
MAX_DEPTH = 64
MAX_WORK = 2_000_000
_TOKEN = re.compile(r"\s*(true|false|&&|\|\||[!()]|[<\[][a-z.*-]{1,48}[>\]])")


class _Parser:
    def __init__(self, payload: bytes):
        if len(payload) > MAX_FORMULA_BYTES:
            raise EvidenceIntegrityError("formula budget exceeded")
        try:
            text = payload.decode("ascii").strip()
        except UnicodeError:
            raise EvidenceIntegrityError("invalid formula syntax") from None
        self.tokens = []
        cursor = 0
        while cursor < len(text):
            match = _TOKEN.match(text, cursor)
            if match is None:
                raise EvidenceIntegrityError("invalid formula syntax")
            self.tokens.append(match[1])
            cursor = match.end()
            if len(self.tokens) > MAX_NODES * 3:
                raise EvidenceIntegrityError("formula budget exceeded")
        self.position = 0
        self.nodes = 0

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def node(self, *parts):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise EvidenceIntegrityError("formula budget exceeded")
        return parts

    def expression(self, depth=0):
        return self.binary("||", self.conjunction, depth)

    def conjunction(self, depth):
        return self.binary("&&", self.atom, depth)

    def binary(self, operator, operand, depth):
        result = operand(depth + 1)
        while self.peek() == operator:
            self.position += 1
            result = self.node(operator, result, operand(depth + 1))
        return result

    def atom(self, depth):
        if depth > MAX_DEPTH:
            raise EvidenceIntegrityError("formula budget exceeded")
        lexeme = self.peek()
        self.position += 1
        if lexeme in {"true", "false"}:
            return self.node(lexeme)
        if lexeme == "!":
            return self.node("!", self.atom(depth + 1))
        if lexeme == "(":
            result = self.expression(depth + 1)
            if self.peek() != ")":
                raise EvidenceIntegrityError("invalid formula syntax")
            self.position += 1
            return result
        if lexeme and lexeme[0] in "<[":
            label = lexeme[1:-1]
            if lexeme[-1] != {"<": ">", "[": "]"}[lexeme[0]] or label not in (*VISIBLE, "tau", "tau*"):
                raise EvidenceIntegrityError("invalid formula label")
            return self.node(lexeme[0], label, self.atom(depth + 1))
        raise EvidenceIntegrityError("invalid formula syntax")


def _render(node):
    op = node[0]
    if op in {"true", "false"}:
        return op
    if op == "!":
        return "!(" + _render(node[1]) + ")"
    if op in {"&&", "||"}:
        return "(" + _render(node[1]) + op + _render(node[2]) + ")"
    return op + node[1] + {"<": ">", "[": "]"}[op] + _render(node[2])


def _graph(payload):
    initial, count, edges = parse_aut(payload, max_states=512, max_bytes=65536)
    if len(edges) > 4096:
        raise EvidenceIntegrityError("witness graph budget exceeded")
    return initial, count, edges


def _truth(payload, formula):
    initial, count, edges = _graph(payload)
    universe = frozenset(range(count))
    reverse = defaultdict(lambda: defaultdict(set))
    for source, label, target in edges:
        reverse["tau" if label == "internal" else label][target].add(source)
    work = 0

    def predecessors(label, targets):
        nonlocal work
        reached = set(targets) if label == "tau*" else set()
        queue = deque(targets)
        while queue:
            target = queue.popleft()
            sources = reverse["tau" if label == "tau*" else label][target]
            work += len(sources) + 1
            if work > MAX_WORK:
                raise EvidenceIntegrityError("formula evaluation budget exceeded")
            if label == "tau*":
                queue.extend(sources - reached)
            reached.update(sources)
        return frozenset(reached)

    def evaluate(node, depth=0):
        if depth > MAX_DEPTH:
            raise EvidenceIntegrityError("formula budget exceeded")
        op = node[0]
        if op == "true":
            return universe
        if op == "false":
            return frozenset()
        if op == "!":
            return universe - evaluate(node[1], depth + 1)
        if op in {"&&", "||"}:
            left, right = evaluate(node[1], depth + 1), evaluate(node[2], depth + 1)
            return left & right if op == "&&" else left | right
        target = evaluate(node[2], depth + 1)
        return predecessors(node[1], target) if op == "<" else universe - predecessors(node[1], universe - target)

    return initial in evaluate(formula)


def check_formula(left: bytes, right: bytes, candidate: bytes) -> bytes:
    """Return safe canonical syntax only when true on left and false on right."""

    parser = _Parser(candidate)
    formula = parser.expression()
    if parser.peek() is not None:
        raise EvidenceIntegrityError("invalid formula syntax")
    if not _truth(left, formula) or _truth(right, formula):
        raise EvidenceIntegrityError("formula does not distinguish ordered inputs")
    return (_render(formula) + "\n").encode("ascii")


def _walk(path, start, edges, *, internal=False):
    if not isinstance(path, list) or len(path) > 512:
        raise EvidenceIntegrityError("invalid divergence path")
    current = start
    for edge in path:
        if (
            not isinstance(edge, list)
            or len(edge) != 3
            or type(edge[0]) is not int
            or type(edge[2]) is not int
            or not isinstance(edge[1], str)
            or edge[0] != current
            or tuple(edge) not in edges
            or internal
            and edge[1] != "internal"
        ):
            raise EvidenceIntegrityError("invalid divergence path")
        current = edge[2]
    return current


def check_divergence(left: bytes, right: bytes, witness: dict) -> None:
    """Check the narrow rev2 refutation: reachable divergence versus no tau edge."""

    _, _, opposing = _graph(left)
    initial, _, edges = _graph(right)
    if any(label == "internal" for _, label, _ in opposing):
        raise EvidenceIntegrityError("opposing graph has internal transitions")
    if not isinstance(witness, dict) or set(witness) != {"prefix", "cycle"} or not witness["cycle"]:
        raise EvidenceIntegrityError("invalid divergence witness")
    actual = set(edges)
    start = _walk(witness["prefix"], initial, actual)
    if _walk(witness["cycle"], start, actual, internal=True) != start:
        raise EvidenceIntegrityError("divergence cycle is not closed")
