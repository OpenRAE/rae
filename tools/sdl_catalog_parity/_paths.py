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

_NODE_VALIDATOR = "[node validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py)"
_INFRASTRUCTURE_VALIDATOR = (
    "[infrastructure validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py)"
)
_SECTION_VALIDATOR = "[section validator](../../implementations/python/packages/raes/validator/_sections.py)"
_CONTENT_VALIDATOR = "[content validator](../../implementations/python/packages/raes/validator/_content_objectives.py)"
_SERVICE_MATERIALIZATION_VALIDATOR = (
    "[service materialization validator]"
    "(../../implementations/python/packages/raes/validator/_service_materialization.py)"
)
_CONTENT_COMPILER = "[content compiler](../../implementations/python/packages/raes_processor/compiler/placement.py)"
_ACCOUNT_VALIDATOR = "[account validator](../../implementations/python/packages/raes/validator/_content_objectives.py)"
_STATEFUL_MODEL = "[scenario model](../../implementations/python/packages/raes/scenario.py)"
_RELATIONSHIP_VALIDATOR = (
    "[relationship validator](../../implementations/python/packages/raes/validator/_relationships.py)"
)
_RELATIONSHIP_PROXY_VALIDATOR = (
    "[proxy relationship validator](../../implementations/python/packages/raes/validator/_relationships_proxy.py)"
)
_MAIL_VALIDATOR = "[mail validator](../../implementations/python/packages/raes/validator/_runtime_mail.py)"
_DOMAIN_TOPOLOGY_SEMANTICS = (
    "[domain topology semantics](../../implementations/python/packages/raes/semantics/domain_topology.py)"
)
_ENTERPRISE_IDENTITY_SEMANTICS = (
    "[enterprise identity semantics](../../implementations/python/packages/raes/semantics/enterprise_identity.py)"
)
_DEPLOYMENT_TENANCY_SEMANTICS = (
    "[deployment tenancy semantics](../../implementations/python/packages/raes/semantics/deployment_tenancy.py)"
)
_PARTICIPANT_VALIDATOR = (
    "[participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py)"
)
_PARTICIPANT_SEMANTICS = (
    "[participant semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py)"
)
_PARTICIPANT_INTERACTIVE_ACCESS_SEMANTICS = (
    "[participant interactive-access semantics]"
    "(../../implementations/python/packages/raes/semantics/participant_interactive_access.py)"
)
_OUTCOME_SEMANTICS = "[outcome semantics](../../implementations/python/packages/raes/semantics/participant_outcome.py)"
_BEHAVIOR_SEMANTICS = (
    "[behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py)"
)
_BEHAVIOR_VALIDATOR = (
    "[behavior validator](../../implementations/python/packages/raes/validator/_content_objectives.py)"
)
_MIXED_CONTROL_VALIDATOR = (
    "[behavior validator](../../implementations/python/packages/raes/validator/_mixed_control.py)"
)
_TOOL_AFFORDANCE_VALIDATOR = (
    "[tool-affordance validator](../../implementations/python/packages/raes/validator/_participant_tool_affordances.py)"
)
_PARTICIPANT_INJECT_DELIVERY_VALIDATOR = (
    "[participant-inject delivery validator]"
    "(../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py)"
)
_BEHAVIOR_MODEL = "[behavior model](../../implementations/python/packages/raes/participant_behavior/__init__.py)"
_MIXED_CONTROL_MODEL = (
    "[behavior model](../../implementations/python/packages/raes/participant_behavior_specification.py)"
)
_EVIDENCE_VALIDATOR = (
    "[evidence validator](../../implementations/python/packages/raes/validator/_evidence_requirements.py)"
)
_OBJECTIVE_SEMANTICS = (
    "[objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py)"
)
_WORKFLOW_SEMANTICS = "[workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py)"
_PROPOSITION_VALIDATOR = (
    "[proposition validator](../../implementations/python/packages/raes/validator/_propositions.py)"
)
_VARIATION_VALIDATOR = "[variation validator](../../implementations/python/packages/raes/validator/_variation.py)"
_PARTICIPANT_TEMPORAL_MODEL = (
    "[temporal model](../../implementations/python/packages/raes/participant_temporal_semantics.py)"
)
_TIME_MODEL_VALIDATOR = "[time-model validator](../../implementations/python/packages/raes/validator/_time_model.py)"
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
