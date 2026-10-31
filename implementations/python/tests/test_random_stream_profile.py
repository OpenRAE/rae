"""Fixture-driven contract tests for the random-stream profile shape and loader.

Mirrors ``test_semantic_profiles.py``'s structure, but the loader is hardened
per the EXP-718 preflight's "Normative profile and corpus gate": profile ids
are validated against the portable-identifier pattern *before* any path is
joined, and unsupported/unknown ids are rejected explicitly rather than
silently 404ing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import RandomStreamProfileModel
from raes_contracts.contracts.random_stream_profiles import (
    SUPPORTED_RANDOM_STREAM_PROFILE_IDS,
    load_random_stream_profile,
    random_stream_profile_path,
    random_stream_profiles_root,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = REPO_ROOT / "contracts" / "profiles" / "random-stream" / "blake3-xof-v1.json"
PARTICIPANT_PROFILE_PATH = REPO_ROOT / "contracts" / "profiles" / "random-stream" / "blake3-xof-participant-v1.json"
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures" / "profiles" / "random-stream-profile-v1"
VALID_DIR = FIXTURES_ROOT / "valid"
INVALID_DIR = FIXTURES_ROOT / "invalid"


def test_load_reference_random_stream_profile() -> None:
    profile = load_random_stream_profile("blake3-xof-v1")

    assert profile.profile_id == "blake3-xof-v1"
    assert profile.generator.family == "blake3"
    assert "bounded-integer" in profile.transforms

    participant_profile = load_random_stream_profile("blake3-xof-participant-v1")
    assert participant_profile.profile_id == "blake3-xof-participant-v1"
    assert participant_profile.generator.family == "blake3"
    assert "bounded-integer" in participant_profile.transforms


def test_reference_profile_path_resolves() -> None:
    assert random_stream_profile_path("blake3-xof-v1") == PROFILE_PATH
    assert random_stream_profile_path("blake3-xof-participant-v1") == PARTICIPANT_PROFILE_PATH


def test_reference_profile_matches_valid_fixture() -> None:
    payload = json.loads((VALID_DIR / "blake3-xof-v1.json").read_text(encoding="utf-8"))
    authoritative = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    assert payload == authoritative
    assert RandomStreamProfileModel.model_validate(payload).profile_id == "blake3-xof-v1"


def test_random_stream_profile_valid_fixtures_pass_validation() -> None:
    for path in sorted(VALID_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        model = RandomStreamProfileModel.model_validate(payload)
        assert model.profile_id, f"Valid random-stream profile fixture {path.name} should have a profile id"


def test_random_stream_profile_invalid_fixtures_fail_validation() -> None:
    for path in sorted(INVALID_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        with pytest.raises(ValidationError):
            RandomStreamProfileModel.model_validate(payload)


def test_random_stream_profile_rejects_transform_key_mismatch() -> None:
    payload = json.loads((INVALID_DIR / "transform-key-mismatch.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError, match="transform_id"):
        RandomStreamProfileModel.model_validate(payload)


class TestLoaderHardening:
    def test_root_resolves_under_profiles_family(self) -> None:
        assert random_stream_profiles_root().name == "random-stream"

    def test_rejects_path_traversal_before_join(self) -> None:
        with pytest.raises(ValueError, match="portable"):
            random_stream_profile_path("../../etc/passwd")

    def test_rejects_absolute_path_component(self) -> None:
        with pytest.raises(ValueError, match="portable"):
            random_stream_profile_path("/etc/passwd")

    def test_rejects_uppercase_id(self) -> None:
        with pytest.raises(ValueError, match="portable"):
            random_stream_profile_path("Blake3-Xof-V1")

    def test_rejects_unsupported_but_syntactically_valid_id(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            random_stream_profile_path("nonexistent-profile-v1")

    def test_supported_profile_ids_contains_blake3_xof(self) -> None:
        expected_ids = {
            "blake3-xof-participant-v1",
            "blake3-xof-v1",
        }
        assert not SUPPORTED_RANDOM_STREAM_PROFILE_IDS.symmetric_difference(expected_ids)

    def test_load_unsupported_profile_fails_closed_without_file_probe(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            load_random_stream_profile("totally-unknown-v1")
