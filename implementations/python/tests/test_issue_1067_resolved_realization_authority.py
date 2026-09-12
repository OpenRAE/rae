"""Issue #1067 resolved realization-authority handoff conformance."""

from __future__ import annotations

import json
import textwrap
from copy import deepcopy
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes.instantiate import instantiate_scenario
from raes.parser import parse_sdl
from raes_backend_libvirt.driver import DriverResult as LibvirtDriverResult
from raes_backend_libvirt.manifest import create_libvirt_manifest
from raes_backend_libvirt.provisioner import LibvirtProvisioner
from raes_backend_protocols.capabilities import (
    BackendManifest,
    OperatingSystemCompatibility,
    ProvisionerCapabilities,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.apparatus import ConceptBinding, RealizationObservationCapability
from raes_contracts.bounded_domains import EnumDomain
from raes_contracts.contracts import ProvisioningPlanModel, ResolvedRealizationAuthorityModel, schema_bundle
from raes_contracts.plan_projection import provisioning_plan_model
from raes_contracts.planning import (
    ChangeAction,
    ProvisioningPlan,
    ProvisionOp,
    RealizationAuthorityBound,
    RealizationAuthorityMode,
    RealizationResolutionSource,
    ResolvedRealizationAuthority,
    planned_realization_authority,
)
from raes_contracts.realization_authority import planned_realization_selection_diagnostics
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import (
    Closure,
    ObservationStrength,
    RealizationSupportMode,
    RealizationVerificationScope,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import (
    plan,
    realization_authority_diagnostics,
    realization_authority_disclosure,
)
from raes_processor.planner.realization_authority_materialization import materialize_realization_authority
from raes_reference_backend.drivers.inprocess import InProcessDriver
from raes_reference_backend.target import create_reference_backend_target
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
from raes_runtime.control_plane import RuntimeControlPlane


def _scenario(realization: str = "", *, web_os: str = ""):
    realization_block = textwrap.dedent(realization).strip()
    os_line = f"    os: {web_os}\n" if web_os else ""
    return instantiate_scenario(
        parse_sdl(
            "name: authority-handoff\n"
            f"{realization_block + chr(10) if realization_block else ''}"
            "nodes:\n"
            "  web:\n"
            "    type: compute\n"
            f"{os_line}"
            "    resources: {ram: 1 gib, cpu: 1}\n"
        )
    )


def _manifest(mode: RealizationSupportMode = RealizationSupportMode.OPEN_REALIZATION) -> BackendManifest:
    base = create_libvirt_manifest()
    support = replace(
        base.realization_support[0],
        support_mode=mode,
        supported_constraint_kinds=(
            frozenset()
            if mode is RealizationSupportMode.EXACT_ONLY
            else frozenset({*base.realization_support[0].supported_constraint_kinds, "os-family", "node-architecture"})
        ),
        observation_capabilities={
            **base.realization_support[0].observation_capabilities,
            "operating-system": RealizationObservationCapability(
                verification_scope=RealizationVerificationScope.PRESENCE,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
            ),
        },
    )
    return BackendManifest(
        name="authority-handoff",
        version="1.0.0",
        supported_contract_versions=frozenset({"backend-manifest-v2", "realization-envelope-v1"}),
        compatible_processors=frozenset({"raes-reference-processor"}),
        realization_support=(support,),
        concept_bindings=(ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),),
        provisioner=ProvisionerCapabilities(
            name="authority-handoff",
            supported_node_types=frozenset({"compute"}),
            supported_os_families=frozenset({"linux", "windows"}),
            operating_systems=(
                OperatingSystemCompatibility("linux", "ubuntu", frozenset({"22.04"})),
                OperatingSystemCompatibility("windows", "windows-server", frozenset({"2022"})),
            ),
        ),
        realization_envelope=base.realization_envelope,
    )


def _compiled_authority(model, field_path: str):
    return next(entry for entry in model.realization_authority if entry.field_path == field_path)


def _planned_authority(execution, field_path: str):
    return next(entry for entry in execution.provisioning.realization_authority if entry.field_path == field_path)


def test_compiler_retains_closed_omissions_and_exact_leaf_precedence() -> None:
    closed = compile_runtime_model(_scenario("realization:\n  default: closed"))
    open_with_exact = compile_runtime_model(_scenario("realization:\n  default: open", web_os="linux"))

    closed_os = _compiled_authority(closed, "nodes.web.os")
    exact_os = _compiled_authority(open_with_exact, "nodes.web.os")

    assert closed_os.mode is RealizationAuthorityMode.CLOSED
    assert closed_os.source is RealizationResolutionSource.AUTHORED_SCOPE
    assert closed_os.governing_scope == "#/"
    assert exact_os.mode is RealizationAuthorityMode.EXACT
    assert exact_os.source is RealizationResolutionSource.AUTHORED_LEAF
    assert exact_os.governing_scope == "#/nodes/web/os"


def test_legacy_closed_and_delegated_defaults_remain_distinct_until_planning() -> None:
    legacy = compile_runtime_model(_scenario())
    delegated = compile_runtime_model(_scenario("realization:\n  default: unspecified"))

    legacy_os = _compiled_authority(legacy, "nodes.web.os")
    delegated_os = _compiled_authority(delegated, "nodes.web.os")

    assert legacy_os.mode is RealizationAuthorityMode.CLOSED
    assert legacy_os.source is RealizationResolutionSource.LEGACY_DEFAULT
    assert legacy_os.delegated is False
    assert delegated_os.mode is RealizationAuthorityMode.CLOSED
    assert delegated_os.source is RealizationResolutionSource.APPARATUS_DEFAULT
    assert delegated_os.delegated is True


def test_planner_resolves_delegation_and_carries_complete_authority() -> None:
    model = compile_runtime_model(_scenario("realization:\n  default: unspecified"))

    execution = plan(
        model,
        _manifest(),
        apparatus_realization_default=lambda _requirement, _manifest: Closure.OPEN_WORLD,
    )
    os_authority = _planned_authority(execution, "nodes.web.os")
    distribution_authority = _planned_authority(execution, "nodes.web.os_distribution")
    version_authority = _planned_authority(execution, "nodes.web.os_version")

    assert os_authority.mode is RealizationAuthorityMode.OPEN
    assert os_authority.source is RealizationResolutionSource.APPARATUS_DEFAULT
    assert distribution_authority.mode is RealizationAuthorityMode.OPEN
    assert distribution_authority.source is RealizationResolutionSource.APPARATUS_DEFAULT
    assert version_authority.mode is RealizationAuthorityMode.OPEN
    assert version_authority.source is RealizationResolutionSource.APPARATUS_DEFAULT
    assert not hasattr(os_authority, "delegated")
    assert len(execution.provisioning.realization_authority) == len(model.realization_authority)
    assert {entry.requirement_kind for entry in execution.provisioning.realization_authority} >= {
        "node-type",
        "os-family",
        "os-distribution",
        "os-version",
        "node-architecture",
        "runtime-environment",
    }


def test_planner_resolves_each_apparatus_default_once_for_demand_and_authority() -> None:
    model = compile_runtime_model(_scenario("realization:\n  default: unspecified"))
    calls: dict[tuple[str, str, str], int] = {}

    def stateful_default(requirement, _manifest):
        identity = (requirement.address, requirement.field_path, requirement.requirement_kind)
        calls[identity] = calls.get(identity, 0) + 1
        return Closure.OPEN_WORLD if calls[identity] == 1 else Closure.CLOSED_WORLD

    execution = plan(
        model,
        _manifest(),
        apparatus_realization_default=stateful_default,
    )
    delegated = {
        (requirement.address, requirement.field_path, requirement.requirement_kind)
        for requirement in model.realization_requirements
        if requirement.delegated
    }
    effective = {
        (requirement.address, requirement.field_path, requirement.requirement_kind)
        for requirement in execution.model.realization_requirements
        if (requirement.address, requirement.field_path, requirement.requirement_kind) in delegated
    }
    apparatus_authority = {
        (entry.address, entry.field_path, entry.requirement_kind): entry.mode
        for entry in execution.provisioning.realization_authority
        if entry.source is RealizationResolutionSource.APPARATUS_DEFAULT
    }

    assert calls == dict.fromkeys(delegated, 1)
    assert effective == delegated
    assert apparatus_authority == dict.fromkeys(delegated, RealizationAuthorityMode.OPEN)


def test_processor_derived_provisioning_requirement_uses_the_same_plan_authority() -> None:
    model = compile_runtime_model(
        parse_sdl(
            textwrap.dedent(
                """
                name: processor-derived-authority
                nodes:
                  worker: {type: compute, os: linux}
                generated_artifacts:
                  config:
                    generator: rendered_config
                    lifecycle: regenerate_on_change
                    provenance: config/template.yml
                    outputs:
                      - {name: config, path: config.yml, sensitivity: restricted}
                    consumers:
                      - {node: worker, mount_destination: /etc/app/config.yml, access_mode: read_only}
                """
            )
        )
    )
    compiled = next(entry for entry in model.realization_authority if entry.requirement_kind == "generated-artifact")
    execution = plan(model, create_stub_target().manifest)
    resolved = planned_realization_authority(
        execution.provisioning,
        "provision.generated-artifact.config",
        "generated-artifact",
    )

    assert compiled.mode is RealizationAuthorityMode.EXACT
    assert compiled.source is RealizationResolutionSource.PROCESSOR_DERIVED
    assert resolved is not None
    assert resolved.mode is RealizationAuthorityMode.EXACT
    assert resolved.payload_pointer == "/spec"
    assert realization_authority_diagnostics(execution.provisioning) == []

    missing = replace(
        execution.provisioning,
        realization_authority=tuple(
            entry
            for entry in execution.provisioning.realization_authority
            if entry.requirement_kind != "generated-artifact"
        ),
    )
    assert realization_authority_diagnostics(missing)[0].code == "realization.authority-incomplete"


def test_plan_projection_and_reverse_model_round_trip_authority_losslessly() -> None:
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), _manifest())

    projected = provisioning_plan_model(execution.provisioning)
    dumped = json.loads(projected.model_dump_json())
    restored = ProvisioningPlanModel.model_validate(dumped)

    assert restored.realization_authority == projected.realization_authority
    assert dumped["realization_authority"]
    assert dumped["realization_authority"][0]["payload_pointer"].startswith("/")


