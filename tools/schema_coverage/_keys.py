"""Closed key sets, bounds, and rule identifiers for published-schema coverage."""

from __future__ import annotations

import re

ASSURANCE_FULFILLMENT_RELATIVE_PATH = "specs/formal/assurance-fulfillment.yaml"
MANIFEST_RELATIVE_PATH = "contracts/schema-publication-manifest.json"

COVERAGE_KEY = "coverage"
CATALOG_RULE_ID = "schema-coverage-catalog-unreadable"
DECLARATION_RULE_ID = "schema-coverage-declaration-invalid"
MISSING_RULE_ID = "schema-coverage-missing"

MAX_SOURCES = 8
RATIONALE_BOUNDS = (20, 500)
SUPPORTS_BOUNDS = (10, 200)
MAX_SOURCE_BYTES = 1_000_000
MAX_SCHEMA_BYTES = 4_000_000
MAX_POINTER_LENGTH = 256

COVERAGE_KEYS = frozenset({"rationale", "sources"})
SOURCE_KEYS = frozenset({"kind", "path", "pointer", "schema_pointer", "supports"})
SOURCE_KINDS = frozenset({"fixture", "embedded"})

CONTRACTS_ROOT = "contracts/"
JSON_SUFFIX = ".json"
DEFS_PREFIX = "#/$defs/"
METASCHEMA = "https://json-schema.org/draft/2020-12/schema"
VERSION_SUFFIX = re.compile(r"^(?P<base>.+)-(?P<version>v\d+)$")

# Covering legs, strongest evidence first.
CORPUS = "corpus"
FORMAL = "formal"
DECLARED = "declared"
UNCOVERED = "uncovered"

__all__ = [
    "ASSURANCE_FULFILLMENT_RELATIVE_PATH",
    "CATALOG_RULE_ID",
    "CONTRACTS_ROOT",
    "CORPUS",
    "COVERAGE_KEY",
    "COVERAGE_KEYS",
    "DECLARATION_RULE_ID",
    "DECLARED",
    "DEFS_PREFIX",
    "FORMAL",
    "JSON_SUFFIX",
    "MANIFEST_RELATIVE_PATH",
    "MAX_POINTER_LENGTH",
    "MAX_SCHEMA_BYTES",
    "MAX_SOURCE_BYTES",
    "MAX_SOURCES",
    "METASCHEMA",
    "MISSING_RULE_ID",
    "RATIONALE_BOUNDS",
    "SOURCE_KEYS",
    "SOURCE_KINDS",
    "SUPPORTS_BOUNDS",
    "UNCOVERED",
    "VERSION_SUFFIX",
]
