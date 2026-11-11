"""Preserve safe-state definitions and private proof bindings across imports."""

from typing import Any

from raes_contracts.safe_state import SafeStateDocument, SafeStateScope

from .._composition_provenance import prefixed_scope_pointer
from ._lexical_scope import rewritten_namespaces


def rewrite_safe_state(payload: dict[str, Any], symbols: dict[str, dict[str, str]], namespace: str) -> None:
    if payload.get("safe_state") is None:
        return
    document = SafeStateDocument.model_validate(payload["safe_state"])
    rules = list(document.scopes)
    if document.default is not None:
        rules.append(SafeStateScope(state=document.default))
    rewritten = []
    for rule in rules:
        state = rule.state.model_dump(mode="python")
        state["assertion_refs"] = tuple(symbols["assertions"].get(ref, ref) for ref in rule.state.assertion_refs)
        for owner in rewritten_namespaces(rule, symbols, namespace, frozenset({"nodes"})):
            rewritten.append(
                SafeStateScope(
                    namespace=owner,
                    scope=prefixed_scope_pointer(rule.scope, symbols=symbols),
                    state=state,
                )
            )
    payload["safe_state"] = SafeStateDocument(scopes=tuple(rewritten)).model_dump(mode="python")


def merge_safe_state(root: dict[str, Any], incoming: dict[str, Any]) -> None:
    if incoming.get("safe_state") is None:
        return
    local = SafeStateDocument.model_validate(root.get("safe_state") or {})
    imported = SafeStateDocument.model_validate(incoming["safe_state"])
    root["safe_state"] = SafeStateDocument(default=local.default, scopes=(*local.scopes, *imported.scopes)).model_dump(
        mode="python"
    )
