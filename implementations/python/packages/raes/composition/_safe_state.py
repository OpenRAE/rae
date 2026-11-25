"""Preserve safe-state definitions and private proof bindings across imports."""

from typing import Any

from raes_contracts.safe_state import SafeState, SafeStateDocument, SafeStateScope

from .._composition_provenance import prefixed_scope_pointer
from ._lexical_scope import rewritten_namespaces


def rewrite_safe_state(payload: dict[str, Any], symbols: dict[str, dict[str, str]], namespace: str) -> None:
    if payload.get("safe_state") is None:
        return
    document = SafeStateDocument.model_validate(payload["safe_state"])
    rules = list(document.scopes)
    default = None
    if document.default is not None:
        # An imported default governs only its own namespace; an unprefixed rewrite keeps the root default.
        if namespace:
            rules.append(SafeStateScope(state=document.default))
        else:
            default = _rewritten_state(document.default, symbols)
    rewritten = []
    for rule in rules:
        state = _rewritten_state(rule.state, symbols)
        for owner in rewritten_namespaces(rule, symbols, namespace, frozenset({"nodes"})):
            rewritten.append(
                SafeStateScope(
                    namespace=owner,
                    scope=prefixed_scope_pointer(rule.scope, symbols=symbols),
                    state=state,
                )
            )
    payload["safe_state"] = SafeStateDocument(default=default, scopes=tuple(rewritten)).model_dump(mode="python")


def _rewritten_state(state: SafeState, symbols: dict[str, dict[str, str]]) -> dict[str, Any]:
    value = state.model_dump(mode="python")
    value["assertion_refs"] = tuple(symbols["assertions"].get(ref, ref) for ref in state.assertion_refs)
    return value


def merge_safe_state(root: dict[str, Any], incoming: dict[str, Any]) -> None:
    if incoming.get("safe_state") is None:
        return
    local = SafeStateDocument.model_validate(root.get("safe_state") or {})
    imported = SafeStateDocument.model_validate(incoming["safe_state"])
    root["safe_state"] = SafeStateDocument(default=local.default, scopes=(*local.scopes, *imported.scopes)).model_dump(
        mode="python"
    )
