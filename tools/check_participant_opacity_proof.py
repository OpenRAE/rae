from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raes_contracts.behavioral_relation_profiles import (  # noqa: E402
    load_behavioral_relation_profile_revision,
)
from raes_contracts.behavioral_relations import (  # noqa: E402
    load_behavioral_relation_catalog_revision,
    validate_behavioral_claim_binding,
)
from raes_contracts.contracts.base import BehavioralClaimBindingModel  # noqa: E402
from raes_contracts.json_ingress import parse_bounded_json_object  # noqa: E402

from tools.isabelle_tool import (  # noqa: E402
    ISABELLE_BUILD_TIMEOUT_SECONDS,
    ISABELLE_FILE_LIMIT_BYTES,
    ISABELLE_JAVA_MAX_HEAP_MIB,
    ISABELLE_ML_MAX_HEAP_MIB,
    ISABELLE_OUTPUT_LIMIT_BYTES,
    ISABELLE_PROCESS_ADDRESS_SPACE_LIMIT_MIB,
    ISABELLE_SESSION,
    ISABELLE_SESSION_RELATIVE_PATH,
    expected_isabelle_result,
    run_isabelle_build,
)
from tools.tool_versions import ISABELLE_VERSION  # noqa: E402
from tools.tooling_policy_gate import LockedManifestEntry, load_tooling_artifact_selection  # noqa: E402

MANIFEST_RELATIVE_PATH = Path("specs/formal/participant-semantics/participant-opacity-proof-evidence.json")
THEORY_RELATIVE_PATH = ISABELLE_SESSION_RELATIVE_PATH / "Participant_Opacity.thy"
ROOT_RELATIVE_PATH = ISABELLE_SESSION_RELATIVE_PATH / "ROOT"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024

POSITIVE_THEOREMS = frozenset(
    {
        "participant_opacity_kernel",
        "participant_opacity_knowledge_characterization",
        "matching_policy_noninterference_implies_participant_opacity",
    }
)
SUPPORTING_THEOREMS = frozenset(
    {
        "information_cell_reflexive",
        "participant_knowledge_is_factive",
    }
)
NEGATIVE_THEOREMS = {
    "opacity_does_not_imply_policy_noninterference": "SEM231-MUT-OPACITY-TO-NONINTERFERENCE",
    "one_equal_history_pair_is_insufficient": "SEM231-MUT-ONE-PAIR",
    "declassification_can_change_information_and_knowledge": "SEM231-MUT-DECLASSIFICATION",
    "revocation_does_not_erase_retained_observation": "SEM231-MUT-REVOCATION-MEMORY",
    "behavioral_relations_without_preservation_do_not_imply_opacity": "SEM231-MUT-RELATION-SUBSTITUTION",
    "untimed_individual_observation_does_not_imply_stronger_observation_opacity": ("SEM231-MUT-STRONGER-OBSERVATION"),
    "possibilistic_opacity_does_not_imply_a_probability_bound": "SEM231-MUT-PROBABILITY-PROMOTION",
}
ASSUMPTION_IDS = frozenset(
    {
        "active-same-strategy",
        "complete-low-history-support",
        "eligible-label-preservation",
        "eligible-nonsecret-public-class-variation",
        "exact-information-cell",
        "matching-profile-coordinates",
        "reachable-alternative",
        "retained-memory-no-erasure",
    }
)
FORBIDDEN_FEATURES = (
    "axiomatization",
    "axioms",
    "nitpick",
    "oops",
    "oracle",
    "quick_and_dirty",
    "skip_proofs",
    "sorry",
)
_FORBIDDEN_RE = re.compile(r"\b(?:" + "|".join(FORBIDDEN_FEATURES) + r")\b", re.IGNORECASE)


class ProofEvidenceError(ValueError):
    """A stable failure from the repository-local mathematical-proof gate."""


