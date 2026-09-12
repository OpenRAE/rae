"""Initial service state stays ordinary content with exact service realization."""

from __future__ import annotations

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from raes import SDLParseError, SDLValidationError, parse_sdl, parse_sdl_file
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_stubs.stubs import create_stub_manifest, create_stub_target
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import schema_bundle
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.models import resource_payload
from raes_processor.planner import plan
from raes_processor.semantics.realization import realization_disclosure
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget

REPO_ROOT = Path(__file__).resolve().parents[3]


def _direct_provisioning_plan(model, manifest: BackendManifest, operation: ProvisionOp) -> ProvisioningPlan:
    """Retain planner-resolved authority while exercising a direct operation."""

    planned = plan(model, manifest).provisioning
    return replace(
        planned,
        resources={},
        operations=[operation],
        diagnostics=[],
        realization_authority=tuple(
            authority for authority in planned.realization_authority if authority.address == operation.address
        ),
        realization_constraints=[
            constraint for constraint in planned.realization_constraints if constraint.address == operation.address
        ],
    )


def _scenario(*replacements: tuple[str, str]):
    source = """
name: initial-service-state
nodes:
  app:
    type: compute
    os: linux
    resources:
      ram: 1 gib
      cpu: 1
    services:
      - name: mail
        port: 143
  other:
    type: compute
    os: linux
    resources:
      ram: 1 gib
      cpu: 1
    services:
      - name: mail
        port: 143
deployment_tenants:
  range:
    description: one isolated range
deployment_cells:
  range-cell:
    tenant_ref: range
    node_refs: [app, other]
    cross_tenant_isolation: default_deny
content:
  messages:
    type: dataset
    target: app
    items:
      - name: welcome
    service_materialization:
      target_service_ref: nodes.app.services.mail
      interface_profile: service-content
      profile_version: "1"
      requirements:
        operation: ensure-owned-items
        conflict_policy: reject-unowned-collision
        readback: canonical-content-digest
      readback_assertion_refs: [messages-visible]
      evidence_requirement_refs: [service-readback]
      observation_boundary_refs: [participant-view]
propositions:
  messages-visible:
    description: The authored message set is visible through the service.
    subjects: [content.messages]
    basis: observed_state
    predicate:
      kind: boolean
      property: service-content-visible
      semantic_ref: urn:raes:observable:service-content-visible
      expected: true
    evidence_requirements: [service-readback]
assertions:
  messages-visible:
    proposition: messages-visible
    role: postcondition
observation_boundaries:
  participant-view:
    projection_basis: ordinary participant access to the named service
    observable_refs: [content.messages]
    redaction_policy: preserve authored participant-visible fields
    latency_profile: available before participant admission
evidence_requirements:
  service-readback:
    source_refs: [content.messages]
    scope: native service readback
    boundary_kind: participant_equivalent
    channel: api_response
    artifact_role: service_materialization_readback
    media_types: [application/json]
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
"""
    for old, new in replacements:
        source = source.replace(old, new)
    return parse_sdl(textwrap.dedent(source))


def _search_index_schema_scenario(*replacements: tuple[str, str]):
    profile_replacements = (
        ("    items:\n      - name: welcome\n", ""),
        ("interface_profile: service-content", "interface_profile: service-search-index-schema"),
        ("operation: ensure-owned-items", "operation: ensure-search-index-field-schema"),
        ("readback: canonical-content-digest", "readback: canonical-portable-field-schema-digest"),
        (
            "        readback: canonical-portable-field-schema-digest",
            "        readback: canonical-portable-field-schema-digest\n"
            "        field_semantics:\n"
            "          key: exact-token\n"
            "          status: exact-token\n"
            "          relations: exact-token",
        ),
    )
    return _scenario(*profile_replacements, *replacements)


def _manifest_with_profile(
    profile: str = "service-content-v1",
    requirement_kind: str | None = "service-content-materialization",
) -> BackendManifest:
    manifest = create_stub_manifest()
    provisioner = replace(
        manifest.provisioner,
        supported_service_materialization_profiles=frozenset({profile}),
    )
    realization_support = (
        tuple(
            replace(
                declaration,
                supported_exact_requirement_kinds=(
                    declaration.supported_exact_requirement_kinds | frozenset({requirement_kind})
                ),
            )
            for declaration in manifest.realization_support
        )
        if requirement_kind is not None
        else manifest.realization_support
    )
    return BackendManifest(
        identity=manifest.identity,
        supported_contract_versions=manifest.supported_contract_versions,
        compatibility=manifest.compatibility,
        realization_support=realization_support,
        concept_bindings=manifest.concept_bindings,
        constraints=manifest.constraints,
        capabilities=replace(manifest.capabilities, provisioner=provisioner),
        realization_envelope=manifest.realization_envelope,
    )


