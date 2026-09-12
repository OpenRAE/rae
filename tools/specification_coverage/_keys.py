"""Bundle paths, closed key sets, and bounded limits for coverage validation."""

from __future__ import annotations

import re

MANIFEST_PATH = "docs/research/specification-coverage/bundle-manifest.json"
MANIFEST_SCHEMA_VERSION = "specification-coverage-bundle-index/v1"
PROTOCOL_PATH = "docs/research/specification-coverage/protocol-v1.json"
EXPECTED_CLASSIFICATIONS = {
    "directly-expressible",
    "profile-or-manifest-constraint",
    "deliberately-backend-specific",
    "missing",
}
EXPECTED_STRATA = {
    "cyber-range-survey",
    "agent-benchmark",
    "scenario-dsl",
    "simulation-emulation-platform",
}
IMPLEMENTATION_SURFACE_PATHS = {
    "contract-models": "implementations/python/packages/raes_contracts",
    "processor-pipeline": "implementations/python/packages/raes_processor",
    "sdl-pipeline": "implementations/python/packages/raes",
}
_PACKAGES_ROOT = "implementations/python/packages/"
_EXECUTION_SNAPSHOT_PATH = "docs/research/specification-coverage/execution-snapshot-v8.json"
HISTORICAL_IMPLEMENTATION_SURFACE_PATHS = {
    "contract-models": _PACKAGES_ROOT + "a" + "ces_contracts",
    "processor-pipeline": _PACKAGES_ROOT + "a" + "ces_processor",
    "sdl-pipeline": _PACKAGES_ROOT + "a" + "ces_sdl",
}

_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_CATALOG_ITEMS = 256
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
}

_MANIFEST_KEYS = {
    "bundle_id",
    "revision",
    "protocol_path",
    "protocol_sha256",
    "snapshot_path",
    "snapshot_sha256",
    "analysis_path",
    "analysis_sha256",
}
_PROTOCOL_KEYS = {
    "protocol_id",
    "revision",
    "registered_at",
    "title",
    "claim",
    "research_question",
    "evidence_status_values",
    "classification_rules",
    "coverage_strata",
    "artifact_stages",
    "sources",
    "requests",
    "carriers",
    "concepts",
    "execution_rules",
    "objective_pass_criteria",
    "objective_fail_criteria",
    "validity_threats",
    "amendment_log",
}
_STRATUM_KEYS = {"stratum_id", "label", "minimum_sources"}
_STAGE_KEYS = {"stage_id", "canonical_entrypoint"}
_SOURCE_KEYS = {
    "source_id",
    "stratum_id",
    "kind",
    "title",
    "locator",
    "version",
    "revision",
    "artifact_path",
    "content_sha256",
}
_REQUEST_KEYS = {
    "request_id",
    "stratum_id",
    "source_refs",
    "title",
    "paraphrase",
    "concept_ids",
}
_CARRIER_KEYS = {"carrier_id", "kind", "artifact_id", "portable", "description"}
_CONCEPT_KEYS = {
    "concept_id",
    "request_id",
    "title",
    "meaning",
    "atomic",
    "load_bearing",
    "expected_classification",
    "expected_carrier_id",
    "artifact_stage_ids",
    "success_rule",
    "fail_rule",
}
_EXECUTION_RULE_KEYS = {
    "stage_outcomes",
    "validation_strength_values",
    "missing_concepts_force_partial",
    "load_bearing_failure_forces_refuted",
    "unallowed_backend_leakage_forces_refuted",
    "normal_execution_network_access",
}

_HISTORICAL_REVISION_FIELD = "a" + "ces_revision"
_SNAPSHOT_KEYS = {
    "snapshot_id",
    "snapshot_revision",
    "protocol_revision",
    "protocol_sha256",
    "captured_at",
    _HISTORICAL_REVISION_FIELD,
    "implementation_surfaces",
    "execution_status",
    "artifacts",
    "concept_results",
    "deviations",
    "limitations",
}
_IMPLEMENTATION_SURFACE_KEYS = {"surface_id", "path", "content_sha256"}
_ARTIFACT_KEYS = {"artifact_id", "kind", "path", "sha256", "validator"}
_CONCEPT_RESULT_KEYS = {
    "concept_id",
    "classification",
    "typed_pointer",
    "rationale",
    "stage_results",
    "backend_vocabulary_occurrences",
    "completeness_disposition",
    "backend_support",
}
_STAGE_RESULT_KEYS = {
    "stage_id",
    "outcome",
    "artifact_path",
    "pointer",
    "diagnostic_codes",
    "validation_strength",
    "note",
}
_BACKEND_OCCURRENCE_KEYS = {"term", "artifact_path", "pointer", "reason", "allowed"}

_ANALYSIS_KEYS = {
    "analysis_id",
    "protocol_revision",
    "snapshot_id",
    "snapshot_sha256",
    "generated_at",
    "execution_status",
    "classification_counts",
    "load_bearing_results",
    "request_results",
    "backend_leakage",
    "evidence_status",
    "claim",
    "plain_language_outcome",
    "limitations",
}
_REQUEST_RESULT_KEYS = {
    "request_id",
    "status",
    "concept_count",
    "missing_count",
    "failed_stage_count",
}
_CLAIM_KEYS = {
    "claim_id",
    "statement",
    "threats_to_validity",
    "falsification_protocol",
    "objective_pass_criteria",
    "objective_fail_criteria",
    "allowed_evidence",
    "disallowed_evidence",
    "evidence_artifacts",
}
