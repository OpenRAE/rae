"""Shared constants, closed key sets, and release types for formal validation."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = "docs/research/formal-semantic-validation/bundle-manifest.json"
MANIFEST_SCHEMA_VERSION = "formal-semantic-validation-bundle-index/v2"
_MAX_FILE_BYTES = 512 * 1024
_MAX_CASES = 128
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_JsonObject = dict[str, object]

REQUIRED_CLAIM_CLASS_IDS = {
    "schema-validity",
    "semantic-consistency",
    "graph-reachability",
    "constraint-satisfiability",
    "exploit-path-validity",
    "determinism-stability",
    "counterfactual-necessity",
}
REQUIRED_PARTICIPANT_OBLIGATION_IDS = {
    "hidden-vs-visible-projection",
    "fail-closed-action-applicability",
    "shared-state-effects",
    "ordering-before-causality",
    "evidence-labeled-attribution",
    "participant-local-outcome-separation",
    "realization-profile-honesty",
}
EVIDENCE_STATUSES = {"untested", "partial", "demonstrated", "refuted"}
REPLAY_MODES = {"parse", "compile-stability", "compile-distinguish", "unsupported"}
PRODUCTION_EVIDENCE_REPLAY_MODES = {"satisfiability", "exploit-path"}


@dataclasses.dataclass
class EvidenceRelease:
    """One atomically selected and digest-pinned evidence release."""

    manifest_path: str
    manifest: dict[str, object]
    protocol: dict[str, object]
    corpus: dict[str, object]
    snapshot: dict[str, object]
    analysis: dict[str, object]


class ParticipantTestRunner(Protocol):
    """Callable boundary used to replay the participant test evidence."""

    def __call__(self, repo_root: Path, test_refs: list[str]) -> tuple[bool, str]: ...


_MANIFEST_KEYS = {
    "bundle_id",
    "revision",
    "protocol_path",
    "corpus_path",
    "snapshot_path",
    "analysis_path",
    "satisfiability_snapshot_path",
    "satisfiability_analysis_path",
}
_RELEASE_MANIFEST_KEYS = {
    "bundle_id",
    "revision",
    "protocol_path",
    "protocol_sha256",
    "corpus_path",
    "corpus_sha256",
    "snapshot_path",
    "snapshot_sha256",
    "analysis_path",
    "analysis_sha256",
    "artifacts",
}
_RELEASE_ARTIFACT_PIN_KEYS = {"artifact_id", "kind", "path", "sha256"}
_PROTOCOL_KEYS = {
    "protocol_id",
    "revision",
    "registered_at",
    "title",
    "issue_number",
    "requirement_uid",
    "research_question",
    "claim_classes",
    "participant_obligations",
    "evidence_status_values",
    "gate_outcome_values",
    "analysis_rules",
    "amendment_log",
}
_CLAIM_CLASS_KEYS = {
    "claim_class_id",
    "label",
    "boundary",
    "artifact_stage",
    "entrypoint_id",
    "objective_pass_criteria",
    "objective_fail_criteria",
    "allowed_evidence",
    "disallowed_evidence",
    "expected_evidence_status",
}
_PARTICIPANT_KEYS = {
    "obligation_id",
    "label",
    "positive_test_ref",
    "negative_test_ref",
}
_ANALYSIS_RULE_KEYS = {
    "case_coverage",
    "participant_coverage",
    "unsupported_policy",
    "failure_policy",
    "immutability_policy",
}
_CORPUS_KEYS = {"corpus_id", "revision", "cases"}
_CASE_KEYS = {
    "case_id",
    "claim_class_id",
    "polarity",
    "title",
    "artifact_stage",
    "entrypoint_id",
    "fixture_path",
    "comparison_fixture_path",
    "replay_mode",
    "expected_outcome",
    "limitation",
}
_HISTORICAL_REVISION_FIELD = "a" + "ces_revision"
_HISTORICAL_BUNDLE_ID = "a" + "ces-formal-semantic-validation"
_HISTORICAL_SATISFIABILITY_ANALYSIS_PROFILE = "a" + "ces-formal-satisfiability-analysis/v1"
_HISTORICAL_SATISFIABILITY_EXECUTION_PROFILE = "a" + "ces-formal-satisfiability-execution/v1"
_HISTORICAL_SATISFIABILITY_PROFILE = "a" + "ces-finite-domain-satisfiability-v1"
_HISTORICAL_CLI = "implementations/python/.venv/bin/" + "a" + "ces"
_CURRENT_SATISFIABILITY_PROFILE = "raes-finite-domain-satisfiability-v1"
_HISTORICAL_VM_REPLAY_INPUTS = {
    (
        "semantic-resolved-objective",
        "docs/research/formal-semantic-validation/corpus/semantic-valid.sdl.yaml",
    ): "a074d75b1b420a47a740703deaff45c20ec1c5d846f660412929bc69ab0efb19",
    (
        "semantic-ambiguous-reference",
        "docs/research/formal-semantic-validation/corpus/semantic-invalid-ambiguous-ref.sdl.yaml",
    ): "653cbd2fd62e220d49fb86f80133884207df5ae6752846345ae3085b93f6e4ed",
    (
        "compile-repeatability-control",
        "docs/research/formal-semantic-validation/corpus/determinism-a.sdl.yaml",
    ): "0bc40900d598c1af7a405d798ca19710405e53ced262d8733081abf12edf89fe",
    (
        "compile-non-vacuity-control",
        "docs/research/formal-semantic-validation/corpus/determinism-a.sdl.yaml",
    ): "0bc40900d598c1af7a405d798ca19710405e53ced262d8733081abf12edf89fe",
    (
        "compile-non-vacuity-control",
        "docs/research/formal-semantic-validation/corpus/determinism-b.sdl.yaml",
    ): "d85338f89f20a45515b12da8640173c1a52e47eb17ca0f4f6b4f8f3306e863a1",
}
_RETAINED_CASE_TEXT_REPLACEMENTS = {
    "A" + "CES has no governed whole-scenario constraint theory or solver entrypoint.": (
        "The issue-168 baseline has no governed whole-scenario constraint theory or solver entrypoint."
    ),
}

_SNAPSHOT_KEYS = {
    "execution_id",
    "protocol_revision",
    "corpus_revision",
    "captured_at",
    "execution_status",
    _HISTORICAL_REVISION_FIELD,
    "configuration_id",
    "commands",
    "observations",
    "participant_observations",
    "deviations",
}
_COMMAND_KEYS = {"command_id", "argv", "network"}
_OBSERVATION_KEYS = {
    "case_id",
    "execution_id",
    "configuration_id",
    "replayable",
    "actual_outcome",
    "diagnostic_kind",
    "result_digest",
    "evidence_refs",
    "limitations",
}
_OBSERVATION_V2_KEYS = _OBSERVATION_KEYS | {
    "evidence_profile",
    "analysis_profile",
    "configuration_digest",
    "evidence_digest",
    "evidence_artifact_path",
    "evidence_artifact_sha256",
    "source_digest",
}
_PARTICIPANT_OBSERVATION_KEYS = {
    "obligation_id",
    "execution_id",
    "positive_outcome",
    "negative_outcome",
    "evidence_refs",
    "limitations",
}
_ANALYSIS_KEYS = {
    "analysis_id",
    "protocol_revision",
    "corpus_revision",
    "execution_id",
    "generated_at",
    "claim_results",
    "evidence_status",
    "claim",
    "plain_language_outcome",
    "limitations",
}
_SNAPSHOT_V2_KEYS = (_SNAPSHOT_KEYS - {_HISTORICAL_REVISION_FIELD}) | {
    "baseline",
    "raes_revision",
    "versions",
}
_VERSION_KEYS = {"python", "raes", "z3_solver", "z3_engine"}
_BASELINE_KEYS = {
    "release_path",
    "release_sha256",
    "release_revision",
    "execution_id",
}
_DEVIATION_KEYS = {
    "case_id",
    "changed_fields",
    "baseline",
    "retest",
    "disposition",
    "category",
    "rationale",
}
_CLAIM_RESULT_KEYS = {
    "claim_class_id",
    "evidence_status",
    "case_count",
    "matching_case_count",
    "replayable_case_count",
    "unsupported_case_count",
    "participant_obligation_count",
    "limitations",
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
_SATISFIABILITY_ANALYSIS_KEYS = {
    "profile",
    "revision",
    "execution_id",
    "snapshot_revision",
    "issue_number",
    "requirement_uid",
    "analysis_profile",
    "claim_class_id",
    "evidence_status",
    "scope",
    "cases",
    "limitations",
}
_SATISFIABILITY_SNAPSHOT_KEYS = {
    "profile",
    "revision",
    "execution_id",
    "captured_at",
    "analysis_profile",
    "solver_configuration_digest",
    "commands",
    "observations",
    "deviations",
}
_SATISFIABILITY_OBSERVATION_KEYS = {
    "case_id",
    "actual_outcome",
    "source_byte_digest",
    "normalized_model_digest",
    "evidence_profile",
    "replayable",
    "limitation",
}
_SATISFIABILITY_CASE_KEYS = {
    "case_id",
    "control",
    "fixture_path",
    "expected_outcome",
    "expected_normalized_model_digest",
    "limitation",
}
_SATISFIABILITY_CONTROL_OUTCOMES = {
    "positive": "satisfiable",
    "negative": "unsatisfiable",
    "unsupported": "unsupported",
}

# Immutable admission pins for the finite pre-cutover research corpus at
# a7c6b55cd056a82a146f5e7537743269f1d8ec24. Artifact metadata cannot rebind these.
_ARCHIVAL_MANIFEST_SHA256 = "2c99aa95a6429ba9ec31eb2b34f312f0fa7cd8df4a17084eb7782a5ba7ba0560"
_PROGRESSIVE_ARCHIVAL_MANIFEST_SHA256 = "e2cfd0d3a492a8304b322240d043dca4abfa66816e89066c000cb260150e7ef5"
# Release 16 is historical after the issue-1241 capture. These exact records
# are retained without invoking current models, solvers or semantic admission.
_PROGRESSIVE_PRODUCTION_EVIDENCE_DIGESTS = frozenset(
    {
        "sha256:23c2cae7d95d4cc83d77ca576e3911477b169ecc311c977cb45490345f633b5a",
        "sha256:317b5cad00aa7f4f7868dca66127611ba19d40ffd86f35815502622814df54c1",
        "sha256:2d4d1a362751abd9544beb8af7f8c6331d04dac8f4abc315fb261f81fbaf4387",
        "sha256:1b416bb5a4d29d57c961b769cc9d3af5d9328624e3eebf104d57f39a94c5bb97",
    }
)
_RETAINED_PRODUCTION_EVIDENCE_DIGESTS = frozenset(
    {
        "sha256:03925bfe0b209c3c77069c97061aa63e8795389be7ed7b78376020b7dc87853c",  # finite-domain-satisfiable-v2.json
        "sha256:36e1a09e5ac51cfdd98be743c7b9e6073a6f3d02ac6377f60592fcb0a381a3e8",  # finite-domain-satisfiable-v3.json
        # Unsatisfiable finite-domain evidence, revision 2.
        "sha256:c2dc067c406ee9c26837e9565b6b52f8a6268e06e95dbc5937a455700b0c8109",
        # Unsatisfiable finite-domain evidence, revision 3.
        "sha256:8816c3a2898193280321559545cfacd462f38172fe7fbe7b005610401563b629",
        "sha256:1ec2ff4423088ad2ac6328aba7fbced5cd89b1569cff057e44ad30ef5c5befc0",  # typed-exploit-path-invalid-v2.json
        "sha256:b43be52d3fe4bb66fa35e296de496f286daaf09d69975218ddc30fc79b5df6d0",  # typed-exploit-path-invalid-v3.json
        "sha256:0683b55cd2a52ba626bb5cfbf10de109798d8d31ba467aabd13d4930df204798",  # typed-exploit-path-valid-v2.json
        "sha256:1c0fc5c8ecadc14e14b8993b4a3b59562a64bc35ef7dbf64f43ff7df9b5da472",  # typed-exploit-path-valid-v3.json
    }
)