def test_search_index_schema_profile_is_typed_schema_only_desired_state() -> None:
    scenario = _search_index_schema_scenario()

    content = scenario.content["messages"]
    assert content.items == []
    assert content.source is None
    binding = content.service_materialization
    assert binding is not None
    assert binding.interface_profile == "service-search-index-schema"
    assert binding.requirements.field_semantics == {
        "key": "exact-token",
        "status": "exact-token",
        "relations": "exact-token",
    }


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            ("          key: exact-token", "          key: keyword"),
            "Input should be",
        ),
        (
            (
                "        field_semantics:\n"
                "          key: exact-token\n"
                "          status: exact-token\n"
                "          relations: exact-token",
                "        field_semantics: {}",
            ),
            "at least 1 item",
        ),
        (
            ("          relations: exact-token", "          relations: exact-token\n        native_mapping: {}"),
            "Extra inputs are not permitted",
        ),
        (
            ("    service_materialization:", "    items:\n      - name: forbidden\n    service_materialization:"),
            "must not carry source or items",
        ),
    ],
)
def test_search_index_schema_profile_rejects_non_portable_or_payload_shapes(
    replacement: tuple[str, str],
    message: str,
) -> None:
    with pytest.raises(SDLParseError, match=message):
        _search_index_schema_scenario(replacement)


def test_search_index_schema_compiles_portable_map_digest_and_exact_requirement() -> None:
    model = compile_scenario_runtime_model(_search_index_schema_scenario())

    placement = model.content_placements["provision.content.messages"]
    binding = placement.service_materialization
    assert binding is not None
    assert binding.interface_profile == "service-search-index-schema"
    assert binding.profile_version == "1"
    assert binding.operation == "ensure-search-index-field-schema"
    assert binding.conflict_policy == "reject-unowned-collision"
    assert binding.readback == "canonical-portable-field-schema-digest"
    assert binding.field_semantics == {
        "key": "exact-token",
        "status": "exact-token",
        "relations": "exact-token",
    }
    assert binding.canonical_field_schema_digest == canonical_json_digest(
        {
            "interface_profile": "service-search-index-schema",
            "profile_version": "1",
            "projection_scope": "declared-fields",
            "field_semantics": {
                "key": "exact-token",
                "status": "exact-token",
                "relations": "exact-token",
            },
        }
    )
    assert any(
        requirement.requirement_kind == "service-search-index-schema-materialization"
        and requirement.address == placement.address
        for requirement in model.realization_requirements
    )


def test_search_index_schema_digest_is_order_independent_and_semantic_sensitive() -> None:
    original = compile_scenario_runtime_model(_search_index_schema_scenario())
    reordered = compile_scenario_runtime_model(
        _search_index_schema_scenario(
            (
                "          key: exact-token\n          status: exact-token\n          relations: exact-token",
                "          relations: exact-token\n          key: exact-token\n          status: exact-token",
            )
        )
    )
    changed = compile_scenario_runtime_model(
        _search_index_schema_scenario(("          status: exact-token", "          status: full-text"))
    )

    original_binding = original.content_placements["provision.content.messages"].service_materialization
    reordered_binding = reordered.content_placements["provision.content.messages"].service_materialization
    changed_binding = changed.content_placements["provision.content.messages"].service_materialization
    assert original_binding is not None
    assert reordered_binding is not None
    assert changed_binding is not None
    assert original_binding.canonical_field_schema_digest == reordered_binding.canonical_field_schema_digest
    assert original_binding.canonical_field_schema_digest != changed_binding.canonical_field_schema_digest


def test_search_index_schema_profile_requires_separate_capability() -> None:
    model = compile_scenario_runtime_model(_search_index_schema_scenario())

    unsupported = plan(model, _manifest_with_profile())
    assert "provisioner.unsupported-service-materialization-profile" in {
        diagnostic.code for diagnostic in unsupported.diagnostics
    }
    supported = plan(
        model,
        _manifest_with_profile(
            "service-search-index-schema-v1",
            "service-search-index-schema-materialization",
        ),
    )
    assert "provisioner.unsupported-service-materialization-profile" not in {
        diagnostic.code for diagnostic in supported.diagnostics
    }


