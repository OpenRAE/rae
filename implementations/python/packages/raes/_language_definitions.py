"""Definition locations projected from typed declarations and their captured provenance."""

from __future__ import annotations

from typing import Any

from raes_contracts.json_pointer import pointer_from_tokens
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from ._declarations import DeclarationIndex


def indexed_definitions(root: Node, index: DeclarationIndex) -> list[dict[str, Any]]:
    definitions = []
    for declaration in index.declarations:
        tokens = declaration.model_tokens
        if not tokens:
            continue
        location = declaration.source_location
        if location is not None:
            definition = {
                "path": location.pointer,
                "range": location.source_range.as_dict(),
                "composed_path": pointer_from_tokens(tokens),
                "module_id": location.module_id,
                "namespace": list(location.namespace),
                "content_digest": location.content_digest,
            }
            if location.source is not None:
                definition["source"] = location.source
        else:
            node = _definition_node(root, tokens)
            if node is None:
                continue
            definition = {
                "path": pointer_from_tokens(tokens),
                "range": {
                    "start": {"line": node.start_mark.line + 1, "column": node.start_mark.column + 1},
                    "end": {"line": node.end_mark.line + 1, "column": node.end_mark.column + 1},
                },
            }
        definition.update(
            name=declaration.address.rsplit(".", 1)[-1],
            qualified_name=declaration.address,
            section=tokens[0],
        )
        definitions.append(definition)
    return definitions


def _definition_node(root: Node, tokens: tuple[str, ...]) -> Node | None:
    current = root
    key: Node | None = None
    for token in tokens:
        if isinstance(current, MappingNode):
            pair = next(
                (
                    (name, value)
                    for name, value in current.value
                    if isinstance(name, ScalarNode) and name.value == token
                ),
                None,
            )
            if pair is None:
                return None
            key, current = pair
        elif isinstance(current, SequenceNode) and token.isdecimal() and int(token) < len(current.value):
            key, current = None, current.value[int(token)]
        else:
            return None
    # Dictionary declarations are defined by their literal key; list records
    # and the scenario name are defined by their authored identifier value.
    return current if _is_identifier_value(tokens) else key


def _is_identifier_value(tokens: tuple[str, ...]) -> bool:
    return tokens == ("name",) or len(tokens) > 1 and tokens[-2].isdecimal()
