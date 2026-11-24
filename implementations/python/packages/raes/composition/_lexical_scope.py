"""Shared lexical ownership rewriting through module symbol maps."""

from raes_contracts.json_pointer import unescape_token
from raes_contracts.lexical_scope import LexicalScope


def rewritten_namespaces(
    rule: LexicalScope,
    symbols: dict[str, dict[str, str]],
    namespace: str,
    sections: frozenset[str],
) -> tuple[tuple[str, ...], ...]:
    prefix = (namespace,) if namespace else ()
    if not rule.namespace:
        return (prefix,)
    targets = set()
    pointer = rule.scope.split("/")
    for section in sections:
        if rule.scope and pointer[1] != section:
            continue
        for old, new in symbols.get(section, {}).items():
            owner = _renamed_owner(rule, pointer, old, new)
            if owner is not None:
                targets.add(owner)
    return tuple(sorted(targets)) if targets else ((*prefix, *rule.namespace),)


def _renamed_owner(rule: LexicalScope, pointer: list[str], old: str, new: str) -> tuple[str, ...] | None:
    if len(pointer) >= 3 and old != unescape_token(pointer[2]):
        return None
    old_owner = tuple(old.split(".")[:-1])
    if old_owner[: len(rule.namespace)] != rule.namespace:
        return None
    new_owner = tuple(new.split(".")[:-1])
    # Visibility can insert a private segment before the original lexical path.
    depth = len(new_owner) - len(old_owner) + len(rule.namespace)
    return new_owner[:depth]
