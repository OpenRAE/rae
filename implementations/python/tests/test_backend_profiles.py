"""Backend capability profile contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_contracts.backend_profiles import (
    BackendProfileIdentityError,
    BackendProfileModel,
    backend_profile_path,
    backend_profiles_root,
    load_backend_profile,
    load_backend_profile_from_path,
)
from raes_contracts.manifest_authority import BACKEND_SUPPORTED_CONTRACT_IDS

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_PROFILES_ROOT = REPO_ROOT / "contracts" / "profiles" / "backend"


def _discovered_published_profile_ids() -> list[str]:
    """Return the published profile ids discovered from the contracts tree.

    Tests parameterize on this rather than on a hard-coded tuple so adding a
    new ``contracts/profiles/backend/<id>.json`` is automatically covered
    without a coordinated Python edit (ASR-502 — the published JSON is the
    single authority for profile identity)."""

    return sorted(path.stem for path in BACKEND_PROFILES_ROOT.glob("*.json"))


PUBLISHED_PROFILE_IDS = _discovered_published_profile_ids()


def test_backend_profiles_root_resolves_to_contracts_tree():
    assert backend_profiles_root() == BACKEND_PROFILES_ROOT


def test_backend_profile_path_resolves_per_profile_id():
    assert backend_profile_path("provisioning-only") == BACKEND_PROFILES_ROOT / "provisioning-only.json"


def test_at_least_one_published_backend_profile_exists():
    """Sanity guard: the discovery-driven tests below are no-ops if the
    corpus is empty. Pin only the *existence* of a non-empty corpus."""

    assert PUBLISHED_PROFILE_IDS, "contracts/profiles/backend/ must contain at least one published profile"


@pytest.mark.parametrize("profile_id", PUBLISHED_PROFILE_IDS)
def test_load_published_backend_profile(profile_id: str):
    profile = load_backend_profile(profile_id)

    assert profile.profile == profile_id
    assert profile.required_contracts
    assert set(profile.required_contracts) <= set(BACKEND_SUPPORTED_CONTRACT_IDS)


def test_full_remote_profile_includes_participant_episode_contracts():
    """ASR-502: the published FULL_REMOTE_CONTROL_PLANE profile is the
    single source of truth for the contract set the FULL conformance
    sweep validates. The participant-episode envelope + history stream
    are part of that surface (RUN-311) and must be declared on the
    published profile, not just in a stale in-code copy."""

    profile = load_backend_profile("full-remote-control-plane")

    assert "participant-episode-state-envelope-v1" in profile.required_contracts
    assert "participant-episode-history-event-stream-v1" in profile.required_contracts
    assert "participant-behavior-history-event-stream-v1" in profile.required_contracts
    assert "participant-control-occurrence-v1" in profile.required_contracts
    assert "participant-crossing-occurrence-v1" in profile.required_contracts


def test_backend_profile_model_rejects_unknown_contract_id():
    with pytest.raises(ValidationError):
        BackendProfileModel.model_validate(
            {"profile": "synthetic", "required_contracts": ["definitely-not-a-published-contract-v999"]}
        )


def test_backend_profile_model_rejects_extra_keys():
    with pytest.raises(ValidationError):
        BackendProfileModel.model_validate(
            {
                "profile": "synthetic",
                "required_contracts": ["backend-manifest-v2"],
                "extra_unknown_field": "x",
            }
        )


def test_backend_profile_model_rejects_duplicate_contract_ids():
    with pytest.raises(ValidationError):
        BackendProfileModel.model_validate(
            {
                "profile": "synthetic",
                "required_contracts": ["backend-manifest-v2", "backend-manifest-v2"],
            }
        )


def test_backend_profile_model_rejects_empty_required_contracts():
    with pytest.raises(ValidationError):
        BackendProfileModel.model_validate({"profile": "synthetic", "required_contracts": []})


@pytest.mark.parametrize("profile_id", PUBLISHED_PROFILE_IDS)
def test_published_profiles_match_loader_round_trip(profile_id: str):
    raw = json.loads(backend_profile_path(profile_id).read_text(encoding="utf-8"))
    model = load_backend_profile(profile_id)

    assert raw["profile"] == model.profile
    assert raw["required_contracts"] == list(model.required_contracts)


def test_load_backend_profile_from_path_rejects_identity_mismatch(tmp_path: Path):
    """ASR-502 + codex review (issue #66, finding 2): the shared loader must
    reject an artifact whose ``profile`` field doesn't match the requested id,
    so a swapped or mislabeled file cannot silently drive the wrong contract set."""

    path = tmp_path / "provisioning-only.json"
    path.write_text(
        json.dumps(
            {
                "profile": "full-remote-control-plane",
                "required_contracts": ["backend-manifest-v2"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BackendProfileIdentityError, match="full-remote-control-plane"):
        load_backend_profile_from_path("provisioning-only", path)


def test_load_backend_profile_from_path_accepts_identity_match(tmp_path: Path):
    """The shared loader accepts an artifact whose ``profile`` field matches
    the requested id; the canonical loader uses it on the file-stem path."""

    path = tmp_path / "provisioning-only.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "backend-profile/v1",
                "profile": "provisioning-only",
                "required_contracts": ["backend-manifest-v2"],
            }
        ),
        encoding="utf-8",
    )

    model = load_backend_profile_from_path("provisioning-only", path)
    assert model.profile == "provisioning-only"


@pytest.mark.parametrize(
    "malicious_id",
    [
        "../evil",
        "..",
        "/etc/passwd",
        "subdir/profile",
        "id with spaces",
        "PROFILE-UPPER",
        "../../etc/shadow",
        ".hidden",
    ],
)
def test_backend_profile_path_rejects_malicious_ids(malicious_id: str):
    """ASR-502 + codex review (issue #66, cycle 4 security finding): the
    canonical loader must reject any profile id that doesn't match the
    published profile-id grammar, BEFORE the id is interpolated into a
    filesystem path. This prevents path traversal and absolute-path
    interpolation from a caller-controlled value."""

    with pytest.raises(ValueError, match="backend profile id must match"):
        backend_profile_path(malicious_id)


def test_load_backend_profile_rejects_malicious_id():
    """The path-construction layer rejects bad ids; the shared loader does too,
    so callers that construct ``path`` themselves still go through the same
    grammar check."""

    with pytest.raises(ValueError, match="backend profile id must match"):
        load_backend_profile("../etc/passwd")