def test_published_plan_requires_realization_authority_even_when_empty() -> None:
    with pytest.raises(ValidationError):
        ProvisioningPlanModel.model_validate({"operations": [], "diagnostics": []})

    model = ProvisioningPlanModel.model_validate({"operations": [], "diagnostics": [], "realization_authority": []})
    assert model.realization_authority == []


def test_authority_contract_rejects_unbounded_constrained_and_bound_nonconstrained_modes() -> None:
    base = {
        "address": "provision.node.web",
        "field_path": "nodes.web.os",
        "domain": "runtime-realization",
        "requirement_kind": "os-family",
        "payload_pointer": "/os_family",
        "source": "authored-leaf",
        "provenance": "author-declared",
    }
    with pytest.raises(ValidationError):
        ResolvedRealizationAuthorityModel.model_validate({**base, "mode": "constrained", "bounds": []})
    with pytest.raises(ValidationError):
        ResolvedRealizationAuthorityModel.model_validate(
            {
                **base,
                "mode": "exact",
                "bounds": [{"value_pointer": "", "domain": {"kind": "enum", "values": ["linux"]}}],
            }
        )


def test_published_schema_rejects_the_same_invalid_mode_source_combinations() -> None:
    base = {
        "address": "provision.node.web",
        "field_path": "nodes.web.os",
        "domain": "runtime-realization",
        "requirement_kind": "os-family",
        "payload_pointer": "/os_family",
        "provenance": "author-declared",
        "bounds": [],
    }
    invalid_entries = [
        {**base, "mode": "constrained", "source": "authored-leaf"},
        {
            **base,
            "mode": "exact",
            "source": "authored-leaf",
            "bounds": [{"value_pointer": "", "domain": {"kind": "enum", "values": ["linux"]}}],
        },
        {**base, "mode": "open", "source": "legacy-default"},
        {**base, "mode": "exact", "source": "apparatus-default"},
    ]
    schema = schema_bundle()["provisioning-plan-v1"]
    operation = {
        "action": "create",
        "address": "provision.node.web",
        "resource_type": "node",
        "payload": {},
    }

    for entry in invalid_entries:
        with pytest.raises(ValidationError):
            ResolvedRealizationAuthorityModel.model_validate(entry)
        errors = list(
            Draft202012Validator(schema).iter_errors(
                {"operations": [operation], "diagnostics": [], "realization_authority": [entry]}
            )
        )
        assert errors


