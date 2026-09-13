"""Vocabulary ownership reaches SDL consumers without authorizing backend work."""

from pathlib import Path

from tools.policy.requirement_governance import _check_path_ownership, load_policy, match_phase


def test_vocabulary_ownership_includes_its_authoring_and_publication_surfaces():
    policy = load_policy(Path(__file__).resolve().parents[3])
    phase = match_phase(policy, "GOV-922")
    paths = [
        "implementations/python/packages/raes/runtime_values.py",
        "contracts/schemas/sdl/instantiated-scenario-v1.json",
        "contracts/schema-publication/entries/instantiated-scenario-v1.json",
        "specs/sdl/runtime-inventory.md",
        "docs/research/language-extensibility/scope-inventory.md",
        "docs/requirements/GOV-922/requirement.md",
    ]
    assert not _check_path_ownership(policy, phase, paths)
    for path in (
        "implementations/python/packages/raes_reference_backend/provisioner.py",
        "implementations/python/packages/raes_runtime/control_plane.py",
    ):
        assert _check_path_ownership(policy, phase, [path])
