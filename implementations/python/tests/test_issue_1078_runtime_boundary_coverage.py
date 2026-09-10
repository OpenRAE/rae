"""Issue #1078: every authored runtime dimension has SEM-218 authority."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.runtime_configuration import RuntimeConfiguration
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.planning import RuntimeDomain
from raes_contracts.realization_authority import planned_realization_selection_diagnostics
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import (
    ObservationStrength,
    RealizationSupportMode,
    RealizationVerificationScope,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan, realization_authority_disclosure
from raes_processor.semantics.realization import (
    CompiledRealizationRequirement,
    realization_support_diagnostics,
)
from raes_processor.semantics.realization_concerns import (
    project_realization_concern,
    realization_concern_descriptors,
    runtime_configuration_boundary_inventory,
)


def _runtime_descriptors():
    return tuple(
        descriptor for descriptor in realization_concern_descriptors() if descriptor.authored_path[:1] == ("runtime",)
    )


def test_runtime_boundary_inventory_partitions_all_32_fields_once() -> None:
    inventory = runtime_configuration_boundary_inventory()

    assert tuple(item.field_name for item in inventory) == tuple(RuntimeConfiguration.model_fields)
    assert len(inventory) == 32
    assert all(item.concern_kinds or item.delegated_paths or item.observation_only_paths for item in inventory)
    assert all(
        item.semantic_owner
        and (
            item.enforcement_status.startswith("registered") or item.enforcement_status == "delegated-to-existing-owner"
        )
        for item in inventory
    )

    descriptors = _runtime_descriptors()
    descriptor_kinds = {descriptor.concern_kind for descriptor in descriptors}
    inventoried_kinds = {kind for item in inventory for kind in item.concern_kinds}
    assert inventoried_kinds == descriptor_kinds
    assert len(descriptor_kinds) == len(descriptors)
    assert len({descriptor.authored_path for descriptor in descriptors}) == len(descriptors)


def test_mixed_runtime_dimensions_are_split_at_typed_semantic_boundaries() -> None:
    inventory = {item.field_name: item for item in runtime_configuration_boundary_inventory()}

    assert len(inventory["operational_policy"].concern_kinds) == 6
    assert len(inventory["container"].concern_kinds) > 5
    assert inventory["network"].concern_kinds == (
        "runtime-network-hostname",
        "runtime-network-domainname",
        "runtime-network-endpoints",
        "published-ports",
    )
    assert inventory["mounts"].delegated_paths == ("source_kind:volume", "source_kind:image")
    assert inventory["environment_files"].concern_kinds == ()
    assert inventory["environment_files"].delegated_paths == ("generated-artifact-output",)
    assert "run_state" in inventory["scheduled_jobs"].observation_only_paths
    assert "realized_children" in inventory["orchestration_authorities"].observation_only_paths


def test_every_runtime_concern_reaches_total_plan_authority() -> None:
    model = compile_runtime_model(
        parse_sdl(
            """
name: issue-1078-total-runtime-authority
nodes:
  worker:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    runtime: {}