def test_total_lookup_preserves_typed_constraint_bounds() -> None:
    authority = ResolvedRealizationAuthority(
        address="provision.node.web",
        field_path="nodes.web.os",
        domain="runtime-realization",
        requirement_kind="os-family",
        payload_pointer="/os_family",
        mode=RealizationAuthorityMode.CONSTRAINED,
        source=RealizationResolutionSource.AUTHORED_LEAF,
        bounds=(
            RealizationAuthorityBound(
                value_pointer="",
                domain=EnumDomain(values=["linux", "windows"]),
            ),
        ),
    )
    from raes_contracts.planning import ProvisioningPlan

    plan_value = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.web",
                resource_type="node",
                payload={},
            )
        ],
        realization_authority=(authority,),
    )

    assert planned_realization_authority(plan_value, "provision.node.web", "os-family") is authority
    assert planned_realization_authority(plan_value, "provision.node.web", "node-type") is None


def test_authority_rejects_unknown_resolution_source_and_noncanonical_pointer() -> None:
    base = {
        "address": "provision.node.web",
        "field_path": "nodes.web.os",
        "domain": "runtime-realization",
        "requirement_kind": "os-family",
        "mode": "closed",
        "provenance": "author-declared",
        "bounds": [],
    }
    with pytest.raises(ValidationError):
        ResolvedRealizationAuthorityModel.model_validate(
            {**base, "payload_pointer": "os_family", "source": "legacy-default"}
        )
    with pytest.raises(ValidationError):
        ResolvedRealizationAuthorityModel.model_validate(
            {**base, "payload_pointer": "/os_family", "source": "backend-capability"}
        )


