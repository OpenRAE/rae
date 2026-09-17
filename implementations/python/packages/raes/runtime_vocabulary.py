"""One field adapter for catalog-governed SDL identity vocabularies."""

from enum import Enum
from functools import partial
from typing import Annotated, TypeVar, get_args

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema

from ._base import VARIABLE_TOKEN_PATTERN
from .runtime_values import parse_runtime_enum_or_var


def _alias_pattern(value: str) -> str:
    """Encode only the incumbent case and hyphen/underscore authoring aliases."""
    return "".join(
        "[-_]" if char == "_" else f"[{char.lower()}{char.upper()}]" if char.isalpha() else char for char in value
    )


class _VocabularyField:
    def __get_pydantic_core_schema__(self, source: object, handler: GetCoreSchemaHandler) -> CoreSchema:
        enum_type = next(arg for arg in get_args(source) if isinstance(arg, type) and issubclass(arg, Enum))
        return core_schema.no_info_before_validator_function(
            partial(parse_runtime_enum_or_var, enum_cls=enum_type, field_name=enum_type.__name__),
            handler(source),
        )

    def __get_pydantic_json_schema__(self, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        from raes_contracts.controlled_vocabularies import (
            controlled_vocabulary_id_for_scope,
            load_controlled_vocabulary_catalog,
        )

        result = handler(schema)
        choices = result["anyOf"]
        enum_schema = next(handler.resolve_ref_schema(choice) for choice in choices if "$ref" in choice)
        scope = f"sdl.definitions.{enum_schema['title']}"
        vocabulary_id = controlled_vocabulary_id_for_scope(scope)
        vocabulary = (
            load_controlled_vocabulary_catalog().vocabularies[vocabulary_id] if vocabulary_id is not None else None
        )
        alternatives = [_alias_pattern(term) for term in enum_schema["enum"]]
        if vocabulary is not None and vocabulary.extension_policy == "governed-extension":
            alternatives.append(vocabulary.extension_pattern.removeprefix("^").removesuffix("$"))
        alternatives.append(VARIABLE_TOKEN_PATTERN)
        # JSON Schema's $ also matches before a trailing newline. The final
        # negative lookahead gives it Python fullmatch's whole-value boundary.
        string_schema = next(choice for choice in choices if choice.get("type") == "string")
        string_schema["pattern"] = "^(?:" + "|".join(alternatives) + r")$(?![\s\S])"
        return result


_Identity = TypeVar("_Identity", bound=Enum)
GovernedVocabulary = Annotated[_Identity | str, _VocabularyField()]
