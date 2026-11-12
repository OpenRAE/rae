"""Lexical execution-policy binding through the canonical composition seam."""

from typing import Any

from raes_contracts.execution_policy import ExecutionPolicy, ExecutionPolicyDocument, ExecutionPolicyScope
from raes_contracts.json_pointer import escape_token, unescape_token

from .._composition_provenance import prefixed_scope_pointer
from ..execution_policy_scope import EXECUTION_SECTIONS
from ._lexical_scope import rewritten_namespaces


def rewrite_execution_policy(payload: dict[str, Any], symbols: dict[str, dict[str, str]], namespace: str) -> None:
    raw = payload.get("execution_policy")
    if raw is None:
        return
    document = ExecutionPolicyDocument.model_validate(raw)
    prefix = (namespace,) if namespace else ()
    scopes = []
    for rule in document.scopes:
        policy = _rewritten_policy(rule.policy, symbols)
        for owner in rewritten_namespaces(rule, symbols, namespace, EXECUTION_SECTIONS):
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
        identity = unescape_token(parts[4])
        renamed = symbols[parts[3]].get(identity, identity)
        parts[4] = escape_token(renamed)
    return "/".join(parts)


def merge_execution_policy(root: dict[str, Any], incoming: dict[str, Any]) -> None:
    if incoming.get("execution_policy") is None:
        return
    local = ExecutionPolicyDocument.model_validate(root.get("execution_policy") or {})
    imported = ExecutionPolicyDocument.model_validate(incoming["execution_policy"])
    root["execution_policy"] = ExecutionPolicyDocument(
        default=local.default, scopes=(*local.scopes, *imported.scopes)
    ).model_dump(mode="python")
