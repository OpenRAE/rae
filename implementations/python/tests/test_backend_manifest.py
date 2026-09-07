"""Backend manifest declaration tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JSONSchemaValidationError
from pydantic import ValidationError
from raes_backend_protocols.capabilities import (
    OBSERVATION_CAPABILITY_CAPTURE_KIND_SCOPE,
    OBSERVATION_CAPABILITY_CHANNEL_KIND_SCOPE,
    OBSERVATION_CAPABILITY_SEALING_MODE_SCOPE,
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_POLICY_FEATURES,
    PARTICIPANT_RUNTIME_ROLE_SCOPE,
    BackendManifest,
    ObservationCapabilities,
    OrchestratorCapabilities,
    ParticipantFeatureSupport,
    ParticipantRuntimeCapabilities,
    ProvisionerCapabilities,
    observation_capability_contract_gaps,
    participant_feature_support_gaps,
    participant_runtime_capability_contract_gaps,
    resolve_participant_feature_support,
)
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_backend_protocols.provisioner_manifest import provisioner_from_model
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.manifest_authority import BACKEND_SUPPORTED_CONTRACT_IDS
from raes_contracts.vocabulary import (
    GeneratedArtifactDeliveryMode,
    ParticipantFeatureSupportLevel,
    WorkflowFeature,
    WorkflowStatePredicateFeature,
)

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"
V2_VALID_DIR = FIXTURES_ROOT / "backend-manifest" / "backend-manifest-v2" / "valid"
V2_INVALID_DIR = FIXTURES_ROOT / "backend-manifest" / "backend-manifest-v2" / "invalid"
EXPECTED_SUPPORTED_CONTRACT_VERSIONS_V2 = [
    contract_id
    for contract_id in BACKEND_SUPPORTED_CONTRACT_IDS
    if contract_id not in {"experiment-binding-descriptors-v1", "realization-envelope-v1"}
]


def test_backend_workflow_vocab_enum_values():
    assert {feature.value for feature in WorkflowFeature} == {
        "decision",
        "switch",
        "retry",
        "call",
        "parallel-barrier",
        "failure-transitions",
        "cancellation",
        "timeouts",
        "compensation",
        "objective-steps",
        "scaffolded-steps",
    }
    assert {feature.value for feature in WorkflowStatePredicateFeature} == {
        "outcome-matching",
        "attempt-counts",
    }


def test_backend_manifest_rejects_hollow_defaults():
    with pytest.raises(ValueError):
        BackendManifest(
            name="stub",
            provisioner=ProvisionerCapabilities(
                name="stub-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
        )


def test_backend_manifest_rejects_unknown_keywords():
    with pytest.raises(TypeError, match="unexpected keyword argument.*unknown"):
        BackendManifest(unknown=True)


def test_provisioner_capabilities_reject_hollow_declaration():
    with pytest.raises(ValueError):
        ProvisionerCapabilities(
            name="stub-provisioner",
            supported_node_types=frozenset(),
            supported_os_families=frozenset({"linux"}),
        )


def test_backend_manifest_v2_roundtrip_from_stub_manifest():
    payload = backend_manifest_payload(create_stub_manifest(with_time=True))
    model = BackendManifestV2Model.model_validate(payload)

    assert model.schema_version == "backend-manifest/v2"
    assert model.identity.name == "stub"
    assert model.identity.version
    assert model.compatibility.processors == ["raes-reference-processor"]
    assert model.compatibility.model_dump(mode="json") == {"processors": ["raes-reference-processor"]}
    assert model.supported_contract_versions == EXPECTED_SUPPORTED_CONTRACT_VERSIONS_V2
    assert model.capabilities.orchestrator is not None
    assert model.capabilities.provisioner.supported_generated_artifact_kinds == [
        "certificate_bundle",
        "rendered_config",
        "ssh_key_bundle",
    ]
    assert model.capabilities.orchestrator.supported_workflow_features == [
        WorkflowFeature.CALL,
        WorkflowFeature.CANCELLATION,
        WorkflowFeature.COMPENSATION,
        WorkflowFeature.DECISION,
        WorkflowFeature.FAILURE_TRANSITIONS,
        WorkflowFeature.PARALLEL_BARRIER,
        WorkflowFeature.RETRY,
        WorkflowFeature.SWITCH,
        WorkflowFeature.TIMEOUTS,
    ]
    assert model.realization_support[0].support_mode.value == "constrained"
    roundtrip = model.model_dump(mode="json")
    roundtrip.pop("realization_envelope", None)
    assert roundtrip == payload


def test_legacy_generated_artifact_capability_defaults_to_mount_delivery():
    payload = backend_manifest_payload(create_stub_manifest())
    provisioner_payload = payload["capabilities"]["provisioner"]
    provisioner_payload.pop("supported_generated_artifact_delivery_modes")

    model = BackendManifestV2Model.model_validate(payload)
    provisioner = provisioner_from_model(model.capabilities.provisioner)

    assert provisioner.supported_generated_artifact_delivery_modes == frozenset({GeneratedArtifactDeliveryMode.MOUNT})


def test_generated_artifact_capability_requires_explicit_kind_support():
    manifest = create_stub_manifest()
    provisioner = manifest.provisioner
    empty_kinds: frozenset[str] = frozenset()
    rendered_config_kinds = frozenset({"rendered_config"})

    with pytest.raises(ValueError, match="must declare supported_generated_artifact_kinds"):
        replace(provisioner, supported_generated_artifact_kinds=empty_kinds)

    with pytest.raises(ValueError, match="require supports_generated_artifacts=True"):
        replace(
            provisioner,
            supports_generated_artifacts=False,
            supported_generated_artifact_kinds=rendered_config_kinds,
        )


def test_backend_manifest_v2_rejects_contradictory_generated_artifact_capabilities():
    payload = backend_manifest_payload(create_stub_manifest())
    provisioner = payload["capabilities"]["provisioner"]

    provisioner["supported_generated_artifact_kinds"] = []
    with pytest.raises(ValidationError, match="must declare supported_generated_artifact_kinds"):
        BackendManifestV2Model.model_validate(payload)

    provisioner["supports_generated_artifacts"] = False
    provisioner["supported_generated_artifact_kinds"] = ["rendered_config"]
    with pytest.raises(ValidationError, match="require supports_generated_artifacts=true"):
        BackendManifestV2Model.model_validate(payload)


@pytest.mark.parametrize(
    ("support_flag", "supported_values"),
    [
        ("supports_accounts", "supported_account_features"),
        ("supports_generated_artifacts", "supported_generated_artifact_kinds"),
    ],
)
def test_backend_manifest_schema_requires_true_support_flag_for_nonempty_supported_values(
    support_flag: str,
    supported_values: str,
) -> None:
    schema = BackendManifestV2Model.model_json_schema()
    payload = backend_manifest_payload(create_stub_manifest())
    provisioner = payload["capabilities"]["provisioner"]
    provisioner.pop(support_flag)
    validator = Draft202012Validator(schema)

    with pytest.raises(JSONSchemaValidationError):
        validator.validate(payload)
    with pytest.raises(ValidationError):
        BackendManifestV2Model.model_validate(payload)

    provisioner[supported_values] = []
    if support_flag == "supports_generated_artifacts":
        # supports_generated_artifacts also gates the delivery-mode list; clear it
        # too so the otherwise-consistent payload validates.
        provisioner["supported_generated_artifact_delivery_modes"] = []
    validator.validate(payload)
    BackendManifestV2Model.model_validate(payload)


def test_coordinated_reset_manifest_claim_requires_participant_runtime_capabilities():
    manifest = create_stub_manifest(with_time=True, with_participant_runtime=False)
    assert manifest.time is not None
    assert not manifest.time.supports_coordinated_participant_reset

    payload = backend_manifest_payload(create_stub_manifest(with_time=True))
    payload["capabilities"]["participant_runtime"] = None
    with pytest.raises(ValidationError, match="coordinated participant reset support"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_declares_participant_capability_dimensions():
    """API-405: participant-runtime backends must declare the participant
    roles, behavior features, and interaction features they support."""

    payload = backend_manifest_payload(create_stub_manifest())
    participant_runtime = payload["capabilities"]["participant_runtime"]

    assert participant_runtime["supported_participant_roles"] == ["blue", "green", "red", "white"]
    assert participant_runtime["supported_behavior_features"] == [
        "action_contracts",
        "attribution_support",
        "behavior_history",
        "effects",
        "failure_classes",
        "observation_boundaries",
        "outcome_interpretation",
        "preconditions",
        "state_transitions",
        "temporal_contracts",
    ]
    assert participant_runtime["supported_interaction_features"] == [
        "contention",
        "coordination",
        "interference",
        "shared_state_change",
    ]
    assert {entry["feature"]: entry["support_level"] for entry in participant_runtime["feature_support"]} == {
        feature: "unsupported" for feature in sorted(PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES)
    }
    assert all(entry["limitation_refs"] for entry in participant_runtime["feature_support"])
    assert all(entry["disclosure_refs"] for entry in participant_runtime["feature_support"])
    assert participant_runtime["supports_autonomous_execution"] is False
    assert participant_runtime["supported_autonomous_action_contracts"] == []
    assert participant_runtime["supported_autonomous_observation_boundaries"] == []
    assert participant_runtime["supported_autonomous_selection_strategies"] == []
    assert participant_runtime["supported_autonomous_target_addresses"] == []
    assert participant_runtime["max_autonomous_participants"] is None
    assert participant_runtime["max_autonomous_action_attempts"] is None
    assert participant_runtime["max_autonomous_in_flight"] is None

    model = BackendManifestV2Model.model_validate(payload)
    assert model.capabilities.participant_runtime is not None
    assert model.capabilities.participant_runtime.supported_participant_roles == [
        "blue",
        "green",
        "red",
        "white",
    ]


def test_backend_manifest_v2_declares_observation_capability_dimensions():
    """EXP-715: observation and evidence-collection support is a separate
    backend capability block, not an execution or evaluator side effect."""

    payload = backend_manifest_payload(create_stub_manifest())
    observation = payload["capabilities"]["observation"]

    assert observation["supported_capture_kinds"] == [
        "artifact",
        "log",
        "observation",
        "packet-capture",
        "telemetry",
        "trace",
    ]
    assert observation["supported_channel_kinds"] == [
        "backend-log",
        "evaluation-history",
        "file-artifact",
        "packet-capture",
        "participant-observation",
        "runtime-snapshot",
        "workflow-history",
    ]
    assert observation["supported_evidence_contracts"] == [
        "experiment-capture-spec-v1",
        "experiment-derived-measure-v1",
        "experiment-evidence-record-v1",
        "experiment-run-v1",
    ]
    assert observation["supported_sealing_modes"] == ["digest", "immutable-store"]
    assert observation["supports_redaction"] is True
    assert observation["supports_loss_disclosure"] is True

    model = BackendManifestV2Model.model_validate(payload)
    assert model.capabilities.observation is not None
    assert model.capabilities.observation.supported_capture_kinds == [
        "artifact",
        "log",
        "observation",
        "packet-capture",
        "telemetry",
        "trace",
    ]


def test_backend_manifest_without_participant_runtime_declares_no_participant_runtime_surface():
    payload = backend_manifest_payload(create_stub_manifest(with_participant_runtime=False))

    assert payload["capabilities"]["participant_runtime"] is None
    model = BackendManifestV2Model.model_validate(payload)
    assert model.capabilities.participant_runtime is None


def test_backend_manifest_without_observation_declares_no_observation_surface():
    payload = backend_manifest_payload(create_stub_manifest(with_observation=False))

    assert payload["capabilities"]["observation"] is None
    model = BackendManifestV2Model.model_validate(payload)
    assert model.capabilities.observation is None


def test_observation_capabilities_validate_exp_715_vocabularies():
    capability = ObservationCapabilities(
        name="observation",
        supported_capture_kinds=frozenset({"observation", "x-acme:custom-capture"}),
        supported_channel_kinds=frozenset({"participant-observation", "x-acme:custom-channel"}),
        supported_evidence_contracts=frozenset({"experiment-evidence-record-v1"}),
        supported_media_types=frozenset({"application/json"}),
        supported_sealing_modes=frozenset({"digest", "x-acme:attested-store"}),
        supports_redaction=True,
        supports_loss_disclosure=True,
    )

    assert "x-acme:custom-capture" in capability.supported_capture_kinds
    assert "x-acme:custom-channel" in capability.supported_channel_kinds
    assert "x-acme:attested-store" in capability.supported_sealing_modes

    with pytest.raises(ValueError, match="observation-capture-kinds"):
        ObservationCapabilities(
            name="observation",
            supported_capture_kinds=frozenset({"custom_capture"}),
            supported_channel_kinds=frozenset({"participant-observation"}),
            supported_evidence_contracts=frozenset({"experiment-evidence-record-v1"}),
            supported_media_types=frozenset({"application/json"}),
            supported_sealing_modes=frozenset({"digest"}),
        )


def test_observation_capability_claims_require_published_contract_evidence():
    manifest = create_stub_manifest()
    weak_manifest = BackendManifest(
        identity=manifest.identity,
        supported_contract_versions=manifest.supported_contract_versions - frozenset({"experiment-evidence-record-v1"}),
        compatibility=manifest.compatibility,
        realization_support=manifest.realization_support,
        concept_bindings=manifest.concept_bindings,
        constraints=manifest.constraints,
        capabilities=manifest.capabilities,
        realization_envelope=manifest.realization_envelope,
    )

    assert observation_capability_contract_gaps(manifest) == ()
    gaps = observation_capability_contract_gaps(weak_manifest)
    assert any("experiment-evidence-record-v1" in gap for gap in gaps)


@pytest.mark.parametrize(
    "field_name",
    [
        "supported_participant_roles",
        "supported_behavior_features",
        "supported_interaction_features",
    ],
)
def test_backend_manifest_v2_rejects_participant_runtime_without_api_405_declarations(field_name: str):
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["capabilities"]["participant_runtime"].pop(field_name, None)

    with pytest.raises(ValidationError, match=field_name):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_duplicate_api_405_declarations():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["capabilities"]["participant_runtime"]["supported_participant_roles"].append("blue")

    with pytest.raises(ValidationError, match="duplicate"):
        BackendManifestV2Model.model_validate(payload)


def test_participant_runtime_capabilities_validate_api_405_vocabularies():
    capability = ParticipantRuntimeCapabilities(
        name="participant-runtime",
        supported_participant_roles=frozenset({"blue", "x-acme:observer"}),
        supported_behavior_features=frozenset({"action_contracts", "x-acme:custom-feature"}),
        supported_interaction_features=frozenset({"coordination", "x-acme:custom-interaction"}),
    )

    assert "x-acme:observer" in capability.supported_participant_roles
    assert "x-acme:custom-feature" in capability.supported_behavior_features
    assert "x-acme:custom-interaction" in capability.supported_interaction_features

    with pytest.raises(ValueError, match="participant-runtime-behavior-features"):
        ParticipantRuntimeCapabilities(
            name="participant-runtime",
            supported_participant_roles=frozenset({"blue"}),
            supported_behavior_features=frozenset({"custom_feature"}),
            supported_interaction_features=frozenset({"coordination"}),
        )


def test_participant_feature_support_validates_api_407_declarations():
    declaration = ParticipantFeatureSupport(
        feature="coordination",
        support_level=ParticipantFeatureSupportLevel.EXACT,
    )

    assert declaration.support_level == ParticipantFeatureSupportLevel.EXACT

    with pytest.raises(ValueError, match="governed participant behavior or interaction feature"):
        ParticipantFeatureSupport(
            feature="custom_feature",
            support_level=ParticipantFeatureSupportLevel.EXACT,
        )

    with pytest.raises(ValueError, match="disclosure_refs"):
        ParticipantFeatureSupport(
            feature="coordination",
            support_level=ParticipantFeatureSupportLevel.BOUNDED,
        )

    unsupported_declaration = ParticipantFeatureSupport(
        feature="coordination",
        support_level=ParticipantFeatureSupportLevel.UNSUPPORTED,
        disclosure_refs=("disclosures.coordination.unsupported.v1",),
    )
    with pytest.raises(ValueError, match="supported feature unsupported"):
        ParticipantRuntimeCapabilities(
            name="participant-runtime",
            supported_participant_roles=frozenset({"blue"}),
            supported_behavior_features=frozenset({"action_contracts"}),
            supported_interaction_features=frozenset({"coordination"}),
            feature_support=(unsupported_declaration,),
        )


def test_backend_manifest_payload_renders_api_407_feature_support_entries():
    manifest = create_stub_manifest()
    assert manifest.participant_runtime is not None
    participant_runtime = replace(
        manifest.participant_runtime,
        feature_support=(
            ParticipantFeatureSupport(
                feature="behavior_history",
                support_level=ParticipantFeatureSupportLevel.BOUNDED,
                constraint_refs=("constraints.behavior-history.retention-window",),
                disclosure_refs=("disclosures.behavior-history.bounded.v1",),
            ),
            ParticipantFeatureSupport(
                feature="coordination",
                support_level=ParticipantFeatureSupportLevel.EXACT,
            ),
        ),
    )
    capabilities = replace(manifest.capabilities, participant_runtime=participant_runtime)
    manifest = BackendManifest(
        identity=manifest.identity,
        supported_contract_versions=manifest.supported_contract_versions,
        compatibility=manifest.compatibility,
        realization_support=manifest.realization_support,
        concept_bindings=manifest.concept_bindings,
        constraints=manifest.constraints,
        capabilities=capabilities,
        realization_envelope=manifest.realization_envelope,
    )

    payload = backend_manifest_payload(manifest)

    assert payload["capabilities"]["participant_runtime"]["feature_support"] == [
        {
            "feature": "behavior_history",
            "support_level": "bounded",
            "constraint_refs": ["constraints.behavior-history.retention-window"],
            "limitation_refs": [],
            "disclosure_refs": ["disclosures.behavior-history.bounded.v1"],
            "evidence_refs": [],
        },
        {
            "feature": "coordination",
            "support_level": "exact",
            "constraint_refs": [],
            "limitation_refs": [],
            "disclosure_refs": [],
            "evidence_refs": [],
        },
    ]
    BackendManifestV2Model.model_validate(payload)


def test_participant_runtime_capability_evidence_covers_standard_vocabularies():
    catalog_path = FIXTURES_ROOT / "concept-authority" / "controlled-vocabularies-v1" / "valid" / "reference.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    terms_by_scope = {
        scope: set(definition["terms"])
        for definition in catalog["vocabularies"].values()
        for scope in definition.get("governed_scopes", ())
        if scope.startswith("capabilities.participant_runtime.")
    }

    assert (
        set(PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[PARTICIPANT_RUNTIME_ROLE_SCOPE])
        == terms_by_scope[PARTICIPANT_RUNTIME_ROLE_SCOPE]
    )
    assert (
        set(PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE])
        == terms_by_scope[PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE]
    )
    assert (
        set(PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE])
        == terms_by_scope[PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE]
    )
    assert terms_by_scope[PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE] >= PARTICIPANT_RUNTIME_POLICY_FEATURES
    for feature in PARTICIPANT_RUNTIME_POLICY_FEATURES:
        assert PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE][feature]


def test_observation_capability_evidence_covers_standard_vocabularies():
    catalog_path = FIXTURES_ROOT / "concept-authority" / "controlled-vocabularies-v1" / "valid" / "reference.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    terms_by_scope = {
        scope: set(definition["terms"])
        for definition in catalog["vocabularies"].values()
        for scope in definition.get("governed_scopes", ())
        if scope.startswith("capabilities.observation.")
    }

    assert set(terms_by_scope) == {
        OBSERVATION_CAPABILITY_CAPTURE_KIND_SCOPE,
        OBSERVATION_CAPABILITY_CHANNEL_KIND_SCOPE,
        OBSERVATION_CAPABILITY_SEALING_MODE_SCOPE,
    }
    capability = ObservationCapabilities(
        name="observation",
        supported_capture_kinds=frozenset(terms_by_scope[OBSERVATION_CAPABILITY_CAPTURE_KIND_SCOPE]),
        supported_channel_kinds=frozenset(terms_by_scope[OBSERVATION_CAPABILITY_CHANNEL_KIND_SCOPE]),
        supported_evidence_contracts=frozenset({"experiment-evidence-record-v1"}),
        supported_media_types=frozenset({"application/json"}),
        supported_sealing_modes=frozenset(terms_by_scope[OBSERVATION_CAPABILITY_SEALING_MODE_SCOPE]),
    )
    assert capability.supported_capture_kinds == terms_by_scope[OBSERVATION_CAPABILITY_CAPTURE_KIND_SCOPE]
    assert capability.supported_channel_kinds == terms_by_scope[OBSERVATION_CAPABILITY_CHANNEL_KIND_SCOPE]
    assert capability.supported_sealing_modes == terms_by_scope[OBSERVATION_CAPABILITY_SEALING_MODE_SCOPE]


def test_participant_runtime_capability_claims_require_published_contract_evidence():
    manifest = create_stub_manifest()
    weak_manifest = BackendManifest(
        identity=manifest.identity,
        supported_contract_versions=manifest.supported_contract_versions
        - frozenset({"participant-behavior-history-event-stream-v1"}),
        compatibility=manifest.compatibility,
        realization_support=manifest.realization_support,
        concept_bindings=manifest.concept_bindings,
        constraints=manifest.constraints,
        capabilities=manifest.capabilities,
        realization_envelope=manifest.realization_envelope,
    )

    assert participant_runtime_capability_contract_gaps(manifest) == ()
    gaps = participant_runtime_capability_contract_gaps(weak_manifest)
    assert any("supported_behavior_features.action_contracts" in gap for gap in gaps)
    assert any("supported_interaction_features.coordination" in gap for gap in gaps)


def _stub_payload_with_feature_support(entries: list[dict]) -> dict:
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["capabilities"]["participant_runtime"]["feature_support"] = entries
    return payload


def test_backend_manifest_v2_accepts_feature_support_declarations():
    """API-407: per-feature support declarations carry governed terms and levels."""

    payload = json.loads((V2_VALID_DIR / "feature-support-bounded.json").read_text(encoding="utf-8"))
    model = BackendManifestV2Model.model_validate(payload)

    assert model.capabilities.participant_runtime is not None
    feature_support = model.capabilities.participant_runtime.feature_support
    assert [entry.feature for entry in feature_support] == [
        "behavior_history",
        "coordination",
        "participant_transformation",
        "x-acme:custom-feature",
    ]
    assert feature_support[0].support_level == ParticipantFeatureSupportLevel.BOUNDED
    assert feature_support[0].disclosure_refs == ["disclosures.behavior-history.bounded.v1"]
    assert feature_support[2].evidence_refs == ["conformance:participant-transformation:bounded-case-1"]
    assert feature_support[3].support_level == ParticipantFeatureSupportLevel.DISCLOSED_WEAK


def test_backend_manifest_v2_accepts_evidence_backed_participant_policy_support():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "participant_ingress_admission",
                "support_level": "exact",
                "constraint_refs": [],
                "limitation_refs": [],
                "disclosure_refs": [],
                "evidence_refs": ["conformance:participant-ingress-admission:case-1"],
            }
        ]
    )
    participant_runtime = payload["capabilities"]["participant_runtime"]
    participant_runtime["supported_behavior_features"].append("participant_ingress_admission")

    model = BackendManifestV2Model.model_validate(payload)

    assert model.capabilities.participant_runtime is not None
    declaration = model.capabilities.participant_runtime.feature_support[0]
    assert declaration.feature == "participant_ingress_admission"
    assert declaration.evidence_refs == ["conformance:participant-ingress-admission:case-1"]


def test_backend_manifest_v2_rejects_positive_participant_policy_support_without_evidence():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "participant_ingress_admission",
                "support_level": "exact",
                "constraint_refs": [],
                "limitation_refs": [],
                "disclosure_refs": [],
                "evidence_refs": [],
            }
        ]
    )
    payload["capabilities"]["participant_runtime"]["supported_behavior_features"].append(
        "participant_ingress_admission"
    )

    with pytest.raises(ValidationError, match="evidence_refs"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_bounded_policy_support_without_constraints():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "participant_transformation",
                "support_level": "bounded",
                "constraint_refs": [],
                "limitation_refs": ["limitation:participant-transformation:finite-rules"],
                "disclosure_refs": ["disclosure:participant-transformation:bounded"],
                "evidence_refs": ["conformance:participant-transformation:case-1"],
            }
        ]
    )
    payload["capabilities"]["participant_runtime"]["supported_behavior_features"].append("participant_transformation")

    with pytest.raises(ValidationError, match="constraint_refs"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_weak_policy_support_without_limitations():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "participant_declassification",
                "support_level": "disclosed_weak",
                "constraint_refs": [],
                "limitation_refs": [],
                "disclosure_refs": ["disclosure:participant-declassification:weak"],
                "evidence_refs": ["conformance:participant-declassification:case-1"],
            }
        ]
    )
    payload["capabilities"]["participant_runtime"]["supported_behavior_features"].append("participant_declassification")

    with pytest.raises(ValidationError, match="limitation_refs"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_positive_participant_policy_support_without_required_contracts():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "participant_intervention",
                "support_level": "bounded",
                "constraint_refs": ["constraint:participant-intervention:bounded"],
                "limitation_refs": ["limitation:participant-intervention:finite-scope"],
                "disclosure_refs": ["disclosure:participant-intervention:bounded"],
                "evidence_refs": ["conformance:participant-intervention:case-1"],
            }
        ]
    )
    payload["capabilities"]["participant_runtime"]["supported_behavior_features"].append("participant_intervention")
    payload["supported_contract_versions"].remove("participant-control-occurrence-v1")

    with pytest.raises(ValidationError, match="required contracts"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_positive_policy_support_absent_from_supported_features():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "participant_egress_projection",
                "support_level": "exact",
                "constraint_refs": [],
                "limitation_refs": [],
                "disclosure_refs": [],
                "evidence_refs": ["conformance:participant-egress-projection:case-1"],
            }
        ]
    )
    with pytest.raises(ValidationError, match="positive support"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_supported_policy_feature_without_strength_declaration():
    payload = _stub_payload_with_feature_support([])
    payload["capabilities"]["participant_runtime"]["supported_behavior_features"].append(
        "participant_ingress_admission"
    )

    with pytest.raises(ValidationError, match="require explicit feature_support declarations"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_accepts_honest_unsupported_policy_features():
    entries = [
        {
            "feature": feature,
            "support_level": "unsupported",
            "constraint_refs": [],
            "limitation_refs": [f"limitation:{feature}:not-realized"],
            "disclosure_refs": [f"disclosure:{feature}:unsupported"],
            "evidence_refs": [],
        }
        for feature in sorted(PARTICIPANT_RUNTIME_POLICY_FEATURES)
    ]

    model = BackendManifestV2Model.model_validate(_stub_payload_with_feature_support(entries))

    assert model.capabilities.participant_runtime is not None
    assert {entry.feature for entry in model.capabilities.participant_runtime.feature_support} == set(
        PARTICIPANT_RUNTIME_POLICY_FEATURES
    )
    assert all(
        entry.support_level == ParticipantFeatureSupportLevel.UNSUPPORTED
        for entry in model.capabilities.participant_runtime.feature_support
    )


def test_participant_policy_feature_support_admission_fails_closed_and_demotes_authorized_downgrade():
    base = create_stub_manifest()
    feature = "participant_transformation"
    declaration = ParticipantFeatureSupport(
        feature=feature,
        support_level=ParticipantFeatureSupportLevel.BOUNDED,
        constraint_refs=("constraint:participant-transformation:bounded",),
        limitation_refs=("limitation:participant-transformation:finite-rules",),
        disclosure_refs=("disclosure:participant-transformation:bounded",),
        evidence_refs=("conformance:participant-transformation:case-1",),
    )
    participant_runtime = replace(
        base.participant_runtime,
        supported_behavior_features=base.participant_runtime.supported_behavior_features | {feature},
        feature_support=(declaration,),
    )
    manifest = BackendManifest(
        identity=base.identity,
        supported_contract_versions=base.supported_contract_versions | {"participant-crossing-occurrence-v1"},
        compatibility=base.compatibility,
        realization_support=base.realization_support,
        concept_bindings=base.concept_bindings,
        constraints=base.constraints,
        capabilities=replace(base.capabilities, participant_runtime=participant_runtime),
        realization_envelope=base.realization_envelope,
    )

    assert participant_feature_support_gaps(manifest, (feature,)) == (
        "participant feature 'participant_transformation' requires exact support; backend declares bounded",
    )
    with pytest.raises(ValueError, match="explicit downgrade authorization"):
        resolve_participant_feature_support(
            manifest,
            feature,
            required_level=ParticipantFeatureSupportLevel.EXACT,
            allowed_downgrade_level=ParticipantFeatureSupportLevel.BOUNDED,
        )

    effective = resolve_participant_feature_support(
        manifest,
        feature,
        required_level=ParticipantFeatureSupportLevel.EXACT,
        allowed_downgrade_level=ParticipantFeatureSupportLevel.BOUNDED,
        downgrade_policy_ref="policy:participant-crossing:revision-3",
        downgrade_provenance_ref="provenance:participant-crossing:decision-7",
    )

    assert effective is declaration
    assert effective.support_level == ParticipantFeatureSupportLevel.BOUNDED
    assert effective.support_level != ParticipantFeatureSupportLevel.EXACT


def test_participant_policy_feature_support_admission_accepts_evidence_backed_exact_support():
    base = create_stub_manifest()
    assert base.participant_runtime is not None
    feature = "participant_ingress_admission"
    declaration = ParticipantFeatureSupport(
        feature=feature,
        support_level=ParticipantFeatureSupportLevel.EXACT,
        evidence_refs=("conformance:participant-ingress-admission:case-1",),
    )
    manifest = replace(
        base,
        capabilities=replace(
            base.capabilities,
            participant_runtime=replace(
                base.participant_runtime,
                supported_behavior_features=base.participant_runtime.supported_behavior_features | {feature},
                feature_support=(declaration,),
            ),
        ),
    )

    assert resolve_participant_feature_support(manifest, feature) is declaration
    assert participant_feature_support_gaps(manifest, (feature,)) == ()


def test_participant_policy_feature_support_admission_rejects_missing_declaration():
    base = create_stub_manifest()
    assert base.participant_runtime is not None
    manifest = replace(
        base,
        capabilities=replace(
            base.capabilities,
            participant_runtime=replace(base.participant_runtime, feature_support=()),
        ),
    )

    assert participant_feature_support_gaps(manifest, ("participant_ingress_admission",)) == (
        "participant feature 'participant_ingress_admission' has no explicit support declaration",
    )


def test_backend_manifest_v2_feature_support_defaults_to_empty():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["capabilities"]["participant_runtime"].pop("feature_support")
    model = BackendManifestV2Model.model_validate(payload)

    assert model.capabilities.participant_runtime is not None
    assert model.capabilities.participant_runtime.feature_support == []


def test_backend_manifest_v2_accepts_exact_feature_support_without_disclosure():
    payload = _stub_payload_with_feature_support(
        [{"feature": "coordination", "support_level": "exact", "constraint_refs": [], "disclosure_refs": []}]
    )
    model = BackendManifestV2Model.model_validate(payload)

    assert model.capabilities.participant_runtime is not None
    assert model.capabilities.participant_runtime.feature_support[0].support_level == (
        ParticipantFeatureSupportLevel.EXACT
    )


def test_backend_manifest_v2_accepts_unsupported_feature_support_for_undeclared_feature():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "x-acme:custom-feature",
                "support_level": "unsupported",
                "constraint_refs": [],
                "disclosure_refs": ["disclosures.acme.custom-feature.unsupported.v1"],
            }
        ]
    )
    model = BackendManifestV2Model.model_validate(payload)

    assert model.capabilities.participant_runtime is not None
    assert model.capabilities.participant_runtime.feature_support[0].support_level == (
        ParticipantFeatureSupportLevel.UNSUPPORTED
    )


def test_backend_manifest_v2_rejects_unguarded_feature_support_terms():
    payload = _stub_payload_with_feature_support(
        [{"feature": "custom-feature", "support_level": "exact", "constraint_refs": [], "disclosure_refs": []}]
    )

    with pytest.raises(ValidationError, match="not a governed term"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_unknown_feature_support_levels():
    payload = _stub_payload_with_feature_support(
        [{"feature": "coordination", "support_level": "partial", "constraint_refs": [], "disclosure_refs": []}]
    )

    with pytest.raises(ValidationError, match="support_level"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_duplicate_feature_support_features():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "coordination",
                "support_level": "bounded",
                "constraint_refs": [],
                "disclosure_refs": ["disclosures.coordination.bounded.v1"],
            },
            {"feature": "coordination", "support_level": "exact", "constraint_refs": [], "disclosure_refs": []},
        ]
    )

    with pytest.raises(ValidationError, match="duplicate"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_unsupported_feature_support_for_declared_feature():
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "behavior_history",
                "support_level": "unsupported",
                "constraint_refs": [],
                "disclosure_refs": ["disclosures.behavior-history.unsupported.v1"],
            }
        ]
    )

    with pytest.raises(ValidationError, match="declares support_level 'unsupported'"):
        BackendManifestV2Model.model_validate(payload)


@pytest.mark.parametrize("support_level", ["unsupported", "disclosed_weak", "bounded"])
def test_backend_manifest_v2_rejects_below_exact_feature_support_without_disclosure(support_level: str):
    payload = _stub_payload_with_feature_support(
        [
            {
                "feature": "x-acme:custom-feature",
                "support_level": support_level,
                "constraint_refs": [],
                "disclosure_refs": [],
            }
        ]
    )

    with pytest.raises(ValidationError, match="disclosure_refs"):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_schema_publishes_feature_support_disclosure_rule():
    from raes_contracts.contracts import schema_bundle

    schema = schema_bundle()["backend-manifest-v2"]
    feature_support_schema = schema["$defs"]["ParticipantFeatureSupportModel"]

    assert feature_support_schema["additionalProperties"] is False
    assert feature_support_schema["properties"]["support_level"]["$ref"] == "#/$defs/ParticipantFeatureSupportLevel"
    assert schema["$defs"]["ParticipantFeatureSupportLevel"]["enum"] == [
        "unsupported",
        "disclosed_weak",
        "bounded",
        "exact",
    ]
    assert {
        "if": {
            "properties": {"support_level": {"enum": ["unsupported", "disclosed_weak", "bounded"]}},
            "required": ["support_level"],
        },
        "then": {
            "required": ["disclosure_refs"],
            "properties": {"disclosure_refs": {"minItems": 1}},
        },
    } in feature_support_schema["allOf"]
    assert {"limitation_refs", "evidence_refs"} <= feature_support_schema["properties"].keys()
    assert any(
        condition.get("then", {}).get("properties", {}).get("limitation_refs", {}).get("minItems") == 1
        for condition in feature_support_schema["allOf"]
    )
    assert any(
        condition.get("then", {}).get("properties", {}).get("constraint_refs", {}).get("minItems") == 1
        for condition in feature_support_schema["allOf"]
    )
    assert any(
        condition.get("then", {}).get("properties", {}).get("evidence_refs", {}).get("minItems") == 1
        for condition in feature_support_schema["allOf"]
    )


def test_backend_manifest_v2_requires_manifest_sections():
    with pytest.raises(ValidationError):
        BackendManifestV2Model(
            identity={"name": "stub", "version": "0.0.1"},
            capabilities={
                "provisioner": {
                    "name": "stub-provisioner",
                }
            },
        )


def test_backend_manifest_runtime_rejects_unknown_supported_contract_versions():
    with pytest.raises(ValueError, match="supported_contract_versions"):
        BackendManifest(
            name="bad",
            version="0.0.1",
            supported_contract_versions=frozenset({"semantic-profile-v1"}),
            compatible_processors=frozenset({"raes-reference-processor"}),
            realization_support=create_stub_manifest().realization_support,
            concept_bindings=create_stub_manifest().concept_bindings,
            provisioner=ProvisionerCapabilities(
                name="stub-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
        )


def test_backend_manifest_v2_rejects_empty_compatibility():
    with pytest.raises(ValidationError) as excinfo:
        BackendManifestV2Model.model_validate(
            {
                "schema_version": "backend-manifest/v2",
                "identity": {"name": "stub", "version": "0.0.1"},
                "supported_contract_versions": ["backend-manifest-v2"],
                "compatibility": {},
                "realization_support": [
                    {
                        "domain": "runtime-realization",
                        "support_mode": "constrained",
                        "supported_constraint_kinds": ["node-type"],
                        "disclosure_kinds": ["runtime-snapshot-v1"],
                    }
                ],
                "concept_bindings": [
                    {"scope": "capabilities.provisioner.supported_node_types", "family": "assets"},
                    {"scope": "capabilities.provisioner.supported_os_families", "family": "assets"},
                ],
                "capabilities": {
                    "provisioner": {
                        "name": "stub-provisioner",
                        "supported_node_types": ["compute"],
                        "supported_os_families": ["linux"],
                    }
                },
            }
        )
    assert "compatibility.processors" in str(excinfo.value)


def test_backend_manifest_v2_rejects_non_processor_compatibility_surfaces():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["compatibility"] = {
        "processors": ["raes-reference-processor"],
        "backends": ["peer-backend"],
    }

    with pytest.raises(ValidationError):
        BackendManifestV2Model.model_validate(payload)

    payload["compatibility"] = {
        "processors": ["raes-reference-processor"],
        "participant_implementations": ["participant-impl"],
    }

    with pytest.raises(ValidationError):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_hollow_realization_support():
    with pytest.raises(ValidationError) as excinfo:
        BackendManifestV2Model.model_validate(
            {
                "schema_version": "backend-manifest/v2",
                "identity": {"name": "stub", "version": "0.0.1"},
                "supported_contract_versions": ["backend-manifest-v2"],
                "compatibility": {"processors": ["raes-reference-processor"]},
                "realization_support": [
                    {
                        "domain": "runtime-realization",
                        "support_mode": "constrained",
                        "disclosure_kinds": ["runtime-snapshot-v1"],
                    }
                ],
                "concept_bindings": [
                    {"scope": "capabilities.provisioner.supported_node_types", "family": "assets"},
                    {"scope": "capabilities.provisioner.supported_os_families", "family": "assets"},
                ],
                "capabilities": {
                    "provisioner": {
                        "name": "stub-provisioner",
                        "supported_node_types": ["compute"],
                        "supported_os_families": ["linux"],
                    }
                },
            }
        )
    assert "supported_constraint_kinds" in str(excinfo.value)


def test_backend_manifest_v2_rejects_hollow_capability_blocks():
    with pytest.raises(ValidationError) as excinfo:
        BackendManifestV2Model.model_validate(
            {
                "schema_version": "backend-manifest/v2",
                "identity": {"name": "stub", "version": "0.0.1"},
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
                "concept_bindings": [
                    {"scope": "capabilities.provisioner.supported_node_types", "family": "assets"},
                    {"scope": "capabilities.provisioner.supported_os_families", "family": "assets"},
                ],
                "capabilities": {
                    "provisioner": {
                        "name": "stub-provisioner",
                    }
                },
            }
        )
    assert "supported_node_types" in str(excinfo.value)


def test_reference_backend_v2_fixture_matches_emitted_manifest():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    emitted = backend_manifest_payload(create_stub_manifest())
    # identity.version is the live raes distribution version (the committed
    # __version__ literal, #684), which is bumped every release and is not pinned
    # to the fixture's example version. Normalize it before the structural
    # comparison; a non-empty real version is asserted elsewhere.
    assert emitted["identity"]["version"]
    emitted = {**emitted, "identity": {**emitted["identity"], "version": payload["identity"]["version"]}}
    assert payload == emitted


def test_backend_manifest_valid_fixtures_pass_validation():
    for path in sorted(V2_VALID_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        model = BackendManifestV2Model.model_validate(payload)
        assert model.identity.name, f"Valid v2 fixture {path.name} should have a name"


def test_backend_manifest_invalid_fixtures_fail_validation():
    for path in sorted(V2_INVALID_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        with pytest.raises(ValidationError):
            BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_requires_concept_bindings():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    del payload["concept_bindings"]
    with pytest.raises(ValidationError):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_rejects_empty_concept_bindings():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["concept_bindings"] = []
    with pytest.raises(ValidationError):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_accepts_governed_extension_vocabulary_values():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["capabilities"]["provisioner"]["supported_node_types"].append("x-acme:bare-metal")
    payload["capabilities"]["orchestrator"]["supported_sections"].append("x-acme:custom-stage")

    model = BackendManifestV2Model.model_validate(payload)

    assert "x-acme:bare-metal" in model.capabilities.provisioner.supported_node_types
    assert "x-acme:custom-stage" in model.capabilities.orchestrator.supported_sections


def test_backend_manifest_rejects_unguarded_vocabulary_values():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["capabilities"]["provisioner"]["supported_node_types"].append("bare-metal")

    with pytest.raises(ValidationError, match="provisioner-node-types"):
        BackendManifestV2Model.model_validate(payload)


def test_runtime_capabilities_accept_governed_extension_vocabulary_values():
    provisioner = ProvisionerCapabilities(
        name="stub-provisioner",
        supported_node_types=frozenset({"compute", "x-acme:bare-metal"}),
        supported_os_families=frozenset({"linux"}),
    )
    orchestrator = OrchestratorCapabilities(
        name="stub-orchestrator",
        supported_sections=frozenset({"events", "scripts", "workflows", "x-acme:custom-stage"}),
        supports_workflows=True,
        supported_workflow_features=frozenset({WorkflowFeature.DECISION}),
    )

    assert "x-acme:bare-metal" in provisioner.supported_node_types
    assert "x-acme:custom-stage" in orchestrator.supported_sections


def test_runtime_capabilities_reject_unguarded_vocabulary_values():
    with pytest.raises(ValueError, match="provisioner-node-types"):
        ProvisionerCapabilities(
            name="stub-provisioner",
            supported_node_types=frozenset({"compute", "bare-metal"}),
            supported_os_families=frozenset({"linux"}),
        )


def test_backend_manifest_v2_rejects_duplicate_binding_scopes():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    payload["concept_bindings"] = [
        {"scope": "capabilities.provisioner.supported_node_types", "family": "assets"},
        {"scope": "capabilities.provisioner.supported_node_types", "family": "identities"},
    ]
    with pytest.raises(ValidationError):
        BackendManifestV2Model.model_validate(payload)


def test_backend_manifest_v2_concept_bindings_roundtrip():
    payload = json.loads((V2_VALID_DIR / "stub.json").read_text(encoding="utf-8"))
    model = BackendManifestV2Model.model_validate(payload)
    assert len(model.concept_bindings) == 15
    assert model.concept_bindings[0].scope == "capabilities.provisioner.supported_node_types"
    assert model.concept_bindings[0].family == "assets"