def test_search_index_schema_profile_is_published_in_every_scenario_contract() -> None:
    bundle = schema_bundle()

    for contract_id in (
        "sdl-authoring-input-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
        "scenario-satisfiability-evidence-v1",
    ):
        assert "service-search-index-schema" in str(bundle[contract_id])


def test_initial_service_state_example_covers_search_index_schema_profile() -> None:
    scenario = parse_sdl_file(REPO_ROOT / "examples" / "scenarios" / "initial-service-state.sdl.yaml")

    binding = scenario.content["job-index-schema"].service_materialization
    assert binding is not None
    assert binding.interface_profile == "service-search-index-schema"


def test_search_index_schema_profile_requires_separate_exact_realization_support() -> None:
    model = compile_scenario_runtime_model(_search_index_schema_scenario())

    unsupported = plan(
        model,
        _manifest_with_profile("service-search-index-schema-v1", None),
    )

    assert "realization.unsupported-exact-requirement" in {diagnostic.code for diagnostic in unsupported.diagnostics}
    authority = next(
        entry
        for entry in unsupported.provisioning.realization_authority
        if entry.requirement_kind == "service-search-index-schema-materialization"
    )
    assert authority.mode.value == "exact"
    assert authority.payload_pointer == "/service_materialization"


def test_direct_plan_submission_rejects_tampered_search_index_schema_digest() -> None:
    model = compile_scenario_runtime_model(_search_index_schema_scenario())
    placement = model.content_placements["provision.content.messages"]
    payload = resource_payload(placement)
    changed_payload = dict(payload)
    changed_binding = dict(changed_payload["service_materialization"])
    changed_binding["canonical_field_schema_digest"] = "sha256:" + "f" * 64
    changed_payload["service_materialization"] = changed_binding
    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address=placement.address,
        resource_type="content-placement",
        payload=changed_payload,
    )
    base_target = create_stub_target()
    manifest = _manifest_with_profile(
        "service-search-index-schema-v1",
        "service-search-index-schema-materialization",
    )
    target = RuntimeTarget(
        name=base_target.name,
        manifest=manifest,
        provisioner=base_target.provisioner,
        orchestrator=base_target.orchestrator,
        evaluator=base_target.evaluator,
        participant_runtime=base_target.participant_runtime,
    )

    result = RuntimeControlPlane(target).submit_provisioning(_direct_provisioning_plan(model, manifest, operation))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "provisioner.service-materialization-contract-invalid"
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", ""),
        ("source", False),
        ("items", ""),
        ("items", {}),
    ],
)
def test_direct_plan_submission_rejects_falsey_malformed_search_index_content(
    field: str,
    value: object,
) -> None:
    model = compile_scenario_runtime_model(_search_index_schema_scenario())
    placement = model.content_placements["provision.content.messages"]
    payload = resource_payload(placement)
    changed_payload = dict(payload)
    changed_spec = dict(changed_payload["spec"])
    changed_spec[field] = value
    changed_payload["spec"] = changed_spec
    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address=placement.address,
        resource_type="content-placement",
        payload=changed_payload,
    )

    target = create_stub_target()
    result = RuntimeControlPlane(target).submit_provisioning(
        _direct_provisioning_plan(model, target.manifest, operation)
    )

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "provisioner.service-materialization-contract-invalid"
    ]


def test_direct_plan_submission_requires_search_index_schema_readback() -> None:
    model = compile_scenario_runtime_model(_search_index_schema_scenario())
    placement = model.content_placements["provision.content.messages"]
    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address=placement.address,
        resource_type="content-placement",
        payload=resource_payload(placement),
    )
    base_target = create_stub_target()
    manifest = _manifest_with_profile(
        "service-search-index-schema-v1",
        "service-search-index-schema-materialization",
    )
    target = RuntimeTarget(
        name=base_target.name,
        manifest=manifest,
        provisioner=base_target.provisioner,
        orchestrator=base_target.orchestrator,
        evaluator=base_target.evaluator,
        participant_runtime=base_target.participant_runtime,
    )

    result = RuntimeControlPlane(target).submit_provisioning(_direct_provisioning_plan(model, manifest, operation))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "provisioner.service-materialization-readback-unsupported"
    ]


def test_direct_plan_submission_requires_search_index_schema_exact_support() -> None:
    model = compile_scenario_runtime_model(_search_index_schema_scenario())
    placement = model.content_placements["provision.content.messages"]
    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address=placement.address,
        resource_type="content-placement",
        payload=resource_payload(placement),
    )
    base_target = create_stub_target()
    manifest = _manifest_with_profile("service-search-index-schema-v1", None)
    target = RuntimeTarget(
        name=base_target.name,
        manifest=manifest,
        provisioner=base_target.provisioner,
        orchestrator=base_target.orchestrator,
        evaluator=base_target.evaluator,
        participant_runtime=base_target.participant_runtime,
    )

    result = RuntimeControlPlane(target).submit_provisioning(_direct_provisioning_plan(model, manifest, operation))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["realization.unsupported-exact-requirement"]


