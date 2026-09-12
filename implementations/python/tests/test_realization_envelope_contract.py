"""Published realization-envelope carrier and identity tests (ASR-519)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts import BackendManifestV2Model, ProvisioningPlanModel, RuntimeSnapshotEnvelopeModel
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    ConcernDisposition,
    ObservationStrength,
    RealizationConcern,
    RealizationConcernDisclosureModel,
    RealizationEnvelopeIdentityModel,
    RealizationEnvelopeModel,
    RealizerConfigurationModel,
    realization_envelope_digest,
    realizer_configuration_digest,
    validate_backend_realization_envelope,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane_store import LocalControlPlaneStore


def _payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "realization-envelope/v1",
        "contract_id": "realization-envelope-v1",
        "id": "libvirt-qemu.generic.v1",
        "expression": {
            "id": "libvirt-qemu.generic.expression.v1",
            "scope": "scenario",
            "domains": {},
            "bindings": [],
            "closure": [],
        },
        "configuration": {
            "mode": "generic",
            "configuration_digest": "sha256:" + "1" * 64,
            "architecture": "x86_64",
            "image_policy": "local-qcow2",
            "network_policy": "libvirt-managed",
            "supported_node_types": ["switch", "compute"],
            "supported_os_families": ["linux"],
            "supported_content_types": ["file"],
            "supported_account_features": ["groups"],
            "supported_domain_profiles": [],
            "supports_acls": True,
            "memory_mib": {"minimum": 128, "maximum": None},
            "vcpus": {"minimum": 1, "maximum": None},
        },
        "concerns": [
            {
                "concern": "topology",
                "disposition": "realized",
                "observation_strength": "driver-reported",
                "mechanism": "libvirt-domain-network",
                "transformations": [],
            },
            {
                "concern": "resource-allocation",
                "disposition": "transformed",
                "observation_strength": "driver-reported",
                "mechanism": "libvirt-domain-xml",
                "transformations": ["bounded-normalization"],
            },
            {
                "concern": "compute-substrate",
                "disposition": "realized",
                "observation_strength": "daemon-observed",
                "mechanism": "virtual-machine",
                "transformations": [],
            },
            *[
                {
                    "concern": concern,
                    "disposition": "unsupported",
                    "observation_strength": "none",
                    "mechanism": None,
                    "transformations": [],
                }
                for concern in (
                    "operating-system",
                    "architecture",
                    "image",
                    "network",
                    "content-placement",
                    "account-placement",
                    "feature-binding",
                    "service",
                    "acl",
                )
            ],
        ],
    }
    payload["configuration"]["configuration_digest"] = realizer_configuration_digest(payload["configuration"])  # type: ignore[index]
    payload["digest"] = realization_envelope_digest(payload)
    return payload


def test_backend_realization_envelope_validates_its_canonical_digest():
    model = BackendRealizationEnvelopeModel.model_validate(_payload())

    assert model.expression == RealizationEnvelopeModel.model_validate(_payload()["expression"])
    assert model.configuration == RealizerConfigurationModel(
        mode="generic",
        configuration_digest=realizer_configuration_digest(_payload()["configuration"]),
        architecture="x86_64",
        image_policy="local-qcow2",
        network_policy="libvirt-managed",
        supported_node_types=["switch", "compute"],
        supported_os_families=["linux"],
        supported_content_types=["file"],
        supported_account_features=["groups"],
        supported_domain_profiles=[],
        supports_acls=True,
        memory_mib={"minimum": 128, "maximum": None},
        vcpus={"minimum": 1, "maximum": None},
    )
    assert model.concerns[0] == RealizationConcernDisclosureModel(
        concern="topology",
        disposition=ConcernDisposition.REALIZED,
        observation_strength=ObservationStrength.DRIVER_REPORTED,
        mechanism="libvirt-domain-network",
    )
    assert model.identity == RealizationEnvelopeIdentityModel(
        contract_id="realization-envelope-v1",
        envelope_id="libvirt-qemu.generic.v1",
        schema_version="realization-envelope/v1",
        digest=model.digest,
        configuration_digest=model.configuration.configuration_digest,
    )


def test_realization_concern_taxonomy_accounts_for_declared_services():
    assert RealizationConcern.SERVICE.value == "service"
    assert RealizationConcern.COMPUTE_SUBSTRATE.value == "compute-substrate"


def test_backend_realization_envelope_rejects_content_tampering():
    payload = _payload()
    payload["configuration"]["mode"] = "techvault-appliance"  # type: ignore[index]

    with pytest.raises(ValidationError, match="digest does not match"):
        BackendRealizationEnvelopeModel.model_validate(payload)


def test_backend_realization_envelope_rejects_duplicate_concerns():
    payload = _payload()
    payload["concerns"] = [deepcopy(payload["concerns"][0]), deepcopy(payload["concerns"][0])]  # type: ignore[index]
    payload["digest"] = realization_envelope_digest(payload)

    with pytest.raises(ValidationError, match="concerns must not contain duplicate concern values"):
        BackendRealizationEnvelopeModel.model_validate(payload)


def test_backend_realization_envelope_rejects_missing_concern_disclosure():
    payload = _payload()
    payload["concerns"] = payload["concerns"][:-1]  # type: ignore[index]
    payload["digest"] = realization_envelope_digest(payload)

    with pytest.raises(ValidationError, match="must disclose every governed concern"):
        BackendRealizationEnvelopeModel.model_validate(payload)


def test_operating_system_capability_rows_require_realized_guest_observed_claim():
    payload = _payload()
    payload["configuration"]["operating_systems"] = [  # type: ignore[index]
        {"family": "linux", "distribution": "ubuntu", "versions": ["22.04"]}
    ]
    payload["configuration"]["configuration_digest"] = realizer_configuration_digest(  # type: ignore[index]
        payload["configuration"]
    )
    payload["digest"] = realization_envelope_digest(payload)

    with pytest.raises(ValidationError, match="capability rows require a realized guest-observed"):
        BackendRealizationEnvelopeModel.model_validate(payload)


def test_operating_system_claim_requires_coupled_capability_rows():
    payload = _payload()
    operating_system = next(claim for claim in payload["concerns"] if claim["concern"] == "operating-system")  # type: ignore[index]
    operating_system.update(
        disposition="realized",
        observation_strength="guest-observed",
        mechanism="guest-os-release",
    )
    payload["digest"] = realization_envelope_digest(payload)

    with pytest.raises(ValidationError, match="support requires coupled operating_systems capability rows"):
        BackendRealizationEnvelopeModel.model_validate(payload)


def test_published_schema_enforces_expressible_realization_invariants():
    schema = BackendRealizationEnvelopeModel.model_json_schema()
    validator = Draft202012Validator(schema)

    duplicate_term = _payload()
    duplicate_term["configuration"]["supported_node_types"] = ["compute", "compute"]  # type: ignore[index]
    assert list(validator.iter_errors(duplicate_term))

    missing_concern = _payload()
    missing_concern["concerns"] = missing_concern["concerns"][:-1]  # type: ignore[index]
    assert list(validator.iter_errors(missing_concern))

    incoherent_disposition = _payload()
    incoherent_disposition["concerns"][0]["transformations"] = ["default-substitution"]  # type: ignore[index]
    assert list(validator.iter_errors(incoherent_disposition))


def test_published_schema_declares_callable_canonical_semantic_validator():
    schema = BackendRealizationEnvelopeModel.model_json_schema()
    invariant = schema["x-raes-invariants"][0]

    assert invariant["validator"] == "raes_contracts.realization_envelope.validate_backend_realization_envelope"
    with pytest.raises(ValidationError, match="digest does not match"):
        validate_backend_realization_envelope({**_payload(), "digest": "sha256:" + "f" * 64})


def test_transformed_concern_requires_a_transformation():
    with pytest.raises(ValidationError, match="transformed disposition requires transformations"):
        RealizationConcernDisclosureModel(
            concern="resource-allocation",
            disposition="transformed",
            observation_strength="driver-reported",
            mechanism="libvirt-domain-xml",
        )


def test_unsupported_concern_cannot_claim_observation_or_mechanism():
    with pytest.raises(ValidationError, match="unsupported disposition"):
        RealizationConcernDisclosureModel(
            concern="content-placement",
            disposition="unsupported",
            observation_strength="driver-reported",
            mechanism="descriptor-only",
        )


def test_identity_rejects_non_sha256_digests():
    with pytest.raises(ValidationError):
        RealizationEnvelopeIdentityModel(
            contract_id="realization-envelope-v1",
            envelope_id="libvirt-qemu.generic.v1",
            schema_version="realization-envelope/v1",
            digest="sha256:short",
            configuration_digest="sha256:" + "1" * 64,
        )


def test_manifest_plan_and_snapshot_publish_the_same_typed_identity():
    identity = BackendRealizationEnvelopeModel.model_validate(_payload()).identity.model_dump(mode="json")
    manifest = BackendManifestV2Model.model_validate(
        {
            "identity": {"name": "test-backend", "version": "1.0.0"},
            "supported_contract_versions": [
                "backend-manifest-v2",
                "realization-envelope-v1",
                "provisioning-plan-v1",
                "runtime-snapshot-v1",
            ],
            "compatibility": {"processors": ["raes-reference-processor"]},
            "realization_support": [
                {
                    "domain": "runtime-realization",
                    "support_mode": "constrained",
                    "supported_constraint_kinds": ["node-type"],
                    "supported_exact_requirement_kinds": ["declared-capability-match"],
                    "disclosure_kinds": ["runtime-snapshot-v1"],
                }
            ],
            "concept_bindings": [{"scope": "capabilities.provisioner.supported_node_types", "family": "assets"}],
            "capabilities": {
                "provisioner": {
                    "name": "test",
                    "supported_node_types": ["compute"],
                    "supported_os_families": ["linux"],
                }
            },
            "realization_envelope": identity,
        }
    )
    plan = ProvisioningPlanModel(realization_authority=[], realization_envelope=identity)
    snapshot = RuntimeSnapshotEnvelopeModel(realization_envelope=identity)

    assert manifest.realization_envelope == plan.realization_envelope == snapshot.realization_envelope


def test_local_control_plane_store_roundtrips_envelope_identity(tmp_path):
    identity = BackendRealizationEnvelopeModel.model_validate(_payload()).identity
    store = LocalControlPlaneStore(tmp_path / "store")

    store.save_snapshot(
        RuntimeSnapshot(realization_envelope=identity),
        expected_revision=store.load_snapshot_state().revision,
    )

    assert store.load_snapshot().realization_envelope == identity


def test_published_realization_envelope_fixture_corpus_is_nonvacuous():
    root = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "fixtures"
        / "realization-envelope"
        / "realization-envelope-v1"
    )
    valid = sorted((root / "valid").glob("*.json"))
    invalid = sorted((root / "invalid").glob("*.json"))

    assert valid and invalid
    for path in valid:
        BackendRealizationEnvelopeModel.model_validate(json.loads(path.read_text(encoding="utf-8")))
    for path in invalid:
        with pytest.raises(ValidationError):
            BackendRealizationEnvelopeModel.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_backend_manifest_requires_contract_declaration_for_envelope_identity():
    identity = BackendRealizationEnvelopeModel.model_validate(_payload()).identity
    base = {
        "identity": {"name": "test-backend", "version": "1.0.0"},
        "supported_contract_versions": ["backend-manifest-v2"],
        "compatibility": {"processors": ["raes-reference-processor"]},
        "realization_support": [
            {
                "domain": "runtime-realization",
                "support_mode": "constrained",
                "supported_constraint_kinds": ["node-type"],
                "disclosure_kinds": ["runtime-snapshot-v1"],
            }
        ],
        "concept_bindings": [{"scope": "capabilities.provisioner.supported_node_types", "family": "assets"}],
        "capabilities": {
            "provisioner": {
                "name": "test",
                "supported_node_types": ["compute"],
                "supported_os_families": ["linux"],
            }
        },
        "realization_envelope": identity.model_dump(mode="json"),
    }

    with pytest.raises(ValidationError, match="realization-envelope-v1"):
        BackendManifestV2Model.model_validate(base)

    schema_validator = Draft202012Validator(BackendManifestV2Model.model_json_schema())
    explicit_null = {**base, "realization_envelope": None}
    BackendManifestV2Model.model_validate(explicit_null)
    schema_validator.validate(explicit_null)

    declared_with_null = {
        **explicit_null,
        "supported_contract_versions": ["backend-manifest-v2", "realization-envelope-v1"],
    }
    with pytest.raises(ValidationError, match="requires realization_envelope identity"):
        BackendManifestV2Model.model_validate(declared_with_null)
    assert list(schema_validator.iter_errors(declared_with_null))
