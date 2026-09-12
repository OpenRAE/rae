"""Closed condition, trust, secret, runner, and workflow parsing helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from tools.tooling_artifact_policy_common import (
    SHA40_RE,
    as_list,
    as_mapping,
)

_SECRET_DOT_RE = re.compile(r"\bsecrets\.([A-Za-z_]\w*)\b", re.ASCII)
_SECRET_BRACKET_RE = re.compile(r"\bsecrets\s*\[\s*(['\"])([A-Za-z_]\w*)\1\s*\]", re.ASCII)
_SECRET_CONTEXT_RE = re.compile(r"\bsecrets\b", re.IGNORECASE)
_WORKFLOW_EXPRESSION_RE = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)
_CONDITION_TOKEN_RE = re.compile(
    r"\s*(?:(?P<operator>&&|\|\||==|!=|[!()])|"
    r"(?P<string>'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")|"
    r"(?P<identifier>[A-Za-z_][A-Za-z0-9_.-]*))"
)
_EVENT_NAME = "github.event_name"
_REF = "github.ref"


class _ConditionSyntaxError(ValueError):
    """Raised when a job/step condition is outside the admitted grammar."""


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
                raise _ConditionSyntaxError("unsupported condition token")
            tokens.append(match.group("operator") or match.group("string") or match.group("identifier"))
            position = match.end()
        return tokens

    def parse(self) -> tuple[Any, ...]:
        expression = ("literal", True) if not self.tokens else self._parse_or()
        if self.position != len(self.tokens):
            raise _ConditionSyntaxError("trailing condition tokens")
        return expression

    def _accept(self, token: str) -> bool:
        accepted = self.position < len(self.tokens) and self.tokens[self.position] == token
        if accepted:
            self.position += 1
        return accepted

    def _parse_or(self) -> tuple[Any, ...]:
        expression = self._parse_and()
        while self._accept("||"):
            expression = ("or", expression, self._parse_and())
        return expression

    def _parse_and(self) -> tuple[Any, ...]:
        expression = self._parse_unary()
        while self._accept("&&"):
            expression = ("and", expression, self._parse_unary())
        return expression

    def _parse_unary(self) -> tuple[Any, ...]:
        expression = ("not", self._parse_unary()) if self._accept("!") else self._parse_primary()
        return expression

    def _parse_primary(self) -> tuple[Any, ...]:
        if self._accept("("):
            expression = self._parse_or()
            if not self._accept(")"):
                raise _ConditionSyntaxError("unclosed condition group")
            return expression
        left = self._parse_operand()
        comparison = self.position < len(self.tokens) and self.tokens[self.position] in {"==", "!="}
        if not comparison:
            return ("truthy", left)
        operator = self.tokens[self.position]
        self.position += 1
        return (operator, left, self._parse_operand())

    def _parse_operand(self) -> tuple[Any, ...]:
        if self.position >= len(self.tokens):
            raise _ConditionSyntaxError("missing condition operand")
        lexeme = self.tokens[self.position]
        if lexeme in {"&&", "||", "==", "!=", "!", "(", ")"}:
            raise _ConditionSyntaxError("invalid condition operand")
        self.position += 1
        if lexeme.startswith(("'", '"')):
            operand: tuple[Any, ...] = ("literal", lexeme[1:-1])
        elif lexeme in {"true", "false"}:
            operand = ("literal", lexeme == "true")
        elif self._accept("("):
            if not self._accept(")"):
                raise _ConditionSyntaxError("only zero-argument condition functions are admitted")
            operand = ("function", lexeme)
        else:
            operand = ("variable", lexeme)
        return operand


def condition_ast(value: object) -> tuple[Any, ...] | None:
    expression: tuple[Any, ...] | None
    if value is None or value == "":
        expression = ("literal", True)
    elif isinstance(value, bool):
        expression = ("literal", value)
    elif not isinstance(value, str):
        expression = None
    else:
        text = value.strip()
        if text.startswith("${{") and text.endswith("}}"):
            text = text[3:-2].strip()
        try:
            expression = _ConditionParser(text).parse()
        except _ConditionSyntaxError:
            expression = None
    return expression


def _condition_operand(expression: tuple[Any, ...], context: Mapping[str, object]) -> tuple[bool, object]:
    if expression[0] == "literal":
        return True, expression[1]
    if expression[0] == "variable" and expression[1] in context:
        return True, context[expression[1]]
    return False, None


def _logical_values(expression: tuple[Any, ...], context: Mapping[str, object]) -> set[bool]:
    left = condition_values(expression[1], context)
    right = condition_values(expression[2], context)
    if expression[0] == "and":
        return {first and second for first in left for second in right}
    return {first or second for first in left for second in right}


def _comparison_values(expression: tuple[Any, ...], context: Mapping[str, object]) -> set[bool]:
    left_known, left = _condition_operand(expression[1], context)
    right_known, right = _condition_operand(expression[2], context)
    if not left_known or not right_known:
        return {False, True}
    equal = left == right
    return {equal if expression[0] == "==" else not equal}


def _leaf_condition_values(
    kind: object,
    expression: tuple[Any, ...],
    context: Mapping[str, object],
) -> set[bool] | None:
    if kind == "literal":
        values: set[bool] | None = {bool(expression[1])}
    elif kind == "variable":
        value = context.get(str(expression[1]))
        values = {bool(value)} if value is not None else {False, True}
    elif kind == "function":
        values = {True} if expression[1] == "always" else {False, True}
    else:
        values = None
    return values


def condition_values(expression: tuple[Any, ...], context: Mapping[str, object]) -> set[bool]:
    kind = expression[0]
    values = _leaf_condition_values(kind, expression, context)
    if values is not None:
        return values
    if kind == "truthy":
        values = condition_values(expression[1], context)
    elif kind == "not":
        values = {not value for value in condition_values(expression[1], context)}
    elif kind in {"and", "or"}:
        values = _logical_values(expression, context)
    elif kind in {"==", "!="}:
        values = _comparison_values(expression, context)
    else:
        values = {False, True}
    return values


def _condition_string_literals(expression: tuple[Any, ...]) -> set[str]:
    literals = {expression[1]} if expression[0] == "literal" and isinstance(expression[1], str) else set()
    for child in expression[1:]:
        if isinstance(child, tuple):
            literals.update(_condition_string_literals(child))
    return literals


def _unmodeled_ref(known_refs: set[str], candidate: str = "refs/heads/__gc-unmodeled-ref__") -> str:
    while candidate in known_refs:
        candidate += "-other"
    return candidate


def generic_trust_contexts(
    protected_refs: set[str],
    expression: tuple[Any, ...],
    trigger_names: set[str] | None = None,
) -> dict[str, list[dict[str, object]]]:
    protected_set = protected_refs or {"refs/heads/main"}
    protected = sorted(protected_set)
    literal_refs = {value for value in _condition_string_literals(expression) if value.startswith("refs/")}
    unprotected = sorted(literal_refs - protected_set)
    unprotected.append(_unmodeled_ref(literal_refs | protected_set))
    all_refs = [*protected, *unprotected]
    pull_events = sorted((trigger_names or set()) & {"pull_request", "pull_request_target"})
    pull_events = pull_events or ["pull_request", "pull_request_target"]
    pull_refs = sorted(value for value in literal_refs if value.startswith("refs/pull/"))
    pull_refs.append(_unmodeled_ref(literal_refs | protected_set | set(pull_refs), "refs/pull/other/merge"))
    return {
        "untrusted-pr": _pull_request_contexts(pull_events, pull_refs, all_refs),
        "untrusted-ref": _event_contexts("push", unprotected),
        "protected-branch": _event_contexts("push", protected),
        "manual": _event_contexts("workflow_dispatch", all_refs),
        "scheduled": _event_contexts("schedule", protected[:1]),
        "reusable": _event_contexts("workflow_call", protected[:1]),
    }


def _event_contexts(event: str, references: list[str]) -> list[dict[str, object]]:
    return [{_EVENT_NAME: event, _REF: reference} for reference in references]


def _pull_request_contexts(
    events: list[str],
    pull_refs: list[str],
    all_refs: list[str],
) -> list[dict[str, object]]:
    return [
        {_EVENT_NAME: event, _REF: reference}
        for event in events
        for reference in (pull_refs if event == "pull_request" else all_refs)
    ]


def filter_trust_classes(
    classes: set[str],
    condition: object,
    protected_refs: set[str],
    trigger_names: set[str] | None = None,
) -> tuple[set[str], bool]:
    expression = condition_ast(condition)
    if expression is None:
        return classes, False
    contexts = generic_trust_contexts(protected_refs, expression, trigger_names)
    filtered = {
        trust_class
        for trust_class in classes
        if any(True in condition_values(expression, context) for context in contexts[trust_class])
    }
    return filtered, True


def action_identity(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    action_name, separator, selector = value.rpartition("@")
    if not separator or not action_name or action_name.startswith(("./", "docker://", "http://", "https://")):
        return None
    return action_name.lower(), selector


def trigger_names(workflow: Mapping[str, Any]) -> set[str]:
    triggers = workflow.get("on", workflow.get(True))
    if isinstance(triggers, str):
        names = {triggers}
    elif isinstance(triggers, list):
        names = {item for item in triggers if isinstance(item, str)}
    elif isinstance(triggers, Mapping):
        names = {str(key) for key in triggers}
    else:
        names = set()
    return names


def _branch_trust_class(branch: object, protected_refs: set[str]) -> str:
    if isinstance(branch, str) and not any(character in branch for character in "*?[]"):
        return "protected-branch" if f"refs/heads/{branch}" in protected_refs else "untrusted-ref"
    return "untrusted-ref"


def _push_trust_classes(workflow: Mapping[str, Any], protected_refs: set[str]) -> set[str]:
    push = as_mapping(as_mapping(workflow.get("on", workflow.get(True))).get("push"))
    branches = as_list(push.get("branches"))
    tags = as_list(push.get("tags"))
    classes = {_branch_trust_class(branch, protected_refs) for branch in branches}
    if not branches and not tags:
        classes.update({"protected-branch", "untrusted-ref"})
    ignored = as_list(push.get("branches-ignore")) or as_list(push.get("tags-ignore"))
    if tags or ignored:
        classes.add("untrusted-ref")
    return classes


def trust_classes(
    workflow: Mapping[str, Any],
    job: Mapping[str, Any],
    protected_refs: set[str],
) -> tuple[set[str], bool]:
    triggers = trigger_names(workflow)
    classes: set[str] = set()
    class_triggers = {
        "branch_protection_rule": "protected-branch",
        "workflow_dispatch": "manual",
        "schedule": "scheduled",
        "workflow_call": "reusable",
    }
    if triggers & {"pull_request", "pull_request_target"}:
        classes.add("untrusted-pr")
    if "push" in triggers:
        classes.update(_push_trust_classes(workflow, protected_refs))
    classes.update(value for key, value in class_triggers.items() if key in triggers)
    return filter_trust_classes(classes, job.get("if"), protected_refs, triggers)


def workflow_trust_classes(
    workflows: Mapping[str, Mapping[str, Any]],
    protected_refs: set[str],
) -> tuple[dict[str, set[str]], set[str]]:
    unsupported: set[str] = set()
    classes: dict[str, set[str]] = {}
    for path, workflow in workflows.items():
        classes[path], supported = trust_classes(workflow, {}, protected_refs)
        if not supported:
            unsupported.add(path)
    changed = True
    while changed:
        changed = _propagate_reusable_trust(workflows, protected_refs, classes, unsupported)
    return classes, unsupported


def _propagate_reusable_trust(
    workflows: Mapping[str, Mapping[str, Any]],
    protected_refs: set[str],
    classes: dict[str, set[str]],
    unsupported: set[str],
) -> bool:
    changed = False
    for path, workflow in workflows.items():
        for job_value in as_mapping(workflow.get("jobs")).values():
            job = as_mapping(job_value)
            uses = job.get("uses")
            if not isinstance(uses, str) or not uses.startswith("./"):
                continue
            target = uses.removeprefix("./")
            if target not in classes:
                continue
            inherited, supported = trust_classes(workflow, job, protected_refs)
            if not supported:
                unsupported.add(path)
            expanded = classes[target] | inherited
            if expanded != classes[target]:
                classes[target] = expanded
                changed = True
    return changed


def permissions(workflow: Mapping[str, Any], job: Mapping[str, Any]) -> tuple[dict[str, str], bool]:
    value = job.get("permissions") if "permissions" in job else workflow.get("permissions")
    permission_map = {str(key): str(child) for key, child in value.items()} if isinstance(value, Mapping) else {}
    invalid = not isinstance(value, Mapping) or any(
        level not in {"none", "read", "write"} for level in permission_map.values()
    )
    return permission_map, invalid


def _text_secret_classes(value: str) -> tuple[set[str], bool]:
    matches = [*_SECRET_DOT_RE.finditer(value), *_SECRET_BRACKET_RE.finditer(value)]
    classes = {
        f"secret:{(match.group(1) if match.re is _SECRET_DOT_RE else match.group(2)).lower().replace('_', '-')}"
        for match in matches
    }
    scrubbed = list(value)
    for match in matches:
        scrubbed[match.start() : match.end()] = " " * (match.end() - match.start())
    unsupported = any(
        _SECRET_CONTEXT_RE.search(expression.group()) is not None
        for expression in _WORKFLOW_EXPRESSION_RE.finditer("".join(scrubbed))
    )
    return classes, unsupported


def _nested_secret_classes(values: Iterable[object]) -> tuple[set[str], bool]:
    classes: set[str] = set()
    unsupported = False
    for child in values:
        child_classes, child_unsupported = secret_classes(child)
        classes.update(child_classes)
        unsupported = unsupported or child_unsupported
    return classes, unsupported


def secret_classes(value: object) -> tuple[set[str], bool]:
    if isinstance(value, str):
        result = _text_secret_classes(value)
    elif isinstance(value, Mapping):
        result = _nested_secret_classes(value.values())
    elif isinstance(value, list):
        result = _nested_secret_classes(value)
    else:
        result = (set(), False)
    return result


def job_credential_classes(
    workflow: Mapping[str, Any],
    job: Mapping[str, Any],
    permission_map: Mapping[str, str],
) -> tuple[set[str], bool]:
    workflow_secrets, workflow_unsupported = secret_classes(as_mapping(workflow.get("env")))
    job_context = dict(job)
    job_context.pop("steps", None)
    job_secrets, job_unsupported = secret_classes(job_context)
    credentials = {"github-token", *workflow_secrets, *job_secrets}
    if permission_map.get("id-token") == "write":
        credentials.add("github-oidc")
    return credentials, workflow_unsupported or job_unsupported


def condition_proves_protected_manual(condition: object, protected_refs: set[str]) -> bool:
    expression = condition_ast(condition)
    if expression is None:
        return False
    effective_refs = protected_refs or {"refs/heads/main"}
    contexts = generic_trust_contexts(effective_refs, expression, {"workflow_dispatch"})["manual"]
    unprotected = [context for context in contexts if context[_REF] not in effective_refs]
    return all(True not in condition_values(expression, context) for context in unprotected)


__all__ = (
    "SHA40_RE",
    "action_identity",
    "condition_proves_protected_manual",
    "filter_trust_classes",
    "job_credential_classes",
    "permissions",
    "secret_classes",
    "trigger_names",
    "workflow_trust_classes",
)
