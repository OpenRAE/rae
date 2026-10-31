"""Typed descriptor profiles are owned by their field and admitted by the target (#298, ADR-120)."""

from __future__ import annotations

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from raes import SDLValidationError, parse_sdl, parse_sdl_file
from raes_contracts.domain_profiles import (
    DomainProfileBindingModel,
    DomainProfileBindingProvenanceModel,
    DomainProfileOperation,
    DomainProfileSemanticContractModel,
    draft_domain_profile_definition,
    seal_domain_profile_definition,
)
from raes_contracts.realization_profiles import profile_context_digest
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from test_enterprise_deployment_tenancy import _valid_payload
from test_issue_1202_domain_profiles import _context, _schema, _support
from test_participant_interactive_access import _scenario as _access_scenario

_UNSUPPORTED = "realization.descriptor-profile-unsupported"
_VALIDATION = (DomainProfileOperation.STRUCTURAL_VALIDATION, DomainProfileOperation.SEMANTIC_VALIDATION)
_HOSTS = {
    "facade": ("identities", "identity-facade-protocol", "#/identity_facades/workforce-oidc/protocol"),
    "trust": ("relationships", "forest-trust-type", "#/relationships/partner-trust/forest_trust/trust_type"),
    "federation-protocol": (
        "relationships",
        "identity-federation-protocol",
        "#/relationships/workforce-federation/identity_federation/protocol",
    ),
    "federation-mapping": (
        "relationships",
        "identity-federation-mapping-intent",
        "#/relationships/workforce-federation/identity_federation/mapping_intent",
    ),
    "channel": (
        "relationships",
        "participant-interactive-access-channel",
        "#/agents/blue-participant/interactive_access/console/channel",
    ),
}
_HOST_IDS = tuple(_HOSTS)


def _definition(context: str):
    return seal_domain_profile_definition(
        draft_domain_profile_definition(
            namespace="com.example.private",
            authority="urn:example:profiles",
            profile_id="descriptor",
            revision="1.0.0",
            schema=_schema(title="descriptor"),
            semantic_contract=DomainProfileSemanticContractModel(
                authority="urn:example:profiles",
                contract_id="descriptor-semantics",
                revision="1.0.0",
                digest="sha256:" + "4" * 64,
            ),
            allowed_contexts=(context,),
        )
    )


def _binding(
    host: str, *, value: object = None, binding_id: str = "selection", **owner: str
) -> DomainProfileBindingModel:
    family, context, pointer = _HOSTS[host]
    return DomainProfileBindingModel(
        binding_id=binding_id,
        coordinate=_definition(context).coordinate,
        owner={
            "owning_contract_id": "sdl-authoring-input-v1",
            "canonical_address": pointer,
            "concept_family": family,
            "lifecycle_phase": "authoring",
            "context": context,
            "use": "constraint",
            **owner,
        },
        value={"name": "blue"} if value is None else value,
        provenance={"basis": "author-supplied", "source_ref": "urn:example:author"},
    )


def _target_context(host: str, *operations: DomainProfileOperation):
    definition = _definition(_HOSTS[host][1])
    return _context(definition, support_declarations=(_support(definition, *(operations or _VALIDATION)),))


def _enterprise_payload() -> dict[str, object]:
    payload = _valid_payload()
    payload["nodes"]["partner-dc"] = {
        "type": "compute",
        "os": "windows",
        "endpoint_persona": "service",
        "services": [{"name": "ldap", "port": 389}],
    }
    payload["accounts"]["partner-admin"] = {"username": "Administrator", "node": "partner-dc"}
    payload["identity_domains"]["partner-corp"] = {
        "profile": "active_directory",
        "dns_name": "partner.example",
        "netbios_name": "PARTNER",
        "authority_account_ref": "partner-admin",
    }
    payload["identity_forests"]["partner"] = {"root_domain_ref": "partner-corp", "domain_refs": ["partner-corp"]}
    payload["deployment_cells"]["range-a-cell"]["node_refs"].append("partner-dc")
    payload["relationships"]["partner-dc-role"] = {
        "type": "domain_controller_for",
        "source": "partner-dc",
        "target": "partner-corp",
        "domain_controller": {},
    }
    payload["relationships"]["partner-trust"] = {
        "type": "forest_trusts",
        "source": "enterprise",
        "target": "partner",
        "forest_trust": {"trust_type": "forest", "direction": "bidirectional"},
    }
    return payload


