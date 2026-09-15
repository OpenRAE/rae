"""Owner-specific typed selections preserve independent execution authority."""

from dataclasses import replace

import pytest
from pydantic import ValidationError
from raes.accounts import Account
from raes_contracts.domain_profiles import (
    DomainProfileBindingModel,
    DomainProfileDefinitionDraftModel,
    DomainProfileOperation,
    DomainProfileSchemaModel,
    seal_domain_profile_definition,
)
from raes_contracts.realization_profiles import profile_context_digest
from test_issue_1202_domain_profiles import _context, _support
from test_issue_1204_profile_carrier import _profiles


def _account_profile(
    semantic_contract=None, *, profile_context="account-materialization", value=None, address="provision.account.admin"
):
    value = value or {"mailbox_ref": "nodes.mail.runtime.mail_services.mail.mailboxes.admin"}
    authority, _ = _profiles()
    binding = authority.bindings[0]
    original = authority.definitions[0].definition
    definition = seal_domain_profile_definition(
        DomainProfileDefinitionDraftModel(
            identity=original.coordinate.model_dump(exclude={"definition_digest"}),
            profile_schema=DomainProfileSchemaModel(
                schema_id="urn:example:mailbox-profile",
                revision="1",
                schema_document={
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$id": "urn:example:mailbox-profile",
                    "type": "object",
                    "properties": {key: {"type": "string"} for key in value},
                    "required": list(value),
                    "additionalProperties": False,
                },
            ),
            semantic_contract=semantic_contract or original.semantic_contract,
            allowed_contexts=(profile_context,),
        )
    )
    context = _context(definition, support_declarations=(_support(definition, *DomainProfileOperation),))
    return binding.model_copy(
        update={
            "coordinate": definition.coordinate,
            "owner": binding.owner.model_copy(
                update={
                    "canonical_address": f"#/resources/{address}",
                    "context": profile_context,
                }
            ),
            "value": value,
        }
    ), context


def test_account_materialization_is_an_optional_existing_typed_binding():
    binding, _ = _account_profile()
    account = Account.model_validate(
        {"username": "admin", "node": "mail", "materialization_profile": binding.model_dump(mode="json")}
    )
    assert isinstance(account.materialization_profile, DomainProfileBindingModel)
    assert account.materialization_profile == binding
    assert Account(username="admin", node="mail").materialization_profile is None
    assert Account.model_validate(account.model_dump(mode="json")) == account


def test_private_service_selection_compiles_and_requires_target_support():
    from raes.scenario import Scenario
    from raes.validator import SemanticValidator
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan

    binding, context = _account_profile(
        profile_context="service-materialization", address="provision.content.seed", value={"format": "private"}
    )
    scenario = Scenario.model_validate(
        {
            "name": "private-content",
            "nodes": {"host": {"type": "compute"}},
            "content": {
                "seed": {"type": "file", "target": "host", "path": "/seed", "service_materialization": binding}
            },
        }
    )
    SemanticValidator(scenario).validate()
    model = compile_runtime_model(scenario)
    unsupported = plan(model, create_stub_manifest())
    assert any(item.code == "realization.profile-unsupported" for item in unsupported.diagnostics)
    manifest = create_stub_manifest()
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions
        | {"plan-realization-profiles-v1", "backend-realization-preparation-v1"},
        domain_profile_context_digest=profile_context_digest(context),
    )
    unadvertised = plan(model, manifest, profile_context=context)
    assert any(
        item.code == "provisioner.unsupported-service-materialization-profile" for item in unadvertised.diagnostics
    )
    manifest = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            provisioner=replace(
                manifest.capabilities.provisioner,
                supported_service_materialization_profiles=frozenset({binding.coordinate}),
            ),
        ),
    )
    supported = plan(model, manifest, profile_context=context)
    assert supported.provisioning.profile_authority.bindings == (binding,)
    assert supported.provisioning.resources["provision.content.seed"].profile_bindings == (binding,)