def _snapshot_from_plan(plan_value: ProvisioningPlan) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        realization_envelope=plan_value.realization_envelope,
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain="provisioning",
                resource_type=operation.resource_type,
                payload=deepcopy(operation.payload),
            )
            for operation in plan_value.operations
            if operation.action is not ChangeAction.DELETE
        },
    )


def _constrained_os_selection(
    plan_value: ProvisioningPlan,
    *,
    allowed_values: list[str],
) -> ProvisioningPlan:
    replacement = next(entry for entry in plan_value.realization_authority if entry.requirement_kind == "os-family")
    replacement = replace(
        replacement,
        mode=RealizationAuthorityMode.CONSTRAINED,
        # This fixture explicitly exercises the legacy scalar-bound contract.
        constraint_document=None,
        constraint_binding=None,
        source=RealizationResolutionSource.AUTHORED_LEAF,
        bounds=(
            RealizationAuthorityBound(
                value_pointer="",
                domain=EnumDomain(values=allowed_values),
            ),
        ),
    )
    return replace(
        plan_value,
        realization_authority=tuple(
            replacement if entry.requirement_kind == "os-family" else entry
            for entry in plan_value.realization_authority
        ),
    )


def test_registry_derived_completeness_rejects_missing_and_wrong_payload_authority() -> None:
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), _manifest())
    complete = execution.provisioning.realization_authority
    missing = replace(execution.provisioning, realization_authority=complete[:-1])
    wrong_entry = replace(complete[0], payload_pointer="/not-the-registered-path")
    wrong = replace(execution.provisioning, realization_authority=(wrong_entry, *complete[1:]))

    assert realization_authority_diagnostics(execution.provisioning) == []
    assert realization_authority_diagnostics(missing)[0].code == "realization.authority-incomplete"
    assert realization_authority_diagnostics(wrong)[0].code == "realization.authority-payload-pointer-invalid"


