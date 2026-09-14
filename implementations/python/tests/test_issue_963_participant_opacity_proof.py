"""SEM-231/ASR-535 mathematical participant-opacity proof assurance."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import tools.isabelle_tool as isabelle_tool
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.behavioral_relation_profiles import (
    AbstractOpacityCarrierModel,
    BehavioralRelationProfileModel,
    OpacityFiniteBoundsModel,
    load_behavioral_relation_profile,
    load_behavioral_relation_profile_revision,
)
from raes_contracts.behavioral_relations import (
    load_behavioral_relation_catalog,
    load_behavioral_relation_catalog_revision,
)
from tools.check_participant_opacity_proof import (
    ProofEvidenceError,
    _validate_theorem_inventory,
    load_proof_manifest,
    validate_proof_manifest,
)
from tools.isabelle_tool import (
    ISABELLE_PROCESS_ADDRESS_SPACE_LIMIT_MIB,
    ISABELLE_REQUIRED_FONTCONFIG_PATHS,
    ISABELLE_SYSTEM_RUNTIME_PATHS,
    _bubblewrap_setup_failed,
    _proof_process_limits,
    _proof_sandbox_command,
    _require_fontconfig_runtime,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "specs/formal/participant-semantics/participant-opacity-proof-evidence.json"
PROFILE_SCHEMA_PATH = REPO_ROOT / "contracts/schemas/profiles/behavioral-relation-profile-v1.json"
FINITE_PROFILE_PATH = REPO_ROOT / "contracts/profiles/behavioral-relation/participant-opacity-baseline-v1.json"
THEOREM_PROFILE_PATH = REPO_ROOT / "contracts/profiles/behavioral-relation/participant-opacity-theorem-v1.json"
THEOREM_PROFILE_ID = "participant-opacity-theorem-v1"
THEOREM_PROFILE_REVISION = "sem-231-proof/rev1"


def test_theorem_profile_uses_the_shared_nonfinite_profile_variant() -> None:
    profile = load_behavioral_relation_profile_revision(
        THEOREM_PROFILE_ID,
        THEOREM_PROFILE_REVISION,
    )

    assert profile.finite_analysis_scope == "abstract-parameterized-theorem-carrier"
    assert isinstance(profile.parameters.carrier, AbstractOpacityCarrierModel)
    assert profile.parameters.bounds is None
    assert profile.parameters.carrier.eligibility_ref == "sem-231-eligible-predicate"
    assert profile.parameters.carrier.correspondence_ref == "sem-230-sem-231-profile-correspondence"


def test_finite_profile_still_requires_bounds() -> None:
    profile = load_behavioral_relation_profile("participant-opacity-baseline-v1")

    assert profile.finite_analysis_scope == "declared-complete-finite-carrier"
    assert isinstance(profile.parameters.bounds, OpacityFiniteBoundsModel)


def test_carrier_variant_rejects_finite_bounds_and_scope_drift() -> None:
    theorem_payload = load_behavioral_relation_profile(THEOREM_PROFILE_ID).model_dump(mode="json")
    finite_bounds = load_behavioral_relation_profile("participant-opacity-baseline-v1").parameters.bounds
    theorem_payload["parameters"]["bounds"] = finite_bounds.model_dump(mode="json")

    with pytest.raises(ValidationError, match="must not declare finite bounds"):
        BehavioralRelationProfileModel.model_validate(theorem_payload)

    theorem_payload["parameters"]["bounds"] = None
    theorem_payload["finite_analysis_scope"] = "declared-complete-finite-carrier"
    with pytest.raises(ValidationError, match="scope must match"):
        BehavioralRelationProfileModel.model_validate(theorem_payload)


def test_published_schema_rejects_every_carrier_bounds_and_scope_mismatch() -> None:
    schema = json.loads(PROFILE_SCHEMA_PATH.read_text(encoding="utf-8"))
    finite_profile = json.loads(FINITE_PROFILE_PATH.read_text(encoding="utf-8"))
    theorem_profile = json.loads(THEOREM_PROFILE_PATH.read_text(encoding="utf-8"))

    finite_without_bounds = deepcopy(finite_profile)
    finite_without_bounds["parameters"].pop("bounds")
    abstract_with_bounds = deepcopy(theorem_profile)
    abstract_with_bounds["parameters"]["bounds"] = finite_profile["parameters"]["bounds"]
    finite_with_abstract_scope = deepcopy(finite_profile)
    finite_with_abstract_scope["finite_analysis_scope"] = "abstract-parameterized-theorem-carrier"
    abstract_with_finite_scope = deepcopy(theorem_profile)
    abstract_with_finite_scope["finite_analysis_scope"] = "declared-complete-finite-carrier"

    validator = Draft202012Validator(schema)
    invalid_profiles = {
        "finite carrier without bounds": finite_without_bounds,
        "abstract carrier with finite bounds": abstract_with_bounds,
        "finite carrier with theorem scope": finite_with_abstract_scope,
        "abstract carrier with finite scope": abstract_with_finite_scope,
    }
    for label, payload in invalid_profiles.items():
        assert not validator.is_valid(payload), label


def test_proof_sandbox_exposes_only_fixed_inputs_runtime_and_private_state() -> None:
    command = _proof_sandbox_command(
        bwrap=Path("/usr/bin/bwrap"),
        home=Path("/cache/isabelle"),
        session_root=Path("/repo/fixed-session"),
        state_root=Path("/private/state"),
    )
    ro_bindings = {
        (command[index + 1], command[index + 2]) for index, value in enumerate(command) if value == "--ro-bind"
    }

    assert ("/", "/") not in ro_bindings
    assert ("/cache/isabelle", "/opt/isabelle") in ro_bindings
    assert ("/repo/fixed-session", "/workspace/session") in ro_bindings
    assert "/home" not in command
    assert "--unshare-net" in command
    assert "--unshare-pid" in command
    sandbox_tmp = str(Path("/") / "tmp")
    assert command[command.index("TMPDIR") + 1] == sandbox_tmp
    assert command[command.index("--tmpfs") + 1] == sandbox_tmp
    assert command[-2:] == ["-D", "/workspace/session"]


def test_proof_sandbox_allowlists_fontconfig_symlink_targets() -> None:
    assert Path("/etc/fonts") in ISABELLE_SYSTEM_RUNTIME_PATHS
    assert Path("/usr/share/fontconfig") in ISABELLE_SYSTEM_RUNTIME_PATHS
    assert Path("/usr/share/fonts") in ISABELLE_SYSTEM_RUNTIME_PATHS
    assert set(ISABELLE_REQUIRED_FONTCONFIG_PATHS) <= set(ISABELLE_SYSTEM_RUNTIME_PATHS)
    assert Path("/usr/share/fontconfig") not in ISABELLE_REQUIRED_FONTCONFIG_PATHS


def test_proof_runtime_requires_complete_fontconfig_data(tmp_path: Path) -> None:
    existing = tuple(tmp_path / name for name in ("etc-fonts", "share-fontconfig", "share-fonts"))
    for path in existing:
        path.mkdir()

    _require_fontconfig_runtime(existing, font_query=lambda: True)

    existing[-1].rmdir()
    with pytest.raises(isabelle_tool.IsabelleToolError, match="fontconfig runtime is required"):
        _require_fontconfig_runtime(existing, font_query=lambda: True)


def test_proof_runtime_requires_a_discoverable_font(tmp_path: Path) -> None:
    existing = tuple(tmp_path / name for name in ("etc-fonts", "share-fonts"))
    for path in existing:
        path.mkdir()

    with pytest.raises(isabelle_tool.IsabelleToolError, match="fontconfig runtime is required"):
        _require_fontconfig_runtime(existing, font_query=lambda: False)


def test_fontconfig_query_requires_a_successful_nonempty_listing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    font_list = tmp_path / "fc-list"
    font_list.write_text("stub", encoding="ascii")
    font_list.chmod(0o755)

    monkeypatch.setattr(
        isabelle_tool.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=b"/usr/share/fonts/example.ttf\n"),
    )
    assert isabelle_tool._fontconfig_has_fonts(font_list) is True

    monkeypatch.setattr(
        isabelle_tool.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=b""),
    )
    assert isabelle_tool._fontconfig_has_fonts(font_list) is False


def test_proof_replay_checks_fontconfig_before_session_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_is_executable_file = isabelle_tool._is_executable_file

    def reject_missing_fontconfig() -> None:
        raise isabelle_tool.IsabelleToolError("fontconfig test sentinel")

    monkeypatch.setattr(isabelle_tool, "require_isabelle", lambda _repo_root: tmp_path)
    monkeypatch.setattr(
        isabelle_tool,
        "_is_executable_file",
        lambda path: path == Path("/usr/bin/bwrap") or original_is_executable_file(path),
    )
    monkeypatch.setattr(
        isabelle_tool,
        "_require_fontconfig_runtime",
        reject_missing_fontconfig,
    )

    with pytest.raises(isabelle_tool.IsabelleToolError, match="fontconfig test sentinel"):
        isabelle_tool.run_isabelle_build(tmp_path)


def test_proof_replay_distinguishes_sandbox_setup_from_kernel_rejection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_root = tmp_path / isabelle_tool.ISABELLE_SESSION_RELATIVE_PATH
    session_root.mkdir(parents=True)
    original_is_executable_file = isabelle_tool._is_executable_file

    monkeypatch.setattr(isabelle_tool, "require_isabelle", lambda _repo_root: tmp_path / "isabelle")
    monkeypatch.setattr(
        isabelle_tool,
        "_is_executable_file",
        lambda path: path == Path("/usr/bin/bwrap") or original_is_executable_file(path),
    )
    monkeypatch.setattr(isabelle_tool, "_require_fontconfig_runtime", lambda: None)
    monkeypatch.setattr(isabelle_tool, "_require_locale_runtime", lambda: None)

    def completed_with(output: bytes):
        def fake_run(*_args: object, stdout: object, **_kwargs: object) -> SimpleNamespace:
            stdout.write(output)
            return SimpleNamespace(returncode=1)

        return fake_run

    assert _bubblewrap_setup_failed("  bwrap: loopback setup denied\n") is True
    assert _bubblewrap_setup_failed("*** Isabelle theorem failure\n") is False

    monkeypatch.setattr(isabelle_tool.subprocess, "run", completed_with(b"bwrap: network namespace denied\n"))
    with pytest.raises(isabelle_tool.IsabelleToolError, match="bubblewrap network isolation is unavailable"):
        isabelle_tool.run_isabelle_build(tmp_path)

    monkeypatch.setattr(isabelle_tool.subprocess, "run", completed_with(b"*** Isabelle theorem failure\n"))
    with pytest.raises(isabelle_tool.IsabelleToolError, match="Isabelle kernel rejected"):
        isabelle_tool.run_isabelle_build(tmp_path)


def test_proof_process_limit_enforces_per_process_address_space(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(isabelle_tool.resource, "setrlimit", lambda kind, limits: calls.append((kind, limits)))

    _proof_process_limits()

    address_space_bytes = ISABELLE_PROCESS_ADDRESS_SPACE_LIMIT_MIB * 1024 * 1024
    assert (isabelle_tool.resource.RLIMIT_AS, (address_space_bytes, address_space_bytes)) in calls


def test_current_and_historical_authority_resolve_by_exact_revision() -> None:
    current_catalog = load_behavioral_relation_catalog()
    semantic_catalog = load_behavioral_relation_catalog_revision("rev11")
    proof_catalog = load_behavioral_relation_catalog_revision("rev9")
    historical_catalog = load_behavioral_relation_catalog_revision("rev8")
    current_profile = load_behavioral_relation_profile("participant-opacity-baseline-v1")
    historical_profile = load_behavioral_relation_profile_revision(
        "participant-opacity-baseline-v1",
        "sem-231/rev2",
    )

    assert current_catalog.taxonomy_revision == "rev12"
    assert semantic_catalog.taxonomy_revision == "rev11"
    assert proof_catalog.taxonomy_revision == "rev9"
    assert current_profile.profile_revision == "sem-231/rev3"
    assert current_profile.taxonomy_revision == "rev9"
    assert historical_catalog.taxonomy_revision == "rev8"
    assert historical_profile.profile_revision == "sem-231/rev2"
    assert historical_profile.taxonomy_revision == "rev8"


@pytest.mark.integration
def test_proof_manifest_closes_claim_theorem_assumption_and_digest_joins() -> None:
    manifest = load_proof_manifest(MANIFEST_PATH)

    summary = validate_proof_manifest(manifest, repo_root=REPO_ROOT, run_prover=False)

    assert summary.evidence_id == "participant-opacity-proof:sem-231/rev1"
    assert summary.taxonomy_revision == "rev9"
    assert (summary.profile_id, summary.profile_revision) == ("participant-opacity-theorem-v1", "sem-231-proof/rev1")
    assert summary.positive_theorem_ids == tuple(item["theorem_id"] for item in manifest["positive_theorems"])
    assert summary.positive_theorem_ids
    assert summary.prover_replayed is False


def _tamper_digest(value: str) -> str:
    prefix, digest = value.split(":", 1)
    return f"{prefix}:{'0' if digest[0] != '0' else '1'}{digest[1:]}"


@pytest.mark.integration
@pytest.mark.parametrize(
    "location",
    [
        ("taxonomy", "digest"),
        ("profiles", 0, "digest"),
        ("semantic_sources", 0, "digest"),
        ("dependencies", 0, "digest"),
        ("toolchain", "tool_sources", 0, "digest"),
        ("toolchain", "tool_sources", -1, "digest"),
        ("session", "root_digest"),
        ("session", "theory_digest"),
    ],
)
def test_proof_manifest_rejects_every_digest_bound_source_drift(location: tuple[object, ...]) -> None:
    manifest = deepcopy(load_proof_manifest(MANIFEST_PATH))
    container = manifest
    for key in location[:-1]:
        container = container[key]
    container[location[-1]] = _tamper_digest(container[location[-1]])

    with pytest.raises(ProofEvidenceError, match="digest"):
        validate_proof_manifest(manifest, repo_root=REPO_ROOT, run_prover=False)


@pytest.mark.integration
def test_theorem_inventory_rejects_unfinished_proofs_and_missing_declarations() -> None:
    manifest = load_proof_manifest(MANIFEST_PATH)
    theory_path = REPO_ROOT / manifest["session"]["theory_path"]
    theory_text = theory_path.read_text(encoding="utf-8")
    _validate_theorem_inventory(manifest, theory_text)

    for feature in ("sorry", "oops", "axiomatization"):
        unfinished = theory_text.replace("\nend", f"\nlemma unfinished_{feature}: True\n  {feature}\nend", 1)
        with pytest.raises(ProofEvidenceError, match="unfinished or undeclared proof feature"):
            _validate_theorem_inventory(manifest, unfinished)

    theorem_id = manifest["positive_theorems"][0]["theorem_id"]
    renamed = re.sub(rf"\b(lemma|theorem)\s+{re.escape(theorem_id)}\s*:", r"\1 renamed_theorem:", theory_text)
    assert renamed != theory_text
    with pytest.raises(ProofEvidenceError, match="absent from the checked theory"):
        _validate_theorem_inventory(manifest, renamed)


def _set(manifest: dict, location: tuple[object, ...], value: object) -> None:
    container = manifest
    for key in location[:-1]:
        container = container[key]
    container[location[-1]] = value


@pytest.mark.integration
@pytest.mark.parametrize(
    ("location", "value", "message"),
    [
        (("evidence_id",), "participant-opacity-proof:sem-231/rev2", "identity or requirements drifted"),
        (("requirements",), ["SEM-231"], "identity or requirements drifted"),
        (("limitations",), [], "proof limitations must be a non-empty list"),
        (("taxonomy", "taxonomy_revision"), "rev10", "declared rev9 authority"),
        (("profiles", 0, "profile_revision"), "sem-231-proof/rev2", "exact theorem profile"),
        (("semantic_sources", 0, "requirement"), "SEM-229", "do not cover SEM-230 and SEM-231"),
        (("dependencies", 0, "issue"), 811, "dependency set is incomplete"),
        (("assumptions", 0, "statement"), "  ", "assumption statement is empty"),
        (("assumptions", 0, "assumption_id"), "zz-out-of-order", "assumption set or canonical order"),
        (("toolchain", "network"), "unrestricted", "pin or execution posture drifted"),
        (("toolchain", "filesystem"), "host-root", "pin or execution posture drifted"),
        (("toolchain", "archive_bytes"), 1, "pin or execution posture drifted"),
        (("toolchain", "archive_url"), "https://mirror.invalid/Isabelle.tar.gz", "outside the reviewed lock"),
        (("toolchain", "limits", "wall_seconds"), 6000, "process limits drifted"),
        (("toolchain", "limits", "max_address_space_mib_per_process"), 65536, "process limits drifted"),
        (("toolchain", "acquire_command", 3), "implementations/python", "fixed repository command"),
        (("toolchain", "replay_command", -1), "tools.other", "fixed repository command"),
        (("session", "session_id"), "Other_Session", "session declaration drifted"),
        (("session", "generated_artifacts"), ["heap"], "session declaration drifted"),
        (("kernel_result", "network"), "host-network", "kernel result or expected digest drifted"),
        (("independent_reproduction", "reproduced_on"), "2026-01-01", "reproduction record drifted"),
        (("taxonomy", "path"), "/etc/passwd", "immutable rev9 authority"),
        (("semantic_sources", 0, "path"), "/etc/passwd", "unsafe repository path"),
        (("semantic_sources", 0, "path"), "specs/../../outside.md", "unsafe repository path"),
    ],
)
def test_proof_manifest_rejects_every_closed_identity_posture_and_path_drift(
    location: tuple[object, ...],
    value: object,
    message: str,
) -> None:
    manifest = deepcopy(load_proof_manifest(MANIFEST_PATH))
    _set(manifest, location, value)

    with pytest.raises(ProofEvidenceError, match=re.escape(message)):
        validate_proof_manifest(manifest, repo_root=REPO_ROOT, run_prover=False)


@pytest.mark.integration
def test_proof_manifest_rejects_axis_and_checked_theorem_drift() -> None:
    manifest = load_proof_manifest(MANIFEST_PATH)
    drifted = deepcopy(manifest)
    drifted["positive_theorems"][0]["claim"]["assurance_axis"] = "model-check"

    with pytest.raises(ProofEvidenceError, match="proof claim"):
        validate_proof_manifest(drifted, repo_root=REPO_ROOT, run_prover=False)

    missing = deepcopy(manifest)
    missing["negative_theorems"].pop()
    with pytest.raises(ProofEvidenceError, match="negative theorem"):
        validate_proof_manifest(missing, repo_root=REPO_ROOT, run_prover=False)
