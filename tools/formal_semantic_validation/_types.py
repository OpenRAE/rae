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
_RENAMED_FORMAL_REPLAY_DIGESTS = {
    "semantic-resolved-objective": (
        "ba0ecbfcb3090ffd6b660cb51324fafcd47ca8dedbbb985e98b6e7f64f8cc25b",
        "5332666a0299d2c303d7a7da4b56dfd309cebf021af187b063ef597cf81bf40a",
    ),
    "compile-repeatability-control": (
        "a7a03db548d2a62214567834da0876609f9ff64f988878f719f846e6c5218f31",
        "0e03b80171b795c24babcca3b4dc337584c1ae1483327124ff1717b50acaf9d9",
    ),
    "compile-non-vacuity-control": (
        "a9705de7191f3d2a76bd7aa53a1da0603c1cdc60f154a90c4e9cba6bf4d37e76",
        "204baf2963c10a9c3c10b2ac0881b7041a845fc7d11b6d4a25b4f14f9bdb5760",
    ),
}
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
_RENAMED_SATISFIABILITY_MODEL_DIGESTS = {
    "finite-domain-satisfiable": (
        "sha256:32ac029d9279e6c7ea4cd9082435eb6fa455122bba57498923b8371818ef708c",
        "sha256:fbd664cb97b3f95d89220c967af0c9c55b3bcb60ff755442b54007dad6971423",
    ),
    "finite-domain-unsatisfiable": (
        "sha256:3a061baa67090e312abc4bca7a3ed24cc9458487b67f2fc37b3b7abcac2ecf1b",
        "sha256:525d1520b96cc8a606dcfbc16d4c8c833ef00d6e258aed0a9bd47ba986b33e61",
    ),
    "finite-domain-unsupported": (
        "sha256:2f0f762771dc329419ab739766f684c18261aba28c2fbc50a26ee8ad80224ba5",
        "sha256:9cb311dac08cb20ed21d48d8cd5a4d49c51eb1036a0c6ba97e6f56a88d05ccfa",
    ),
}
_MIGRATED_PRODUCTION_EVIDENCE_DIGESTS = {
    "finite-domain-satisfiable-v2": (
        "sha256:03925bfe0b209c3c77069c97061aa63e8795389be7ed7b78376020b7dc87853c",
        "sha256:60495371aecdd9dff463726e54af424359e09429f8283cd31c1de847bbc38cba",
    ),
    "finite-domain-unsatisfiable-v2": (
        "sha256:c2dc067c406ee9c26837e9565b6b52f8a6268e06e95dbc5937a455700b0c8109",
        "sha256:8816c3a2898193280321559545cfacd462f38172fe7fbe7b005610401563b629",
    ),
    "typed-exploit-path-valid-v2": (
        "sha256:0683b55cd2a52ba626bb5cfbf10de109798d8d31ba467aabd13d4930df204798",
        "sha256:00a7d75ddaf8e21fb82de2ecbff3dfafc29660d0e60829610fcb607d3da5ef0f",
    ),
    "typed-exploit-path-invalid-v2": (
        "sha256:1ec2ff4423088ad2ac6328aba7fbced5cd89b1569cff057e44ad30ef5c5befc0",
        "sha256:74db3e5df9c19fe7a9a203ad3440656229af9df56164d63ec90f0c55e0aab8f2",
    ),
}
_RENAMED_SOLVER_CONFIGURATION_DIGEST = (
    "sha256:63e58f4637dbd8328d84a286e1e5af1f3a69557e5209f683909ce22f39838e7d",
    "sha256:1204635e17e759e9ad3bd6be2ecb28c6de05c07ead6dfdd15936ed5d3d5b81b2",
)
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
