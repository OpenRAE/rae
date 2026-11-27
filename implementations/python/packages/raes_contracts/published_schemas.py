"""Published contract schemas, read as data from the normative corpus.

The schemas under ``contracts/schemas/`` are the normative authority (ADR-009).
Run-time code that needs a published schema reads it here, through
:mod:`raes_contracts.corpus`. ``raes_schemas`` generates the same schemas from
the models, and ``tools/check_generated_schemas.py`` proves that both agree
(ADR-121).

A contract id is only a key of the index of published files. It never becomes
part of a file path.
"""

from __future__ import annotations

import json
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any

from .corpus import SCHEMAS, corpus_family_root


@cache
def _published_schema_paths() -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for path in sorted(corpus_family_root(SCHEMAS).rglob("*.json")):
        if path.stem in paths:
            # A corpus defect, not a domain failure (E2).
            raise RuntimeError(f"published schema contract id {path.stem!r} is not unique in the corpus")
        paths[path.stem] = path
    return paths


@cache
def _published_schema(contract_id: str) -> dict[str, Any]:
    return json.loads(_published_schema_paths()[contract_id].read_text(encoding="utf-8"))


def published_contract_ids() -> frozenset[str]:
    """Return the contract id of every published schema."""

    return frozenset(_published_schema_paths())


def published_schema(contract_id: str) -> dict[str, Any]:
    """Return an isolated copy of one published schema.

    Raises :class:`KeyError` for a contract id that has no published schema.
    """

    return deepcopy(_published_schema(contract_id))


__all__ = ["published_contract_ids", "published_schema"]