def _payload(host: str, selection: object) -> dict[str, object]:
    raw = selection.model_dump(mode="json") if isinstance(selection, DomainProfileBindingModel) else selection
    if host == "channel":
        payload = yaml.safe_load(_access_scenario())
        payload["agents"]["blue-participant"]["interactive_access"] = {
            "console": {"target_ref": "workstation", "channel": raw, "account_ref": "operator"}
        }
        return payload
    payload = _enterprise_payload()
    relationships = payload["relationships"]
    if host == "facade":
        payload["identity_facades"]["workforce-oidc"]["protocol"] = raw
    elif host == "trust":
        relationships["partner-trust"]["forest_trust"]["trust_type"] = raw
    else:
        field = "protocol" if host == "federation-protocol" else "mapping_intent"
        relationships["workforce-federation"]["identity_federation"][field] = raw
    return payload


def _parse(host: str, selection: object):
    return parse_sdl(yaml.safe_dump(_payload(host, selection), sort_keys=False))


def _manifest(context=None):
    from raes_backend_stubs.stubs import create_stub_manifest

    manifest = create_stub_manifest()
    if context is None:
        return manifest
    return replace(
        manifest,
        supported_contract_versions=manifest.supported_contract_versions
        | {"plan-realization-profiles-v1", "backend-realization-preparation-v1"},
        domain_profile_context_digest=profile_context_digest(context),
    )


def _codes(execution_plan) -> set[str]:
    return {item.code for item in execution_plan.diagnostics}


@pytest.mark.parametrize("host", _HOST_IDS)
def test_field_owned_binding_validates_and_compiles_into_the_descriptor_tuple(host):
    binding = _binding(host)
    model = compile_runtime_model(_parse(host, binding))
    assert model.descriptor_profile_bindings == (binding,)


@pytest.mark.parametrize("host", _HOST_IDS)
@pytest.mark.parametrize(
    "owner",
    [
        {"owning_contract_id": "plan-realization-profiles-v1"},
        {"canonical_address": "#/resources/provision.account.admin"},
        {"concept_family": "resource-realization"},
        {"lifecycle_phase": "planning"},
        {"context": "account-materialization"},
        {"use": "annotation"},
    ],
    ids=["contract", "address", "family", "phase", "context", "use"],
)
def test_binding_owned_by_anything_but_its_field_fails_validation(host, owner):
    with pytest.raises(SDLValidationError, match="typed profile binding must be owned by its own field"):
        _parse(host, _binding(host, **owner))


@pytest.mark.parametrize("host", _HOST_IDS)
def test_binding_owner_of_another_descriptor_field_fails_validation(host):
    other = next(item for item in _HOST_IDS if item != host)
    family, context, pointer = _HOSTS[other]
    with pytest.raises(SDLValidationError, match="typed profile binding must be owned by its own field"):
        _parse(host, _binding(host, canonical_address=pointer, concept_family=family, context=context))


def test_nested_binding_must_keep_its_parent_owner():
    parent = _binding("channel")
    child = _binding("channel", binding_id="child", canonical_address="#/agents/other/interactive_access/x/channel")
    with pytest.raises(SDLValidationError, match="typed profile binding must be owned by its own field"):
        _parse("channel", parent.model_copy(update={"children": (child,)}))
    owned = parent.model_copy(update={"children": (_binding("channel", binding_id="child"),)})
    assert compile_runtime_model(_parse("channel", owned)).descriptor_profile_bindings == (owned,)


