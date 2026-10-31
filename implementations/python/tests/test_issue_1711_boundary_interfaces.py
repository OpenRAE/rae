"""Client-owned boundary interfaces of ADR-121 (issue #1711).

``raes_contracts`` declares what it needs from a higher-layer object. ``raes``
implements it for SDL objects, and the contracts package implements it for its
own experiment models. Each implementation keeps the parent and scenario rules
that the validators applied before the move.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from types import SimpleNamespace

import pytest
from raes import canonical_sdl_digest, parse_sdl
from raes.associated_artifacts import ScenarioArtifactParent
from raes.authored_scenario_evidence import AuthoredScenarioEvidenceView
from raes.instantiate import instantiate_scenario
from raes_contracts.associated_artifacts import (
    ArtifactParent,
    ExperimentArtifactParent,
    associated_artifact_set_digest,
    validate_associated_artifact_manifest,
)
from raes_contracts.contracts import AssociatedArtifactManifestModel
from raes_contracts.contracts.experiment_evidence_refinement import AuthoredScenarioEvidence

PAYLOAD = b"operator guide\n"
PAYLOAD_SHA256 = hashlib.sha256(PAYLOAD).hexdigest()


def _manifest(parent_ref: dict[str, object], *, scope: str = "scenario") -> AssociatedArtifactManifestModel:
    manifest = AssociatedArtifactManifestModel.model_validate(
        {
            "schema_version": "associated-artifact-manifest/v1",
            "manifest_id": "guidance",
            "manifest_version": "1.0.0",
            "canonicalization_profile": "associated-artifact-set/v1",
            "scope": scope,
            "parent_ref": parent_ref,
            "artifacts": {
                "operator-guide": {
                    "artifact_id": "operator-guide",
                    "role": "operator-guide",
                    "media_type": "text/markdown",
                    "uri": "urn:sha256:" + PAYLOAD_SHA256,
                    "checksum": {"algorithm": "sha256", "value": PAYLOAD_SHA256},
                    "size_bytes": len(PAYLOAD),
                    "created_at": "2026-07-12T00:00:00Z",
                    "source": "scenario-author",
                    "sensitivity": "internal",
                }
            },
            "set_digest": "sha256:" + ("0" * 64),
        }
    )
    return manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})


def _codes(manifest: AssociatedArtifactManifestModel, parent: object) -> set[str]:
    diagnostics = validate_associated_artifact_manifest(
        manifest,
        parent=parent,  # type: ignore[arg-type]
        artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
    )
    return {diagnostic.code for diagnostic in diagnostics}


GENERIC = {"ref_kind": "scenario", "ref_id": "training-range"}


def test_adapters_satisfy_the_client_interfaces() -> None:
    scenario = parse_sdl("name: training-range\nversion: 1.0.0\n")

    assert isinstance(ScenarioArtifactParent(scenario), ArtifactParent)
    assert isinstance(ExperimentArtifactParent(scenario), ArtifactParent)
    assert isinstance(AuthoredScenarioEvidenceView(scenario), AuthoredScenarioEvidence)


def test_an_object_that_is_not_an_artifact_parent_fails_closed() -> None:
    scenario = parse_sdl("name: training-range\nversion: 1.0.0\n")

    assert _codes(_manifest(GENERIC), ScenarioArtifactParent(scenario)) == set()
    assert _codes(_manifest(GENERIC), scenario) == {"associated-artifact.parent-mismatch"}
    assert _codes(_manifest(GENERIC), SimpleNamespace(matches_parent_ref=None)) == {
        "associated-artifact.parent-mismatch"
    }


def test_scenario_parent_keeps_the_generic_snapshot_and_phase_rules() -> None:
    scenario = parse_sdl("name: training-range\nversion: 1.0.0\n")
    digest = canonical_sdl_digest(scenario).value
    snapshot = {"ref_kind": "scenario-snapshot", "ref_id": "training-range", "ref_version": "1.0.0"}

    assert _codes(_manifest(snapshot), ScenarioArtifactParent(scenario)) == set()
    assert (
        _codes(
            _manifest(
                {
                    **snapshot,
                    "ref_digest": "sha256:" + digest.removeprefix("sha256:").upper(),
                    "ref_path": "scenario.yaml",
                }
            ),
            ScenarioArtifactParent(scenario),
        )
        == set()
    )
    assert _codes(_manifest({**snapshot, "ref_version": "2.0.0"}), ScenarioArtifactParent(scenario)) == {
        "associated-artifact.parent-mismatch"
    }
    instantiated = instantiate_scenario(scenario)
    assert _codes(_manifest(snapshot), ScenarioArtifactParent(instantiated)) == {"associated-artifact.parent-mismatch"}
    assert _codes(_manifest(GENERIC), ScenarioArtifactParent(instantiated)) == {"associated-artifact.parent-mismatch"}


def test_parent_adapters_refuse_the_other_layer_kinds() -> None:
    scenario = parse_sdl("name: training-range\nversion: 1.0.0\n")
    task_ref = {"ref_kind": "task", "ref_id": "training-range"}

    assert _codes(_manifest(task_ref, scope="experiment"), ScenarioArtifactParent(scenario)) == {
        "associated-artifact.parent-mismatch"
    }
    assert _codes(_manifest(GENERIC), ExperimentArtifactParent(scenario)) == {"associated-artifact.parent-mismatch"}
    assert _codes(_manifest(task_ref, scope="experiment"), ExperimentArtifactParent(scenario)) == {
        "associated-artifact.parent-mismatch"
    }


def test_authored_scenario_view_computes_the_digest_on_first_use() -> None:
    scenario = parse_sdl("name: training-range\nversion: 1.0.0\n")
    view = AuthoredScenarioEvidenceView(scenario)

    assert view.evidence_requirements == scenario.evidence_requirements
    assert view.scenario_identity == (
        "scenario-snapshot",
        "training-range",
        "1.0.0",
        canonical_sdl_digest(scenario).value,
        None,
    )


def test_authored_scenario_view_defers_digest_errors_until_identity_is_read() -> None:
    broken = SimpleNamespace(name="x", version=None, evidence_requirements={})
    view = AuthoredScenarioEvidenceView(broken)  # type: ignore[arg-type]

    assert view.evidence_requirements == {}
    with pytest.raises(Exception):  # noqa: B017 - the digest error type belongs to the SDL
        _ = view.scenario_identity