def test_private_domain_preserves_profile_and_core_authority_without_ad_names():
    from raes.scenario import Scenario
    from raes.validator import SemanticValidator
    from raes_backend_protocols.domain_topology import DomainTopologyBinding
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_contracts.profile_selections import authored_resource_profiles
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan

    binding, _ = _account_profile(profile_context="identity-domain", address="provision.domain-controller.corp.dc")
    scenario = Scenario.model_validate(
        {
            "name": "private-domain",
            "nodes": {"dc": {"type": "compute"}},
            "accounts": {"admin": {"node": "dc", "username": "admin"}},
            "identity_domains": {"corp": {"profile": binding, "authority_account_ref": "admin"}},
            "relationships": {
                "controller": {
                    "type": "domain_controller_for",
                    "source": "dc",
                    "target": "corp",
                    "domain_controller": {},
                }
            },
        }
    )
    SemanticValidator(scenario).validate()
    model = compile_runtime_model(scenario)
    topology = model.domain_controller_placements["provision.domain-controller.corp.dc"].domain_topology
    assert topology.profile == binding
    assert topology.authority_account_address == "provision.account.admin"
    from dataclasses import asdict

    assert DomainTopologyBinding.from_mapping(asdict(topology)) == topology
    execution = plan(model, create_stub_manifest())
    assert any(item.code == "realization.profile-unsupported" for item in execution.diagnostics)
    assert authored_resource_profiles(execution.provisioning.resources.values()) == (binding,)


def test_authored_account_profile_becomes_required_plan_authority():
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan
    from test_issue_673_account_credential_bindings import _account_payload, _scenario_with_account

    binding, context = _account_profile()
    account = _account_payload()
    account["materialization_profile"] = binding.model_dump(mode="json")
    model = compile_runtime_model(_scenario_with_account(account))
    manifest = create_stub_manifest()
    unsupported = plan(model, manifest)
    assert any(item.code == "realization.profile-unsupported" for item in unsupported.diagnostics)
    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions
        | {"plan-realization-profiles-v1", "backend-realization-preparation-v1"},
        domain_profile_context_digest=profile_context_digest(context),
    )
    supported = plan(model, manifest, profile_context=context)
    assert supported.provisioning.profile_authority.bindings == (binding,)
    operation = next(op for op in supported.provisioning.operations if op.address == "provision.account.admin")
    assert operation.profile_bindings == (binding,)


def test_direct_account_profile_without_negotiation_never_calls_backend():
    from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
    from raes_runtime.backend_calls import _call_backend_apply
    from test_issue_673_account_credential_bindings import _account_payload, _credential_plan

    binding, _ = _account_profile()
    account = _account_payload()
    account["materialization_profile"] = binding.model_dump(mode="json")
    request = _credential_plan(account)
    calls = []

    def apply(plan, snapshot):
        calls.append(plan)
        return ApplyResult(success=False, snapshot=snapshot)

    baseline = RuntimeSnapshot()
    result = _call_backend_apply(apply, request, baseline, snapshot=baseline, address="runtime.test.apply")
    assert not calls
    assert not result.success
    assert result.snapshot == baseline


def test_private_generator_uses_typed_binding_and_keeps_output_protection():
    from raes.stateful_resources import GeneratedArtifact

    binding, _ = _account_profile()
    binding = binding.model_copy(update={"owner": binding.owner.model_copy(update={"context": "artifact-generation"})})
    payload = {
        "generator": binding.model_dump(mode="json"),
        "lifecycle": "reuse_valid",
        "provenance": "urn:example:private-generator",
        "outputs": [{"name": "seed", "path": "seed.txt", "sensitivity": "restricted"}],
        "consumers": [
            {"node": "host", "mount_destination": "/seed", "access_mode": "read_only", "selected_outputs": ["seed"]}
        ],
    }
    artifact = GeneratedArtifact.model_validate(payload)
    assert artifact.generator == binding
    payload["outputs"][0]["disposition"] = "producer_private"
    with pytest.raises(ValidationError, match="producer-private"):
        GeneratedArtifact.model_validate(payload)


