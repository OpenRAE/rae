"""Pinned plan-owned extension constraints share the recursive relation."""

from dataclasses import replace

import pytest
from raes_contracts.bounded_domains import EnumDomain
from raes_contracts.domain_profiles import (
    DomainProfileBindingBasis,
    DomainProfileBindingOwnerModel,
    DomainProfileBindingUse,
    DomainProfileOperation,
)
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationDomainValue,
    normalize_realization_literal,
    realization_constraint_binding,
)
from test_issue_1202_domain_profiles import _admitted, _binding, _context, _definition, _support


def _profiles(namespace="com.example.private"):
    from raes_contracts.realization_profiles import (
        PLAN_PROFILE_CONTRACT,
        PlanProfileAuthority,
        ProfileBindingConstraint,
    )

    definition = _definition(namespace=namespace, authority="urn:example:profiles", profile_id="resource-label")
    binding = _binding(definition, value={"name": "blue"}).model_copy(
        update={
            "owner": DomainProfileBindingOwnerModel(
                owning_contract_id=PLAN_PROFILE_CONTRACT,
                canonical_address="#/resources/provision.node.host",
                concept_family="resource-realization",
                lifecycle_phase="planning",
                context="artifact-acquisition",
                use="constraint",
            )
        }
    )
    document = normalize_realization_literal(
        binding.value,
        semantic_profile=definition.coordinate.definition_digest,
        default_closure=RealizationClosure(posture="closed", universe="profile-value", profile="test/v1"),
        leaf_constraints={"/name": RealizationDomainValue(kind="domain", domain=EnumDomain(values=["blue", "green"]))},
    ).document
    authority = PlanProfileAuthority(
        definitions=(_admitted(definition),),
        bindings=(binding,),
        constraints=(
            ProfileBindingConstraint(
                binding_path=(binding.binding_id,),
                document=document,
                source_binding=realization_constraint_binding(document, binding.value),
            ),
        ),
    )
    context = _context(definition, support_declarations=(_support(definition, *DomainProfileOperation),))
    return authority, context


@pytest.mark.parametrize("namespace", ["org.openrae.standard", "com.example.private"])
def test_plan_profile_carrier_retains_pins_and_null_safe_authenticated_roundtrip(namespace):
    from raes_contracts.contracts import ProvisioningPlanModel
    from raes_contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
    from raes_runtime.control_plane_api_models import _provisioning_plan
    from test_issue_1204_backend_preparation import _request

    authority, _ = _profiles(namespace)
    plan, _ = _request()
    plan = replace(plan, profile_authority=authority)
    wire = provisioning_plan_model(plan).model_dump(mode="json", exclude_none=True)
    restored = _provisioning_plan(ProvisioningPlanModel.model_validate(wire))
    assert restored.profile_authority == authority
    assert runtime_plan_digest(restored) == runtime_plan_digest(plan)
    altered = authority.model_copy(
        update={"bindings": (authority.bindings[0].model_copy(update={"value": {"name": "green"}}),)}
    )
    assert runtime_plan_digest(replace(plan, profile_authority=altered)) != runtime_plan_digest(plan)


def test_profile_admission_requires_independent_target_support_and_checks_recursive_value():
    from raes_contracts.realization_profiles import profile_authority_violation, profile_selection_violation

    authority, context = _profiles()
    assert profile_authority_violation(authority, context) is None
    assert profile_authority_violation(authority, context.model_copy(update={"support_declarations": ()}))
    selected = authority.bindings[0].model_copy(
        update={
            "value": {"name": "green"},
            "provenance": authority.bindings[0].provenance.model_copy(
                update={"basis": DomainProfileBindingBasis.BACKEND_SELECTED}
            ),
        }
    )
    assert profile_selection_violation(authority, (selected,), context) is None
    assert profile_selection_violation(authority, (selected.model_copy(update={"value": {"name": "red"}}),), context)
    assert profile_selection_violation(authority, (), context)


def _apply_profile_request(backend, *, negotiate=True):
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.realization_preparation import preparation_authority
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
    from test_issue_1204_backend_preparation import _request

    authority, _ = _profiles()
    plan, manifest = _request()
    if negotiate:
        from raes_contracts.realization_profiles import profile_context_digest

        manifest = replace(
            manifest,
            supported_contract_versions=manifest.supported_contract_versions | {"plan-realization-profiles-v1"},
            domain_profile_context_digest=profile_context_digest(_profiles()[1]),
        )
    plan = replace(plan, profile_authority=authority, preparation=preparation_authority(manifest))
    previous = RuntimeSnapshot(metadata={"trusted": ["predecessor"]})
    result = _call_backend_apply(
        backend.apply,
        plan,
        previous,
        snapshot=previous,
        address="runtime.test.profiles",
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )
    return previous, result