def test_registry_derived_completeness_rejects_excess_authority() -> None:
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), _manifest())
    extra = replace(
        execution.provisioning.realization_authority[0],
        field_path="generated_artifacts.unplanned",
        requirement_kind="generated-artifact",
        payload_pointer="/spec",
        mode=RealizationAuthorityMode.EXACT,
        source=RealizationResolutionSource.PROCESSOR_DERIVED,
        bounds=(),
    )
    excessive = replace(
        execution.provisioning,
        realization_authority=(*execution.provisioning.realization_authority, extra),
    )

    assert realization_authority_diagnostics(excessive)[0].code == "realization.authority-excess"


def test_manifest_readmission_rejects_unreconstructable_authority_demand() -> None:
    manifest = _manifest()
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), manifest)
    process_limits = next(
        entry
        for entry in execution.provisioning.realization_authority
        if entry.requirement_kind == "process-resource-limits"
    )
    invalid = replace(
        process_limits,
        mode=RealizationAuthorityMode.CONSTRAINED,
        source=RealizationResolutionSource.AUTHORED_LEAF,
        bounds=(
            RealizationAuthorityBound(
                identity_digest=f"sha256:{'0' * 64}",
                value_pointer="/soft",
                domain=EnumDomain(values=[1024, 2048]),
            ),
        ),
    )
    invalid_plan = replace(
        execution.provisioning,
        realization_authority=tuple(
            invalid if entry is process_limits else entry for entry in execution.provisioning.realization_authority
        ),
    )

    assert realization_authority_diagnostics(invalid_plan, manifest)[0].code == ("realization.authority-demand-invalid")


def test_materialization_reports_unresolved_delegated_authority() -> None:
    model = compile_runtime_model(_scenario("realization:\n  default: unspecified"))

    _, diagnostics = materialize_realization_authority(
        model,
        _manifest(),
        apparatus_decisions={},
    )

    assert diagnostics
    assert {diagnostic.code for diagnostic in diagnostics} == {"realization.authority-unresolved"}


def test_closed_omission_rejects_backend_materialization_and_emits_no_provenance() -> None:
    execution = plan(
        compile_runtime_model(_scenario("realization:\n  default: closed")),
        _manifest(RealizationSupportMode.EXACT_ONLY),
    )
    snapshot = _snapshot_from_plan(execution.provisioning)
    entry = snapshot.entries["provision.node.web"]
    payload = deepcopy(entry.payload)
    payload["spec"]["node"]["runtime"] = {"environment": [{"name": "EXCESS", "value": "1"}]}
    snapshot = snapshot.with_entries({**snapshot.entries, entry.address: replace(entry, payload=payload)})

    diagnostics, provenance = realization_authority_disclosure(
        execution.provisioning,
        snapshot,
        manifest=_manifest(RealizationSupportMode.EXACT_ONLY),
    )

    assert diagnostics[0].code == "runtime.backend-contract-invalid"
    assert diagnostics[0].address == "provision.node.web"
    assert not any(item.field_path == "nodes.web.runtime.environment" for item in provenance)