"""
        )
    )

    expected = {descriptor.concern_kind for descriptor in _runtime_descriptors()}
    actual = {
        authority.requirement_kind
        for authority in model.realization_authority
        if authority.address == "provision.node.worker"
    }

    assert expected <= actual
    assert all(
        authority.mode.value == "closed"
        for authority in model.realization_authority
        if authority.address == "provision.node.worker" and authority.requirement_kind in expected
    )


@pytest.mark.parametrize(
    ("kind", "value", "identity"),
    [
        (
            "runtime-packages",
            [
                {"manager": "apt", "name": "zlib1g", "version": "1.2"},
                {"manager": "apt", "name": "bash", "version": "5.2"},
            ],
            "bash",
        ),
        (
            "runtime-software-components",
            [
                {"component_id": "zlib", "name": "zlib"},
                {"component_id": "bash", "name": "bash"},
            ],
            "bash",
        ),
        (
            "runtime-dependency-manifests",
            [
                {"ecosystem": "python", "path": "/z/requirements.txt"},
                {"ecosystem": "python", "path": "/a/requirements.txt"},
            ],
            "/a/requirements.txt",
        ),
    ],
)
def test_keyed_collection_projections_are_order_stable_and_model_closed(
    kind: str,
    value: list[dict[str, object]],
    identity: str,
) -> None:
    projected = project_realization_concern(kind, value)

    assert projected == project_realization_concern(kind, list(reversed(value)))
    assert identity in repr(projected[0])
    assert project_realization_concern(kind, projected, observed=True) == projected
    with pytest.raises(ValueError):
        project_realization_concern(kind, [{**value[0], "backend_private": True}], observed=True)


def test_service_projection_excludes_outcomes_and_commits_sensitive_values() -> None:
    scheduled = project_realization_concern(
        "runtime-scheduled-jobs",
        [
            {
                "scheduled_job_id": "sync",
                "enabled": True,
                "schedule": {"kind": "cron", "spec": "*/5 * * * *", "enabled": True},
                "run_state": {"last_run": "2026-09-03T12:00:00Z", "last_result": "success"},
                "description": "observation annotation",
            }
        ],
    )
    database = project_realization_concern(
        "runtime-database-services",
        [
            {
                "database_service_id": "primary",
                "settings": [
                    {
                        "name": "mode",
                        "value": "strict",
                        "value_classification": "plain",
                        "provenance": "configuration_file",
                    },
                    {
                        "name": "fixture-token",
                        "value": "deliberate-secret",
                        "value_classification": "secret_fixture",
                        "provenance": "configuration_file",
                    },
                ],
            }
        ],
    )

    assert "run_state" not in repr(scheduled)
    assert "description" not in repr(scheduled)
    assert "deliberate-secret" not in repr(database)
    assert "value_commitment" in repr(database)
    assert project_realization_concern("runtime-database-services", database, observed=True) == database

    reversed_settings = deepcopy(database)
    reversed_settings[0]["settings"] = list(reversed(reversed_settings[0]["settings"]))
    assert project_realization_concern("runtime-database-services", reversed_settings, observed=True) == database

    withheld = project_realization_concern(
        "runtime-database-services",
        [
            {
                "database_service_id": "protected",
                "settings": [
                    {
                        "name": "password",
                        "value_classification": "operator_secret",
                        "provenance": "configuration_file",
                    }
                ],
            }
        ],
    )
    assert isinstance(withheld, list)
    assert isinstance(withheld[0], dict)
    withheld_settings = withheld[0]["settings"]
    assert isinstance(withheld_settings, list)
    assert isinstance(withheld_settings[0], dict)
    withheld_settings[0]["value_present"] = False
    with pytest.raises(ValueError):
        project_realization_concern("runtime-database-services", withheld, observed=True)

    with pytest.raises(ValueError, match="explicit presence marker"):
        project_realization_concern(
            "runtime-database-services",
            [
                {
                    "database_service_id": "protected",
                    "settings": [
                        {
                            "name": "password",
                            "value_classification": "operator_secret",
                            "provenance": "configuration_file",
                        }
                    ],
                }
            ],
            observed=True,
        )


def test_typed_projection_canonicalizes_model_defaults() -> None:
    minimal = project_realization_concern(
        "runtime-database-services",
        [{"database_service_id": "primary"}],
    )

    assert isinstance(minimal, list)
    assert isinstance(minimal[0], dict)
    assert minimal[0]["engine"] == "other"
    assert minimal[0]["protocol"] == "other"
    assert minimal == project_realization_concern("runtime-database-services", minimal)


def test_observation_only_outcomes_do_not_weaken_authored_configuration_posture() -> None:
    model = compile_runtime_model(
        parse_sdl(
            """
name: issue-1078-observation-only-explicitness
nodes:
  worker:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    runtime:
      scheduled_jobs:
        - scheduled_job_id: sync
          enabled: true
          run_state: {last_result: unknown}
"""
        )
    )

    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "runtime-scheduled-jobs"
    )

    assert requirement.explicitness is ExplicitnessClass.EXACT


def test_closed_runtime_authority_rejects_an_unauthorized_managed_addition() -> None:
    model = compile_runtime_model(
        parse_sdl(
            """
name: issue-1078-closed-runtime-selection
nodes:
  worker:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    runtime: {}
"""
        )
    )
    provisioning = plan(model, create_stub_manifest()).provisioning
    operation = provisioning.operations[0]
    payload = deepcopy(operation.payload)
    payload["spec"]["node"]["runtime"]["packages"] = [{"manager": "apt", "name": "unapproved", "version": "1"}]
    selected = replace(provisioning, operations=[replace(operation, payload=payload)])

    assert [item.code for item in planned_realization_selection_diagnostics(selected)] == [
        "realization.authority-selection-invalid"
    ]

    returned = RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=payload,
            )
        }
    )
    diagnostics, _provenance = realization_authority_disclosure(
        provisioning,
        returned,
        manifest=create_stub_manifest(),
    )
    assert any(
        item.code == "runtime.backend-contract-invalid" and "runtime-packages" in item.message for item in diagnostics
    )


@pytest.mark.parametrize("unauthorized_value", ["unknown", "other"])
def test_closed_runtime_authority_does_not_treat_global_sentinel_strings_as_absent(
    unauthorized_value: str,
) -> None:
    model = compile_runtime_model(
        parse_sdl(
            """
name: issue-1078-closed-runtime-sentinel
nodes:
  worker:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    runtime: {}
