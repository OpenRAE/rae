"""The closed boolean grammar admitted for GitHub Actions job and step conditions."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

EVENT_NAME_CONTEXT = "github.event_name"
REF_CONTEXT = "github.ref"
UNTRUSTED_TRUST_CLASSES = frozenset({"untrusted-pr", "untrusted-ref"})
_CONDITION_TOKEN_RE = re.compile(
    r"\s*(?:(?P<operator>&&|\|\||==|!=|[!()])|"
    r"(?P<string>'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")|"
    r"(?P<identifier>[A-Za-z_][A-Za-z0-9_.-]*))"
)
_OPERATOR_TOKENS = frozenset({"&&", "||", "==", "!=", "!", "(", ")"})
_COMPARISON_TOKENS = frozenset({"==", "!="})
_BOOLEAN_LEXEMES = {"true": True, "false": False}
_BOTH = (False, True)


class ConditionSyntaxError(ValueError):
    """Raised when a job/step condition is outside the admitted grammar."""


@dataclass(frozen=True)
class Condition:
    """One node of the closed boolean condition grammar."""

    kind: str
    value: object = None
    operands: tuple[Condition, ...] = field(default=())


class _ConditionParser:
    """Parse the closed boolean subset used by repository workflow conditions."""

    def __init__(self, text: str) -> None:
        self.tokens = self._tokenize(text)
        self.position = 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens: list[str] = []
        position = 0
        while position < len(text):
            match = _CONDITION_TOKEN_RE.match(text, position)
            if match is None:
                raise ConditionSyntaxError("unsupported condition token")
            tokens.append(match.group("operator") or match.group("string") or match.group("identifier"))
            position = match.end()
        return tokens

    def parse(self) -> Condition:
        if not self.tokens:
            return Condition("literal", value=True)
        expression = self._parse_or()
        if self.position != len(self.tokens):
            raise ConditionSyntaxError("trailing condition tokens")
        return expression

    def _accept(self, token: str) -> bool:
        if self.position < len(self.tokens) and self.tokens[self.position] == token:
            self.position += 1
            return True
        return False

    def _parse_or(self) -> Condition:
        expression = self._parse_and()
        while self._accept("||"):
            expression = Condition("or", operands=(expression, self._parse_and()))
        return expression

    def _parse_and(self) -> Condition:
        expression = self._parse_unary()
        while self._accept("&&"):
            expression = Condition("and", operands=(expression, self._parse_unary()))
        return expression

    def _parse_unary(self) -> Condition:
        if self._accept("!"):
            return Condition("not", operands=(self._parse_unary(),))
        return self._parse_primary()

    def _parse_primary(self) -> Condition:
        if self._accept("("):
            expression = self._parse_or()
            if not self._accept(")"):
                raise ConditionSyntaxError("unclosed condition group")
            return expression
        left = self._parse_operand()
        operator = self._take_comparison()
        if operator is None:
            return Condition("truthy", operands=(left,))
        return Condition(operator, operands=(left, self._parse_operand()))

    def _take_comparison(self) -> str | None:
        """Consume a comparison operator when one follows the current operand."""

        if self.position >= len(self.tokens) or self.tokens[self.position] not in _COMPARISON_TOKENS:
            return None
        operator = self.tokens[self.position]
        self.position += 1
        return operator

    def _take_operand_lexeme(self) -> str:
        """Consume the next token, requiring it to be a valid operand."""

        if self.position >= len(self.tokens):
            raise ConditionSyntaxError("missing condition operand")
        lexeme = self.tokens[self.position]
        if lexeme in _OPERATOR_TOKENS:
            raise ConditionSyntaxError("invalid condition operand")
        self.position += 1
        return lexeme

    def _parse_operand(self) -> Condition:
        lexeme = self._take_operand_lexeme()
        if lexeme.startswith(("'", '"')):
            return Condition("literal", value=lexeme[1:-1])
        if lexeme in _BOOLEAN_LEXEMES:
            return Condition("literal", value=_BOOLEAN_LEXEMES[lexeme])
        return self._parse_named_operand(lexeme)

    def _parse_named_operand(self, lexeme: str) -> Condition:
        """Resolve a bare identifier as a variable or a zero-argument function."""

        if not self._accept("("):
            return Condition("variable", value=lexeme)
        if not self._accept(")"):
            raise ConditionSyntaxError("only zero-argument condition functions are admitted")
        return Condition("function", value=lexeme)


def _literal_condition(value: object) -> Condition | None:
    """Return the constant condition a non-expression value denotes."""

    if value is None or value == "":
        return Condition("literal", value=True)
    return Condition("literal", value=value) if isinstance(value, bool) else None


def _expression_text(value: str) -> str:
    """Strip one optional ``${{ ... }}`` wrapper from a condition."""

    text = value.strip()
    return text[3:-2].strip() if text.startswith("${{") and text.endswith("}}") else text


def condition_ast(value: object) -> Condition | None:
    """Parse one job/step condition, or None when it leaves the closed grammar."""

    literal = _literal_condition(value)
    if literal is not None or not isinstance(value, str):
        return literal
    try:
        parsed: Condition | None = _ConditionParser(_expression_text(value)).parse()
    except ConditionSyntaxError:
        parsed = None
    return parsed


def condition_operand(expression: Condition, context: Mapping[str, object]) -> tuple[bool, object]:
    """Resolve one operand to a known value, or report it as unknown."""

    if expression.kind == "literal":
        return True, expression.value
    if expression.kind == "variable" and expression.value in context:
        return True, context[str(expression.value)]
    return False, None


def _literal_values(expression: Condition, _context: Mapping[str, object]) -> set[bool]:
    return {bool(expression.value)}


def _variable_values(expression: Condition, context: Mapping[str, object]) -> set[bool]:
    value = context.get(str(expression.value))
    return set(_BOTH) if value is None else {bool(value)}


def _function_values(expression: Condition, _context: Mapping[str, object]) -> set[bool]:
    return {True} if expression.value == "always" else set(_BOTH)


def _truthy_values(expression: Condition, context: Mapping[str, object]) -> set[bool]:
    return condition_values(expression.operands[0], context)


def _not_values(expression: Condition, context: Mapping[str, object]) -> set[bool]:
    return {not value for value in condition_values(expression.operands[0], context)}


def _and_values(expression: Condition, context: Mapping[str, object]) -> set[bool]:
    left = condition_values(expression.operands[0], context)
    right = condition_values(expression.operands[1], context)
    return {first and second for first in left for second in right}


def _or_values(expression: Condition, context: Mapping[str, object]) -> set[bool]:
    left = condition_values(expression.operands[0], context)
    right = condition_values(expression.operands[1], context)
    return {first or second for first in left for second in right}


def _comparison_values(expression: Condition, context: Mapping[str, object]) -> set[bool]:
    left_known, left = condition_operand(expression.operands[0], context)
    right_known, right = condition_operand(expression.operands[1], context)
    if not left_known or not right_known:
        return set(_BOTH)
    equal = left == right
    return {equal if expression.kind == "==" else not equal}


_CONDITION_EVALUATORS: Mapping[str, Callable[[Condition, Mapping[str, object]], set[bool]]] = {
    "literal": _literal_values,
    "variable": _variable_values,
    "function": _function_values,
    "truthy": _truthy_values,
    "not": _not_values,
    "and": _and_values,
    "or": _or_values,
    "==": _comparison_values,
    "!=": _comparison_values,
}


def condition_values(expression: Condition, context: Mapping[str, object]) -> set[bool]:
    """Evaluate one condition to every boolean it can take in this context."""

    evaluator = _CONDITION_EVALUATORS.get(expression.kind)
    return set(_BOTH) if evaluator is None else evaluator(expression, context)


def condition_string_literals(expression: Condition) -> set[str]:
    """Collect every string literal the condition compares against."""

    literals: set[str] = set()
    if expression.kind == "literal" and isinstance(expression.value, str):
        literals.add(expression.value)
    for child in expression.operands:
        literals.update(condition_string_literals(child))
    return literals


def _unmodeled_ref(
    known_refs: set[str],
    candidate: str = "refs/heads/__gc-unmodeled-ref__",
) -> str:
    while candidate in known_refs:
        candidate += "-other"
    return candidate


def generic_trust_contexts(
    protected_refs: set[str],
    expression: Condition,
    trigger_names: set[str] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Enumerate the representative event contexts each trust class can occur in."""

    protected_set = protected_refs or {"refs/heads/main"}
    protected = sorted(protected_set)
    literal_refs = {value for value in condition_string_literals(expression) if value.startswith("refs/")}
    unprotected = sorted(literal_refs - protected_set)
    unprotected.append(_unmodeled_ref(literal_refs | protected_set))
    all_refs = [*protected, *unprotected]
    pull_request_events = sorted((trigger_names or set()) & {"pull_request", "pull_request_target"})
    if not pull_request_events:
        pull_request_events = ["pull_request", "pull_request_target"]
    pull_request_refs = sorted(value for value in literal_refs if value.startswith("refs/pull/"))
    pull_request_refs.append(
        _unmodeled_ref(
            literal_refs | protected_set | set(pull_request_refs),
            "refs/pull/__gc-unmodeled-ref__/merge",
        )
    )
    return {
        "untrusted-pr": [
            {EVENT_NAME_CONTEXT: event_name, REF_CONTEXT: reference}
            for event_name in pull_request_events
            for reference in (pull_request_refs if event_name == "pull_request" else all_refs)
        ],
        "untrusted-ref": [{EVENT_NAME_CONTEXT: "push", REF_CONTEXT: reference} for reference in unprotected],
        "protected-branch": [{EVENT_NAME_CONTEXT: "push", REF_CONTEXT: reference} for reference in protected],
        "manual": [{EVENT_NAME_CONTEXT: "workflow_dispatch", REF_CONTEXT: reference} for reference in all_refs],
        "scheduled": [{EVENT_NAME_CONTEXT: "schedule", REF_CONTEXT: protected[0]}],
        "reusable": [{EVENT_NAME_CONTEXT: "workflow_call", REF_CONTEXT: protected[0]}],
    }


