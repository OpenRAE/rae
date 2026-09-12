"""GitHub Actions source, transitive-input, and workflow-use validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    ACTIONS_POLICY_PATH,
    ADMISSION_POLICY_PATH,
    ARTIFACT_LOCK_PATH,
    PROFILES_PATH,
    SHA40_RE,
    YAML_SUFFIXES,
    as_list,
    as_mapping,
    failure,
    has_secret_bearing_locator,
    policy_join_failures,
    safe_text,
    string_set,
    walk_forbidden_keys,
)

DEPENDABOT_PATH = ".github/dependabot.yml"
_GITHUB_EVENT_NAME = "github.event_name"
_GITHUB_PR_HEAD_REPOSITORY = "github.event.pull_request.head.repo.full_name"
_GITHUB_REF = "github.ref"
_SECRET_DOT_RE = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)\b")
_SECRET_BRACKET_RE = re.compile(r"\bsecrets\s*\[\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\1\s*\]")
_SECRET_CONTEXT_RE = re.compile(r"\bsecrets\b", re.IGNORECASE)
_WORKFLOW_EXPRESSION_RE = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)
_MATRIX_EXPRESSION_RE = re.compile(r"^\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*)\s*\}\}$")
_CONDITION_TOKEN_RE = re.compile(
    r"\s*(?:(?P<operator>&&|\|\||==|!=|[!()])|"
    r"(?P<string>'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")|"
    r"(?P<identifier>[A-Za-z_][A-Za-z0-9_.-]*))"
)
_ORIGIN_RE = re.compile(r"^(?:\*\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
_MUTABLE_RUNNERS = frozenset({"ubuntu-latest", "windows-latest", "macos-latest"})
_RUNNER_PROFILES = {
    "ubuntu-22.04": "proof-ubuntu-22.04-x86_64",
    "ubuntu-24.04": "public-ubuntu-24.04-x86_64",
    "ubuntu-24.04-arm": "public-linux-arm64",
    "macos-15": "public-macos-arm64",
    "macos-15-intel": "public-macos-x86_64",
}
_MAX_MATRIX_ROWS = 256


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
        if not self.tokens:
            return ("literal", True)
        expression = self._parse_or()
        if self.position != len(self.tokens):
            raise _ConditionSyntaxError("trailing condition tokens")
        return expression

    def _accept(self, token: str) -> bool:
        if self.position < len(self.tokens) and self.tokens[self.position] == token:
            self.position += 1
            return True
        return False

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
        if self._accept("!"):
            return ("not", self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> tuple[Any, ...]:
        if self._accept("("):
            expression = self._parse_or()
            if not self._accept(")"):
                raise _ConditionSyntaxError("unclosed condition group")
            return expression
        left = self._parse_operand()
        if self.position < len(self.tokens) and self.tokens[self.position] in {
            "==",
            "!=",
        }:
            operator = self.tokens[self.position]
            self.position += 1
            return (operator, left, self._parse_operand())
        return ("truthy", left)

    def _parse_operand(self) -> tuple[Any, ...]:
        if self.position >= len(self.tokens):
            raise _ConditionSyntaxError("missing condition operand")
        lexeme = self.tokens[self.position]
        if lexeme in {"&&", "||", "==", "!=", "!", "(", ")"}:
            raise _ConditionSyntaxError("invalid condition operand")
        self.position += 1
        if lexeme.startswith(("'", '"')):
            return ("literal", lexeme[1:-1])
        if lexeme == "true":
            return ("literal", True)
        if lexeme == "false":
            return ("literal", False)
        if self._accept("("):
            if not self._accept(")"):
                raise _ConditionSyntaxError("only zero-argument condition functions are admitted")
            return ("function", lexeme)
        return ("variable", lexeme)


def _condition_ast(value: object) -> tuple[Any, ...] | None:
    if value is None or value == "":
        return ("literal", True)
    if isinstance(value, bool):
        return ("literal", value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    try:
        return _ConditionParser(text).parse()
    except _ConditionSyntaxError:
        return None


def _condition_values(expression: tuple[Any, ...], context: Mapping[str, object]) -> set[bool]:
    kind = expression[0]
    if kind == "literal":
        return {bool(expression[1])}
    if kind == "variable":
        value = context.get(str(expression[1]))
        return {bool(value)} if value is not None else {False, True}
    if kind == "function":
        return {True} if expression[1] == "always" else {False, True}
    if kind == "truthy":
        return _condition_values(expression[1], context)
    if kind == "not":
        return {not value for value in _condition_values(expression[1], context)}
    if kind in {"and", "or"}:
        left = _condition_values(expression[1], context)
        right = _condition_values(expression[2], context)
        if kind == "and":
            return {first and second for first in left for second in right}
        return {first or second for first in left for second in right}
    if kind in {"==", "!="}:
        left_known, left = _condition_operand(expression[1], context)
        right_known, right = _condition_operand(expression[2], context)
        if not left_known or not right_known:
            return {False, True}
        equal = left == right
        return {equal if kind == "==" else not equal}
    return {False, True}


def _condition_operand(expression: tuple[Any, ...], context: Mapping[str, object]) -> tuple[bool, object]:
    if expression[0] == "literal":
        return True, expression[1]
    if expression[0] == "variable" and expression[1] in context:
        return True, context[expression[1]]
    return False, None


def _condition_string_literals(expression: tuple[Any, ...]) -> set[str]:
    literals: set[str] = set()
    if expression[0] == "literal" and isinstance(expression[1], str):
        literals.add(expression[1])
    for child in expression[1:]:
        if isinstance(child, tuple):
            literals.update(_condition_string_literals(child))
    return literals


def _condition_variables(expression: tuple[Any, ...]) -> set[str]:
    variables: set[str] = set()
    if expression[0] == "variable":
        variables.add(str(expression[1]))
    for child in expression[1:]:
        if isinstance(child, tuple):
            variables.update(_condition_variables(child))
    return variables


def _unmodeled_ref(
    known_refs: set[str],
    candidate: str = "refs/heads/__gc-unmodeled-ref__",
) -> str:
    while candidate in known_refs:
        candidate += "-other"
    return candidate


def _generic_trust_contexts(
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
    repository = "gc/repository"
    repository_actors = ["gc-repository-actor", "dependabot[bot]"]
    return {
        "untrusted-pr": [
            {
                _GITHUB_EVENT_NAME: event_name,
                _GITHUB_REF: reference,
                "github.repository": repository,
                _GITHUB_PR_HEAD_REPOSITORY: "gc/fork",
                "github.actor": actor,
            }
            for event_name in pull_request_events
            for reference in (pull_request_refs if event_name == "pull_request" else all_refs)
            for actor in repository_actors
        ],
        "same-repository-pr": [
            {
                _GITHUB_EVENT_NAME: event_name,
                _GITHUB_REF: reference,
                "github.repository": repository,
                _GITHUB_PR_HEAD_REPOSITORY: repository,
                "github.actor": actor,
            }
            for event_name in pull_request_events
            for reference in (pull_request_refs if event_name == "pull_request" else all_refs)
            for actor in repository_actors
        ],
        "untrusted-ref": [{_GITHUB_EVENT_NAME: "push", _GITHUB_REF: reference} for reference in unprotected],
        "protected-branch": [{_GITHUB_EVENT_NAME: "push", _GITHUB_REF: reference} for reference in protected],
        "manual": [{_GITHUB_EVENT_NAME: "workflow_dispatch", _GITHUB_REF: reference} for reference in all_refs],
        "scheduled": [{_GITHUB_EVENT_NAME: "schedule", _GITHUB_REF: protected[0]}],
        "reusable": [{_GITHUB_EVENT_NAME: "workflow_call", _GITHUB_REF: protected[0]}],
    }


def _filter_trust_classes(
    classes: set[str],
    condition: object,
    protected_refs: set[str],
    trigger_names: set[str] | None = None,
) -> tuple[set[str], bool]:
    expression = _condition_ast(condition)
    if expression is None:
        return classes, False
    candidate_classes = set(classes)
    if "untrusted-pr" in candidate_classes and (_GITHUB_PR_HEAD_REPOSITORY in _condition_variables(expression)):
        candidate_classes.add("same-repository-pr")
    contexts = _generic_trust_contexts(protected_refs, expression, trigger_names)
    return {
        trust_class
        for trust_class in candidate_classes
        if any(True in _condition_values(expression, context) for context in contexts[trust_class])
    }, True


@dataclass
class _UseEffects:
    origins: set[str] = field(default_factory=set)
    credentials: set[str] = field(default_factory=set)
    cache_roles: set[str] = field(default_factory=set)
    artifact_roles: set[str] = field(default_factory=set)
    input_contract_invalid: bool = False
    host_join_invalid: bool = False


class _ClosedWorkflowLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects aliases and duplicate mapping keys."""

    def compose_node(self, parent: object, index: object) -> yaml.Node:
        if self.check_event(AliasEvent):
            raise ConstructorError(
                None,
                None,
                "workflow aliases are not admitted",
                self.peek_event().start_mark,
            )
        return super().compose_node(parent, index)