def test_unnegotiated_profile_host_fails_before_preparation_or_mutation():
    from test_issue_1204_backend_preparation import _PreparingBackend

    backend = _PreparingBackend()
    previous, result = _apply_profile_request(backend, negotiate=False)
    assert not result.success
    assert result.snapshot == previous
    assert (backend.prepares, backend.applies) == (0, 0)


def _profile_backend(*, choice="green", delivered=None, supported=True):
    from raes_contracts.domain_profiles import DomainProfileBindingProvenanceModel
    from test_issue_1204_backend_preparation import _PreparingBackend

    class ProfileBackend(_PreparingBackend):
        domain_profile_context = _profiles()[1] if supported else None

        def validate_profiles(self, plan):
            return []

        def prepare(self, plan, snapshot):
            response = super().prepare(plan, snapshot)
            binding = plan.profile_authority.bindings[0].model_copy(
                update={
                    "value": {"name": choice},
                    "provenance": DomainProfileBindingProvenanceModel(
                        basis="backend-selected", source_ref="urn:example:backend-selection"
                    ),
                }
            )
            return replace(
                response, operations=tuple(replace(op, profile_bindings=(binding,)) for op in response.operations)
            )

        def apply(self, plan, snapshot):
            result = super().apply(plan, snapshot)
            for op in plan.operations:
                bindings = op.profile_bindings
                if delivered:
                    bindings = (bindings[0].model_copy(update={"value": {"name": delivered}}),)
                result.snapshot.entries[op.address] = replace(
                    result.snapshot.entries[op.address], profile_bindings=bindings
                )
            return result

    return ProfileBackend()


@pytest.mark.parametrize(
    "choice,delivered,supported,accepted,applies",
    [
        ("green", None, True, True, 1),
        ("red", None, True, False, 0),
        ("green", None, False, False, 0),
        ("green", "blue", True, False, 1),
    ],
)
def test_prepared_profile_conjunction_and_actual_delivery(choice, delivered, supported, accepted, applies):
    backend = _profile_backend(choice=choice, delivered=delivered, supported=supported)
    previous, result = _apply_profile_request(backend)
    assert result.success is accepted, result.diagnostics
    assert backend.applies == applies
    if accepted:
        binding = next(iter(result.snapshot.entries.values())).profile_bindings[0]
        assert binding.value == {"name": "green"}
        assert binding.provenance.basis is DomainProfileBindingBasis.BACKEND_SELECTED
        assert result.snapshot.realization_observations == previous.realization_observations
    else:
        assert result.snapshot == previous
        assert result.changed_addresses == []


def test_profile_snapshot_codec_preserves_typed_backend_selected_values():
    from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload

    _, result = _apply_profile_request(_profile_backend())
    assert result.success
    restored = _snapshot_from_payload(_snapshot_payload(result.snapshot))
    assert restored == result.snapshot
    assert (
        next(iter(restored.entries.values())).profile_bindings[0].provenance.basis
        is DomainProfileBindingBasis.BACKEND_SELECTED
    )


def test_programmatic_compiler_and_planner_keep_profiles_without_sdl_syntax():
    from raes import parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan
    from test_issue_1204_backend_preparation import _request

    authority, context = _profiles()
    _, manifest = _request()
    from raes_contracts.realization_profiles import profile_context_digest

    manifest = replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions | {"plan-realization-profiles-v1"},
        domain_profile_context_digest=profile_context_digest(context),
    )
    scenario = parse_sdl("name: profiles\nnodes:\n  host: {type: compute}\n")
    model = compile_runtime_model(scenario, profile_authority=authority)
    execution = plan(model, manifest, profile_context=context)
    assert execution.provisioning.profile_authority == authority
    assert not [diagnostic for diagnostic in execution.diagnostics if diagnostic.is_error]
    assert execution.provisioning.operations[0].profile_bindings == authority.bindings
    unsupported = plan(model, manifest, profile_context=context.model_copy(update={"support_declarations": ()}))
    assert any(diagnostic.code == "realization.profile-unsupported" for diagnostic in unsupported.diagnostics)