"""
        )
    )
    provisioning = plan(model, create_stub_manifest()).provisioning
    operation = provisioning.operations[0]
    payload = deepcopy(operation.payload)
    payload["spec"]["node"]["runtime"]["network"] = {"hostname": unauthorized_value}
    selected = replace(provisioning, operations=[replace(operation, payload=payload)])

    assert [item.code for item in planned_realization_selection_diagnostics(selected)] == [
        "realization.authority-selection-invalid"
    ]


@pytest.mark.parametrize(
    "descriptor",
    [item for item in _runtime_descriptors() if item.concern_kind != "process-resource-limits"],
    ids=lambda item: item.concern_kind,
)
def test_each_runtime_family_has_fail_closed_exact_open_and_constrained_admission(descriptor) -> None:
    def requirement(explicitness: ExplicitnessClass) -> CompiledRealizationRequirement:
        return CompiledRealizationRequirement(
            field_path=f"nodes.worker.{descriptor.authored_suffix}",
            address="provision.node.worker",
            domain="runtime-realization",
            requirement_kind=descriptor.concern_kind,
            explicitness=explicitness,
            provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
            verification_scope=RealizationVerificationScope.CONFIGURATION,
            required_observation_strength=ObservationStrength.GUEST_OBSERVED,
        )

    manifest = create_stub_manifest()
    declaration = manifest.realization_support[0]
    capability = RealizationObservationCapability(
        verification_scope=RealizationVerificationScope.CONFIGURATION,
        observation_strength=ObservationStrength.GUEST_OBSERVED,
    )
    exact = replace(
        manifest,
        realization_support=(
            replace(
                declaration,
                supported_exact_requirement_kinds=(
                    declaration.supported_exact_requirement_kinds | {descriptor.concern_kind}
                ),
                observation_capabilities={descriptor.concern_kind: capability},
            ),
        ),
    )
    open_manifest = replace(
        exact,
        realization_support=(
            replace(exact.realization_support[0], support_mode=RealizationSupportMode.OPEN_REALIZATION),
        ),
    )
    constrained = replace(
        exact,
        realization_support=(
            replace(
                exact.realization_support[0],
                supported_constraint_kinds=(
                    exact.realization_support[0].supported_constraint_kinds | {descriptor.concern_kind}
                ),
            ),
        ),
    )

    assert [
        item.code for item in realization_support_diagnostics((requirement(ExplicitnessClass.EXACT),), manifest)
    ] == ["realization.unsupported-exact-requirement"]
    assert realization_support_diagnostics((requirement(ExplicitnessClass.EXACT),), exact) == []
    assert [
        item.code for item in realization_support_diagnostics((requirement(ExplicitnessClass.OPEN),), manifest)
    ] == ["realization.unsupported-open-requirement"]
    assert realization_support_diagnostics((requirement(ExplicitnessClass.OPEN),), open_manifest) == []
    assert [
        item.code for item in realization_support_diagnostics((requirement(ExplicitnessClass.CONSTRAINED),), manifest)
    ] == ["realization.unsupported-constraint-requirement"]
    assert realization_support_diagnostics((requirement(ExplicitnessClass.CONSTRAINED),), constrained) == []


def test_runtime_exact_support_requires_separate_operational_corroboration() -> None:
    model = compile_runtime_model(
        parse_sdl(
            """
name: issue-1078-package-observation
nodes:
  worker:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    runtime:
      packages:
        - {manager: apt, name: bash, version: '5.2'}
"""
        )
    )
    requirement = next(item for item in model.realization_requirements if item.requirement_kind == "runtime-packages")
    manifest = create_stub_manifest()

    declaration = manifest.realization_support[0]
    supported = replace(
        manifest,
        realization_support=(
            replace(
                declaration,
                supported_exact_requirement_kinds=(
                    declaration.supported_exact_requirement_kinds | {"runtime-packages"}
                ),
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "runtime-packages": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                },
            ),
        ),
    )

    assert requirement.explicitness is ExplicitnessClass.EXACT
    assert model.observation_demands == ()
    assert requirement.verification_scope is RealizationVerificationScope.CONFIGURATION
    assert requirement.required_observation_strength is ObservationStrength.GUEST_OBSERVED
    assert [item.code for item in realization_support_diagnostics((requirement,), manifest)] == [
        "realization.unsupported-exact-requirement"
    ]
    assert realization_support_diagnostics((requirement,), supported) == []


def test_portable_runtime_concerns_do_not_own_observation_policy() -> None:
    for descriptor in _runtime_descriptors():
        assert not hasattr(descriptor, "verification_scope"), descriptor.concern_kind
        assert not hasattr(descriptor, "observation_strength"), descriptor.concern_kind