def _require_keys(payload: dict[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ProofEvidenceError(f"{label} has an open or incomplete shape")


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ProofEvidenceError(f"{label} must be a non-empty list")
    return value


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProofEvidenceError(f"{label} must be an object")
    return value


def _resolve_repo_path(repo_root: Path, raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise ProofEvidenceError("proof evidence contains an unsafe repository path")
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProofEvidenceError("proof evidence contains an unsafe repository path")
    resolved = (repo_root / relative).resolve()
    root = repo_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ProofEvidenceError("proof evidence path escapes the repository")
    if not resolved.is_file():
        raise ProofEvidenceError("proof evidence references a missing repository file")
    return resolved


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _validate_digest_bound_path(repo_root: Path, payload: dict[str, Any], label: str) -> Path:
    path = _resolve_repo_path(repo_root, payload.get("path"))
    if payload.get("digest") != _file_digest(path):
        raise ProofEvidenceError(f"{label} digest does not match its repository source")
    return path


def load_proof_manifest(
    path: Path = REPO_ROOT / MANIFEST_RELATIVE_PATH,
) -> dict[str, Any]:
    try:
        return parse_bounded_json_object(path.read_bytes(), max_bytes=MAX_MANIFEST_BYTES)
    except (OSError, ValueError) as exc:
        raise ProofEvidenceError("participant-opacity proof manifest is invalid") from exc


def _validate_authorities(manifest: dict[str, Any], repo_root: Path) -> tuple[Any, Any]:
    taxonomy = _require_object(manifest["taxonomy"], "taxonomy authority")
    _require_keys(
        taxonomy,
        {"taxonomy_id", "taxonomy_revision", "path", "digest"},
        "taxonomy authority",
    )
    if taxonomy["taxonomy_id"] != "raes-behavioral-relations" or taxonomy["taxonomy_revision"] != "rev9":
        raise ProofEvidenceError("proof taxonomy authority is not the declared rev9 authority")
    if taxonomy["path"] != "contracts/concept-authority/history/behavioral-relations-v1-rev9.json":
        raise ProofEvidenceError("proof taxonomy authority path is not the immutable rev9 authority")
    _validate_digest_bound_path(repo_root, taxonomy, "taxonomy authority")
    catalog = load_behavioral_relation_catalog_revision("rev9")
    relation = catalog.relations["participant-predicate-opacity"]
    if relation.assurance.proof_status != "proved":
        raise ProofEvidenceError("participant-opacity catalog proof axis is not proved")

    profiles = _require_list(manifest["profiles"], "proof profiles")
    if len(profiles) != 1:
        raise ProofEvidenceError("proof evidence must bind exactly one theorem profile")
    profile_item = _require_object(profiles[0], "proof profile")
    _require_keys(
        profile_item,
        {"profile_id", "profile_revision", "path", "digest"},
        "proof profile",
    )
    if (
        profile_item["profile_id"] != "participant-opacity-theorem-v1"
        or profile_item["profile_revision"] != "sem-231-proof/rev1"
        or profile_item["path"] != "contracts/profiles/behavioral-relation/participant-opacity-theorem-v1.json"
    ):
        raise ProofEvidenceError("proof evidence does not bind the exact theorem profile")
    _validate_digest_bound_path(repo_root, profile_item, "proof profile")
    profile = load_behavioral_relation_profile_revision(
        profile_item["profile_id"],
        profile_item["profile_revision"],
    )
    return catalog, profile


def _validate_sources(manifest: dict[str, Any], repo_root: Path) -> None:
    sources = _require_list(manifest["semantic_sources"], "semantic sources")
    if len(sources) != 2:
        raise ProofEvidenceError("proof evidence must bind SEM-230 and SEM-231 sources")
    source_requirements: set[str] = set()
    for source in sources:
        item = _require_object(source, "semantic source")
        _require_keys(item, {"requirement", "revision", "path", "digest"}, "semantic source")
        source_requirements.add(item["requirement"])
        _validate_digest_bound_path(repo_root, item, "semantic source")
    if source_requirements != {"SEM-230", "SEM-231"}:
        raise ProofEvidenceError("proof evidence semantic sources do not cover SEM-230 and SEM-231")

    dependencies = _require_list(manifest["dependencies"], "proof dependencies")
    dependency_issues: set[int] = set()
    for dependency in dependencies:
        item = _require_object(dependency, "proof dependency")
        _require_keys(
            item,
            {"issue", "artifact_revision", "path", "digest", "evidence_boundary"},
            "proof dependency",
        )
        dependency_issues.add(item["issue"])
        _validate_digest_bound_path(repo_root, item, "proof dependency")
    if dependency_issues != {810, 961, 962}:
        raise ProofEvidenceError("proof evidence dependency set is incomplete")


def _validate_assumptions(manifest: dict[str, Any]) -> None:
    assumptions = _require_list(manifest["assumptions"], "proof assumptions")
    assumption_ids: list[str] = []
    for assumption in assumptions:
        item = _require_object(assumption, "proof assumption")
        _require_keys(item, {"assumption_id", "statement"}, "proof assumption")
        if not isinstance(item["statement"], str) or not item["statement"].strip():
            raise ProofEvidenceError("proof assumption statement is empty")
        assumption_ids.append(item["assumption_id"])
    if assumption_ids != sorted(ASSUMPTION_IDS):
        raise ProofEvidenceError("proof assumption set or canonical order is invalid")


def _validate_claims(manifest: dict[str, Any], catalog: Any, profile: Any) -> None:
    positive = _require_list(manifest["positive_theorems"], "positive theorems")
    theorem_ids: list[str] = []
    for theorem in positive:
        item = _require_object(theorem, "positive theorem")
        _require_keys(item, {"theorem_id", "statement", "claim"}, "positive theorem")
        theorem_id = item["theorem_id"]
        theorem_ids.append(theorem_id)
        try:
            claim = BehavioralClaimBindingModel.model_validate(item["claim"])
            validate_behavioral_claim_binding(claim, catalog=catalog, profile=profile)
        except ValueError as exc:
            raise ProofEvidenceError("proof claim does not resolve against its exact authorities") from exc
        expected_refs = [
            MANIFEST_RELATIVE_PATH.as_posix(),
            THEORY_RELATIVE_PATH.as_posix(),
            f"isabelle-theorem:{theorem_id}",
        ]
        if (
            claim.assurance_axis != "proof"
            or claim.assurance_status != "proved"
            or claim.evidence_scope != "proof"
            or claim.quantifier_scope != "all-strategies"
            or claim.evidence_refs != expected_refs
        ):
            raise ProofEvidenceError("proof claim axis, scope, status, or evidence refs are invalid")
    if theorem_ids != sorted(POSITIVE_THEOREMS):
        raise ProofEvidenceError("positive theorem set or canonical order is invalid")


def _validate_theorem_inventory(manifest: dict[str, Any], theory_text: str) -> None:
    supporting = _require_list(manifest["supporting_theorems"], "supporting theorems")
    supporting_ids: list[str] = []
    for theorem in supporting:
        item = _require_object(theorem, "supporting theorem")
        _require_keys(item, {"theorem_id", "statement"}, "supporting theorem")
        supporting_ids.append(item["theorem_id"])
    if supporting_ids != sorted(SUPPORTING_THEOREMS):
        raise ProofEvidenceError("supporting theorem set or canonical order is invalid")

    negative = _require_list(manifest["negative_theorems"], "negative theorems")
    negative_ids: list[str] = []
    for theorem in negative:
        item = _require_object(theorem, "negative theorem")
        _require_keys(item, {"theorem_id", "statement", "mutation_id"}, "negative theorem")
        theorem_id = item["theorem_id"]
        negative_ids.append(theorem_id)
        if NEGATIVE_THEOREMS.get(theorem_id) != item["mutation_id"]:
            raise ProofEvidenceError("negative theorem mutation binding is invalid")
    if negative_ids != sorted(NEGATIVE_THEOREMS):
        raise ProofEvidenceError("negative theorem set or canonical order is invalid")

    declared_theorems = POSITIVE_THEOREMS | SUPPORTING_THEOREMS | set(NEGATIVE_THEOREMS)
    for theorem_id in declared_theorems:
        declaration = re.compile(rf"\b(?:lemma|theorem)\s+{re.escape(theorem_id)}\s*:")
        if declaration.search(theory_text) is None:
            raise ProofEvidenceError("proof manifest names a theorem absent from the checked theory")
    if _FORBIDDEN_RE.search(theory_text) is not None:
        raise ProofEvidenceError("checked theory contains an unfinished or undeclared proof feature")


def _validate_toolchain_identity(toolchain: dict[str, Any], raw: LockedManifestEntry) -> None:
    expected = {
        "prover": "Isabelle/HOL",
        "version": f"Isabelle{ISABELLE_VERSION}",
        "archive_sha256": f"sha256:{raw.sha256}",
        "archive_bytes": raw.size,
        "working_directory": ".",
        "locale": "C.UTF-8",
        "platform_boundary": "linux-x86_64",
        "network": "explicit-acquire-only; replay-blocked-by-bubblewrap-network-namespace",
        "filesystem": "allowlisted-runtime-session-and-private-state-only",
    }
    if any(toolchain.get(key) != value for key, value in expected.items()):
        raise ProofEvidenceError("proof toolchain pin or execution posture drifted")


def _validate_toolchain_commands(toolchain: dict[str, Any]) -> None:
    expected_acquire = [
        "uv",
        "run",
        "--project",
        "implementations/python",
        "--frozen",
        "python",
        "-m",
        "tools.isabelle_tool",
        "acquire",
    ]
    expected_replay = [
        "uv",
        "run",
        "--project",
        "implementations/python",
        "--frozen",
        "python",
        "-m",
        "tools.check_participant_opacity_proof",
    ]
    if toolchain["acquire_command"] != expected_acquire or toolchain["replay_command"] != expected_replay:
        raise ProofEvidenceError("proof toolchain command is not the fixed repository command")


def _validate_toolchain_limits(toolchain: dict[str, Any]) -> None:
    limits = _require_object(toolchain["limits"], "proof process limits")
    _require_keys(
        limits,
        {
            "wall_seconds",
            "cpu_seconds",
            "threads",
            "max_output_bytes",
            "max_file_bytes",
            "max_address_space_mib_per_process",
            "java_max_heap_mib",
            "ml_max_heap_mib",
            "memory_scope",
            "generated_artifact_retention",
        },
        "proof process limits",
    )
    if limits != {
        "wall_seconds": ISABELLE_BUILD_TIMEOUT_SECONDS,
        "cpu_seconds": ISABELLE_BUILD_TIMEOUT_SECONDS,
        "threads": 2,
        "max_output_bytes": ISABELLE_OUTPUT_LIMIT_BYTES,
        "max_file_bytes": ISABELLE_FILE_LIMIT_BYTES,
        "max_address_space_mib_per_process": ISABELLE_PROCESS_ADDRESS_SPACE_LIMIT_MIB,
        "java_max_heap_mib": ISABELLE_JAVA_MAX_HEAP_MIB,
        "ml_max_heap_mib": ISABELLE_ML_MAX_HEAP_MIB,
        "memory_scope": "per-process-address-space-and-per-runtime-heaps-not-aggregate-tree",
        "generated_artifact_retention": "none",
    }:
        raise ProofEvidenceError("proof process limits drifted")


def _validate_tool_sources(toolchain: dict[str, Any], repo_root: Path) -> None:
    tool_sources = _require_list(toolchain["tool_sources"], "proof tool sources")
    if [item.get("path") for item in tool_sources if isinstance(item, dict)] != [
        "tools/check_participant_opacity_proof.py",
        "tools/isabelle_sandbox.py",
        "tools/isabelle_tool.py",
    ]:
        raise ProofEvidenceError("proof tool source set or order is invalid")
    for source in tool_sources:
        item = _require_object(source, "proof tool source")
        _require_keys(item, {"path", "digest"}, "proof tool source")
        _validate_digest_bound_path(repo_root, item, "proof tool source")


def _validate_toolchain(manifest: dict[str, Any], repo_root: Path) -> None:
    toolchain = _require_object(manifest["toolchain"], "proof toolchain")
    _require_keys(
        toolchain,
        {
            "prover",
            "version",
            "archive_url",
            "archive_sha256",
            "archive_bytes",
            "acquire_command",
            "replay_command",
            "working_directory",
            "locale",
            "platform_boundary",
            "network",
            "filesystem",
            "limits",
            "tool_sources",
        },
        "proof toolchain",
    )
    selection = load_tooling_artifact_selection(
        artifact_id="isabelle",
        version=ISABELLE_VERSION,
        platform_id="linux-x86_64",
        profile_id="proof-linux-x86_64",
    )
    if len(selection.raw_manifest) != 1:
        raise ProofEvidenceError("Isabelle lock selection must contain one raw archive")
    if toolchain.get("archive_url") not in selection.source_urls:
        raise ProofEvidenceError("proof toolchain archive URL is outside the reviewed lock selection")
    _validate_toolchain_identity(toolchain, selection.raw_manifest[0])
    _validate_toolchain_commands(toolchain)
    _validate_toolchain_limits(toolchain)
    _validate_tool_sources(toolchain, repo_root)


def _validate_session(manifest: dict[str, Any], repo_root: Path) -> str:
    session = _require_object(manifest["session"], "proof session")
    _require_keys(
        session,
        {
            "session_id",
            "root_path",
            "root_digest",
            "theory_path",
            "theory_digest",
            "imports",
            "forbidden_features",
            "generated_artifacts",
        },
        "proof session",
    )
    if (
        session["session_id"] != ISABELLE_SESSION
        or session["root_path"] != ROOT_RELATIVE_PATH.as_posix()
        or session["theory_path"] != THEORY_RELATIVE_PATH.as_posix()
        or session["imports"] != ["Main"]
        or session["forbidden_features"] != list(FORBIDDEN_FEATURES)
        or session["generated_artifacts"] != []
    ):
        raise ProofEvidenceError("proof session declaration drifted")
    root_path = _resolve_repo_path(repo_root, session["root_path"])
    theory_path = _resolve_repo_path(repo_root, session["theory_path"])
    if session["root_digest"] != _file_digest(root_path) or session["theory_digest"] != _file_digest(theory_path):
        raise ProofEvidenceError("proof session source digest drifted")
    root_text = root_path.read_text(encoding="utf-8")
    if "session Participant_Opacity = HOL +" not in root_text or "Participant_Opacity" not in root_text:
        raise ProofEvidenceError("proof session root does not bind the fixed HOL session")
    theory_text = theory_path.read_text(encoding="utf-8")
    if not re.search(r"theory\s+Participant_Opacity\s+imports\s+Main\s+begin", theory_text):
        raise ProofEvidenceError("proof theory does not import exactly Isabelle/HOL Main")
    return theory_text


def _validate_results(manifest: dict[str, Any], *, repo_root: Path, run_prover: bool) -> None:
    expected_result = expected_isabelle_result()
    kernel_result = _require_object(manifest["kernel_result"], "kernel result")
    if kernel_result != expected_result:
        raise ProofEvidenceError("proof kernel result or expected digest drifted")
    reproduction = _require_object(manifest["independent_reproduction"], "independent reproduction")
    _require_keys(
        reproduction,
        {"command", "working_directory", "result", "reproduced_on"},
        "independent reproduction",
    )
    if (
        reproduction["command"]
        != [
            "uv",
            "run",
            "--project",
            "implementations/python",
            "--frozen",
            "python",
            "-m",
            "tools.check_participant_opacity_proof",
        ]
        or reproduction["working_directory"] != "."
        or reproduction["result"] != expected_result
        or reproduction["reproduced_on"] != "2026-07-31"
    ):
        raise ProofEvidenceError("independent proof reproduction record drifted")
    if run_prover and run_isabelle_build(repo_root) != expected_result:
        raise ProofEvidenceError("independent Isabelle proof replay did not reproduce")


def validate_proof_manifest(
    manifest: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    run_prover: bool = True,
) -> None:
    _require_keys(
        manifest,
        {
            "schema_version",
            "evidence_id",
            "requirements",
            "taxonomy",
            "profiles",
            "semantic_sources",
            "dependencies",
            "assumptions",
            "positive_theorems",
            "supporting_theorems",
            "negative_theorems",
            "toolchain",
            "session",
            "kernel_result",
            "independent_reproduction",
            "limitations",
            "explicit_non_claims",
        },
        "participant-opacity proof manifest",
    )
    if (
        manifest["schema_version"] != "participant-opacity-proof-evidence/repo-v1"
        or manifest["evidence_id"] != "participant-opacity-proof:sem-231/rev1"
        or manifest["requirements"] != ["ASR-535", "SEM-231"]
    ):
        raise ProofEvidenceError("proof evidence identity or requirements drifted")
    if not _require_list(manifest["limitations"], "proof limitations") or not _require_list(
        manifest["explicit_non_claims"], "proof explicit nonclaims"
    ):
        raise ProofEvidenceError("proof boundaries are incomplete")
    catalog, profile = _validate_authorities(manifest, repo_root)
    _validate_sources(manifest, repo_root)
    _validate_assumptions(manifest)
    _validate_claims(manifest, catalog, profile)
    _validate_toolchain(manifest, repo_root)
    theory_text = _validate_session(manifest, repo_root)
    _validate_theorem_inventory(manifest, theory_text)
    _validate_results(manifest, repo_root=repo_root, run_prover=run_prover)


def main() -> int:
    try:
        manifest = load_proof_manifest()
        validate_proof_manifest(manifest)
    except ProofEvidenceError as exc:
        print(f"participant-opacity-proof: {exc}", file=sys.stderr)
        return 1
    print("participant-opacity-proof: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