def test_open_selection_uses_plan_authority_and_discloses_backend_origin() -> None:
    from raes_contracts.realization_observation import (
        ObservedOperatingSystemIdentity,
        RealizationObservationDisclosure,
    )

    execution = plan(
        compile_runtime_model(
            _scenario("realization:\n  default: closed\n  scopes:\n    - {field_pointer: /nodes/web/os, posture: open}")
        ),
        _manifest(),
    )
    snapshot = _snapshot_from_plan(execution.provisioning)
    entry = snapshot.entries["provision.node.web"]
    payload = deepcopy(entry.payload)
    payload["os_family"] = "linux"
    snapshot = snapshot.with_entries({**snapshot.entries, entry.address: replace(entry, payload=payload)})
    snapshot = replace(
        snapshot,
        realization_observations=(
            RealizationObservationDisclosure(
                address=entry.address,
                field_path="nodes.web.operating-system",
                domain="runtime-realization",
                requirement_kind="operating-system",
                verification_scope=RealizationVerificationScope.PRESENCE,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
                operating_system=ObservedOperatingSystemIdentity(
                    family="linux",
                    distribution="ubuntu",
                    version="22.04",
                ),
                operation_id="op-open-authority-1",
                envelope_digest="sha256:" + "a" * 64,
                configuration_digest="sha256:" + "b" * 64,
                observer_version="guest-os-release/v1",
                sequence=1,
                binding_verified=True,
            ),
        ),
    )

    diagnostics, provenance = realization_authority_disclosure(
        execution.provisioning,
        snapshot,
        manifest=_manifest(),
    )

    assert diagnostics == []
    assert any(
        item.field_path == "nodes.web.os"
        and item.provenance.value == "backend-realized"
        and item.governing_scope == "#/nodes/web/os"
        for item in provenance
    )


def test_in_bound_constrained_selection_passes_pre_mutation_and_runtime_gates() -> None:
    from raes_contracts.realization_observation import (
        ObservedOperatingSystemIdentity,
        RealizationObservationDisclosure,
    )

    manifest = _manifest()
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), manifest)
    plan_value = _constrained_os_selection(
        execution.provisioning,
        allowed_values=["linux", "windows"],
    )

    assert planned_realization_selection_diagnostics(plan_value) == []

    snapshot = _snapshot_from_plan(plan_value)
    entry = snapshot.entries["provision.node.web"]
    payload = deepcopy(entry.payload)
    payload["os_family"] = "windows"
    snapshot = snapshot.with_entries({**snapshot.entries, entry.address: replace(entry, payload=payload)})
    snapshot = replace(
        snapshot,
        realization_observations=(
            RealizationObservationDisclosure(
                address=entry.address,
                field_path="nodes.web.operating-system",
                domain="runtime-realization",
                requirement_kind="operating-system",
                verification_scope=RealizationVerificationScope.PRESENCE,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
                operating_system=ObservedOperatingSystemIdentity(
                    family="windows",
                    distribution="windows-server",
                    version="2022",
                ),
                operation_id="op-constrained-authority-1",
                envelope_digest="sha256:" + "a" * 64,
                configuration_digest="sha256:" + "b" * 64,
                observer_version="guest-os-release/v1",
                sequence=1,
                binding_verified=True,
            ),
        ),
    )
    diagnostics, provenance = realization_authority_disclosure(
        plan_value,
        snapshot,
        manifest=manifest,
    )

    assert diagnostics == []
    assert any(
        entry.field_path == "nodes.web.os" and entry.provenance.value == "backend-realized" for entry in provenance
    )


def test_constrained_selection_must_belong_to_plan_bound() -> None:
    authority = ResolvedRealizationAuthority(
        address="provision.node.web",
        field_path="nodes.web.os",
        domain="runtime-realization",
        requirement_kind="os-family",
        payload_pointer="/os_family",
        mode=RealizationAuthorityMode.CONSTRAINED,
        source=RealizationResolutionSource.AUTHORED_LEAF,
        bounds=(
            RealizationAuthorityBound(
                value_pointer="",
                domain=EnumDomain(values=["linux", "windows"]),
            ),
        ),
    )
    baseline = plan(
        compile_runtime_model(_scenario(web_os="linux")),
        _manifest(),
    )
    authorities = tuple(
        authority if entry.requirement_kind == "os-family" else entry
        for entry in baseline.provisioning.realization_authority
    )
    plan_value = replace(baseline.provisioning, realization_authority=authorities)
    operation = plan_value.operations[0]
    observed_payload = deepcopy(operation.payload)
    observed_payload["os_family"] = "solaris"
    snapshot = RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain="provisioning",
                resource_type="node",
                payload=observed_payload,
            )
        }
    )

    diagnostics, provenance = realization_authority_disclosure(plan_value, snapshot, manifest=_manifest())

    assert diagnostics[0].code == "runtime.backend-contract-invalid"
    assert not any(item.field_path == "nodes.web.os" for item in provenance)