def test_service_content_profile_default_remains_backward_compatible() -> None:
    scenario = _scenario(("      interface_profile: service-content\n", ""))

    binding = scenario.content["messages"].service_materialization
    assert binding is not None
    assert binding.interface_profile == "service-content"
    payload = scenario.model_dump(mode="json", exclude_none=True)
    del payload["content"]["messages"]["service_materialization"]["interface_profile"]
    assert Draft202012Validator(schema_bundle()["sdl-authoring-input-v1"]).is_valid(payload)


def test_service_materialization_compiles_through_content_placement() -> None:
    model = compile_scenario_runtime_model(_scenario())

    placement = model.content_placements["provision.content.messages"]
    assert placement.target_address == "provision.node.app"
    assert placement.target_node == "app"
    binding = placement.service_materialization
    assert binding is not None
    assert binding.target_service_address == "provision.node.app.service.mail"
    assert binding.interface_profile == "service-content"
    assert binding.profile_version == "1"
    assert binding.operation == "ensure-owned-items"
    assert binding.conflict_policy == "reject-unowned-collision"
    assert binding.readback == "canonical-content-digest"
    assert binding.canonical_content_digest.startswith("sha256:")
    assert binding.readback_assertion_addresses == ("evaluation.assertion.messages-visible",)
    assert binding.evidence_requirement_refs == ("service-readback",)
    assert binding.observation_boundary_addresses == ("participant.observation-boundary.participant-view",)
    assert placement.ordering_dependencies == ("provision.node.app",)
    assert any(
        requirement.requirement_kind == "service-content-materialization" and requirement.address == placement.address
        for requirement in model.realization_requirements
    )
    provisioning = plan(model, _manifest_with_profile()).provisioning
    authority = next(
        entry
        for entry in provisioning.realization_authority
        if entry.requirement_kind == "service-content-materialization"
    )
    assert authority.address == placement.address
    assert authority.mode.value == "exact"


def test_backend_profile_support_is_separate_from_content_type_support() -> None:
    model = compile_scenario_runtime_model(_scenario())

    unsupported = plan(model, create_stub_manifest())
    assert "provisioner.unsupported-service-materialization-profile" in {
        diagnostic.code for diagnostic in unsupported.diagnostics
    }
    supported = plan(model, _manifest_with_profile())
    assert "provisioner.unsupported-service-materialization-profile" not in {
        diagnostic.code for diagnostic in supported.diagnostics
    }


def test_direct_plan_submission_repeats_profile_and_readback_admission() -> None:
    model = compile_scenario_runtime_model(_scenario())
    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address="provision.content.messages",
        resource_type="content-placement",
        payload={
            "target_address": "provision.node.app",
            "spec": {"type": "dataset"},
            "service_materialization": {
                "target_service_address": "provision.node.app.service.mail",
                "interface_profile": "service-content",
                "profile_version": "1",
                "content_type": "dataset",
                "operation": "ensure-owned-items",
                "conflict_policy": "reject-unowned-collision",
                "readback": "canonical-content-digest",
                "canonical_content_digest": "sha256:" + "a" * 64,
                "shared_service_relationship_ref": "",
                "consumer_tenant_ref": "",
                "mutable_state_owner": "",
                "reset_generation_owner": "",
                "readback_assertion_addresses": ["evaluation.assertion.messages-visible"],
                "evidence_requirement_refs": ["service-readback"],
                "observation_boundary_addresses": ["participant.observation-boundary.participant-view"],
            },
        },
    )
    base_target = create_stub_target()
    unsupported = RuntimeControlPlane(base_target).submit_provisioning(
        _direct_provisioning_plan(model, base_target.manifest, operation)
    )
    assert [diagnostic.code for diagnostic in unsupported.diagnostics] == [
        "provisioner.unsupported-service-materialization-profile"
    ]

    manifest = _manifest_with_profile()
    target = RuntimeTarget(
        name=base_target.name,
        manifest=manifest,
        provisioner=base_target.provisioner,
        orchestrator=base_target.orchestrator,
        evaluator=base_target.evaluator,
        participant_runtime=base_target.participant_runtime,
    )
    missing_readback = RuntimeControlPlane(target).submit_provisioning(
        _direct_provisioning_plan(model, manifest, operation)
    )
    assert [diagnostic.code for diagnostic in missing_readback.diagnostics] == [
        "provisioner.service-materialization-readback-unsupported"
    ]


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            ("readback_assertion_refs: [messages-visible]", "readback_assertion_refs: [missing]"),
            "readback_assertion_ref 'missing'",
        ),
        (
            ("observation_boundary_refs: [participant-view]", "observation_boundary_refs: [missing]"),
            "observation_boundary_ref 'missing'",
        ),
    ],
)
def test_service_materialization_readback_refs_fail_closed(
    replacement: tuple[str, str],
    message: str,
) -> None:
    with pytest.raises(SDLValidationError, match=message):
        _scenario(replacement)