def _construct_unique_mapping(
    loader: _ClosedWorkflowLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_ClosedWorkflowLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _safe_origins(value: object) -> bool:
    origins = as_list(value)
    return all(
        isinstance(origin, str)
        and _ORIGIN_RE.fullmatch(origin) is not None
        and not has_secret_bearing_locator(f"https://{origin}")
        for origin in origins
    )


def _workflow_paths(tracked_paths: Sequence[str]) -> list[str]:
    return [
        path for path in tracked_paths if path.startswith(".github/workflows/") and Path(path).suffix in YAML_SUFFIXES
    ]


def _parse_yaml_mapping(repo_root: Path, path: str) -> tuple[Mapping[str, Any] | None, list[PolicyFailure]]:
    text = safe_text(repo_root, path)
    if text is None:
        return None, [
            failure(
                "tooling-action-scan",
                "workflow policy input could not be read safely",
                path,
            )
        ]
    try:
        # The custom loader subclasses SafeLoader and only tightens mapping semantics.
        document = yaml.load(text, Loader=_ClosedWorkflowLoader)  # noqa: S506
    except (ConstructorError, yaml.YAMLError):
        return None, [
            failure(
                "tooling-action-scan",
                "workflow policy input could not be parsed safely",
                path,
            )
        ]
    if not isinstance(document, Mapping):
        return None, [failure("tooling-action-scan", "workflow policy input must be a mapping", path)]
    return document, []


def _workflow_documents(
    repo_root: Path,
    tracked_paths: Sequence[str],
) -> tuple[dict[str, Mapping[str, Any]], list[PolicyFailure]]:
    documents: dict[str, Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    for path in _workflow_paths(tracked_paths):
        document, parse_failures = _parse_yaml_mapping(repo_root, path)
        failures.extend(parse_failures)
        if document is not None:
            documents[path] = document
    return documents, failures


def _action_identity(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    action_name, separator, selector = value.rpartition("@")
    if not separator or not action_name or action_name.startswith(("./", "docker://", "http://", "https://")):
        return None
    return action_name.lower(), selector


def _declared_action_sources(
    policy: Mapping[str, Any],
    admission_policies: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[tuple[str, str], tuple[str, Mapping[str, Any]]],
    list[PolicyFailure],
]:
    failures = policy_join_failures(
        policy_refs=string_set(policy.get("policy_refs")),
        expected_subjects={"action"},
        provided_evidence={"git-commit-sha", "reviewed-workflow-reference"},
        policies=admission_policies,
        path=ACTIONS_POLICY_PATH,
        context="actions policy",
        require_all_evidence_per_policy=True,
    )
    sources: dict[str, Mapping[str, Any]] = {}
    identities: dict[tuple[str, str], tuple[str, Mapping[str, Any]]] = {}
    for action_value in as_list(policy.get("actions")):
        action = as_mapping(action_value)
        name = action.get("action")
        commit = action.get("commit")
        if not isinstance(name, str) or not isinstance(commit, str):
            continue
        normalized = name.lower()
        identity = (normalized, commit)
        source_id = action.get("source_id")
        if not isinstance(source_id, str):
            source_id = f"{normalized}@{commit}"
        if source_id in sources or identity in identities:
            failures.append(
                failure(
                    "tooling-action-duplicate",
                    "duplicate action source policy entry",
                    ACTIONS_POLICY_PATH,
                )
            )
        sources[source_id] = action
        identities[identity] = (source_id, action)
        if string_set(action.get("owner_roles")) & string_set(action.get("reviewer_roles")):
            failures.append(
                failure(
                    "tooling-action-source-review",
                    "action source owner and reviewer roles must be independent",
                    ACTIONS_POLICY_PATH,
                )
            )
    return sources, identities, failures


def _declared_exceptions(
    policy: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[PolicyFailure]]:
    exceptions: dict[str, Mapping[str, Any]] = {}
    failures: list[PolicyFailure] = []
    evaluation_date = policy.get("exception_evaluation_date")
    for value in as_list(policy.get("service_managed_exceptions")):
        item = as_mapping(value)
        exception_id = item.get("exception_id")
        if not isinstance(exception_id, str):
            continue
        if exception_id in exceptions:
            failures.append(
                failure(
                    "tooling-action-exception",
                    "duplicate service-managed exception",
                    ACTIONS_POLICY_PATH,
                )
            )
        exceptions[exception_id] = item
        if string_set(item.get("owner_roles")) & string_set(item.get("reviewer_roles")):
            failures.append(
                failure(
                    "tooling-action-exception",
                    "service-managed exception owner and reviewer roles must be independent",
                    ACTIONS_POLICY_PATH,
                )
            )
        review_on = item.get("review_on")
        if isinstance(evaluation_date, str) and isinstance(review_on, str) and review_on < evaluation_date:
            failures.append(
                failure(
                    "tooling-action-exception-expired",
                    "service-managed exception is expired at the reviewed evaluation date",
                    ACTIONS_POLICY_PATH,
                )
            )
        if not _safe_origins(item.get("allowed_origins")):
            failures.append(
                failure(
                    "tooling-action-origin",
                    "service-managed exception contains an unsafe origin",
                    ACTIONS_POLICY_PATH,
                )
            )
    return exceptions, failures


def _source_closure_failures(
    policy: Mapping[str, Any],
    documents: Mapping[str, dict[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    exceptions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str], list[PolicyFailure]]:
    artifact_ids = {
        item.get("artifact_id")
        for item in as_list(as_mapping(documents.get(ARTIFACT_LOCK_PATH)).get("artifacts"))
        if isinstance(item, Mapping) and isinstance(item.get("artifact_id"), str)
    }
    profile_document = as_mapping(documents.get(PROFILES_PATH))
    artifact_origins: dict[str, set[str]] = {}
    for artifact_value in as_list(as_mapping(documents.get(ARTIFACT_LOCK_PATH)).get("artifacts")):
        artifact = as_mapping(artifact_value)
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        origins = artifact_origins.setdefault(artifact_id, set())
        for platform_value in as_list(artifact.get("platforms")):
            for source_url in as_list(as_mapping(platform_value).get("source_urls")):
                if isinstance(source_url, str) and (hostname := urlsplit(source_url).hostname):
                    origins.add(hostname.lower())
    capabilities = {
        capability
        for host in as_list(profile_document.get("host_profiles"))
        if isinstance(host, Mapping)
        for capability in (
            *string_set(host.get("required_capability_ids")),
            *string_set(host.get("optional_capability_ids")),
        )
    }
    edges: dict[str, set[str]] = {name: set() for name in sources}
    direct_origins: dict[str, set[str]] = {
        name: {"api.github.com", "codeload.github.com", "github.com"} for name in sources
    }
    referenced_exceptions: set[str] = set()
    failures: list[PolicyFailure] = []
    for source_name, source in sources.items():
        input_ids: set[str] = set()
        for value in as_list(source.get("transitive_inputs")):
            transitive_input = as_mapping(value)
            input_id = transitive_input.get("input_id")
            if not isinstance(input_id, str):
                continue
            if input_id in input_ids:
                failures.append(
                    failure(
                        "tooling-action-transitive-input",
                        "duplicate transitive input id",
                        ACTIONS_POLICY_PATH,
                    )
                )
            input_ids.add(input_id)
            artifact_ref = transitive_input.get("artifact_ref")
            capability_ref = transitive_input.get("host_capability_ref")
            exception_ref = transitive_input.get("service_managed_exception_ref")
            action_ref = transitive_input.get("action_source_ref")
            if isinstance(artifact_ref, str) and artifact_ref not in artifact_ids:
                failures.append(
                    failure(
                        "tooling-action-transitive-input",
                        "action references an unknown artifact payload",
                        ACTIONS_POLICY_PATH,
                    )
                )
            elif isinstance(artifact_ref, str):
                direct_origins[source_name].update(artifact_origins.get(artifact_ref, set()))
            if isinstance(capability_ref, str) and capability_ref not in capabilities:
                failures.append(
                    failure(
                        "tooling-action-transitive-input",
                        "action references an unknown host capability",
                        ACTIONS_POLICY_PATH,
                    )
                )
            if isinstance(exception_ref, str):
                referenced_exceptions.add(exception_ref)
                exception = exceptions.get(exception_ref)
                if (
                    exception is None
                    or exception.get("source_id") != source_name
                    or str(exception.get("action", "")).lower() != str(source.get("action", "")).lower()
                    or exception.get("input_id") != input_id
                ):
                    failures.append(
                        failure(
                            "tooling-action-transitive-input",
                            "action exception does not join the exact source and input",
                            ACTIONS_POLICY_PATH,
                        )
                    )
                elif exception is not None:
                    direct_origins[source_name].update(string_set(exception.get("allowed_origins")))
            if isinstance(action_ref, str):
                edges[source_name].add(action_ref)
                if action_ref not in sources:
                    failures.append(
                        failure(
                            "tooling-action-transitive-input",
                            "action references an unknown nested source",
                            ACTIONS_POLICY_PATH,
                        )
                    )
    for _unused in sorted(set(exceptions) - referenced_exceptions):
        failures.append(
            failure(
                "tooling-action-exception",
                "unused service-managed exception",
                ACTIONS_POLICY_PATH,
            )
        )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            failures.append(
                failure(
                    "tooling-action-transitive-cycle",
                    "action source dependency graph is cyclic",
                    ACTIONS_POLICY_PATH,
                )
            )
            return
        if node in visited or node not in edges:
            return
        visiting.add(node)
        for child in sorted(edges[node]):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for source_name in sorted(edges):
        visit(source_name)

    closure_origins: dict[str, set[str]] = {}

    def origins_for(source_name: str, pending: set[str]) -> set[str]:
        if source_name in closure_origins:
            return closure_origins[source_name]
        if source_name in pending:
            return set()
        origins = set(direct_origins.get(source_name, set()))
        for child in edges.get(source_name, set()):
            origins.update(origins_for(child, {*pending, source_name}))
        closure_origins[source_name] = origins
        return origins

    for source_name in sorted(sources):
        origins_for(source_name, set())
    return edges, closure_origins, referenced_exceptions, failures


def _trigger_names(workflow: Mapping[str, Any]) -> set[str]:
    triggers = workflow.get("on", workflow.get(True))
    if isinstance(triggers, str):
        return {triggers}
    if isinstance(triggers, list):
        return {item for item in triggers if isinstance(item, str)}
    if isinstance(triggers, Mapping):
        return {str(key) for key in triggers}
    return set()


def _push_trust_classes(workflow: Mapping[str, Any], protected_refs: set[str]) -> set[str]:
    triggers = workflow.get("on", workflow.get(True))
    push = as_mapping(as_mapping(triggers).get("push"))
    classes: set[str] = set()
    branches = as_list(push.get("branches"))
    tags = as_list(push.get("tags"))
    branch_ignores = as_list(push.get("branches-ignore"))
    tag_ignores = as_list(push.get("tags-ignore"))
    if branches:
        for branch in branches:
            reference = f"refs/heads/{branch}"
            if isinstance(branch, str) and not any(character in branch for character in "*?[]"):
                classes.add("protected-branch" if reference in protected_refs else "untrusted-ref")
            else:
                classes.add("untrusted-ref")
    elif not tags:
        classes.update({"protected-branch", "untrusted-ref"})
    if tags or (not branches and not tags) or branch_ignores or tag_ignores:
        classes.add("untrusted-ref")
    return classes


def _trust_classes(
    workflow: Mapping[str, Any],
    job: Mapping[str, Any],
    protected_refs: set[str],
) -> tuple[set[str], bool]:
    triggers = _trigger_names(workflow)
    classes: set[str] = set()
    if triggers & {"pull_request", "pull_request_target"}:
        classes.add("untrusted-pr")
    if "push" in triggers:
        classes.update(_push_trust_classes(workflow, protected_refs))
    if "branch_protection_rule" in triggers:
        classes.add("protected-branch")
    if "workflow_dispatch" in triggers:
        classes.add("manual")
    if "schedule" in triggers:
        classes.add("scheduled")
    if "workflow_call" in triggers:
        classes.add("reusable")
    return _filter_trust_classes(classes, job.get("if"), protected_refs, triggers)


def _workflow_trust_classes(
    workflows: Mapping[str, Mapping[str, Any]],
    protected_refs: set[str],
) -> tuple[dict[str, set[str]], set[str]]:
    """Propagate caller trust into local reusable workflow definitions."""

    unsupported: set[str] = set()
    classes: dict[str, set[str]] = {}
    for path, workflow in workflows.items():
        classes[path], supported = _trust_classes(workflow, {}, protected_refs)
        if not supported:
            unsupported.add(path)
    changed = True
    while changed:
        changed = False
        for _path, workflow in workflows.items():
            for job_value in as_mapping(workflow.get("jobs")).values():
                job = as_mapping(job_value)
                uses = job.get("uses")
                if not isinstance(uses, str) or not uses.startswith("./"):
                    continue
                target = uses.removeprefix("./")
                if target not in classes:
                    continue
                inherited, supported = _trust_classes(workflow, job, protected_refs)
                if not supported:
                    unsupported.add(_path)
                expanded = classes[target] | inherited
                if expanded != classes[target]:
                    classes[target] = expanded
                    changed = True
    return classes, unsupported


def _permissions(workflow: Mapping[str, Any], job: Mapping[str, Any]) -> tuple[dict[str, str], bool]:
    if "permissions" in job:
        value = job.get("permissions")
    elif "permissions" in workflow:
        value = workflow.get("permissions")
    else:
        return {}, True
    if not isinstance(value, Mapping):
        return {}, True
    permissions = {str(key): str(child) for key, child in value.items()}
    return permissions, any(level not in {"none", "read", "write"} for level in permissions.values())


def _secret_classes(value: object) -> tuple[set[str], bool]:
    classes: set[str] = set()
    unsupported = False
    if isinstance(value, str):
        matches = [*_SECRET_DOT_RE.finditer(value), *_SECRET_BRACKET_RE.finditer(value)]
        for match in matches:
            name = match.group(1) if match.re is _SECRET_DOT_RE else match.group(2)
            classes.add(f"secret:{name.lower().replace('_', '-')}")
        scrubbed = list(value)
        for match in matches:
            scrubbed[match.start() : match.end()] = " " * (match.end() - match.start())
        unsupported = any(
            _SECRET_CONTEXT_RE.search(expression.group()) is not None
            for expression in _WORKFLOW_EXPRESSION_RE.finditer("".join(scrubbed))
        )
    elif isinstance(value, Mapping):
        for child in value.values():
            child_classes, child_unsupported = _secret_classes(child)
            classes.update(child_classes)
            unsupported = unsupported or child_unsupported
    elif isinstance(value, list):
        for child in value:
            child_classes, child_unsupported = _secret_classes(child)
            classes.update(child_classes)
            unsupported = unsupported or child_unsupported
    return classes, unsupported


def _job_credential_classes(
    workflow: Mapping[str, Any],
    job: Mapping[str, Any],
    permissions: Mapping[str, str],
) -> tuple[set[str], bool]:
    workflow_secrets, workflow_unsupported = _secret_classes(as_mapping(workflow.get("env")))
    job_context = dict(job)
    job_context.pop("steps", None)
    job_secrets, job_unsupported = _secret_classes(job_context)
    credentials = {"github-token", *workflow_secrets, *job_secrets}
    if permissions.get("id-token") == "write":
        credentials.add("github-oidc")
    return credentials, workflow_unsupported or job_unsupported


def _matrix_rows(job: Mapping[str, Any]) -> tuple[list[dict[str, object]], bool]:
    matrix = as_mapping(as_mapping(job.get("strategy")).get("matrix"))
    if not matrix:
        return [{}], False
    axis_names = [name for name in matrix if name not in {"include", "exclude"}]
    includes = [dict(item) for item in as_list(matrix.get("include")) if isinstance(item, Mapping)]
    invalid = len(includes) != len(as_list(matrix.get("include")))
    if invalid or len(includes) > _MAX_MATRIX_ROWS:
        return [], True
    if axis_names and includes:
        return [], True
    if includes:
        return includes, False
    axes: list[list[object]] = []
    row_count = 1
    for name in axis_names:
        values = as_list(matrix.get(name))
        if not values:
            return [], True
        axes.append(values)
        row_count *= len(values)
        if row_count > _MAX_MATRIX_ROWS:
            return [], True
    excludes = [item for item in as_list(matrix.get("exclude")) if isinstance(item, Mapping)]
    if len(excludes) != len(as_list(matrix.get("exclude"))):
        return [], True
    rows = [dict(zip(axis_names, values, strict=True)) for values in product(*axes)]
    rows = [
        row
        for row in rows
        if not any(all(row.get(name) == value for name, value in excluded.items()) for excluded in excludes)
    ]
    return rows, False


def _matrix_value(value: object, row: Mapping[str, object]) -> tuple[object, bool]:
    if not isinstance(value, str) or "matrix." not in value:
        return value, False
    match = _MATRIX_EXPRESSION_RE.fullmatch(value)
    if match is None:
        return value, False
    current: object = row
    for component in match.group(1).split("."):
        if not isinstance(current, Mapping) or component not in current:
            return value, True
        current = current[component]
    return current, False


def _runner_profiles(
    job: Mapping[str, Any],
) -> tuple[str, list[tuple[str, dict[str, object]]], bool]:
    runner = job.get("runs-on")
    if runner is None and isinstance(job.get("uses"), str):
        return "reusable-workflow", [], not str(job.get("uses")).startswith("./")
    selector = str(runner)
    rows, invalid = _matrix_rows(job)
    if invalid:
        return selector, [], True
    contexts: list[tuple[str, dict[str, object]]] = []
    for row in rows:
        concrete, unresolved = _matrix_value(runner, row)
        value = str(concrete)
        unresolved_runner = "matrix." in selector and _MATRIX_EXPRESSION_RE.fullmatch(selector) is None
        invalid = (
            invalid or unresolved or unresolved_runner or value in _MUTABLE_RUNNERS or value not in _RUNNER_PROFILES
        )
        if value in _RUNNER_PROFILES:
            contexts.append((_RUNNER_PROFILES[value], row))
    return selector, contexts, invalid


def _step_ref(step: Mapping[str, Any], action_name: str) -> str:
    return str(step.get("id") or step.get("name") or action_name)


def _input_condition_matches(value: object, inputs: Mapping[str, Any]) -> bool:
    condition = as_mapping(value)
    if not condition:
        return True
    name = condition.get("input")
    operator = condition.get("operator")
    if not isinstance(name, str):
        return False
    if operator == "present":
        return name in inputs
    if operator == "absent":
        return name not in inputs
    if operator == "equals":
        return inputs.get(name) == condition.get("value")
    if operator == "not-equals":
        return inputs.get(name) != condition.get("value")
    return False


def _effective_role(roles: set[str], *, kind: str) -> str:
    if kind == "cache":
        order = ("write-trusted", "write-untrusted", "restore", "none")
    else:
        order = ("write-trusted", "write-untrusted", "read-same-run", "none")
    return next(role for role in order if role in roles)


def _condition_proves_protected_manual(condition: object, protected_refs: set[str]) -> bool:
    expression = _condition_ast(condition)
    if expression is None:
        return False
    effective_protected_refs = protected_refs or {"refs/heads/main"}
    contexts = _generic_trust_contexts(
        effective_protected_refs,
        expression,
        {"workflow_dispatch"},
    )["manual"]
    unprotected = [context for context in contexts if context[_GITHUB_REF] not in effective_protected_refs]
    return all(True not in _condition_values(expression, context) for context in unprotected)


def _action_use_effects(
    source_id: str,
    inputs: Mapping[str, Any],
    host_profile_id: str,
    *,
    sources: Mapping[str, Mapping[str, Any]],
    exceptions: Mapping[str, Mapping[str, Any]],
    artifact_platforms: Mapping[str, list[Mapping[str, Any]]],
    host_capabilities: Mapping[str, set[str]],
) -> _UseEffects:
    result = _UseEffects()
    pending: list[tuple[str, Mapping[str, Any]]] = [(source_id, inputs)]
    visited: set[str] = set()
    while pending:
        current_id, current_inputs = pending.pop()
        if current_id in visited:
            continue
        visited.add(current_id)
        source = as_mapping(sources.get(current_id))
        if not source:
            result.host_join_invalid = True
            continue
        result.origins.update({"api.github.com", "codeload.github.com", "github.com"})
        security_effects = as_mapping(source.get("security_effects"))
        for name, allowed_values in as_mapping(security_effects.get("closed_inputs")).items():
            if (
                not isinstance(name, str)
                or name not in current_inputs
                or current_inputs[name] not in as_list(allowed_values)
            ):
                result.input_contract_invalid = True
        for effect_value in as_list(security_effects.get("credentials")):
            effect = as_mapping(effect_value)
            credential_class = effect.get("credential_class")
            if isinstance(credential_class, str) and _input_condition_matches(effect.get("when"), current_inputs):
                result.credentials.add(credential_class)
        for effect_value in as_list(security_effects.get("cache")):
            effect = as_mapping(effect_value)
            role = effect.get("role")
            if isinstance(role, str) and _input_condition_matches(effect.get("when"), current_inputs):
                result.cache_roles.add(role)
        for effect_value in as_list(security_effects.get("artifact")):
            effect = as_mapping(effect_value)
            role = effect.get("role")
            if isinstance(role, str) and _input_condition_matches(effect.get("when"), current_inputs):
                result.artifact_roles.add(role)
        for input_value in as_list(source.get("transitive_inputs")):
            transitive_input = as_mapping(input_value)
            if not _input_condition_matches(transitive_input.get("when"), current_inputs):
                continue
            artifact_ref = transitive_input.get("artifact_ref")
            capability_ref = transitive_input.get("host_capability_ref")
            exception_ref = transitive_input.get("service_managed_exception_ref")
            action_ref = transitive_input.get("action_source_ref")
            if isinstance(artifact_ref, str):
                matching_platforms = [
                    platform
                    for platform in artifact_platforms.get(artifact_ref, [])
                    if host_profile_id in string_set(platform.get("host_profile_ids"))
                ]
                if not matching_platforms:
                    result.host_join_invalid = True
                for platform in matching_platforms:
                    for source_url in as_list(platform.get("source_urls")):
                        if isinstance(source_url, str) and (hostname := urlsplit(source_url).hostname):
                            result.origins.add(hostname.lower())
            if isinstance(capability_ref, str) and capability_ref not in host_capabilities.get(host_profile_id, set()):
                result.host_join_invalid = True
            if isinstance(exception_ref, str):
                exception = as_mapping(exceptions.get(exception_ref))
                result.origins.update(string_set(exception.get("allowed_origins")))
                credential_class = exception.get("credential_class")
                if isinstance(credential_class, str) and credential_class != "none":
                    result.credentials.add(credential_class)
            if isinstance(action_ref, str):
                pending.append((action_ref, {}))
    return result


def _job_and_use_failures(
    workflows: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
    source_identities: Mapping[tuple[str, str], tuple[str, Mapping[str, Any]]],
    sources: Mapping[str, Mapping[str, Any]],
    exceptions: Mapping[str, Mapping[str, Any]],
    artifact_platforms: Mapping[str, list[Mapping[str, Any]]],
    host_capabilities: Mapping[str, set[str]],
    profile_ids: set[str],
    protected_refs: set[str],
) -> tuple[set[str], list[PolicyFailure]]:
    declared_jobs: dict[tuple[object, object], Mapping[str, Any]] = {}
    declared_sites: dict[tuple[object, object, object], Mapping[str, Any]] = {}
    declared_use_ids: set[str] = set()
    failures: list[PolicyFailure] = []
    for value in as_list(policy.get("workflow_jobs")):
        item = as_mapping(value)
        workflow_name = item.get("workflow")
        job_name = item.get("job")
        if not isinstance(workflow_name, str) or not isinstance(job_name, str):
            continue
        key = (workflow_name, job_name)
        if key in declared_jobs:
            failures.append(
                failure(
                    "tooling-action-workflow-job",
                    "duplicate workflow job context",
                    ACTIONS_POLICY_PATH,
                )
            )
        declared_jobs[key] = item
        if not _safe_origins(item.get("allowed_origins")):
            failures.append(
                failure(
                    "tooling-action-origin",
                    "workflow job contains an unsafe origin",
                    ACTIONS_POLICY_PATH,
                )
            )
    for value in as_list(policy.get("use_sites")):
        item = as_mapping(value)
        workflow_name = item.get("workflow")
        job_name = item.get("job")
        step_name = item.get("step")
        if not isinstance(workflow_name, str) or not isinstance(job_name, str) or not isinstance(step_name, str):
            continue
        key = (workflow_name, job_name, step_name)
        use_id = item.get("use_id")
        if key in declared_sites or (isinstance(use_id, str) and use_id in declared_use_ids):
            failures.append(
                failure(
                    "tooling-action-use-site",
                    "duplicate workflow action use site",
                    ACTIONS_POLICY_PATH,
                )
            )
        declared_sites[key] = item
        if isinstance(use_id, str):
            declared_use_ids.add(use_id)
        if not _safe_origins(item.get("allowed_origins")):
            failures.append(
                failure(
                    "tooling-action-origin",
                    "workflow use site contains an unsafe origin",
                    ACTIONS_POLICY_PATH,
                )
            )
    observed_jobs: set[tuple[str, str]] = set()
    observed_sites: set[tuple[str, str, str]] = set()
    observed_sources: set[str] = set()
    workflow_trust, unsupported_workflow_conditions = _workflow_trust_classes(workflows, protected_refs)
    failures.extend(
        failure(
            "tooling-action-condition",
            "workflow condition is outside the closed admission grammar",
            path,
        )
        for path in sorted(unsupported_workflow_conditions)
    )
    for path, workflow in workflows.items():
        jobs = as_mapping(workflow.get("jobs"))
        for job_name, job_value in jobs.items():
            if not isinstance(job_name, str) or not isinstance(job_value, Mapping):
                failures.append(
                    failure(
                        "tooling-action-scan",
                        "workflow jobs must be named mappings",
                        path,
                    )
                )
                continue
            job = job_value
            trust_classes, condition_supported = _filter_trust_classes(
                set(workflow_trust[path]),
                job.get("if"),
                protected_refs,
                _trigger_names(workflow),
            )
            if not condition_supported:
                failures.append(
                    failure(
                        "tooling-action-condition",
                        "job condition is outside the closed admission grammar",
                        path,
                    )
                )
            job_key = (path, job_name)
            observed_jobs.add(job_key)
            declared = as_mapping(declared_jobs.get(job_key))
            if not declared:
                failures.append(
                    failure(
                        "tooling-action-workflow-job",
                        "workflow job is absent from action policy",
                        path,
                    )
                )
            permissions, invalid_permissions = _permissions(workflow, job)
            runner, runner_contexts, invalid_runner = _runner_profiles(job)
            host_profiles = {profile_id for profile_id, _row in runner_contexts}
            credentials, unsupported_job_secret = _job_credential_classes(workflow, job, permissions)
            ambient_credentials = set(credentials)
            if invalid_permissions or invalid_runner:
                failures.append(
                    failure(
                        "tooling-action-runner" if invalid_runner else "tooling-action-permission",
                        "workflow uses implicit/broad permissions or an unqualified runner selector",
                        path,
                    )
                )
            if unsupported_job_secret:
                failures.append(
                    failure(
                        "tooling-action-credential",
                        "workflow uses an unsupported secrets-context expression",
                        path,
                    )
                )
            if host_profiles - profile_ids or host_profiles != string_set(declared.get("host_profile_ids")):
                failures.append(
                    failure(
                        "tooling-action-runner",
                        "workflow runner profile is missing or stale",
                        path,
                    )
                )
            untrusted = bool(trust_classes & {"untrusted-pr", "untrusted-ref"})
            write_permissions = {name for name, level in permissions.items() if level == "write"}
            if untrusted and write_permissions:
                failures.append(
                    failure(
                        "tooling-action-permission",
                        "pull-request job has write permission",
                        path,
                    )
                )
            if (
                untrusted
                and declared
                and (declared.get("promotion_authority") is True or declared.get("publishing_authority") is True)
            ):
                failures.append(
                    failure(
                        "tooling-action-trust-boundary",
                        "pull-request job has trusted write or publication authority",
                        path,
                    )
                )
            step_refs: set[str] = set()
            job_cache_roles = {"none"}
            job_artifact_roles = {"none"}
            job_origins: set[str] = set()
            step_records: list[dict[str, object]] = []
            untrusted_step_credentials: set[str] = set()
            for step_value in as_list(job.get("steps")):
                if not isinstance(step_value, Mapping):
                    continue
                step = step_value
                step_trust_classes, step_condition_supported = _filter_trust_classes(
                    trust_classes,
                    step.get("if"),
                    protected_refs,
                    _trigger_names(workflow),
                )
                if not step_condition_supported:
                    failures.append(
                        failure(
                            "tooling-action-condition",
                            "workflow step condition is outside the closed admission grammar",
                            path,
                        )
                    )
                step_untrusted = bool(step_trust_classes & {"untrusted-pr", "untrusted-ref"})
                step_secret_classes, unsupported_step_secret = _secret_classes(step)
                credentials.update(step_secret_classes)
                if step_untrusted:
                    untrusted_step_credentials.update(step_secret_classes)
                if unsupported_step_secret:
                    failures.append(
                        failure(
                            "tooling-action-credential",
                            "workflow step uses an unsupported secrets-context expression",
                            path,
                        )
                    )
                if "uses" not in step:
                    continue
                identity = _action_identity(step.get("uses"))
                if identity is None:
                    failures.append(
                        failure(
                            "tooling-action-source",
                            "workflow action source uses an unsupported identity form",
                            path,
                        )
                    )
                    continue
                action_name, commit = identity
                if not SHA40_RE.fullmatch(commit):
                    failures.append(
                        failure(
                            "tooling-action-mutable",
                            "workflow action is not pinned to a full commit",
                            path,
                        )
                    )
                source_entry = source_identities.get((action_name, commit))
                if source_entry is None:
                    failures.append(
                        failure(
                            "tooling-action-unowned",
                            "workflow action source is not policy-owned",
                            path,
                        )
                    )
                    source_id = ""
                else:
                    source_id = source_entry[0]
                    observed_sources.add(source_id)
                step_name = _step_ref(step, action_name)
                if step_name in step_refs and not isinstance(step.get("id"), str):
                    failures.append(
                        failure(
                            "tooling-action-use-site",
                            "repeated action use requires an explicit step id",
                            path,
                        )
                    )
                step_refs.add(step_name)
                site_key = (path, job_name, step_name)
                observed_sites.add(site_key)
                declared_site = as_mapping(declared_sites.get(site_key))
                inputs = {str(key): child for key, child in as_mapping(step.get("with")).items()}
                raw_cache_roles: set[str] = set()
                raw_artifact_roles: set[str] = set()
                expected_origins: set[str] = set()
                for host_profile_id, matrix_row in runner_contexts:
                    concrete_inputs: dict[str, object] = {}
                    unresolved_matrix = False
                    for name, value in inputs.items():
                        concrete_inputs[name], unresolved = _matrix_value(value, matrix_row)
                        unresolved_matrix = unresolved_matrix or unresolved
                    effects = _action_use_effects(
                        source_id,
                        concrete_inputs,
                        host_profile_id,
                        sources=sources,
                        exceptions=exceptions,
                        artifact_platforms=artifact_platforms,
                        host_capabilities=host_capabilities,
                    )
                    expected_origins.update(effects.origins)
                    credentials.update(effects.credentials)
                    if step_untrusted:
                        untrusted_step_credentials.update(effects.credentials)
                    raw_cache_roles.update(effects.cache_roles)
                    raw_artifact_roles.update(effects.artifact_roles)
                    if unresolved_matrix or effects.input_contract_invalid:
                        failures.append(
                            failure(
                                "tooling-action-input-contract",
                                "action inputs are outside the source's closed security contract",
                                path,
                            )
                        )
                    if effects.host_join_invalid:
                        failures.append(
                            failure(
                                "tooling-action-host-join",
                                "action payload or capability is not admitted by the concrete runner profile",
                                path,
                            )
                        )
                actual_cache_role = _effective_role(
                    {
                        ("write-untrusted" if step_untrusted else "write-trusted") if role == "write" else role
                        for role in raw_cache_roles
                    }
                    | {"none"},
                    kind="cache",
                )
                actual_artifact_role = _effective_role(
                    {
                        ("write-untrusted" if step_untrusted else "write-trusted") if role == "write" else role
                        for role in raw_artifact_roles
                    }
                    | {"none"},
                    kind="artifact",
                )
                job_cache_roles.add(actual_cache_role)
                job_artifact_roles.add(actual_artifact_role)
                job_origins.update(expected_origins)
                step_records.append(
                    {
                        "declared": declared_site,
                        "source_id": source_id,
                        "action": action_name,
                        "commit": commit,
                        "inputs": inputs,
                        "trust_classes": step_trust_classes,
                        "cache_role": actual_cache_role,
                        "artifact_role": actual_artifact_role,
                        "allowed_origins": expected_origins,
                    }
                )
                if step_untrusted and actual_cache_role not in {"none", "restore"}:
                    failures.append(
                        failure(
                            "tooling-action-cache",
                            "pull-request action may write a shared cache",
                            path,
                        )
                    )
            privileged_credentials = ((ambient_credentials if untrusted else set()) | untrusted_step_credentials) - {
                "actions-artifact-token",
                "actions-cache-token",
                "github-token",
            }
            if untrusted and privileged_credentials:
                failures.append(
                    failure(
                        "tooling-action-credential",
                        "untrusted job path can receive a secret or OIDC credential",
                        path,
                    )
                )
            if (
                "manual" in trust_classes
                and declared
                and (
                    write_permissions
                    or (
                        credentials
                        - {
                            "actions-artifact-token",
                            "actions-cache-token",
                            "github-token",
                        }
                    )
                    or declared.get("promotion_authority") is True
                    or declared.get("publishing_authority") is True
                )
                and (
                    not isinstance(declared.get("protected_definition_ref"), str)
                    or not _condition_proves_protected_manual(job.get("if"), protected_refs)
                )
            ):
                failures.append(
                    failure(
                        "tooling-action-trust-boundary",
                        "manual privileged job lacks a protected-definition rule",
                        path,
                    )
                )
            if declared and (
                declared.get("runner") != runner
                or string_set(declared.get("trust_classes")) != trust_classes
                or as_mapping(declared.get("permissions")) != permissions
                or string_set(declared.get("credential_classes")) != credentials
                or declared.get("cache_access") != _effective_role(job_cache_roles, kind="cache")
                or declared.get("artifact_access") != _effective_role(job_artifact_roles, kind="artifact")
                or string_set(declared.get("allowed_origins")) != job_origins
            ):
                failures.append(
                    failure(
                        "tooling-action-workflow-job",
                        "workflow job capabilities differ from action policy",
                        path,
                    )
                )
            for record in step_records:
                declared_site = as_mapping(record["declared"])
                if not declared_site or any(
                    (
                        declared_site.get("source_id") != record["source_id"],
                        declared_site.get("action") != record["action"],
                        declared_site.get("commit") != record["commit"],
                        as_mapping(declared_site.get("inputs")) != record["inputs"],
                        string_set(declared_site.get("trust_classes")) != record["trust_classes"],
                        declared_site.get("cache_role") != record["cache_role"],
                        declared_site.get("artifact_role") != record["artifact_role"],
                        string_set(declared_site.get("credential_classes")) != credentials,
                        string_set(declared_site.get("allowed_origins")) != record["allowed_origins"],
                    )
                ):
                    failures.append(
                        failure(
                            "tooling-action-use-site",
                            "workflow action use differs from action policy",
                            path,
                        )
                    )
    for path, _job in sorted(set(declared_jobs) - observed_jobs):
        failures.append(
            failure(
                "tooling-action-workflow-job",
                "action policy contains a stale workflow job",
                str(path),
            )
        )
    for path, _job, _step in sorted(set(declared_sites) - observed_sites):
        failures.append(
            failure(
                "tooling-action-use-site",
                "action policy contains a stale workflow use site",
                str(path),
            )
        )
    return observed_sources, failures


def _local_workflow_failures(
    workflows: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[PolicyFailure]:
    declared: dict[tuple[str, str], Mapping[str, Any]] = {}
    observed: set[tuple[str, str]] = set()
    failures: list[PolicyFailure] = []
    for value in as_list(policy.get("local_workflows")):
        item = as_mapping(value)
        path = item.get("caller_workflow")
        job = item.get("caller_job")
        if not isinstance(path, str) or not isinstance(job, str):
            continue
        key = (path, job)
        if key in declared:
            failures.append(
                failure(
                    "tooling-reusable-workflow",
                    "duplicate local reusable-workflow call",
                    ACTIONS_POLICY_PATH,
                )
            )
        declared[key] = item
    for path, workflow in workflows.items():
        for job_name, job_value in as_mapping(workflow.get("jobs")).items():
            job = as_mapping(job_value)
            uses = job.get("uses")
            if not isinstance(job_name, str) or not isinstance(uses, str):
                continue
            if not uses.startswith("./"):
                failures.append(
                    failure(
                        "tooling-reusable-workflow",
                        "remote reusable workflows are not admitted",
                        path,
                    )
                )
                continue
            key = (path, job_name)
            observed.add(key)
            expected = as_mapping(declared.get(key))
            target_path = uses.removeprefix("./")
            target = workflows.get(target_path)
            permissions, broad = _permissions(workflow, job)
            target_permissions_exceed = False
            contract_invalid = False
            if target is not None:
                levels = {"none": 0, "read": 1, "write": 2}
                for target_job_value in as_mapping(target.get("jobs")).values():
                    target_permissions, target_broad = _permissions(target, as_mapping(target_job_value))
                    target_permissions_exceed = (
                        target_permissions_exceed
                        or target_broad
                        or any(
                            levels.get(level, 3) > levels.get(permissions.get(scope, "none"), 0)
                            for scope, level in target_permissions.items()
                        )
                    )
                triggers = target.get("on", target.get(True))
                call = as_mapping(as_mapping(triggers).get("workflow_call"))
                contract_inputs = as_mapping(call.get("inputs"))
                contract_secrets = as_mapping(call.get("secrets"))
                supplied_inputs = as_mapping(job.get("with"))
                required_inputs = {
                    name
                    for name, definition in contract_inputs.items()
                    if isinstance(name, str) and as_mapping(definition).get("required") is True
                }
                contract_invalid = bool(
                    set(supplied_inputs) - set(contract_inputs)
                    or required_inputs - set(supplied_inputs)
                    or contract_secrets
                )
            if (
                not expected
                or expected.get("path") != uses
                or as_mapping(expected.get("inputs")) != as_mapping(job.get("with"))
                or as_mapping(expected.get("permissions")) != permissions
                or broad
                or target is None
                or "workflow_call" not in _trigger_names(target)
                or "secrets" in job
                or target_permissions_exceed
                or contract_invalid
            ):
                failures.append(
                    failure(
                        "tooling-reusable-workflow",
                        "local reusable-workflow identity or call contract differs",
                        path,
                    )
                )
    for path, _job in sorted(set(declared) - observed):
        failures.append(
            failure(
                "tooling-reusable-workflow",
                "action policy contains a stale reusable-workflow call",
                str(path),
            )
        )
    return failures


def _dependabot_failures(
    repo_root: Path,
    tracked_paths: Sequence[str],
    policy: Mapping[str, Any],
) -> list[PolicyFailure]:
    if DEPENDABOT_PATH not in tracked_paths:
        return []
    document, failures = _parse_yaml_mapping(repo_root, DEPENDABOT_PATH)
    if document is None:
        return failures
    expected = as_mapping(policy.get("dependabot"))
    if document != expected:
        failures.append(
            failure(
                "tooling-action-dependabot",
                "Dependabot configuration differs from the complete admitted update policy",
                DEPENDABOT_PATH,
            )
        )
    return failures


def _reachable_sources(roots: set[str], edges: Mapping[str, set[str]]) -> set[str]:
    reachable: set[str] = set()
    pending = list(roots)
    while pending:
        source = pending.pop()
        if source in reachable:
            continue
        reachable.add(source)
        pending.extend(edges.get(source, ()))
    return reachable


def action_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str],
) -> list[PolicyFailure]:
    """Validate every action source, transitive input, job, and use occurrence."""

    policy = documents.get(ACTIONS_POLICY_PATH)
    if policy is None:
        return []
    admission = documents.get(ADMISSION_POLICY_PATH) or {}
    admission_policies = {
        item["policy_id"]: item
        for item in as_list(admission.get("policies"))
        if isinstance(item, Mapping) and isinstance(item.get("policy_id"), str)
    }
    sources, source_identities, failures = _declared_action_sources(policy, admission_policies)
    exceptions, exception_failures = _declared_exceptions(policy)
    failures.extend(exception_failures)
    failures.extend(walk_forbidden_keys(policy, path=ACTIONS_POLICY_PATH))
    edges, _source_origins, _referenced_exceptions, closure_failures = _source_closure_failures(
        policy,
        documents,
        sources,
        exceptions,
    )
    failures.extend(closure_failures)
    workflows, parse_failures = _workflow_documents(repo_root, tracked_paths)
    failures.extend(parse_failures)
    host_profiles = [
        item
        for item in as_list(as_mapping(documents.get(PROFILES_PATH)).get("host_profiles"))
        if isinstance(item, Mapping) and isinstance(item.get("host_profile_id"), str)
    ]
    profile_ids = {str(item["host_profile_id"]) for item in host_profiles}
    host_capabilities = {
        str(item["host_profile_id"]): {
            *string_set(item.get("required_capability_ids")),
            *string_set(item.get("optional_capability_ids")),
        }
        for item in host_profiles
    }
    artifact_platforms = {
        str(item["artifact_id"]): [
            platform for platform in as_list(item.get("platforms")) if isinstance(platform, Mapping)
        ]
        for item in as_list(as_mapping(documents.get(ARTIFACT_LOCK_PATH)).get("artifacts"))
        if isinstance(item, Mapping) and isinstance(item.get("artifact_id"), str)
    }
    protected_refs = string_set(policy.get("protected_refs"))
    observed_sources, job_failures = _job_and_use_failures(
        workflows,
        policy,
        source_identities,
        sources,
        exceptions,
        artifact_platforms,
        host_capabilities,
        profile_ids,
        protected_refs,
    )
    failures.extend(job_failures)
    failures.extend(_local_workflow_failures(workflows, policy))
    failures.extend(_dependabot_failures(repo_root, tracked_paths, policy))
    reachable = _reachable_sources(observed_sources, edges)
    failures.extend(
        failure(
            "tooling-action-stale",
            "action policy contains an unused source reference",
            ACTIONS_POLICY_PATH,
        )
        for _unused in sorted(set(sources) - reachable)
    )
    return failures
