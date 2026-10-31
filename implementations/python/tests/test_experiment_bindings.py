"""Authoritative cross-plane experiment binding contract tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_conformance.conformance import _validate_payload
from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts import (
    BackendManifestV2Model,
    ConfigurationTargetDeclarationModel,
    ExperimentBindingDescriptorSetModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    LiteralBindingValueModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationProvenanceModel,
    ParticipantImplementationSelectionModel,
    ProcessorManifestV2Model,
    RealizedBindingProvenanceModel,
)
from raes_contracts.contracts.participant_configuration import (
    ConfigurationOverrideModel,
    realize_participant_configuration,
    validate_participant_configuration_selection,
)
from raes_contracts.experiment_bindings import (
    ExperimentBindingTargetError,
    ScenarioBindingResolution,
    validate_experiment_binding_targets,
)
from raes_schemas import schema_bundle

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PARTICIPANT_MANIFEST_FIXTURE = (
    _REPO_ROOT
    / "contracts"
    / "fixtures"
    / "participant-implementation-manifest"
    / "participant-implementation-manifest-v1"
    / "valid"
    / "reference.json"
)


def _scenario_binding_payload() -> dict[str, object]:
    return {
        "schema_version": "experiment-binding-descriptors/v1",
        "descriptors": [
            {
                "binding_id": "binding.worker-count",
                "source_factor_id": "factor.worker-count",
                "source_factor_level_id": "four",
                "source_condition_id": "condition.four-workers",
                "target": {
                    "plane": "scenario",
                    "scenario_family_id": "family.techvault",
                    "variation_point_id": "variation.worker-count",
                    "target_id": "variables.worker_count",
                },
                "value_type": "integer",
                "value": {"kind": "literal", "value": 4},
                "owner": {
                    "contract_id": "sdl-authoring-input-v1",
                    "contract_version": "1",
                    "validator_id": "raes-sdl-instantiation",
                    "validator_version": "1",
                },
            }
        ],
    }


def test_binding_descriptor_preserves_explicit_source_and_plane() -> None:
    model = ExperimentBindingDescriptorSetModel.model_validate(_scenario_binding_payload())

    descriptor = model.descriptors[0]
    assert descriptor.source_factor_id == "factor.worker-count"
    assert descriptor.source_factor_level_id == "four"
    assert descriptor.source_condition_id == "condition.four-workers"
    assert descriptor.target.plane == "scenario"
    assert descriptor.target.target_id == "variables.worker_count"


@pytest.mark.parametrize("value", [True, "4", 4.0])
def test_binding_descriptor_rejects_integer_coercion(value: object) -> None:
    payload = _scenario_binding_payload()
    payload["descriptors"][0]["value"]["value"] = value  # type: ignore[index]

    with pytest.raises(ValidationError, match="value_type"):
        ExperimentBindingDescriptorSetModel.model_validate(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_binding_descriptor_rejects_non_finite_numbers(value: float) -> None:
    payload = _scenario_binding_payload()
    payload["descriptors"][0]["value_type"] = "number"  # type: ignore[index]
    payload["descriptors"][0]["value"]["value"] = value  # type: ignore[index]

    with pytest.raises(ValidationError, match="finite"):
        ExperimentBindingDescriptorSetModel.model_validate(payload)


def test_binding_descriptor_rejects_unknown_plane() -> None:
    payload = _scenario_binding_payload()
    payload["descriptors"][0]["target"]["plane"] = "backend-private"  # type: ignore[index]

    with pytest.raises(ValidationError):
        ExperimentBindingDescriptorSetModel.model_validate(payload)


def test_binding_descriptor_rejects_duplicate_canonical_target_even_when_values_match() -> None:
    payload = _scenario_binding_payload()
    duplicate = deepcopy(payload["descriptors"][0])  # type: ignore[index]
    duplicate["binding_id"] = "binding.worker-count-duplicate"
    payload["descriptors"].append(duplicate)  # type: ignore[union-attr]

    with pytest.raises(ValidationError, match="duplicate canonical target"):
        ExperimentBindingDescriptorSetModel.model_validate(payload)


def test_binding_descriptor_allows_same_target_in_mutually_exclusive_conditions() -> None:
    payload = _scenario_binding_payload()
    second = deepcopy(payload["descriptors"][0])  # type: ignore[index]
    second["binding_id"] = "binding.worker-count.two"
    second["source_factor_level_id"] = "two"
    second["source_condition_id"] = "condition.two-workers"
    second["value"]["value"] = 2
    payload["descriptors"].append(second)  # type: ignore[union-attr]

    model = ExperimentBindingDescriptorSetModel.model_validate(payload)

    assert len(model.descriptors) == 2


def test_secret_reference_is_structurally_distinct_and_has_no_resolved_value_field() -> None:
    payload = _scenario_binding_payload()
    descriptor = payload["descriptors"][0]  # type: ignore[index]
    descriptor["value_type"] = "string"
    descriptor["value"] = {
        "kind": "secret-reference",
        "reference_id": "operator-secret.techvault-password",
    }

    model = ExperimentBindingDescriptorSetModel.model_validate(payload)
    dumped = model.model_dump(mode="json")

    assert dumped["descriptors"][0]["value"] == {
        "kind": "secret-reference",
        "reference_id": "operator-secret.techvault-password",
    }
    assert "resolved_value" not in str(dumped)


def test_secret_reference_rejects_literal_or_locator_smuggling() -> None:
    payload = _scenario_binding_payload()
    descriptor = payload["descriptors"][0]  # type: ignore[index]
    descriptor["value_type"] = "string"
    descriptor["value"] = {
        "kind": "secret-reference",
        "reference_id": "operator-secret.techvault-password",
        "resolved_value": "do-not-record",
    }

    with pytest.raises(ValidationError):
        ExperimentBindingDescriptorSetModel.model_validate(payload)


@pytest.mark.parametrize("reference_id", ["/run/secrets/api-key", "../../secret", "ENV:API_KEY"])
def test_secret_reference_rejects_host_locator_shapes(reference_id: str) -> None:
    payload = _scenario_binding_payload()
    descriptor = payload["descriptors"][0]  # type: ignore[index]
    descriptor["value_type"] = "string"
    descriptor["value"] = {
        "kind": "secret-reference",
        "reference_id": reference_id,
    }

    with pytest.raises(ValidationError):
        ExperimentBindingDescriptorSetModel.model_validate(payload)


def _participant_manifest_payload() -> dict[str, object]:
    payload = json.loads(_PARTICIPANT_MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    for contract_id in ["experiment-binding-descriptors-v1", "participant-configuration-result-v1"]:
        if contract_id not in payload["supported_contract_versions"]:
            payload["supported_contract_versions"].append(contract_id)
    payload["configuration_registry"] = {
        "owner": {
            "contract_id": "participant-configuration-result-v1",
            "contract_version": "1",
            "validator_id": "reference-participant-configuration",
            "validator_version": "1",
        },
        "targets": {
            "policy.temperature": {
                "target_id": "policy.temperature",
                "value_type": "number",
                "aliases": ["temperature"],
                "allowed_value_kinds": ["literal"],
                "sensitivity": "public",
                "default": {"kind": "literal", "value": 0.25},
            },
            "policy.mode": {
                "target_id": "policy.mode",
                "value_type": "string",
                "aliases": ["mode"],
                "allowed_value_kinds": ["literal"],
                "sensitivity": "internal",
            },
            "credentials.api": {
                "target_id": "credentials.api",
                "value_type": "string",
                "aliases": [],
                "allowed_value_kinds": ["secret-reference"],
                "sensitivity": "secret",
            },
        },
    }
    return payload


def test_participant_manifest_publishes_typed_configuration_targets() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())

    assert manifest.configuration_registry is not None
    assert manifest.configuration_registry.targets["policy.temperature"].value_type == "number"
    assert manifest.configuration_registry.targets["policy.temperature"].aliases == ["temperature"]


def test_configuration_registry_rejects_alias_collision_with_canonical_target() -> None:
    payload = _participant_manifest_payload()
    payload["configuration_registry"]["targets"]["policy.temperature"]["aliases"] = ["policy.mode"]  # type: ignore[index]

    with pytest.raises(ValidationError, match="alias"):
        ParticipantImplementationManifestModel.model_validate(payload)


@pytest.mark.parametrize("aliases", [["mode", "mode"], ["policy.mode"]])
def test_configuration_target_rejects_duplicate_or_self_alias(aliases: list[str]) -> None:
    with pytest.raises(ValidationError, match="alias"):
        ConfigurationTargetDeclarationModel(
            target_id="policy.mode",
            value_type="string",
            aliases=aliases,
            allowed_value_kinds=["literal"],
            sensitivity="internal",
        )


def test_secret_configuration_target_rejects_literal_value_kind() -> None:
    with pytest.raises(ValidationError, match="admit only secret-reference"):
        ConfigurationTargetDeclarationModel(
            target_id="credentials.api",
            value_type="string",
            aliases=[],
            allowed_value_kinds=["literal", "secret-reference"],
            sensitivity="secret",
        )


def test_secret_configuration_target_rejects_portable_default() -> None:
    with pytest.raises(ValidationError, match="must not declare portable defaults"):
        ConfigurationTargetDeclarationModel(
            target_id="credentials.api",
            value_type="string",
            aliases=[],
            allowed_value_kinds=["secret-reference"],
            sensitivity="secret",
            default={"kind": "literal", "value": "plaintext"},
        )


@pytest.mark.parametrize(
    "missing_contract_id",
    ["experiment-binding-descriptors-v1", "participant-configuration-result-v1"],
)
def test_participant_configuration_registry_requires_supported_contract_ids(
    missing_contract_id: str,
) -> None:
    payload = _participant_manifest_payload()
    payload["supported_contract_versions"].remove(missing_contract_id)  # type: ignore[union-attr]

    with pytest.raises(ValidationError, match="configuration_registry requires supported_contract_versions"):
        ParticipantImplementationManifestModel.model_validate(payload)


def test_complete_participant_configuration_applies_defaults_and_alias_overrides_atomically() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())

    result = realize_participant_configuration(
        participant_address="participants.red",
        manifest=manifest,
        manifest_ref="manifests/reference-red-agent.json",
        manifest_digest="sha256:" + "1" * 64,
        overrides=[
            ConfigurationOverrideModel(
                target_id="mode",
                value={"kind": "literal", "value": "deterministic"},
            ),
            ConfigurationOverrideModel(
                target_id="credentials.api",
                value={"kind": "secret-reference", "reference_id": "operator-secret.reference-red-api"},
            ),
        ],
    )

    entries = {entry.target_id: entry for entry in result.configuration.values}
    assert entries["policy.temperature"].origin == "default"
    assert entries["policy.mode"].origin == "override"
    assert entries["credentials.api"].value.kind == "secret-reference"
    assert result.configuration_digest == canonical_contract_digest(result.configuration)
    assert "operator-secret.reference-red-api" in result.model_dump_json()
    assert "resolved" not in result.model_dump_json()


def test_participant_configuration_digest_is_independent_of_override_order_and_alias_spelling() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    common = {
        "participant_address": "participants.red",
        "manifest": manifest,
        "manifest_ref": "manifests/reference-red-agent.json",
        "manifest_digest": "sha256:" + "1" * 64,
    }
    canonical = realize_participant_configuration(
        **common,
        overrides=[
            ConfigurationOverrideModel(
                target_id="policy.mode",
                value={"kind": "literal", "value": "deterministic"},
            ),
            ConfigurationOverrideModel(
                target_id="credentials.api",
                value={"kind": "secret-reference", "reference_id": "operator-secret.reference-red-api"},
            ),
        ],
    )
    reordered_alias = realize_participant_configuration(
        **common,
        overrides=[
            ConfigurationOverrideModel(
                target_id="credentials.api",
                value={"kind": "secret-reference", "reference_id": "operator-secret.reference-red-api"},
            ),
            ConfigurationOverrideModel(
                target_id="mode",
                value={"kind": "literal", "value": "deterministic"},
            ),
        ],
    )

    assert canonical.configuration_digest == reordered_alias.configuration_digest


def test_participant_selection_joins_to_authoritative_configuration_result_digest() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    result = realize_participant_configuration(
        participant_address="participants.red",
        manifest=manifest,
        manifest_ref="manifests/reference-red-agent.json",
        manifest_digest="sha256:" + "1" * 64,
        overrides=[
            ConfigurationOverrideModel(
                target_id="mode",
                value={"kind": "literal", "value": "deterministic"},
            ),
            ConfigurationOverrideModel(
                target_id="credentials.api",
                value={"kind": "secret-reference", "reference_id": "operator-secret.reference-red-api"},
            ),
        ],
    )
    selection_payload = json.loads(
        (
            _REPO_ROOT
            / "contracts"
            / "fixtures"
            / "participant-implementation-provenance"
            / "participant-implementation-provenance-v1"
            / "valid"
            / "reference.json"
        ).read_text(encoding="utf-8")
    )["participant_implementations"][0]
    selection_payload.update(
        {
            "manifest_ref": result.manifest_ref,
            "manifest_digest": result.manifest_digest,
            "configuration_ref": "participant-configurations/red/result.json",
            "configuration_digest": result.configuration_digest,
        }
    )
    selection = ParticipantImplementationSelectionModel.model_validate(selection_payload)

    validate_participant_configuration_selection(selection, result)

    mismatched = selection.model_copy(update={"configuration_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="configuration digest"):
        validate_participant_configuration_selection(mismatched, result)


def test_participant_configuration_rejects_duplicate_canonical_override_via_alias() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    overrides = [
        ConfigurationOverrideModel(
            target_id="policy.mode",
            value={"kind": "literal", "value": "deterministic"},
        ),
        ConfigurationOverrideModel(
            target_id="mode",
            value={"kind": "literal", "value": "deterministic"},
        ),
    ]

    with pytest.raises(ValueError, match="duplicate canonical target"):
        realize_participant_configuration(
            participant_address="participants.red",
            manifest=manifest,
            manifest_ref="manifests/reference-red-agent.json",
            manifest_digest="sha256:" + "1" * 64,
            overrides=overrides,
        )


def test_participant_configuration_rejects_missing_required_target_without_partial_result() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())

    with pytest.raises(ValueError, match="required configuration target"):
        realize_participant_configuration(
            participant_address="participants.red",
            manifest=manifest,
            manifest_ref="manifests/reference-red-agent.json",
            manifest_digest="sha256:" + "1" * 64,
            overrides=[],
        )


def test_participant_configuration_rejects_type_coercion() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    overrides = [
        ConfigurationOverrideModel(
            target_id="policy.mode",
            value={"kind": "literal", "value": "deterministic"},
        ),
        ConfigurationOverrideModel(
            target_id="temperature",
            value={"kind": "literal", "value": "0.5"},
        ),
        ConfigurationOverrideModel(
            target_id="credentials.api",
            value={"kind": "secret-reference", "reference_id": "operator-secret.reference-red-api"},
        ),
    ]

    with pytest.raises(ValueError, match="value_type"):
        realize_participant_configuration(
            participant_address="participants.red",
            manifest=manifest,
            manifest_ref="manifests/reference-red-agent.json",
            manifest_digest="sha256:" + "1" * 64,
            overrides=overrides,
        )


class _OriginChangingValidator:
    def validate_and_normalize(self, configuration):
        values = [
            value.model_copy(update={"origin": "default"}) if value.origin == "override" else value
            for value in configuration.values
        ]
        return configuration.model_copy(update={"values": values})


class _SecretDispositionChangingValidator:
    def validate_and_normalize(self, configuration):
        values = [
            value.model_copy(update={"value": LiteralBindingValueModel(kind="literal", value="resolved-secret")})
            if value.target_id == "policy.mode"
            else value
            for value in configuration.values
        ]
        return configuration.model_copy(update={"values": values})


def test_participant_owner_normalization_must_preserve_default_override_provenance() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    overrides = [
        ConfigurationOverrideModel(
            target_id="mode",
            value={"kind": "literal", "value": "deterministic"},
        ),
        ConfigurationOverrideModel(
            target_id="credentials.api",
            value={"kind": "secret-reference", "reference_id": "operator-secret.reference-red-api"},
        ),
    ]
    validator = _OriginChangingValidator()

    with pytest.raises(ValueError, match="origin"):
        realize_participant_configuration(
            participant_address="participants.red",
            manifest=manifest,
            manifest_ref="manifests/reference-red-agent.json",
            manifest_digest="sha256:" + "1" * 64,
            overrides=overrides,
            validator=validator,
        )


def test_participant_owner_normalization_must_not_replace_secret_reference_with_literal() -> None:
    payload = _participant_manifest_payload()
    payload["configuration_registry"]["targets"]["policy.mode"]["allowed_value_kinds"] = [  # type: ignore[index]
        "literal",
        "secret-reference",
    ]
    manifest = ParticipantImplementationManifestModel.model_validate(payload)
    overrides = [
        ConfigurationOverrideModel(
            target_id="mode",
            value={"kind": "secret-reference", "reference_id": "operator-secret.mode"},
        ),
        ConfigurationOverrideModel(
            target_id="credentials.api",
            value={"kind": "secret-reference", "reference_id": "operator-secret.reference-red-api"},
        ),
    ]
    validator = _SecretDispositionChangingValidator()

    with pytest.raises(ValueError, match="literal/secret-reference disposition"):
        realize_participant_configuration(
            participant_address="participants.red",
            manifest=manifest,
            manifest_ref="manifests/reference-red-agent.json",
            manifest_digest="sha256:" + "1" * 64,
            overrides=overrides,
            validator=validator,
        )


def _experiment_spec_payload_with_bindings() -> dict[str, object]:
    payload = json.loads(
        (
            _REPO_ROOT
            / "contracts"
            / "fixtures"
            / "experiment-core"
            / "experiment-authoring-input-v1"
            / "valid"
            / "reference.json"
        ).read_text(encoding="utf-8")
    )
    for condition_id, assignment in payload["run_plan"]["allocation"]["condition_assignments"].items():
        assignment.pop("required_parameters")
        assignment["required_refs"] = [
            {
                "ref_kind": "profile",
                "ref_id": f"protocol.reference-red-tactic.{condition_id}",
            }
        ]
    payload["binding_semantics"] = "explicit-required"
    payload["binding_descriptors"] = {
        "schema_version": "experiment-binding-descriptors/v1",
        "descriptors": [
            {
                **_scenario_binding_payload()["descriptors"][0],
                "binding_id": "binding.red-tactic.aggressive",
                "source_factor_id": "red-tactic",
                "source_factor_level_id": "aggressive",
                "source_condition_id": "cond-aggressive",
                "value_type": "string",
                "value": {"kind": "literal", "value": "aggressive"},
            },
            {
                **_scenario_binding_payload()["descriptors"][0],
                "binding_id": "binding.red-tactic.stealthy",
                "source_factor_id": "red-tactic",
                "source_factor_level_id": "stealthy",
                "source_condition_id": "cond-stealthy",
                "value_type": "string",
                "value": {"kind": "literal", "value": "stealthy"},
            },
        ],
    }
    return payload


def test_experiment_spec_joins_binding_sources_to_declared_factor_levels_and_conditions() -> None:
    spec = ExperimentSpecModel.model_validate(_experiment_spec_payload_with_bindings())

    assert spec.binding_semantics == "explicit-required"
    assert spec.binding_descriptors is not None
    assert {item.source_condition_id for item in spec.binding_descriptors.descriptors} == {
        "cond-aggressive",
        "cond-stealthy",
    }


def test_experiment_spec_rejects_binding_factor_level_mismatch() -> None:
    payload = _experiment_spec_payload_with_bindings()
    payload["binding_descriptors"]["descriptors"][0]["source_factor_level_id"] = "stealthy"  # type: ignore[index]

    with pytest.raises(ValidationError, match="factor level"):
        ExperimentSpecModel.model_validate(payload)


@pytest.mark.parametrize("invalid", ["factor", "level"])
def test_explicit_binding_mode_rejects_invalid_unjoined_condition_factor(invalid: str) -> None:
    payload = _experiment_spec_payload_with_bindings()
    if invalid == "level":
        payload["factors"]["unjoined"] = {"name": "Extra factor", "factor_kind": "other", "levels": ["valid"]}
    assignment = payload["run_plan"]["allocation"]["condition_assignments"]["cond-stealthy"]
    assignment["factor_levels"]["unjoined"] = "invalid"

    with pytest.raises(ValidationError, match="must reference declared factor"):
        ExperimentSpecModel.model_validate(payload)


def test_experiment_spec_fails_closed_when_explicit_bindings_are_required_but_absent() -> None:
    payload = _experiment_spec_payload_with_bindings()
    del payload["binding_descriptors"]

    with pytest.raises(ValidationError, match="explicit-required"):
        ExperimentSpecModel.model_validate(payload)


def test_experiment_spec_rejects_ambiguous_legacy_parameters_in_explicit_binding_mode() -> None:
    payload = _experiment_spec_payload_with_bindings()
    assignment = payload["run_plan"]["allocation"]["condition_assignments"]["cond-aggressive"]  # type: ignore[index]
    assignment["required_parameters"] = [
        {
            "name": "red_tactic",
            "value": "aggressive",
            "value_kind": "protocol",
        }
    ]

    with pytest.raises(ValidationError, match="legacy required_parameters"):
        ExperimentSpecModel.model_validate(payload)


def test_realized_binding_provenance_preserves_non_secret_value_and_configuration_digest() -> None:
    descriptor = ExperimentBindingDescriptorSetModel.model_validate(_scenario_binding_payload()).descriptors[0]

    provenance = RealizedBindingProvenanceModel(
        descriptor=descriptor,
        origin="override",
        configuration_digest="sha256:" + "2" * 64,
    )

    assert provenance.descriptor.binding_id == "binding.worker-count"
    assert provenance.origin == "override"
    assert provenance.configuration_digest == "sha256:" + "2" * 64


@pytest.mark.parametrize(
    ("model_type", "fixture_path"),
    [
        (
            ProcessorManifestV2Model,
            _REPO_ROOT / "contracts/fixtures/processor-manifest/processor-manifest-v2/valid/reference.json",
        ),
        (
            BackendManifestV2Model,
            _REPO_ROOT / "contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json",
        ),
    ],
)
def test_apparatus_manifests_publish_typed_configuration_targets(
    model_type: type[ProcessorManifestV2Model] | type[BackendManifestV2Model],
    fixture_path: Path,
) -> None:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["supported_contract_versions"].append("experiment-binding-descriptors-v1")
    payload["configuration_registry"] = {
        "owner": {
            "contract_id": payload["schema_version"],
            "contract_version": "1",
            "validator_id": f"{payload['identity']['name']}-configuration",
            "validator_version": "1",
        },
        "targets": {
            "execution.parallelism": {
                "target_id": "execution.parallelism",
                "value_type": "integer",
                "aliases": ["parallelism"],
                "allowed_value_kinds": ["literal"],
                "sensitivity": "internal",
                "default": {"kind": "literal", "value": 1},
            }
        },
    }

    manifest = model_type.model_validate(payload)

    assert manifest.configuration_registry is not None
    assert manifest.configuration_registry.targets["execution.parallelism"].value_type == "integer"


def test_experiment_run_archives_realized_binding_provenance() -> None:
    payload = json.loads(
        (
            _REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / "experiment-run-v1" / "valid" / "reference.json"
        ).read_text(encoding="utf-8")
    )
    payload["realized_bindings"] = [
        {
            "descriptor": _scenario_binding_payload()["descriptors"][0],
            "origin": "selection",
        }
    ]

    run = ExperimentRunModel.model_validate(payload)

    assert run.realized_bindings[0].descriptor.source_condition_id == "condition.four-workers"


def test_participant_selection_requires_configuration_ref_and_digest_together() -> None:
    payload = json.loads(
        (
            _REPO_ROOT
            / "contracts"
            / "fixtures"
            / "participant-implementation-provenance"
            / "participant-implementation-provenance-v1"
            / "valid"
            / "reference.json"
        ).read_text(encoding="utf-8")
    )
    del payload["participant_implementations"][0]["configuration_digest"]

    with pytest.raises(ValidationError, match="configuration_ref and configuration_digest"):
        ParticipantImplementationProvenanceModel.model_validate(payload)


class _ScenarioResolver:
    def resolve(
        self,
        scenario_family_id: str,
        variation_point_id: str,
        supplied_target_id: str,
    ) -> ScenarioBindingResolution:
        if (
            scenario_family_id,
            variation_point_id,
            supplied_target_id,
        ) != ("family.techvault", "variation.worker-count", "variables.worker_count"):
            raise ValueError("unknown scenario variation target")
        return ScenarioBindingResolution(
            canonical_target_id="variables.worker_count",
            value_type="integer",
            allowed_value_kinds=["literal"],
            sensitivity="public",
            owner={
                "contract_id": "sdl-authoring-input-v1",
                "contract_version": "1",
                "validator_id": "raes-sdl-instantiation",
                "validator_version": "1",
            },
        )


class _ScenarioTypeMismatchResolver(_ScenarioResolver):
    def resolve(self, scenario_family_id, variation_point_id, supplied_target_id):
        resolution = super().resolve(scenario_family_id, variation_point_id, supplied_target_id)
        return resolution.model_copy(update={"value_type": "string"})


class _ScenarioOwnerMismatchResolver(_ScenarioResolver):
    def resolve(self, scenario_family_id, variation_point_id, supplied_target_id):
        resolution = super().resolve(scenario_family_id, variation_point_id, supplied_target_id)
        owner = resolution.owner.model_copy(update={"validator_version": "2"})
        return resolution.model_copy(update={"owner": owner})


class _SecretLiteralScenarioResolver(_ScenarioResolver):
    def resolve(self, scenario_family_id, variation_point_id, supplied_target_id):
        resolution = super().resolve(scenario_family_id, variation_point_id, supplied_target_id)
        return resolution.model_copy(
            update={
                "allowed_value_kinds": ["literal", "secret-reference"],
                "sensitivity": "secret",
            }
        )


def _participant_binding_payload(target_id: str = "mode") -> dict[str, object]:
    return {
        "schema_version": "experiment-binding-descriptors/v1",
        "descriptors": [
            {
                "binding_id": "binding.participant-mode",
                "source_factor_id": "participant-mode",
                "source_factor_level_id": "deterministic",
                "source_condition_id": "condition.deterministic",
                "target": {
                    "plane": "participant-implementation",
                    "participant_address": "participants.red",
                    "implementation_name": "reference-red-agent",
                    "implementation_version": "1.0.0",
                    "manifest_version": "participant-implementation-manifest/v1",
                    "target_id": target_id,
                },
                "value_type": "string",
                "value": {"kind": "literal", "value": "deterministic"},
                "owner": {
                    "contract_id": "participant-configuration-result-v1",
                    "contract_version": "1",
                    "validator_id": "reference-participant-configuration",
                    "validator_version": "1",
                },
            }
        ],
    }


def _apparatus_binding_payload(
    *,
    component_kind: str = "processor",
    component_name: str = "raes-reference-processor",
    component_version: str = "0.2.0",
    manifest_version: str = "processor-manifest/v2",
) -> dict[str, object]:
    return {
        "schema_version": "experiment-binding-descriptors/v1",
        "descriptors": [
            {
                "binding_id": "binding.apparatus-parallelism",
                "source_factor_id": "parallelism",
                "source_factor_level_id": "four",
                "source_condition_id": "condition.four-workers",
                "target": {
                    "plane": "apparatus",
                    "component_kind": component_kind,
                    "component_name": component_name,
                    "component_version": component_version,
                    "manifest_version": manifest_version,
                    "target_id": "execution.parallelism",
                },
                "value_type": "integer",
                "value": {"kind": "literal", "value": 4},
                "owner": {
                    "contract_id": "processor-manifest/v2",
                    "contract_version": "1",
                    "validator_id": "raes-reference-processor-configuration",
                    "validator_version": "1",
                },
            }
        ],
    }


def _processor_manifest_payload_with_registry() -> dict[str, object]:
    fixture_path = (
        _REPO_ROOT
        / "contracts"
        / "fixtures"
        / "processor-manifest"
        / "processor-manifest-v2"
        / "valid"
        / "reference.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["supported_contract_versions"].append("experiment-binding-descriptors-v1")
    payload["configuration_registry"] = {
        "owner": {
            "contract_id": "processor-manifest/v2",
            "contract_version": "1",
            "validator_id": "raes-reference-processor-configuration",
            "validator_version": "1",
        },
        "targets": {
            "execution.parallelism": {
                "target_id": "execution.parallelism",
                "value_type": "integer",
                "aliases": ["parallelism"],
                "allowed_value_kinds": ["literal"],
                "sensitivity": "internal",
                "default": {"kind": "literal", "value": 1},
            }
        },
    }
    return payload


def _participant_manifest_map(
    manifest: ParticipantImplementationManifestModel,
) -> dict[tuple[str, str, str, str], ParticipantImplementationManifestModel]:
    return {
        (
            "participants.red",
            "reference-red-agent",
            "1.0.0",
            "participant-implementation-manifest/v1",
        ): manifest
    }


def _apparatus_manifest_map(
    manifest: ProcessorManifestV2Model,
    *,
    component_kind: str = "processor",
) -> dict[tuple[str, str, str, str], ProcessorManifestV2Model]:
    return {
        (
            component_kind,
            "raes-reference-processor",
            "0.2.0",
            "processor-manifest/v2",
        ): manifest
    }


def test_canonical_target_identity_preserves_scenario_variation_point() -> None:
    payload = _scenario_binding_payload()
    second = deepcopy(payload["descriptors"][0])  # type: ignore[index]
    second["binding_id"] = "binding.worker-count.alternate-variation"
    second["target"]["variation_point_id"] = "variation.alternate-worker-count"
    payload["descriptors"].append(second)  # type: ignore[union-attr]

    model = ExperimentBindingDescriptorSetModel.model_validate(payload)

    assert len(model.descriptors) == 2


def test_canonical_target_identity_preserves_participant_manifest_version() -> None:
    payload = _participant_binding_payload()
    second = deepcopy(payload["descriptors"][0])  # type: ignore[index]
    second["binding_id"] = "binding.participant-mode.v2"
    second["target"]["manifest_version"] = "participant-implementation-manifest/v2"
    payload["descriptors"].append(second)  # type: ignore[union-attr]

    model = ExperimentBindingDescriptorSetModel.model_validate(payload)

    assert len(model.descriptors) == 2


def test_canonical_target_identity_preserves_apparatus_manifest_version() -> None:
    payload = _apparatus_binding_payload()
    second = deepcopy(payload["descriptors"][0])  # type: ignore[index]
    second["binding_id"] = "binding.apparatus-parallelism.v3"
    second["target"]["manifest_version"] = "processor-manifest/v3"
    payload["descriptors"].append(second)  # type: ignore[union-attr]

    model = ExperimentBindingDescriptorSetModel.model_validate(payload)

    assert len(model.descriptors) == 2


def test_canonical_target_identity_keeps_apparatus_owner_coordinates_structured() -> None:
    payload = _apparatus_binding_payload(component_name="alpha:beta", component_version="gamma")
    second = deepcopy(payload["descriptors"][0])  # type: ignore[index]
    second["binding_id"] = "binding.apparatus-parallelism.distinct-owner"
    second["target"]["component_name"] = "alpha"
    second["target"]["component_version"] = "beta@gamma"
    payload["descriptors"].append(second)  # type: ignore[union-attr]

    model = ExperimentBindingDescriptorSetModel.model_validate(payload)

    assert len(model.descriptors) == 2


def test_binding_admission_resolves_alias_only_through_declared_participant_owner() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(_participant_binding_payload())

    admitted = validate_experiment_binding_targets(
        descriptors,
        scenario_resolver=_ScenarioResolver(),
        participant_manifests={
            (
                "participants.red",
                "reference-red-agent",
                "1.0.0",
                "participant-implementation-manifest/v1",
            ): manifest
        },
        apparatus_manifests={},
    )

    assert admitted.descriptors[0].target.target_id == "policy.mode"


@pytest.mark.parametrize(
    ("resolver", "message"),
    [
        (_ScenarioTypeMismatchResolver(), "value_type"),
        (_ScenarioOwnerMismatchResolver(), "owner"),
    ],
)
def test_scenario_binding_admission_rejects_resolver_contract_mismatch(
    resolver: _ScenarioResolver,
    message: str,
) -> None:
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(_scenario_binding_payload())

    with pytest.raises(ExperimentBindingTargetError, match=message):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=resolver,
            participant_manifests={},
            apparatus_manifests={},
        )


def test_scenario_binding_admission_rejects_literal_for_secret_target() -> None:
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(_scenario_binding_payload())
    scenario_resolver = _SecretLiteralScenarioResolver()

    with pytest.raises(ExperimentBindingTargetError, match="secret scenario targets"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests={},
            apparatus_manifests={},
        )


def test_binding_admission_rejects_miskeyed_participant_manifest_identity() -> None:
    manifest_payload = _participant_manifest_payload()
    manifest_payload["identity"]["name"] = "different-red-agent"  # type: ignore[index]
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(_participant_binding_payload())
    scenario_resolver = _ScenarioResolver()
    participant_manifests = _participant_manifest_map(manifest)

    with pytest.raises(ExperimentBindingTargetError, match="identity must match"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests=participant_manifests,
            apparatus_manifests={},
        )


def test_binding_admission_rejects_participant_manifest_without_registry() -> None:
    manifest_payload = _participant_manifest_payload()
    del manifest_payload["configuration_registry"]
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(_participant_binding_payload())
    scenario_resolver = _ScenarioResolver()
    participant_manifests = _participant_manifest_map(manifest)

    with pytest.raises(ExperimentBindingTargetError, match="no configuration target registry"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests=participant_manifests,
            apparatus_manifests={},
        )


def test_binding_admission_rejects_participant_target_owner_mismatch() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    payload = _participant_binding_payload()
    payload["descriptors"][0]["owner"]["validator_version"] = "2"  # type: ignore[index]
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(payload)
    scenario_resolver = _ScenarioResolver()
    participant_manifests = _participant_manifest_map(manifest)

    with pytest.raises(ExperimentBindingTargetError, match="owner"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests=participant_manifests,
            apparatus_manifests={},
        )


def test_binding_admission_rejects_participant_target_value_type_mismatch() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    payload = _participant_binding_payload()
    payload["descriptors"][0]["value_type"] = "integer"  # type: ignore[index]
    payload["descriptors"][0]["value"]["value"] = 1  # type: ignore[index]
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(payload)
    scenario_resolver = _ScenarioResolver()
    participant_manifests = _participant_manifest_map(manifest)

    with pytest.raises(ExperimentBindingTargetError, match="value_type"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests=participant_manifests,
            apparatus_manifests={},
        )


def test_binding_admission_rejects_miskeyed_apparatus_manifest_identity() -> None:
    manifest_payload = _processor_manifest_payload_with_registry()
    manifest_payload["identity"]["name"] = "different-processor"  # type: ignore[index]
    manifest = ProcessorManifestV2Model.model_validate(manifest_payload)
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(_apparatus_binding_payload())
    scenario_resolver = _ScenarioResolver()
    apparatus_manifests = _apparatus_manifest_map(manifest)

    with pytest.raises(ExperimentBindingTargetError, match="identity and kind must match"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests={},
            apparatus_manifests=apparatus_manifests,
        )


def test_binding_admission_rejects_apparatus_manifest_without_registry() -> None:
    fixture_path = (
        _REPO_ROOT
        / "contracts"
        / "fixtures"
        / "processor-manifest"
        / "processor-manifest-v2"
        / "valid"
        / "reference.json"
    )
    manifest = ProcessorManifestV2Model.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(_apparatus_binding_payload())
    scenario_resolver = _ScenarioResolver()
    apparatus_manifests = _apparatus_manifest_map(manifest)

    with pytest.raises(ExperimentBindingTargetError, match="no configuration target registry"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests={},
            apparatus_manifests=apparatus_manifests,
        )


def test_binding_admission_rejects_apparatus_kind_mismatch() -> None:
    manifest = ProcessorManifestV2Model.model_validate(_processor_manifest_payload_with_registry())
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(
        _apparatus_binding_payload(component_kind="backend")
    )
    scenario_resolver = _ScenarioResolver()
    apparatus_manifests = _apparatus_manifest_map(manifest, component_kind="backend")

    with pytest.raises(ExperimentBindingTargetError, match="identity and kind must match"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests={},
            apparatus_manifests=apparatus_manifests,
        )


def test_binding_admission_rejects_unknown_participant_target_without_cross_plane_fallback() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(
        _participant_binding_payload("variables.worker_count")
    )
    scenario_resolver = _ScenarioResolver()
    participant_manifests = _participant_manifest_map(manifest)

    with pytest.raises(ExperimentBindingTargetError, match="unknown configuration target"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests=participant_manifests,
            apparatus_manifests={},
        )


def test_binding_admission_rejects_alias_and_canonical_duplicate_after_resolution() -> None:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    payload = _participant_binding_payload()
    duplicate = deepcopy(payload["descriptors"][0])  # type: ignore[index]
    duplicate["binding_id"] = "binding.participant-mode-duplicate"
    duplicate["target"]["target_id"] = "policy.mode"
    payload["descriptors"].append(duplicate)  # type: ignore[union-attr]
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(payload)
    scenario_resolver = _ScenarioResolver()
    participant_manifests = _participant_manifest_map(manifest)

    with pytest.raises(ExperimentBindingTargetError, match="duplicate canonical target"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests=participant_manifests,
            apparatus_manifests={},
        )


def test_scenario_binding_admission_enforces_owner_declared_value_disposition() -> None:
    payload = _scenario_binding_payload()
    payload["descriptors"][0]["value_type"] = "integer"  # type: ignore[index]
    payload["descriptors"][0]["value"] = {  # type: ignore[index]
        "kind": "secret-reference",
        "reference_id": "operator-secret.worker-count",
    }
    descriptors = ExperimentBindingDescriptorSetModel.model_validate(payload)
    scenario_resolver = _ScenarioResolver()

    with pytest.raises(ExperimentBindingTargetError, match="value kind"):
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=scenario_resolver,
            participant_manifests={},
            apparatus_manifests={},
        )


def _participant_configuration_result_payload() -> dict[str, object]:
    manifest = ParticipantImplementationManifestModel.model_validate(_participant_manifest_payload())
    result = realize_participant_configuration(
        participant_address="participants.red",
        manifest=manifest,
        manifest_ref="manifests/reference-red-agent.json",
        manifest_digest="sha256:" + "1" * 64,
        overrides=[
            ConfigurationOverrideModel(
                target_id="mode",
                value={"kind": "literal", "value": "deterministic"},
            ),
            ConfigurationOverrideModel(
                target_id="credentials.api",
                value={"kind": "secret-reference", "reference_id": "operator-secret.reference-red-api"},
            ),
        ],
    )
    return result.model_dump(mode="json")


@pytest.mark.parametrize(
    ("contract_id", "model_type", "payload"),
    [
        (
            "experiment-binding-descriptors-v1",
            ExperimentBindingDescriptorSetModel,
            _scenario_binding_payload(),
        ),
        (
            "participant-configuration-result-v1",
            ParticipantConfigurationResultModel,
            _participant_configuration_result_payload(),
        ),
    ],
)
def test_binding_contract_roots_are_published_and_registered(
    contract_id: str,
    model_type: type[ExperimentBindingDescriptorSetModel] | type[ParticipantConfigurationResultModel],
    payload: dict[str, object],
) -> None:
    assert contract_id in schema_bundle()
    assert schema_bundle()[contract_id]["additionalProperties"] is False
    assert not _validate_payload(contract_id, payload)
    assert model_type.model_validate(payload)

    schema_family = (
        "experiment-core"
        if contract_id == "experiment-binding-descriptors-v1"
        else "participant-implementation-configuration"
    )
    schema_path = _REPO_ROOT / "contracts" / "schemas" / schema_family / f"{contract_id}.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(payload))


@pytest.mark.parametrize(
    "contract_id",
    ["experiment-binding-descriptors-v1", "participant-configuration-result-v1"],
)
def test_binding_contract_fixture_corpora_are_nonempty_and_enforced(contract_id: str) -> None:
    fixture_family = (
        "experiment-core"
        if contract_id == "experiment-binding-descriptors-v1"
        else "participant-implementation-configuration"
    )
    root = _REPO_ROOT / "contracts" / "fixtures" / fixture_family / contract_id
    valid_paths = sorted((root / "valid").glob("*.json"))
    invalid_paths = sorted((root / "invalid").glob("*.json"))
    assert valid_paths
    assert invalid_paths
    for path in valid_paths:
        assert not _validate_payload(contract_id, json.loads(path.read_text(encoding="utf-8")))
    for path in invalid_paths:
        assert _validate_payload(contract_id, json.loads(path.read_text(encoding="utf-8")))


def test_binding_schemas_disclose_semantic_invariants_and_explicit_mode_conditionals() -> None:
    bundle = schema_bundle()
    descriptor_invariants = {item["id"] for item in bundle["experiment-binding-descriptors-v1"]["x-raes-invariants"]}
    result_invariants = {item["id"] for item in bundle["participant-configuration-result-v1"]["x-raes-invariants"]}
    assert "binding-descriptors-canonical-targets-injective" in descriptor_invariants
    assert "participant-configuration-digest-valid" in result_invariants
    assert bundle["experiment-authoring-input-v1"]["allOf"]

    selection_schema = bundle["participant-implementation-provenance-v1"]["$defs"][
        "ParticipantImplementationSelectionModel"
    ]
    assert selection_schema["oneOf"]
