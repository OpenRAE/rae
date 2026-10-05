"""Lexical execution-policy binding through the canonical composition seam."""

from typing import Any

from raes_contracts.execution_policy import ExecutionPolicy, ExecutionPolicyDocument, ExecutionPolicyScope

from .._composition_provenance import prefixed_scope_pointer
from ..execution_policy_scope import EXECUTION_SECTIONS


def rewrite_execution_policy(payload: dict[str, Any], symbols: dict[str, dict[str, str]], namespace: str) -> None:
    raw = payload.get("execution_policy")
    if raw is None:
        return
    document = ExecutionPolicyDocument.model_validate(raw)
    prefix = (namespace,) if namespace else ()
    scopes = []
    for rule in document.scopes:
        policy = _rewritten_policy(rule.policy, symbols)
        for owner in _rewritten_namespaces(rule, symbols, namespace):
            scopes.append(
                ExecutionPolicyScope(
                    namespace=owner,
                    scope=_rewritten_scope(rule.scope, symbols),
                    policy=policy,
                )
            )
    default = _rewritten_policy(document.default, symbols) if document.default is not None else None
    if namespace and default is not None:
        scopes.insert(0, ExecutionPolicyScope(namespace=prefix, policy=default))
        default = None
    payload["execution_policy"] = ExecutionPolicyDocument(default=default, scopes=tuple(scopes)).model_dump(
        mode="python"
    )


def _rewritten_policy(policy: ExecutionPolicy, symbols: dict[str, dict[str, str]]) -> dict[str, Any]:
    value = policy.model_dump(mode="python")
    if value["clock_ref"] is not None:
        value["clock_ref"] = symbols["clocks"].get(value["clock_ref"], value["clock_ref"])
    # Reset/compensation refs belong to native cleanup authority, not SDL symbols.
    value["evidence_refs"] = tuple(symbols["evidence_requirements"].get(ref, ref) for ref in value["evidence_refs"])
    return value


def _rewritten_scope(pointer: str, symbols: dict[str, dict[str, str]]) -> str:
    parts = prefixed_scope_pointer(pointer, symbols=symbols).split("/")
    if len(parts) == 5 and parts[1] == "nodes" and parts[3] in {"features", "conditions", "injects"}:
        identity = parts[4].replace("~1", "/").replace("~0", "~")
        renamed = symbols[parts[3]].get(identity, identity)
        parts[4] = renamed.replace("~", "~0").replace("/", "~1")
    return "/".join(parts)


def _rewritten_namespaces(
    rule: ExecutionPolicyScope, symbols: dict[str, dict[str, str]], namespace: str
) -> tuple[tuple[str, ...], ...]:
    prefix = (namespace,) if namespace else ()
    if not rule.namespace:
        return (prefix,)
    targets = set()
    pointer = rule.scope.split("/")
    for section in EXECUTION_SECTIONS:
        if rule.scope and pointer[1] != section:
            continue
        for old, new in symbols.get(section, {}).items():
            owner = _renamed_owner(rule, pointer, old, new)
            if owner is not None:
                targets.add(owner)
    return tuple(sorted(targets)) if targets else ((*prefix, *rule.namespace),)


def _renamed_owner(rule: ExecutionPolicyScope, pointer: list[str], old: str, new: str) -> tuple[str, ...] | None:
    if len(pointer) >= 3 and old != pointer[2].replace("~1", "/").replace("~0", "~"):
        return None
    old_owner = tuple(old.split(".")[:-1])
    if old_owner[: len(rule.namespace)] != rule.namespace:
        return None
    new_owner = tuple(new.split(".")[:-1])
    # Visibility can insert a private segment before the original lexical path.
    depth = len(new_owner) - len(old_owner) + len(rule.namespace)
    return new_owner[:depth]


def merge_execution_policy(root: dict[str, Any], incoming: dict[str, Any]) -> None:
    if incoming.get("execution_policy") is None:
        return
    local = ExecutionPolicyDocument.model_validate(root.get("execution_policy") or {})
    imported = ExecutionPolicyDocument.model_validate(incoming["execution_policy"])
    root["execution_policy"] = ExecutionPolicyDocument(
        default=local.default, scopes=(*local.scopes, *imported.scopes)
    ).model_dump(mode="python")
