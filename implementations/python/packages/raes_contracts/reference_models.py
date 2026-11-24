"""Helpers for loading shared reference model declarations."""

from __future__ import annotations

import json
from pathlib import Path

from raes_contracts.contracts.catalogs import ReferenceModelCatalogModel

from .corpus import CONCEPT_AUTHORITY, corpus_family_root


def reference_model_catalog_path() -> Path:
    return corpus_family_root(CONCEPT_AUTHORITY) / "reference-models-v1.json"


def load_reference_model_catalog() -> ReferenceModelCatalogModel:
    path = reference_model_catalog_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReferenceModelCatalogModel.model_validate(payload)