def test_target_profile_trust_context_drift_is_refused_before_prepare():
    backend = _profile_backend()
    context = backend.domain_profile_context
    admissions = (context.namespace_admissions[0].model_copy(update={"trust_decision_id": "different-decision"}),)
    backend.domain_profile_context = context.model_copy(update={"namespace_admissions": admissions})
    previous, result = _apply_profile_request(backend)
    assert not result.success
    assert result.snapshot == previous
    assert (backend.prepares, backend.applies) == (0, 0)


def test_nested_standard_and_private_profiles_are_a_complete_conjunction():
    from raes_contracts.realization_profiles import profile_authority_violation, profile_selection_violation

    parent, first_context = _profiles("org.openrae.standard")
    child, second_context = _profiles()
    nested = child.bindings[0].model_copy(update={"binding_id": "nested"})
    binding = parent.bindings[0].model_copy(update={"children": (nested,)})
    authority = parent.model_copy(
        update={
            "bindings": (binding,),
            "definitions": (*parent.definitions, *child.definitions),
            "constraints": (
                *parent.constraints,
                child.constraints[0].model_copy(update={"binding_path": (binding.binding_id, "nested")}),
            ),
        }
    )
    context = first_context.model_copy(
        update={
            "namespace_admissions": (*first_context.namespace_admissions, *second_context.namespace_admissions),
            "definitions": (*first_context.definitions, *second_context.definitions),
            "support_declarations": (*first_context.support_declarations, *second_context.support_declarations),
        }
    )
    assert profile_authority_violation(authority, context) is None
    selected_child = nested.model_copy(
        update={
            "provenance": nested.provenance.model_copy(update={"basis": DomainProfileBindingBasis.BACKEND_SELECTED})
        }
    )
    selected = binding.model_copy(
        update={
            "children": (selected_child,),
            "provenance": binding.provenance.model_copy(update={"basis": DomainProfileBindingBasis.BACKEND_SELECTED}),
        }
    )
    assert profile_selection_violation(authority, (selected,), context) is None
    invalid = selected.model_copy(update={"children": (selected_child.model_copy(update={"value": {"name": "red"}}),)})
    assert profile_selection_violation(authority, (invalid,), context)
    assert profile_selection_violation(authority, (selected.model_copy(update={"children": ()}),), context)


@pytest.mark.parametrize("mutation", ["opaque", "owner", "observed", "definition", "constraint", "missing-support"])
def test_profile_authority_tampering_cannot_grant_execution(mutation):
    from raes_contracts.realization_profiles import profile_authority_violation

    authority, context = _profiles()
    binding = authority.bindings[0]
    if mutation == "opaque":
        binding = binding.model_copy(
            update={"owner": binding.owner.model_copy(update={"use": DomainProfileBindingUse.OPAQUE_EXCHANGE})}
        )
    elif mutation == "owner":
        binding = binding.model_copy(
            update={
                "owner": binding.owner.model_copy(update={"canonical_address": "#/resources/participant.agent.host"})
            }
        )
    elif mutation == "observed":
        binding = binding.model_copy(
            update={
                "provenance": binding.provenance.model_copy(
                    update={"basis": DomainProfileBindingBasis.OBSERVED, "evidence_refs": ("invented",)}
                )
            }
        )
    elif mutation == "definition":
        definition = authority.definitions[0].definition
        authority = authority.model_copy(
            update={
                "definitions": (
                    authority.definitions[0].model_copy(
                        update={"definition": definition.model_copy(update={"allowed_contexts": ("different",)})}
                    ),
                )
            }
        )
    elif mutation == "constraint":
        authority = authority.model_copy(
            update={
                "constraints": (authority.constraints[0].model_copy(update={"source_binding": "sha256:" + "0" * 64}),)
            }
        )
    else:
        context = context.model_copy(update={"support_declarations": ()})
    authority = authority.model_copy(update={"bindings": (binding,)})
    assert profile_authority_violation(authority, context)


