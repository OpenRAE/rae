"""Catalog paths, table regexes, and normative-owner link constants."""

from __future__ import annotations

import re

SECTIONS_PATH = "specs/sdl/sections.md"
REFERENCES_PATH = "specs/sdl/references.md"
RUNTIME_PATH = "specs/sdl/runtime-inventory.md"
DOCUMENT_MODEL_PATH = "specs/sdl/document-model.md"
VARIABLES_PATH = "specs/sdl/variables-and-instantiation.md"
DIAGNOSTICS_PATH = "specs/sdl/diagnostics.md"
PHASES_PATH = "specs/formal/sdl-phases/README.md"
SCHEMA_PATH = "contracts/schemas/sdl/sdl-authoring-input-v1.json"

_TOP_LEVEL_HEADING = "## Complete top-level field catalog"
_REFERENCE_HEADING = "## 6. Machine-checkable reference-edge index"
_RUNTIME_HEADING = "## 2. Family index"
_PHASE_HEADING = "## Phase-specific member catalog"
_SUMMARY_RE = re.compile(
    r"<!-- sdl-catalog-summary "
    r"top-level=(?P<top>\d+) metadata-composition=(?P<meta>\d+) "
    r"sections=(?P<sections>\d+) maps=(?P<maps>\d+) lists=(?P<lists>\d+) -->"
)
_SEPARATOR_RE = re.compile(r"^:?-{2,}:?$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\((?P<target>[^)]+)\)")
_IMPLEMENTATION_TERM_RE = re.compile(
    r"\b(?:Python|Pydantic|ValidationError|SDLParseError|SDLInstantiationError|SDLValidationError|"
    r"SDLMigrationPolicy)\b"
)
_VALID_KINDS = frozenset({"metadata", "composition", "section"})
_VALID_SHAPES = frozenset({"scalar", "mapping", "map", "list"})
_VALID_LIFECYCLE = frozenset({"normalized", "expanded", "instantiated"})
_MAX_CATALOG_BYTES = 512 * 1024
_MAX_CATALOG_ROWS = 512
_METADATA_FIELDS = frozenset({"name", "version", "description", "semantic_revision"})
_COMPOSITION_FIELDS = frozenset({"module", "imports", "realization"})

_SEMANTIC = "semantic validation"
_STRUCTURAL = "structural validation"
_DANGLING = "fatal dangling or ambiguous"
_NODE_ROLES = "derived:node_roles"
_DANGLING_ROLE = "fatal dangling role when non-empty"
_SWITCH_BACKED = "fatal unless the target is switch-backed"
_DANGLING_CYCLIC = "fatal dangling, ambiguous, or cyclic"
_NON_PRECONDITION_ROLE = "fatal dangling, ambiguous, or non-precondition role"
_STRUCTURAL_MODEL = "structural model validation"
_ARTIFACT_VOLUME_FIELDS = "generated_artifacts,persistent_volumes"
_MAIL_SERVICE_SCOPE = "fatal outside the target mail service"
_MIXED_CONTROL_IDS = "derived:mixed_control_local_ids"
_STRUCTURAL_SEMANTIC = "structural and semantic validation"
_STALE_LOCAL_REF = "fatal dangling, stale, reversed, or ambiguously ordered local ref"
_UNKNOWN_VOCABULARY = "fatal unknown vocabulary identifier"
_WRONG_SLOT_CANDIDATE = "fatal dangling or wrong slot candidate type"
_VARIATION_MEMBERS = "derived:variation_members"
_VARIATION_SCOPE = "fatal outside the resolved variation point"
_ORDER_POINT_SCOPE = "fatal outside the owning order point"
_DANGLING_UNREACHABLE = "fatal dangling, cyclic, or unreachable"

# This independently owned expectation makes every normative reference row a
# checked contract. The catalog is not generated from this registry; changing