def test_direct_control_plane_submission_rejects_incomplete_authority_before_apply() -> None:
    target = create_stub_target()
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), target.manifest)
    incomplete = replace(execution.provisioning, realization_authority=())
    control_plane = RuntimeControlPlane(target)

    receipt = control_plane.submit_provisioning(incomplete)

    assert receipt.accepted is False
    assert receipt.diagnostics[0].code == "realization.authority-incomplete"
    assert control_plane.snapshot.entries == {}


def test_backend_apply_rejects_empty_authority_before_backend_mutation() -> None:
    target = create_stub_target()
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), target.manifest)
    incomplete = replace(execution.provisioning, realization_authority=())
    baseline = RuntimeSnapshot()
    calls = 0

    def backend(plan_value: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        nonlocal calls
        calls += 1
        return ApplyResult(success=True, snapshot=snapshot)

    result = _call_backend_apply(
        backend,
        incomplete,
        baseline,
        address="runtime.test.realization-authority",
        snapshot=baseline,
        realization=_RealizationApplyContext(plan=incomplete, manifest=target.manifest),
    )

    assert result.success is False
    assert result.snapshot == baseline
    assert result.diagnostics[0].code == "realization.authority-incomplete"
    assert calls == 0


def _unauthorized_os_selection(plan_value: ProvisioningPlan, mode: RealizationAuthorityMode) -> ProvisioningPlan:
    replacement = next(entry for entry in plan_value.realization_authority if entry.requirement_kind == "os-family")
    replacement = replace(
        replacement,
        mode=mode,
        bounds=(
            RealizationAuthorityBound(
                value_pointer="",
                domain=EnumDomain(values=["windows"]),
            ),
        )
        if mode is RealizationAuthorityMode.CONSTRAINED
        else (),
    )
    return replace(
        plan_value,
        realization_authority=tuple(
            replacement if entry.requirement_kind == "os-family" else entry
            for entry in plan_value.realization_authority
        ),
    )


@pytest.mark.parametrize(
    "mode",
    (RealizationAuthorityMode.CLOSED, RealizationAuthorityMode.CONSTRAINED),
)
def test_reference_adapter_rejects_unauthorized_selection_before_driver(mode: RealizationAuthorityMode) -> None:
    driver = InProcessDriver()
    target = create_reference_backend_target(driver=driver)
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), target.manifest)
    unauthorized = _unauthorized_os_selection(execution.provisioning, mode)

    result = target.provisioner.apply(unauthorized, RuntimeSnapshot())

    assert result.success is False
    assert result.diagnostics[0].code == "realization.authority-selection-invalid"
    assert driver.recorded_ops == []


def test_reference_adapter_sends_in_bound_constrained_selection_to_driver() -> None:
    driver = InProcessDriver()
    target = create_reference_backend_target(driver=driver)
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), target.manifest)
    authorized = _constrained_os_selection(
        execution.provisioning,
        allowed_values=["linux", "windows"],
    )
    authorized = replace(authorized, operation_id="issue-1067-reference-apply")

    result = target.provisioner.apply(authorized, RuntimeSnapshot())

    assert result.success is True
    assert any(operation.verb == "realize" for operation in driver.recorded_ops)


class _RecordingLibvirtDriver:
    driver_mode = "generic"

    def __init__(self) -> None:
        self.realize_calls: list[dict[str, object]] = []

    def realize(self, *, networks, domains):
        self.realize_calls.append({"networks": networks, "domains": domains})
        return LibvirtDriverResult()

    def destroy(self, *, networks, domains):
        return LibvirtDriverResult()

    def realized_addresses(self):
        return frozenset()