def test_profile_binding_explicit_null_survives_plan_codec():
    from raes_contracts.contracts import ProvisioningPlanModel
    from raes_contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
    from raes_runtime.control_plane_api_models import _provisioning_plan
    from test_issue_1204_backend_preparation import _request

    authority, _ = _profiles()
    binding = authority.bindings[0].model_copy(update={"value": None})
    document = normalize_realization_literal(None, semantic_profile=binding.coordinate.definition_digest).document
    constraint = authority.constraints[0].model_copy(
        update={"document": document, "source_binding": realization_constraint_binding(document, None)}
    )
    authority = authority.model_copy(update={"bindings": (binding,), "constraints": (constraint,)})
    original, _ = _request()
    request = replace(original, profile_authority=authority)
    wire = provisioning_plan_model(request).model_dump(mode="json", exclude_none=True)
    assert "value" in wire["profile_authority"]["bindings"][0]
    assert wire["profile_authority"]["bindings"][0]["value"] is None
    restored = _provisioning_plan(ProvisioningPlanModel.model_validate(wire))
    assert runtime_plan_digest(restored) == runtime_plan_digest(request)


def test_profile_host_has_a_closed_published_contract():
    from jsonschema import Draft202012Validator
    from raes_contracts.contracts import schema_bundle

    schema = schema_bundle()["plan-realization-profiles-v1"]
    authority, _ = _profiles()
    validator = Draft202012Validator(schema)
    payload = authority.model_dump(mode="json")
    assert not list(validator.iter_errors(payload))
    payload["support_declarations"] = []
    assert list(validator.iter_errors(payload))


@pytest.mark.parametrize("contract_id", ["orchestration-plan-v1", "evaluation-plan-v1"])
def test_other_runtime_domains_do_not_gain_profile_execution_authority(contract_id):
    from jsonschema import Draft202012Validator
    from raes_contracts.contracts import schema_bundle

    binding = _profiles()[0].bindings[0]
    domain, resource_type = (
        ("orchestration", "script") if contract_id.startswith("orchestration") else ("evaluation", "assertion")
    )
    operation = {
        "action": "create",
        "address": f"{domain}.{resource_type}.main",
        "resource_type": resource_type,
        "payload": {},
    }
    validator = Draft202012Validator(schema_bundle()[contract_id])
    assert validator.is_valid({"operations": [operation]})
    operation["profile_bindings"] = [binding.model_dump(mode="json")]
    assert not validator.is_valid({"operations": [operation]})


def test_snapshot_profile_host_cannot_be_moved_to_another_runtime_domain():
    from pydantic import ValidationError
    from raes_contracts.contracts.realization_plans import SnapshotEntryModel

    with pytest.raises(ValidationError, match="profile"):
        SnapshotEntryModel(
            address="orchestration.script.main",
            domain="orchestration",
            resource_type="script",
            profile_bindings=_profiles()[0].bindings,
        )


def test_support_rows_without_a_profile_semantic_implementation_are_not_permission():
    backend = _profile_backend()
    backend.validate_profiles = None
    previous, result = _apply_profile_request(backend)
    assert not result.success
    assert result.snapshot == previous
    assert (backend.prepares, backend.applies) == (0, 0)


def test_installed_profile_semantics_must_accept_the_complete_selected_plan():
    from raes_contracts.diagnostics import Diagnostic

    backend = _profile_backend()
    calls = []

    def validate_profiles(plan):
        calls.append(plan.operations[0].profile_bindings[0].value)
        return [Diagnostic("test.semantic-refusal", "provisioning", "profiles", "Unsupported joint realization.")]

    backend.validate_profiles = validate_profiles
    previous, result = _apply_profile_request(backend)
    assert not result.success
    assert result.snapshot == previous
    assert calls == [{"name": "green"}]
    assert (backend.prepares, backend.applies) == (1, 0)


def test_optional_profile_carrier_preserves_legacy_native_constructor_arguments():
    from raes_processor.models import RuntimeModel

    model = RuntimeModel("legacy", {})
    assert model.feature_templates == {}
    assert model.profile_authority is None


def test_legacy_generic_operations_do_not_require_profile_fields():
    from dataclasses import asdict

    from raes import parse_sdl
    from raes_contracts.planning import PlanOperation
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_reference_backend import create_reference_backend_target
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
    from raes_runtime.manager import RuntimeManager

    target = create_reference_backend_target()
    request = RuntimeManager(target).plan(parse_sdl("name: legacy\nnodes:\n  host: {type: compute}\n")).provisioning
    operations = []
    for operation in request.operations:
        fields = asdict(operation)
        fields.pop("profile_bindings")
        operations.append(PlanOperation(**fields))
    request = replace(request, operations=operations)
    previous = RuntimeSnapshot()
    result = _call_backend_apply(
        target.provisioner.apply,
        request,
        previous,
        address="runtime.legacy",
        snapshot=previous,
        realization=_RealizationApplyContext(plan=request, manifest=target.manifest),
    )
    assert result.success, result.diagnostics
