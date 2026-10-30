"""Associated-artifact manifest contract and byte-binding tests (issue #738)."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes import canonical_sdl_digest, parse_sdl, parse_sdl_file
from raes.instantiate import instantiate_scenario
from raes.scenario import ExpandedScenario, Scenario
from raes_conformance.conformance import _MODEL_VALIDATORS, _fixture_case_diagnostics
from raes_contracts.associated_artifacts import (
    AssociatedArtifactValidationLimits,
    associated_artifact_set_digest,
    load_associated_artifact_manifest_json,
    validate_associated_artifact_manifest,
)
from raes_contracts.contracts import (
    REUSABLE_ASSET_FAMILIES,
    AssociatedArtifactManifestModel,
    ExperimentApparatusContextModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    schema_bundle,
)
from raes_contracts.json_ingress import StrictJsonIngressError
from raes_contracts.versions import ASSOCIATED_ARTIFACT_MANIFEST_SCHEMA_VERSION

PAYLOAD = b"operator guide\n"
PAYLOAD_SHA256 = hashlib.sha256(PAYLOAD).hexdigest()
REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "associated-artifacts" / "associated-artifact-manifest-v1.json"
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures" / "associated-artifacts" / "associated-artifact-manifest-v1"


def _manifest_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "associated-artifact-manifest/v1",
        "manifest_id": "scenario-guidance",
        "manifest_version": "1.0.0",
        "canonicalization_profile": "associated-artifact-set/v1",
        "scope": "scenario",
        "parent_ref": {"ref_kind": "scenario", "ref_id": "training-range"},
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
    payload.update(overrides)
    return payload


def _manifest(**overrides: object) -> AssociatedArtifactManifestModel:
    manifest = AssociatedArtifactManifestModel.model_validate(_manifest_payload(**overrides))
    return manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})


def _codes(diagnostics: tuple[object, ...]) -> set[str]:
    return {diagnostic.code for diagnostic in diagnostics}  # type: ignore[attr-defined]


def test_manifest_set_identity_is_distinct_from_sdl_semantic_identity() -> None:
    scenario = parse_sdl("name: training-range\nversion: 1.0.0\n")
    manifest = _manifest()

    assert manifest.set_digest == associated_artifact_set_digest(manifest)
    assert manifest.set_digest != canonical_sdl_digest(scenario).value


def test_validator_binds_every_checksum_to_concrete_bytes() -> None:
    scenario = parse_sdl("name: training-range\nversion: 1.0.0\n")
    diagnostics = validate_associated_artifact_manifest(
        _manifest(),
        parent=scenario,
        artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
    )

    assert diagnostics == ()


def test_validator_rejects_missing_and_digest_only_bindings() -> None:
    scenario = parse_sdl("name: training-range\n")

    missing = validate_associated_artifact_manifest(_manifest(), parent=scenario, artifact_readers={})
    digest_only = validate_associated_artifact_manifest(
        _manifest(),
        parent=scenario,
        artifact_readers={"operator-guide": PAYLOAD_SHA256},
    )

    assert "associated-artifact.payload-binding-missing" in _codes(missing)
    assert "associated-artifact.payload-binding-invalid" in _codes(digest_only)


def test_validator_rejects_unexpected_and_failing_byte_readers() -> None:
    class FailingReader:
        def read(self, _size: int) -> bytes:
            raise OSError("simulated bounded-reader failure")

    scenario = parse_sdl("name: training-range\n")
    unexpected = validate_associated_artifact_manifest(
        _manifest(),
        parent=scenario,
        artifact_readers={
            "operator-guide": BytesIO(PAYLOAD),
            "undeclared": BytesIO(b""),
        },
    )
    failing = validate_associated_artifact_manifest(
        _manifest(),
        parent=scenario,
        artifact_readers={"operator-guide": FailingReader()},  # type: ignore[dict-item]
    )

    assert "associated-artifact.payload-binding-unexpected" in _codes(unexpected)
    assert "associated-artifact.payload-binding-invalid" in _codes(failing)


def test_validator_reports_checksum_size_set_and_parent_mismatches() -> None:
    scenario = parse_sdl("name: training-range\n")
    original = _manifest()
    changed_bytes = validate_associated_artifact_manifest(
        _manifest(),
        parent=scenario,
        artifact_readers={"operator-guide": BytesIO(b"changed")},
    )
    changed_set = validate_associated_artifact_manifest(
        original.model_copy(update={"set_digest": "sha256:" + ("f" * 64)}),
        parent=scenario,
        artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
    )
    changed_artifact = original.artifacts["operator-guide"].model_copy(update={"role": "documentation"})
    changed_artifact_set = validate_associated_artifact_manifest(
        original.model_copy(update={"artifacts": {"operator-guide": changed_artifact}}),
        parent=scenario,
        artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
    )
    wrong_parent = validate_associated_artifact_manifest(
        _manifest(),
        parent=parse_sdl("name: another-scenario\n"),
        artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
    )

    assert {
        "associated-artifact.payload-checksum-mismatch",
        "associated-artifact.payload-size-mismatch",
    } <= _codes(changed_bytes)
    assert "associated-artifact.set-digest-mismatch" in _codes(changed_set)
    assert "associated-artifact.set-digest-mismatch" in _codes(changed_artifact_set)
    assert "associated-artifact.parent-mismatch" in _codes(wrong_parent)


def test_scope_key_and_collision_rules_are_closed() -> None:
    experiment_parent = {"ref_kind": "run", "ref_id": "run-1", "ref_version": "1"}
    with pytest.raises(ValidationError, match="scope|parent"):
        AssociatedArtifactManifestModel.model_validate(_manifest_payload(parent_ref=experiment_parent))

    keyed_mismatch = _manifest_payload()
    keyed_mismatch["artifacts"]["operator-guide"]["artifact_id"] = "different"  # type: ignore[index]
    with pytest.raises(ValidationError, match="key|artifact_id"):
        AssociatedArtifactManifestModel.model_validate(keyed_mismatch)

    alias = _manifest_payload()
    artifacts = alias["artifacts"]  # type: ignore[assignment]
    artifacts["guide-copy"] = dict(artifacts["operator-guide"], artifact_id="guide-copy")  # type: ignore[index]
    with pytest.raises(ValidationError, match="alias|duplicate"):
        AssociatedArtifactManifestModel.model_validate(alias)


def test_json_ingress_rejects_duplicate_members_and_secret_bearing_locators() -> None:
    duplicate = '{"schema_version":"associated-artifact-manifest/v1","manifest_id":"a","manifest_id":"b"}'
    with pytest.raises(StrictJsonIngressError, match="duplicate JSON member"):
        load_associated_artifact_manifest_json(duplicate)

    secret_uri = _manifest_payload()
    secret_uri["artifacts"]["operator-guide"]["uri"] = "https://user:secret@example.test/guide"  # type: ignore[index]
    with pytest.raises(ValidationError, match="credential|userinfo|secret"):
        AssociatedArtifactManifestModel.model_validate(secret_uri)

    signed_uri = _manifest_payload()
    signed_uri["artifacts"]["operator-guide"]["uri"] = (  # type: ignore[index]
        "https://example.test/guide?X-Amz-Credential=temporary&X-Amz-Signature=secret"
    )
    with pytest.raises(ValidationError, match="secret"):
        AssociatedArtifactManifestModel.model_validate(signed_uri)


def test_streaming_limits_reject_before_or_during_reads() -> None:
    scenario = parse_sdl("name: training-range\n")
    limits = AssociatedArtifactValidationLimits(max_artifacts=1, max_artifact_bytes=4, max_total_bytes=4)

    diagnostics = validate_associated_artifact_manifest(
        _manifest(),
        parent=scenario,
        artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
        limits=limits,
    )

    assert "associated-artifact.resource-limit-exceeded" in _codes(diagnostics)


def test_artifact_count_limit_is_enforced_independently_of_byte_limits() -> None:
    payload = _manifest_payload()
    artifacts = payload["artifacts"]  # type: ignore[assignment]
    artifacts["guide-copy"] = {  # type: ignore[index]
        **artifacts["operator-guide"],  # type: ignore[index]
        "artifact_id": "guide-copy",
        "role": "documentation",
        "uri": "urn:example:guide-copy",
    }
    manifest = AssociatedArtifactManifestModel.model_validate(payload)
    manifest = manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})

    diagnostics = validate_associated_artifact_manifest(
        manifest,
        parent=parse_sdl("name: training-range\n"),
        artifact_readers={},
        limits=AssociatedArtifactValidationLimits(
            max_artifacts=1,
            max_artifact_bytes=len(PAYLOAD),
            max_total_bytes=2 * len(PAYLOAD),
        ),
    )

    assert _codes(diagnostics) == {"associated-artifact.resource-limit-exceeded"}


def test_blake3_payloads_supported_by_the_public_checksum_contract_can_conform() -> None:
    empty_blake3 = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
    payload = _manifest_payload()
    artifact = payload["artifacts"]["operator-guide"]  # type: ignore[index]
    artifact["uri"] = "urn:blake3:" + empty_blake3
    artifact["checksum"] = {"algorithm": "blake3", "value": empty_blake3}
    artifact["size_bytes"] = 0
    manifest = AssociatedArtifactManifestModel.model_validate(payload)
    manifest = manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})

    assert (
        validate_associated_artifact_manifest(
            manifest,
            parent=parse_sdl("name: training-range\n"),
            artifact_readers={"operator-guide": BytesIO(b"")},
        )
        == ()
    )


def test_contract_is_registered_with_fixed_schema_and_trust_family() -> None:
    assert ASSOCIATED_ARTIFACT_MANIFEST_SCHEMA_VERSION == "associated-artifact-manifest/v1"
    assert "associated-artifact-manifest-v1" in schema_bundle()
    assert "associated_artifact_set" in REUSABLE_ASSET_FAMILIES


def test_generic_conformance_runner_reports_required_external_semantic_context() -> None:
    manifest = _manifest()

    assert "associated-artifact-manifest-v1" not in _MODEL_VALIDATORS
    diagnostics = _fixture_case_diagnostics("associated-artifact-manifest-v1", manifest.model_dump(mode="json"))
    assert _codes(tuple(diagnostics)) == {"conformance.semantic-context-required"}


@pytest.mark.parametrize(
    ("ref_kind", "fixture", "model", "id_field", "version_field"),
    [
        ("task", "experiment-task-v1", ExperimentTaskModel, "task_id", "task_version"),
        (
            "authoring-input",
            "experiment-authoring-input-v1",
            ExperimentSpecModel,
            "spec_id",
            "spec_version",
        ),
        (
            "apparatus-context",
            "experiment-apparatus-context-v1",
            ExperimentApparatusContextModel,
            "apparatus_context_id",
            "context_version",
        ),
        ("run", "experiment-run-v1", ExperimentRunModel, "run_id", "run_version"),
        ("study", "experiment-study-v1", ExperimentStudyModel, "study_id", "study_version"),
    ],
)
def test_every_experiment_attachment_scope_binds_its_concrete_parent(
    ref_kind: str,
    fixture: str,
    model: type,
    id_field: str,
    version_field: str,
) -> None:
    path = REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / fixture / "valid" / "reference.json"
    parent = model.model_validate(json.loads(path.read_text(encoding="utf-8")))
    parent_ref = {
        "ref_kind": ref_kind,
        "ref_id": getattr(parent, id_field),
        "ref_version": getattr(parent, version_field),
    }
    manifest = _manifest(scope="experiment", parent_ref=parent_ref)

    assert (
        validate_associated_artifact_manifest(
            manifest,
            parent=parent,
            artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
        )
        == ()
    )
    wrong_version_manifest = _manifest(
        scope="experiment",
        parent_ref={**parent_ref, "ref_version": "definitely-not-the-parent-version"},
    )
    assert "associated-artifact.parent-mismatch" in _codes(
        validate_associated_artifact_manifest(
            wrong_version_manifest,
            parent=parent,
            artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
        )
    )


def test_snapshot_parent_digest_is_checked_without_changing_sdl_identity() -> None:
    scenario = parse_sdl("name: training-range\nversion: 1.0.0\n")
    parent_ref = {
        "ref_kind": "scenario-snapshot",
        "ref_id": scenario.name,
        "ref_version": scenario.version,
        "ref_digest": canonical_sdl_digest(scenario).value,
    }
    manifest = _manifest(parent_ref=parent_ref)

    assert (
        validate_associated_artifact_manifest(
            manifest,
            parent=scenario,
            artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
        )
        == ()
    )
    other_parent = _manifest(parent_ref={"ref_kind": "scenario", "ref_id": scenario.name})
    assert manifest.set_digest != other_parent.set_digest

    wrong_digest = _manifest(parent_ref={**parent_ref, "ref_digest": "sha256:" + ("0" * 64)})
    wrong_version = _manifest(parent_ref={**parent_ref, "ref_version": "2.0.0"})
    for mismatched_manifest in (wrong_digest, wrong_version):
        assert "associated-artifact.parent-mismatch" in _codes(
            validate_associated_artifact_manifest(
                mismatched_manifest,
                parent=scenario,
                artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
            )
        )


def test_snapshot_parent_admits_validated_file_backed_expansion_only(tmp_path: Path) -> None:
    module = tmp_path / "module.yaml"
    module.write_text(
        """\