def test_service_materialization_requires_a_named_service_target() -> None:
    with pytest.raises(SDLValidationError, match="must resolve to a named compute service"):
        _scenario(
            (
                "target_service_ref: nodes.app.services.mail",
                "target_service_ref: nodes.app.services.missing",
            )
        )


def test_service_materialization_target_must_belong_to_content_node() -> None:
    with pytest.raises(SDLValidationError, match="must belong to content target node"):
        _scenario(
            (
                "target_service_ref: nodes.app.services.mail",
                "target_service_ref: nodes.other.services.mail",
            )
        )


def test_runtime_rejects_changed_service_materialization_binding() -> None:
    model = compile_scenario_runtime_model(_scenario())
    placement = model.content_placements["provision.content.messages"]
    payload = resource_payload(placement)
    changed_payload = dict(payload)
    changed_binding = dict(changed_payload["service_materialization"])
    changed_binding["canonical_content_digest"] = "sha256:" + "f" * 64
    changed_payload["service_materialization"] = changed_binding
    returned = RuntimeSnapshot(
        entries={
            placement.address: SnapshotEntry(
                address=placement.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="content-placement",
                payload=changed_payload,
            )
        }
    )
    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "service-content-materialization"
    )

    diagnostics, provenance = realization_disclosure(
        (requirement,),
        ProvisioningPlan(
            operations=[
                ProvisionOp(
                    action=ChangeAction.CREATE,
                    address=placement.address,
                    resource_type="content-placement",
                    payload=payload,
                )
            ]
        ),
        returned,
    )

    assert provenance == ()
    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]


def test_module_composition_rewrites_service_materialization_refs(tmp_path: Path) -> None:
    payload = _scenario().model_dump(mode="json", exclude_none=True)
    payload["module"] = {
        "id": "raes/initial-service-state",
        "version": "1.0.0",
        "exports": {
            section: list(payload[section])
            for section in (
                "nodes",
                "content",
                "propositions",
                "assertions",
                "observation_boundaries",
                "evidence_requirements",
                "deployment_tenants",
                "deployment_cells",
            )
        },
    }
    imported = tmp_path / "initial-service-state.yaml"
    imported.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - path: initial-service-state.yaml
                namespace: shared
                version: 1.0.0
            """
        ),
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)
    binding = scenario.content["shared.messages"].service_materialization

    assert binding is not None
    assert binding.target_service_ref == "nodes.shared.app.services.mail"
    assert binding.readback_assertion_refs == ["shared.messages-visible"]
    assert binding.evidence_requirement_refs == ["shared.service-readback"]
    assert binding.observation_boundary_refs == ["shared.participant-view"]


def test_module_composition_preserves_search_index_field_semantics(tmp_path: Path) -> None:
    payload = _search_index_schema_scenario().model_dump(mode="json", exclude_none=True)
    payload["module"] = {
        "id": "raes/search-index-schema",
        "version": "1.0.0",
        "exports": {
            section: list(payload[section])
            for section in (
                "nodes",
                "content",
                "propositions",
                "assertions",
                "observation_boundaries",
                "evidence_requirements",
                "deployment_tenants",
                "deployment_cells",
            )
        },
    }
    imported = tmp_path / "search-index-schema.yaml"
    imported.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - path: search-index-schema.yaml
                namespace: shared
                version: 1.0.0
            """
        ),
        encoding="utf-8",
    )

    scenario = parse_sdl_file(root)
    binding = scenario.content["shared.messages"].service_materialization

    assert binding is not None
    assert binding.target_service_ref == "nodes.shared.app.services.mail"
    assert binding.requirements.field_semantics == {
        "key": "exact-token",
        "status": "exact-token",
        "relations": "exact-token",
    }