def test_backend_selected_provenance_is_not_an_authored_descriptor():
    binding = _binding("facade").model_copy(
        update={
            "provenance": DomainProfileBindingProvenanceModel(
                basis="backend-selected", source_ref="urn:example:backend"
            )
        }
    )
    with pytest.raises(SDLValidationError, match="typed profile binding must be owned by its own field"):
        _parse("facade", binding)


@pytest.mark.parametrize("host", _HOST_IDS)
def test_unadmitted_binding_is_refused_before_mutation(host):
    model = compile_runtime_model(_parse(host, _binding(host)))
    context = _target_context(host)

    without_context = plan(model, _manifest())
    assert _UNSUPPORTED in _codes(without_context)
    assert not without_context.is_valid

    uncommitted = plan(model, _manifest(), profile_context=context)
    assert _UNSUPPORTED in _codes(uncommitted)

    stale = plan(model, _manifest(_target_context("facade" if host != "facade" else "trust")), profile_context=context)
    assert _UNSUPPORTED in _codes(stale)

    unsupported = _target_context(host, DomainProfileOperation.STRUCTURAL_VALIDATION)
    assert _UNSUPPORTED in _codes(plan(model, _manifest(unsupported), profile_context=unsupported))

    assert _UNSUPPORTED not in _codes(plan(model, _manifest(context), profile_context=context))


@pytest.mark.parametrize("host", _HOST_IDS)
def test_definition_for_another_field_context_is_refused(host):
    other = next(item for item in _HOST_IDS if _HOSTS[item][1] != _HOSTS[host][1])
    definition = _definition(_HOSTS[other][1])
    binding = _binding(host).model_copy(update={"coordinate": definition.coordinate})
    model = compile_runtime_model(_parse(host, binding))
    context = _context(definition, support_declarations=(_support(definition, *_VALIDATION),))
    assert _UNSUPPORTED in _codes(plan(model, _manifest(context), profile_context=context))


def test_value_outside_the_pinned_schema_is_refused_and_not_echoed():
    secret = {"host": "10.0.0.5", "port": 2222, "password": "hunter2"}
    model = compile_runtime_model(_parse("channel", _binding("channel", value=secret)))
    context = _target_context("channel")
    refused = plan(model, _manifest(context), profile_context=context)
    diagnostics = [item for item in refused.diagnostics if item.code == _UNSUPPORTED]
    assert diagnostics
    assert all("hunter2" not in item.message and "10.0.0.5" not in item.message for item in diagnostics)


def test_admitted_channel_grants_no_account_or_endpoint():
    binding = _binding("channel")
    model = compile_runtime_model(_parse("channel", binding))
    participant = next(iter(model.participant_behaviors.values()))
    (access,) = participant.interactive_access
    assert access.channel == binding
    assert access.account_address == "provision.account.operator"
    context = _target_context("channel")
    admitted = plan(model, _manifest(context), profile_context=context)
    assert _UNSUPPORTED not in _codes(admitted)
    assert admitted.model.participant_behaviors == model.participant_behaviors
    source = _payload("channel", binding)
    source["agents"]["blue-participant"]["starting_accounts"] = []
    with pytest.raises(SDLValidationError, match="not in starting_accounts"):
        parse_sdl(yaml.safe_dump(source))


def test_built_in_descriptor_values_need_no_profile_context():
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(_enterprise_payload(), sort_keys=False)))
    assert model.descriptor_profile_bindings == ()
    assert _UNSUPPORTED not in _codes(plan(model, _manifest()))


def test_runtime_rechecks_descriptor_admission_after_plan_diagnostics_are_removed():
    from raes_backend_stubs.stubs import create_stub_target
    from raes_runtime.manager import RuntimeManager

    target = create_stub_target()
    manager = RuntimeManager(target)
    snapshot = manager.snapshot
    model = compile_runtime_model(_parse("facade", _binding("facade")))
    prepared = plan(model, target.manifest, snapshot)
    assert _UNSUPPORTED in _codes(prepared)
    result = manager.apply(replace(prepared, diagnostics=[]))
    assert not result.success
    assert result.snapshot == snapshot
    assert _UNSUPPORTED in {item.code for item in result.diagnostics}


