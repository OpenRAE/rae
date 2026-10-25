"""Private selections keep core authority, disclosure, and lifecycle rules."""

import json

import pytest
import yaml
from raes import SDLValidationError, parse_sdl
from raes_processor.compiler import compile_runtime_model
from test_issue_1208_profile_selections import _account_profile, _mailbox_case


def test_private_access_preserves_typing_and_cannot_expand_account_authority():
    from test_participant_interactive_access import _scenario

    binding, _ = _account_profile()
    source = yaml.safe_load(_scenario())
    agent = source["agents"]["blue-participant"]
    agent["interactive_access"] = {
        "console": {"target_ref": "workstation", "channel": binding.model_dump(mode="json"), "account_ref": "operator"}
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    participant = next(iter(model.participant_behaviors.values()))
    assert participant.interactive_access[0].channel == binding
    assert participant.interactive_access[0].account_address == "provision.account.operator"
    agent["starting_accounts"] = []
    invalid_source = yaml.safe_dump(source)
    with pytest.raises(SDLValidationError, match="not in starting_accounts"):
        parse_sdl(invalid_source)
    agent["starting_accounts"] = ["operator"]
    agent["interactive_access"]["duplicate"] = dict(agent["interactive_access"]["console"])
    duplicate_source = yaml.safe_dump(source)
    with pytest.raises(SDLValidationError, match="duplicates interactive_access"):
        parse_sdl(duplicate_source)


def test_mailbox_public_plan_api_and_durable_snapshot_keep_typed_selection_without_material():
    from raes_cli.processor import _execution_plan_payload
    from raes_contracts.runtime_state import RuntimeSnapshotEnvelope
    from raes_runtime.control_plane_api_models import _snapshot_model
    from raes_runtime.control_plane_store import _snapshot_payload
    from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL, OPERATOR_REFERENCE

    binding, _, manager, execution = _mailbox_case()
    public_plan = _execution_plan_payload(execution)
    result = manager.apply(execution)
    assert result.success
    persisted = _snapshot_payload(result.snapshot)
    published = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=result.snapshot)).model_dump(mode="json")
    for payload in (public_plan, persisted, published):
        rendered = json.dumps(payload)
        assert FIXTURE_SENTINEL not in rendered
        assert OPERATOR_REFERENCE not in rendered
    assert binding.coordinate.definition_digest in json.dumps(persisted)
    assert binding.coordinate.definition_digest in json.dumps(published)


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "bytes"),
        ("accounting_mode", "lease"),
        ("meter_profile_ref", "urn:example:wrong-meter"),
        ("reset", "episode"),
    ],
)
def test_private_resource_measure_rejects_changed_quantity_semantics(field, value):
    from raes_contracts.resource_measure_profiles import resource_measure_supported
    from test_issue_1208_resource_profiles import _resource_profile

    kind, context = _resource_profile()
    request = {
        "unit": "packets",
        "accounting_mode": "cumulative_counter",
        "meter_profile_ref": "urn:example:packet-meter:1",
        "reset": "run",
    }
    assert resource_measure_supported(kind, context=context, **request)
    request[field] = value
    assert not resource_measure_supported(kind, context=context, **request)


def test_abstract_model_creates_no_profile_or_capture_obligation():
    from raes_backend_stubs.stubs import create_stub_target
    from raes_runtime.manager import RuntimeManager

    scenario = parse_sdl("name: abstract-model\nnodes:\n  host:\n    type: compute\n")
    manager = RuntimeManager(create_stub_target())
    execution = manager.plan(scenario)
    assert not [item for item in execution.diagnostics if item.is_error]
    assert execution.provisioning.profile_authority is None
    assert all(not item.profile_bindings for item in execution.provisioning.operations)
    assert not scenario.evidence_requirements
    assert manager.apply(execution).success


def test_profile_capabilities_round_trip_exact_coordinates_alongside_builtins():
    from dataclasses import replace

    from raes_backend_protocols.provisioner_manifest import provisioner_capability_payload, provisioner_from_model
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_contracts.contracts import ProvisionerCapabilitiesModel

    binding, _ = _account_profile()
    base = create_stub_manifest().capabilities.provisioner
    capabilities = replace(
        base,
        supported_domain_profiles=base.supported_domain_profiles | {binding.coordinate},
        supported_service_materialization_profiles=base.supported_service_materialization_profiles
        | {binding.coordinate},
    )
    model = ProvisionerCapabilitiesModel.model_validate(provisioner_capability_payload(capabilities))
    assert provisioner_from_model(model) == capabilities
    invalid_profiles = frozenset({123})
    with pytest.raises(ValueError, match="pinned coordinates"):
        replace(base, supported_domain_profiles=invalid_profiles)


def test_private_domain_schema_keeps_active_directory_names_conditional():
    from jsonschema import Draft202012Validator
    from pydantic import ValidationError
    from raes.identity_domains import IdentityDomain

    validator = Draft202012Validator(IdentityDomain.model_json_schema())
    binding, _ = _account_profile()
    private = {"profile": binding.model_dump(mode="json"), "authority_account_ref": "admin"}
    assert not list(validator.iter_errors(private))
    assert IdentityDomain.model_validate(private).dns_name == ""
    builtin = {"profile": "active_directory", "authority_account_ref": "admin"}
    assert list(validator.iter_errors(builtin))
    with pytest.raises(ValidationError, match="requires dns_name"):
        IdentityDomain.model_validate(builtin)