@pytest.mark.parametrize("kind", ["identity", "facade", "access", "federation", "service"])
def test_containing_identity_access_and_materialization_seams_accept_common_binding(kind):
    from raes.agents import ParticipantInteractiveAccess
    from raes.content import Content
    from raes.enterprise_identity import IdentityFacade, RelationshipIdentityFederation
    from raes.identity_domains import IdentityDomain

    binding, _ = _account_profile()
    raw = binding.model_dump(mode="json")
    constructors = {
        "identity": (IdentityDomain, {"profile": raw, "authority_account_ref": "authority"}, "profile"),
        "facade": (IdentityFacade, {"protocol": raw, "service_ref": "nodes.host.services.login"}, "protocol"),
        "access": (ParticipantInteractiveAccess, {"channel": raw, "target_ref": "host"}, "channel"),
        "federation": (
            RelationshipIdentityFederation,
            {
                "direction": "authority_to_facade",
                "protocol": raw,
                "mapping_intent": "groups_to_roles",
                "tenant_claim_name": "tenant",
                "tenant_claim_owner": "facade",
            },
            "protocol",
        ),
        "service": (
            Content,
            {"type": "file", "target": "host", "path": "/example", "service_materialization": raw},
            "service_materialization",
        ),
    }
    model, payload, field = constructors[kind]
    result = model.model_validate(payload)
    assert getattr(result, field) == binding
    assert model.model_validate(result.model_dump(mode="json")) == result


def test_private_generator_capability_retains_exact_coordinate():
    from raes_backend_protocols.capabilities import ProvisionerCapabilities
    from raes_backend_protocols.provisioner_manifest import provisioner_capability_payload
    from raes_contracts.contracts.capabilities import ProvisionerCapabilitiesModel

    binding, _ = _account_profile()
    capabilities = ProvisionerCapabilities(
        name="private-generator",
        supported_node_types=frozenset({"compute"}),
        supported_os_families=frozenset({"linux"}),
        supports_generated_artifacts=True,
        supported_generated_artifact_kinds=frozenset({binding.coordinate}),
    )
    assert binding.coordinate in capabilities.supported_generated_artifact_kinds
    wire = ProvisionerCapabilitiesModel.model_validate(provisioner_capability_payload(capabilities))
    assert wire.supported_generated_artifact_kinds == [binding.coordinate]


def _mailbox_case(semantics=None):
    from raes.scenario import Scenario
    from raes_contracts.account_materialization import ACCOUNT_MAILBOX_SEMANTICS
    from raes_reference_backend import create_reference_backend_target
    from raes_reference_backend.drivers.inprocess import InProcessDriver
    from raes_reference_backend.mailbox_materialization import InProcessMailboxSink
    from raes_runtime.manager import RuntimeManager
    from test_issue_673_account_credential_bindings import _account_payload

    binding, context = _account_profile(semantics or ACCOUNT_MAILBOX_SEMANTICS)
    account = _account_payload()
    account.update(node="mail", materialization_profile=binding.model_dump(mode="json"))
    scenario = Scenario.model_validate(
        {
            "name": "private-mailbox",
            "accounts": {"admin": account},
            "nodes": {
                "mail": {
                    "type": "compute",
                    "runtime": {
                        "mail_services": [
                            {
                                "mail_service_id": "mail",
                                "mailboxes": [
                                    {"mailbox_id": "admin", "address": "admin@example.test", "account_ref": "admin"}
                                ],
                            }
                        ]
                    },
                }
            },
        }
    )
    mailbox_ref = binding.value["mailbox_ref"]
    sink = InProcessMailboxSink(authorized_bindings=frozenset({("provision.account.admin", mailbox_ref)}))
    driver = InProcessDriver()
    target = create_reference_backend_target(domain_profile_context=context, mailbox_sink=sink, driver=driver)
    manager = RuntimeManager(target)
    execution = manager.plan(scenario)
    assert not [item for item in execution.diagnostics if item.is_error]
    return binding, sink, target, manager, execution, driver