name: shared-host
version: 1.0.0
module:
  id: raes/shared-host
  version: 1.0.0
  exports: {nodes: [host]}
nodes:
  host: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
""",
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        """\
name: training-range
version: 1.0.0
imports:
  - path: module.yaml
    namespace: shared
    version: 1.0.0
""",
        encoding="utf-8",
    )
    expanded = parse_sdl_file(root)
    assert isinstance(expanded, ExpandedScenario)
    parent_ref = {
        "ref_kind": "scenario-snapshot",
        "ref_id": expanded.name,
        "ref_version": expanded.version,
        "ref_digest": canonical_sdl_digest(expanded).value,
    }
    manifest = _manifest(parent_ref=parent_ref)

    assert (
        validate_associated_artifact_manifest(
            manifest,
            parent=expanded,
            artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
        )
        == ()
    )

    wrong_digest = _manifest(parent_ref={**parent_ref, "ref_digest": "sha256:" + ("0" * 64)})
    assert "associated-artifact.parent-mismatch" in _codes(
        validate_associated_artifact_manifest(
            wrong_digest,
            parent=expanded,
            artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
        )
    )

    unvalidated_expanded = ExpandedScenario.model_validate(expanded.model_dump(mode="python"))
    unvalidated_scenario = Scenario.model_validate({"name": expanded.name, "version": expanded.version})
    instantiated = instantiate_scenario(expanded)
    for inadmissible_parent in (unvalidated_expanded, unvalidated_scenario, instantiated):
        assert "associated-artifact.parent-mismatch" in _codes(
            validate_associated_artifact_manifest(
                manifest,
                parent=inadmissible_parent,
                artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
            )
        )

    generic_manifest = _manifest(parent_ref={"ref_kind": "scenario", "ref_id": expanded.name})
    assert (
        validate_associated_artifact_manifest(
            generic_manifest,
            parent=unvalidated_scenario,
            artifact_readers={"operator-guide": BytesIO(PAYLOAD)},
        )
        == ()
    )


def test_published_schema_and_fixture_corpus_cover_both_attachment_scopes() -> None:
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    valid_paths = sorted((FIXTURES_ROOT / "valid").glob("*.json"))
    invalid_paths = sorted((FIXTURES_ROOT / "invalid").glob("*.json"))
    assert {path.stem for path in valid_paths} == {
        "apparatus-context",
        "authoring-input",
        "run",
        "scenario",
        "scenario-snapshot",
        "study",
        "task",
    }
    assert invalid_paths
    for path in valid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(payload, schema)
        AssociatedArtifactManifestModel.model_validate(payload)
    for path in invalid_paths:
        with pytest.raises(ValidationError):
            AssociatedArtifactManifestModel.model_validate(json.loads(path.read_text(encoding="utf-8")))