def filter_trust_classes(
    classes: set[str],
    condition: object,
    protected_refs: set[str],
    trigger_names: set[str] | None = None,
) -> tuple[set[str], bool]:
    """Narrow trust classes by one condition, reporting whether it was admitted."""

    expression = condition_ast(condition)
    if expression is None:
        return classes, False
    contexts = generic_trust_contexts(protected_refs, expression, trigger_names)
    return {
        trust_class
        for trust_class in classes
        if any(True in condition_values(expression, context) for context in contexts[trust_class])
    }, True


def condition_proves_protected_manual(condition: object, protected_refs: set[str]) -> bool:
    """Report whether a manual job's condition admits only protected references."""

    expression = condition_ast(condition)
    if expression is None:
        return False
    effective_protected_refs = protected_refs or {"refs/heads/main"}
    contexts = generic_trust_contexts(
        effective_protected_refs,
        expression,
        {"workflow_dispatch"},
    )["manual"]
    unprotected = [context for context in contexts if context[REF_CONTEXT] not in effective_protected_refs]
    return all(True not in condition_values(expression, context) for context in unprotected)


__all__ = (
    "EVENT_NAME_CONTEXT",
    "REF_CONTEXT",
    "UNTRUSTED_TRUST_CLASSES",
    "Condition",
    "ConditionSyntaxError",
    "condition_ast",
    "condition_proves_protected_manual",
    "condition_values",
    "filter_trust_classes",
    "generic_trust_contexts",
)