def test_reference_mailbox_materialization_uses_an_authorized_sink_and_value_free_outputs():
    import json

    from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL, OPERATOR_REFERENCE

    binding, sink, target, manager, execution, driver = _mailbox_case()
    mailbox_ref = binding.value["mailbox_ref"]
    result = manager.apply(execution)
    assert result.success, result.diagnostics
    assert sink.authenticates(mailbox_ref, FIXTURE_SENTINEL)
    assert not sink.authenticates(mailbox_ref, "wrong-fixture")
    rendered = json.dumps(result.snapshot.entries["provision.account.admin"].payload)
    assert FIXTURE_SENTINEL not in rendered
    assert OPERATOR_REFERENCE not in rendered
    selected = result.snapshot.entries["provision.account.admin"].profile_bindings[0]
    assert selected.coordinate == binding.coordinate
    assert selected.provenance.basis.value == "backend-selected"
    assert manager.destroy().success
    assert not sink.authenticates(mailbox_ref, FIXTURE_SENTINEL)


@pytest.mark.parametrize("mutation", ["denied", "wrong-account", "wrong-target", "extra-service", "label-semantics"])
def test_mailbox_native_boundary_rejects_unsupported_semantics_before_driver_mutation(mutation):
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_reference_backend.profile_preparation import RESOURCE_LABEL_SEMANTICS

    binding, sink, target, manager, execution, driver = _mailbox_case(
        RESOURCE_LABEL_SEMANTICS if mutation == "label-semantics" else None
    )
    prepared = target.provisioner.prepare(execution.provisioning, RuntimeSnapshot())
    native_plan = replace(execution.provisioning, operations=list(prepared.operations))
    if mutation == "denied":
        sink.authorized_bindings = frozenset()
    elif mutation == "wrong-target":
        operation = next(item for item in native_plan.operations if item.resource_type == "account-placement")
        operation.payload["target_address"] = "provision.node.somewhere-else"
    elif mutation in {"wrong-account", "extra-service"}:
        service = execution.provisioning.resources["provision.node.mail"].payload["spec"]["node"]["runtime"][
            "mail_services"
        ][0]
        if mutation == "wrong-account":
            service["mailboxes"][0]["account_ref"] = "someone-else"
        else:
            service["engine"] = "unsupported-engine"
    result = target.provisioner.apply(native_plan, RuntimeSnapshot())
    assert not result.success
    assert not driver.recorded_ops
    assert not sink._verifiers


def test_private_generator_produces_bytes_and_enforces_consumer_projection():
    import hashlib

    from raes.scenario import Scenario
    from raes_contracts.artifact_generation import DIGEST_ARTIFACT_SEMANTICS
    from raes_reference_backend import create_reference_backend_target
    from raes_runtime.manager import RuntimeManager

    binding, context = _account_profile(
        DIGEST_ARTIFACT_SEMANTICS,
        profile_context="artifact-generation",
        value={"seed": "public-example"},
        address="provision.generated-artifact.seed",
    )
    scenario = Scenario.model_validate(
        {
            "name": "private-generator",
            "nodes": {"host": {"type": "compute"}},
            "generated_artifacts": {
                "seed": {
                    "generator": binding.model_dump(mode="json"),
                    "lifecycle": "reuse_valid",
                    "provenance": "urn:example:private-generator",
                    "outputs": [
                        {"name": "digest", "path": "digest.txt", "sensitivity": "public"},
                        {
                            "name": "private",
                            "path": "private.txt",
                            "sensitivity": "secret",
                            "disposition": "producer_private",
                        },
                    ],
                    "consumers": [
                        {
                            "node": "host",
                            "mount_destination": "/generated",
                            "access_mode": "read_only",
                            "selected_outputs": ["digest"],
                        }
                    ],
                }
            },
        }
    )
    target = create_reference_backend_target(domain_profile_context=context)
    manager = RuntimeManager(target)
    execution = manager.plan(scenario)
    assert not [item for item in execution.diagnostics if item.is_error]
    result = manager.apply(execution)
    assert result.success, result.diagnostics
    assert (
        target.provisioner.generated_output("provision.generated-artifact.seed", "provision.node.host", "digest")
        == hashlib.sha256(b"public-example").hexdigest().encode()
    )
    with pytest.raises(ValueError, match="consumer"):
        target.provisioner.generated_output("provision.generated-artifact.seed", "provision.node.host", "private")
    assert manager.destroy().success
    with pytest.raises(ValueError, match="consumer"):
        target.provisioner.generated_output("provision.generated-artifact.seed", "provision.node.host", "digest")
