"""Helpers for loading the UCO alignment evidence catalog."""

from __future__ import annotations

import json
from pathlib import Path

from raes_contracts.contracts.catalogs import UcoAlignmentCatalogModel

from .corpus import CONCEPT_AUTHORITY, corpus_family_root


def uco_alignment_catalog_path() -> Path:
    return corpus_family_root(CONCEPT_AUTHORITY) / "uco-alignment-v1.json"


def load_uco_alignment_catalog() -> UcoAlignmentCatalogModel:
    path = uco_alignment_catalog_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return UcoAlignmentCatalogModel.model_validate(payload)
