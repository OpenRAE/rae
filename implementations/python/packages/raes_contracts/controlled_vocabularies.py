"""Helpers for loading and validating controlled vocabulary declarations."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from .contracts import ControlledVocabularyCatalogModel
from .corpus import CONCEPT_AUTHORITY, corpus_family_root


def controlled_vocabulary_catalog_path() -> Path:
    return corpus_family_root(CONCEPT_AUTHORITY) / "controlled-vocabularies-v1.json"


@lru_cache(maxsize=1)
def load_controlled_vocabulary_catalog() -> ControlledVocabularyCatalogModel:
    path = controlled_vocabulary_catalog_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ControlledVocabularyCatalogModel.model_validate(payload)


@lru_cache(maxsize=1)
def _scope_to_vocabulary_id() -> dict[str, str]:
    catalog = load_controlled_vocabulary_catalog()
    return {
        scope: vocabulary_id
        for vocabulary_id, definition in catalog.vocabularies.items()
        for scope in definition.governed_scopes
    }


def controlled_vocabulary_id_for_scope(scope: str) -> str | None:
    """Return the catalog-owned vocabulary for a declared scope, if any."""
    return _scope_to_vocabulary_id().get(scope)


def validate_controlled_vocabulary_value(vocabulary_id: str, value: str) -> None:
    catalog = load_controlled_vocabulary_catalog()
    try:
        definition = catalog.vocabularies[vocabulary_id]
    except KeyError as exc:
        raise ValueError(f"unknown controlled vocabulary '{vocabulary_id}'") from exc

    if value in definition.terms:
        return
    if definition.extension_policy == "closed":
        raise ValueError(
            f"controlled vocabulary '{vocabulary_id}' does not allow extensions; '{value}' is not a permitted term"
        )
    if definition.extension_pattern is None:
        raise ValueError(f"controlled vocabulary '{vocabulary_id}' is missing its extension pattern")
    if re.fullmatch(definition.extension_pattern, value):
        return
    raise ValueError(
        f"controlled vocabulary '{vocabulary_id}' does not permit term '{value}'; "
        "value is not a permitted term and must match the governed extension pattern"
    )


def validate_controlled_vocabulary_scope_values(scope: str, values: Iterable[str]) -> None:
    vocabulary_id = _scope_to_vocabulary_id().get(scope)
    if vocabulary_id is None:
        raise ValueError(f"scope '{scope}' is not governed by controlled-vocabularies-v1")
    for value in values:
        validate_controlled_vocabulary_value(vocabulary_id, value)