@pytest.mark.parametrize(
    "mode",
    (RealizationAuthorityMode.CLOSED, RealizationAuthorityMode.CONSTRAINED),
)
def test_libvirt_adapter_rejects_unauthorized_selection_before_driver(mode: RealizationAuthorityMode) -> None:
    driver = _RecordingLibvirtDriver()
    manifest = create_libvirt_manifest()
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), manifest)
    unauthorized = _unauthorized_os_selection(execution.provisioning, mode)

    result = LibvirtProvisioner(driver).apply(unauthorized, RuntimeSnapshot())

    assert result.success is False
    assert result.diagnostics[0].code == "realization.authority-selection-invalid"
    assert driver.realize_calls == []


def test_libvirt_adapter_sends_in_bound_constrained_selection_to_driver() -> None:
    driver = _RecordingLibvirtDriver()
    manifest = create_libvirt_manifest()
    execution = plan(compile_runtime_model(_scenario(web_os="linux")), manifest)
    authorized = _constrained_os_selection(
        execution.provisioning,
        allowed_values=["linux", "windows"],
    )

    LibvirtProvisioner(driver).apply(authorized, RuntimeSnapshot())

    assert len(driver.realize_calls) == 1


def test_nonclosed_authority_requires_a_selected_plan_and_manifest_envelope() -> None:
    manifest = replace(
        _manifest(),
        supported_contract_versions=frozenset({"backend-manifest-v2"}),
        realization_envelope=None,
    )
    execution = plan(
        compile_runtime_model(
            _scenario("realization:\n  default: closed\n  scopes:\n    - {field_pointer: /nodes/web/os, posture: open}")
        ),
        manifest,
    )

    diagnostics = realization_authority_diagnostics(execution.provisioning, manifest)
    runtime_diagnostics, _ = realization_authority_disclosure(
        execution.provisioning,
        _snapshot_from_plan(execution.provisioning),
        manifest=manifest,
    )

    assert diagnostics[0].code == "realization.authority-envelope-mismatch"
    assert runtime_diagnostics[0].code == "realization.authority-envelope-mismatch"


def test_backend_apply_uses_plan_authority_and_restores_baseline_on_closed_excess() -> None:
    manifest = _manifest(RealizationSupportMode.EXACT_ONLY)
    execution = plan(
        compile_runtime_model(_scenario("realization:\n  default: closed")),
        manifest,
    )
    baseline = RuntimeSnapshot()

    def materializing_backend(plan_value: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        returned = _snapshot_from_plan(plan_value)
        entry = returned.entries["provision.node.web"]
        payload = deepcopy(entry.payload)
        payload["spec"]["node"]["runtime"] = {"environment": [{"name": "EXCESS", "value": "1"}]}
        returned = returned.with_entries({**returned.entries, entry.address: replace(entry, payload=payload)})
        return ApplyResult(
            success=True,
            snapshot=returned,
            changed_addresses=[entry.address],
        )

    result = _call_backend_apply(
        materializing_backend,
        execution.provisioning,
        baseline,
        address="runtime.test.realization-authority",
        snapshot=baseline,
        realization=_RealizationApplyContext(
            plan=execution.provisioning,
            manifest=manifest,
        ),
    )

    assert result.success is False
    assert result.snapshot == baseline
    assert result.diagnostics[0].code == "runtime.backend-contract-invalid"


def test_apparatus_owned_state_is_not_reclassified_as_scenario_provenance() -> None:
    execution = plan(
        compile_runtime_model(
            _scenario("realization:\n  default: closed\n  scopes:\n    - {field_pointer: /nodes/web/os, posture: open}")
        ),
        _manifest(),
    )
    snapshot = _snapshot_from_plan(execution.provisioning)
    entry = snapshot.entries["provision.node.web"]
    payload = {**deepcopy(entry.payload), "provider_instance_id": "apparatus-owned"}
    snapshot = snapshot.with_entries({**snapshot.entries, entry.address: replace(entry, payload=payload)})

    diagnostics, provenance = realization_authority_disclosure(
        execution.provisioning,
        snapshot,
        manifest=_manifest(),
    )

    assert diagnostics == []
    assert all(item.requirement_kind != "provider-instance-id" for item in provenance)
