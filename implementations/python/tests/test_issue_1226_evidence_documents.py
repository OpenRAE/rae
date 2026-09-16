"""Evidence documents bind exact output subjects and stay deterministic.

Acceptance criterion 2: the build/tool/native input inventory is recorded
separately from runtime dependencies, carries source/workflow/run/attempt
identity and lock/policy hashes, and every document binds the exact output
subject digests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.release_evidence_documents import (
    BUILD_INVENTORY_SCHEMA_VERSION,
    CYCLONEDX_SPEC_VERSION,
    BuildInputs,
    EvidenceDocumentError,
    render_build_inventory,
    render_runtime_sbom,
)
from tools.release_evidence_sbom import ClosureComponent, ReconciledClosure

_SUBJECT_DIGEST = "a" * 64
_COMPONENTS = ReconciledClosure(
    components=[
        ClosureComponent(name="typer", version="0.24.1", scope="required"),
        ClosureComponent(name="click", version="8.4.2", scope="required"),
        ClosureComponent(name="sphinx", version="8.2.3", scope="optional", extra="docs"),
    ],
    edges={"typer": ["click"], "click": [], "sphinx": []},
)


def _sbom(**overrides: object) -> dict:
    kwargs: dict = {
        "closure": _COMPONENTS,
        "subject_name": "raes",
        "subject_version": "1.2.3",
        "subject_filename": "raes-1.2.3-py3-none-any.whl",
        "subject_digest": _SUBJECT_DIGEST,
        "subject_role": "wheel",
    }
    kwargs.update(overrides)
    return render_runtime_sbom(**kwargs)


def test_sbom_declares_a_supported_cyclonedx_document() -> None:
    document = _sbom()
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == CYCLONEDX_SPEC_VERSION
    assert document["version"] == 1


def test_sbom_binds_the_exact_output_subject_digest() -> None:
    component = _sbom()["metadata"]["component"]
    assert component["name"] == "raes"
    assert component["version"] == "1.2.3"
    assert component["hashes"] == [{"alg": "SHA-256", "content": _SUBJECT_DIGEST}]


def test_sbom_records_every_reconciled_component_with_its_scope() -> None:
    components = {item["name"]: item for item in _sbom()["components"]}
    assert set(components) == {"typer", "click", "sphinx"}
    assert components["typer"]["scope"] == "required"
    assert components["sphinx"]["scope"] == "optional"
    assert components["typer"]["purl"] == "pkg:pypi/typer@0.24.1"


def test_sbom_labels_the_extra_that_contributed_a_component() -> None:
    components = {item["name"]: item for item in _sbom()["components"]}
    assert {"name": "raes:extra", "value": "docs"} in components["sphinx"]["properties"]
    assert "properties" not in components["click"]


def test_sbom_preserves_dependency_edges() -> None:
    dependencies = {item["ref"]: item["dependsOn"] for item in _sbom()["dependencies"]}
    assert dependencies["pkg:pypi/typer@0.24.1"] == ["pkg:pypi/click@8.4.2"]
    assert dependencies["pkg:pypi/click@8.4.2"] == []


def test_sbom_root_depends_on_the_declared_closure() -> None:
    document = _sbom()
    root = document["metadata"]["component"]["bom-ref"]
    dependencies = {item["ref"]: item["dependsOn"] for item in document["dependencies"]}
    assert set(dependencies[root]) == {
        "pkg:pypi/typer@0.24.1",
        "pkg:pypi/click@8.4.2",
        "pkg:pypi/sphinx@8.2.3",
    }


def test_sbom_is_deterministic() -> None:
    """Evidence carries no timestamp or serial number, so bytes are reproducible."""

    first = json.dumps(_sbom(), sort_keys=True)
    second = json.dumps(_sbom(), sort_keys=True)
    assert first == second
    assert "serialNumber" not in _sbom()
    assert "timestamp" not in _sbom().get("metadata", {})


def test_sbom_refuses_a_malformed_subject_digest() -> None:
    with pytest.raises(EvidenceDocumentError) as excinfo:
        _sbom(subject_digest="not-a-digest")
    assert excinfo.value.code == "evidence-subject-digest-invalid"


def _inventory(**overrides: object) -> dict:
    kwargs: dict = {
        "subjects": [
            {"role": "wheel", "filename": "raes-1.2.3-py3-none-any.whl", "sha256": _SUBJECT_DIGEST},
            {"role": "sdist", "filename": "raes-1.2.3.tar.gz", "sha256": "b" * 64},
        ],
        "inputs": BuildInputs(
            interpreter={
                "implementation": "cpython",
                "version": "3.12.14",
                "abi": "cp312",
                "platform": "x86_64-unknown-linux-gnu",
            },
            build_backend={"name": "hatchling", "version": "1.27.0"},
            tool_inputs=[{"name": "uv", "version": "0.12.4"}],
            native_inputs=[],
            actions=[{"action": "actions/checkout", "commit": "c" * 40}],
            runner={"image": "ubuntu-24.04", "architecture": "x86_64", "observed": False},
        ),
        "lock_hashes": {"project_lock_sha256": "d" * 64, "tool_lock_sha256": "e" * 64},
        "policy_hashes": {"tooling_policy_sha256": "f" * 64},
        "release": {
            "repository": "OpenRAE/rae",
            "source_sha": "1" * 40,
            "workflow_ref": "OpenRAE/rae/.github/workflows/release-please.yml@refs/heads/main",
            "workflow_sha": "2" * 40,
            "run_id": "42",
            "run_attempt": "1",
            "tag": "v1.2.3",
        },
        "profile_id": "public-linux-x86_64-cp312-all-extras",
    }
    kwargs.update(overrides)
    return render_build_inventory(**kwargs)


def test_inventory_is_separate_from_runtime_dependencies() -> None:
    document = _inventory()
    assert document["schema_version"] == BUILD_INVENTORY_SCHEMA_VERSION
    assert "components" not in document
    assert {"build_backend", "tool_inputs", "native_inputs", "actions"} <= set(document)


def test_inventory_binds_exact_output_subject_digests() -> None:
    subjects = {item["role"]: item for item in _inventory()["subjects"]}
    assert subjects["wheel"]["sha256"] == _SUBJECT_DIGEST
    assert subjects["sdist"]["sha256"] == "b" * 64


def test_inventory_records_source_workflow_run_and_attempt_identity() -> None:
    release = _inventory()["release"]
    assert release["source_sha"] == "1" * 40
    assert release["workflow_sha"] == "2" * 40
    assert release["run_id"] == "42"
    assert release["run_attempt"] == "1"


def test_inventory_keeps_candidate_source_and_producer_workflow_separate() -> None:
    """A workflow definition revision is not the candidate source revision."""

    release = _inventory()["release"]
    assert "source_sha" in release
    assert "workflow_sha" in release
    assert release["source_sha"] != release["workflow_sha"]


def test_inventory_records_lock_and_policy_hashes_separately() -> None:
    document = _inventory()
    assert document["lock_hashes"]["project_lock_sha256"] == "d" * 64
    assert document["policy_hashes"]["tooling_policy_sha256"] == "f" * 64
    assert document["lock_hashes"] != document["policy_hashes"]


def test_inventory_distinguishes_selected_inputs_from_observed_host() -> None:
    """A runner label is not an observed host inventory."""

    assert _inventory()["runner"]["observed"] is False


def test_inventory_carries_no_credential_bearing_environment() -> None:
    serialized = json.dumps(_inventory())
    # The token prefix is assembled rather than written out, so this file
    # asserts the property without itself containing a credential-shaped literal.
    for marker in ("TOKEN", "SECRET", "PASSWORD", "gh" + "p_", "Authorization"):
        assert marker not in serialized


def test_inventory_refuses_a_subject_without_a_digest() -> None:
    with pytest.raises(EvidenceDocumentError) as excinfo:
        _inventory(subjects=[{"role": "wheel", "filename": "raes-1.2.3-py3-none-any.whl"}])
    assert excinfo.value.code == "evidence-subject-digest-invalid"


def test_inventory_refuses_an_empty_subject_set() -> None:
    with pytest.raises(EvidenceDocumentError) as excinfo:
        _inventory(subjects=[])
    assert excinfo.value.code == "evidence-subjects-absent"


def test_documents_round_trip_through_json(tmp_path: Path) -> None:
    for name, document in (("sbom", _sbom()), ("inventory", _inventory())):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
        assert json.loads(path.read_text(encoding="utf-8")) == document