def test_model_refuses_a_compiled_typed_channel_outside_the_descriptor_tuple():
    model = compile_runtime_model(_parse("channel", _binding("channel")))
    with pytest.raises(ValueError, match="descriptor profile"):
        replace(model, descriptor_profile_bindings=())


def test_imported_unit_keeps_a_field_owned_binding_after_namespacing(tmp_path: Path):
    unit = _payload("channel", _binding("channel"))
    unit["module"] = {
        "id": "raes/access",
        "version": "1.0.0",
        "exports": {"agents": ["blue-participant"], "nodes": ["workstation"], "accounts": ["operator"]},
    }
    (tmp_path / "unit.yaml").write_text(yaml.safe_dump(unit, sort_keys=False), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - path: unit.yaml
                namespace: alpha
                version: 1.0.0
            """
        ),
        encoding="utf-8",
    )
    scenario = parse_sdl_file(root)
    channel = scenario.agents["alpha.blue-participant"].interactive_access["console"].channel
    assert channel.owner.canonical_address == "#/agents/alpha.blue-participant/interactive_access/console/channel"
    assert compile_runtime_model(scenario).descriptor_profile_bindings == (channel,)


def test_imported_unit_with_a_foreign_owner_fails_in_the_importer(tmp_path: Path):
    unit = _payload("facade", _binding("facade"))
    unit["module"] = {
        "id": "raes/enterprise",
        "version": "1.0.0",
        "exports": {"identity_facades": ["workforce-oidc"]},
    }
    standalone = _binding("facade", canonical_address="#/identity_facades/other/protocol")
    unit["identity_facades"]["workforce-oidc"]["protocol"] = standalone.model_dump(mode="json")
    (tmp_path / "unit.yaml").write_text(yaml.safe_dump(unit, sort_keys=False), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - path: unit.yaml\n    namespace: alpha\n    version: 1.0.0\n",
        encoding="utf-8",
    )
    with pytest.raises(SDLValidationError, match="typed profile binding must be owned by its own field"):
        parse_sdl_file(root)


@pytest.mark.parametrize(
    "address",
    [
        "#",
        "#/resources/provision.account.admin",
        "#/identity_facades//protocol",
        "#/identity_facades/workforce-oidc/service_ref",
        "#/agents/blue-participant/interactive_access//channel",
    ],
)
def test_admission_refuses_a_binding_that_no_descriptor_field_owns(address):
    from raes.descriptor_profiles import descriptor_profiles_admitted

    context = _target_context("facade")
    digest = profile_context_digest(context)
    assert descriptor_profiles_admitted((_binding("facade"),), context, digest)
    assert not descriptor_profiles_admitted((_binding("facade", canonical_address=address),), context, digest)


def test_admission_refuses_unbounded_input_and_needs_nothing_for_no_bindings():
    from raes.descriptor_profiles import (
        DESCRIPTOR_PROFILE_HOSTS,
        descriptor_owner_violation,
        descriptor_profiles_admitted,
    )

    context = _target_context("facade")
    digest = profile_context_digest(context)
    assert descriptor_profiles_admitted((), None, None)
    assert not descriptor_profiles_admitted(("not-a-binding",), context, digest)
    assert not descriptor_profiles_admitted((_binding("facade"),), "not-a-context", digest)
    deep = _binding("facade")
    for depth in range(17):
        deep = _binding("facade", binding_id=f"level-{depth}").model_copy(update={"children": (deep,)})
    host = DESCRIPTOR_PROFILE_HOSTS[0]
    assert descriptor_owner_violation(deep, host, _HOSTS["facade"][2])
