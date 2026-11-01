"""Scope recording intent is preserved and refused before unsupported effects."""

import json
from copy import deepcopy

import pytest
from cloud_resource_fixtures import PRINCIPAL, authority, cloud_scenario
from pydantic import ValidationError
from raes import parse_sdl
from raes.scenario import Scenario
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization import project_realization_concern


def audit_scenario():
    raw = cloud_scenario()
    authority(raw)["resource_scopes"][0]["audit_logs"] = [
        {
            "audit_log_id": "reads",
            "service": "secretmanager.googleapis.com",
            "log_type": "DATA_READ",
            "exempted_principal_refs": [PRINCIPAL],
        },
        {"audit_log_id": "writes", "service": "secretmanager.googleapis.com", "log_type": "DATA_WRITE"},
    ]
    return raw


def test_audit_settings_survive_parse_compile_and_configuration_projection():
    scenario = parse_sdl(json.dumps(audit_scenario()))
    scopes = scenario.nodes["iam"].runtime.identity_authorities[0].resource_scopes
    assert scopes[0].audit_logs[0].log_type == "DATA_READ"
    projected = project_realization_concern(
        "runtime-identity-authorities", scenario.nodes["iam"].runtime.identity_authorities
    )
    projected_scope = next(scope for scope in projected[0]["resource_scopes"] if scope["scope_id"] == "project-a")
    assert projected_scope["audit_logs"] == [rule.model_dump(mode="json") for rule in scopes[0].audit_logs]
    model = compile_runtime_model(scenario)
    assert any(item.requirement_kind == "runtime-identity-authorities" for item in model.realization_requirements)


@pytest.mark.parametrize("change", ["duplicate-id", "duplicate-pair", "blank", "unknown", "duplicate-exemption"])
def test_invalid_audit_settings_are_rejected(change):
    raw = audit_scenario()
    rules = authority(raw)["resource_scopes"][0]["audit_logs"]
    if change == "duplicate-id":
        rules[1]["audit_log_id"] = "reads"
    elif change == "duplicate-pair":
        rules[1]["log_type"] = "DATA_READ"
    elif change == "blank":
        rules[0]["service"] = " "
    elif change == "unknown":
        rules[0]["credentials"] = "synthetic-sentinel"
    else:
        rules[0]["exempted_principal_refs"] *= 2
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)


@pytest.mark.parametrize("ref", ["nodes.worker", "nodes.absent"])
def test_exemptions_require_exact_subjects(ref):
    from raes import SDLValidationError

    raw = audit_scenario()
    authority(raw)["resource_scopes"][0]["audit_logs"][0]["exempted_principal_refs"] = [ref]
    with pytest.raises(SDLValidationError, match="audit exemption"):
        parse_sdl(json.dumps(raw))


def test_repeated_imports_preserve_native_names_and_rewrite_exemptions(tmp_path):
    from raes import instantiate_scenario, parse_sdl_file

    raw = audit_scenario()
    raw["module"] = {"id": "example/audit", "version": "1.0.0", "exports": {"nodes": ["worker", "iam", "secrets"]}}
    (tmp_path / "audit.yaml").write_text(json.dumps(raw))
    root = tmp_path / "root.yaml"
    root.write_text(
        json.dumps(
            {"name": "two", "imports": [{"source": "local:audit.yaml", "namespace": value} for value in ("one", "two")]}
        )
    )
    scenario = instantiate_scenario(parse_sdl_file(root))
    for namespace in ("one", "two"):
        rule = scenario.nodes[f"{namespace}.iam"].runtime.identity_authorities[0].resource_scopes[0].audit_logs[0]
        assert rule.service == "secretmanager.googleapis.com"
        assert rule.exempted_principal_refs == [PRINCIPAL.replace("nodes.iam.", f"nodes.{namespace}.iam.")]


def test_binding_rechecks_duplicate_service_type_pairs():
    from raes import SDLInstantiationError, instantiate_scenario

    raw = audit_scenario()
    raw["variables"] = {"type": {"type": "string", "default": "DATA_WRITE"}}
    authority(raw)["resource_scopes"][0]["audit_logs"][1]["log_type"] = "${type}"
    parsed = parse_sdl(json.dumps(raw))
    instantiate_scenario(parsed)
    with pytest.raises(SDLInstantiationError):
        instantiate_scenario(parsed, {"type": "DATA_READ"})


def test_runtime_admission_rejects_unsupported_audit_requirements_before_apply(monkeypatch):
    from raes_backend_stubs.stubs import create_stub_target
    from raes_runtime.manager import RuntimeManager

    target = create_stub_target()
    calls = []
    monkeypatch.setattr(target.provisioner, "apply", lambda *args, **kwargs: calls.append(True))
    with RuntimeManager(target) as manager:
        result = manager.apply(manager.plan(parse_sdl(json.dumps(audit_scenario()))))
    assert not result.success
    assert any(d.code == "realization.unsupported-exact-requirement" for d in result.diagnostics)
    assert calls == []


def test_existing_lifecycle_carriers_retain_audit_settings(tmp_path, monkeypatch):
    import test_issue_1653_cloud_lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "cloud_scenario", audit_scenario)
    lifecycle.test_portable_plan_codec_preserves_the_cloud_description()
    lifecycle.test_cloud_snapshot_survives_durable_store_reload(tmp_path)
    lifecycle.test_materialized_description_round_trip_preserves_version_and_claims()


def test_weaker_readback_changes_configuration_projection():
    value = Scenario.model_validate(audit_scenario()).nodes["iam"].runtime.identity_authorities
    expected = project_realization_concern("runtime-identity-authorities", value)
    altered = deepcopy(value)
    altered[0].resource_scopes[0].audit_logs[0].exempted_principal_refs = []
    assert project_realization_concern("runtime-identity-authorities", altered) != expected
    altered[0].resource_scopes[0].audit_logs = []
    assert project_realization_concern("runtime-identity-authorities", altered) != expected


@pytest.mark.parametrize("submitted", [False, True])
def test_runtime_enforces_protocol_validation_rejection_before_effects(monkeypatch, submitted):
    from dataclasses import replace

    from raes_backend_stubs.stubs import create_stub_target
    from raes_contracts.apparatus import RealizationObservationCapability
    from raes_contracts.diagnostics import Diagnostic
    from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
    from raes_processor.planner import plan
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore
    from raes_runtime.manager import RuntimeManager

    raw = audit_scenario()
    raw = {"name": "audit-only", "nodes": {"iam": raw["nodes"]["iam"]}}
    identity = authority(raw)
    for name in ("policies", "identity_uses", "access_observations"):
        identity.pop(name)
    target = create_stub_target()
    declaration = target.manifest.realization_support[0]
    target = replace(
        target,
        manifest=replace(
            target.manifest,
            realization_support=(
                replace(
                    declaration,
                    observation_capabilities={
                        **declaration.observation_capabilities,
                        "runtime-identity-authorities": RealizationObservationCapability(
                            verification_scope=RealizationVerificationScope.CONFIGURATION,
                            observation_strength=ObservationStrength.DAEMON_OBSERVED,
                        ),
                    },
                    supported_exact_requirement_kinds=declaration.supported_exact_requirement_kinds
                    | {"runtime-identity-authorities"},
                ),
            ),
        ),
    )
    model = compile_runtime_model(parse_sdl(json.dumps(raw)))
    planned = plan(model, target.manifest)
    assert not any(d.code == "realization.unsupported-exact-requirement" for d in planned.diagnostics)
    calls = []
    validations = []

    def validate(value):
        validations.append(value)
        return [
            Diagnostic(
                code="backend.audit-unsupported",
                domain="runtime",
                address="nodes.iam",
                message="Audit recording is unsupported.",
            )
        ]

    monkeypatch.setattr(target.provisioner, "validate", validate)
    monkeypatch.setattr(target.provisioner, "apply", lambda *args, **kwargs: calls.append(True))
    store = InMemoryControlPlaneStore()
    with RuntimeManager(target, store=store) as manager:
        if submitted:
            manager.register_planner_produced_plan(planned)
            receipt = manager.submit_provisioning(planned.provisioning)
            result = manager.get_operation(receipt.operation_id)
        else:
            result = manager.apply(manager.plan(parse_sdl(json.dumps(raw))))
    assert validations, receipt.diagnostics if submitted else result
    operation = next(op for op in validations[0].operations if op.address == "provision.node.iam")
    submitted_scopes = operation.payload["spec"]["node"]["runtime"]["identity_authorities"][0]["resource_scopes"]
    normalized_scope = Scenario.model_validate(raw).nodes["iam"].runtime.identity_authorities[0].resource_scopes[0]
    assert submitted_scopes[0]["audit_logs"] == [rule.model_dump(mode="json") for rule in normalized_scope.audit_logs]
    assert not calls
    assert any(d.code == "backend.audit-unsupported" for d in result.diagnostics)
    assert calls == []


@pytest.mark.parametrize(
    "schema_name",
    [
        "sdl/sdl-authoring-input-v1.json",
        "sdl/instantiated-scenario-v1.json",
        "sdl/instantiated-scenario-snapshot-v1.json",
        "sdl/materialized-scenario-v1.json",
        "satisfiability/scenario-satisfiability-evidence-v1.json",
    ],
)
@pytest.mark.parametrize("invalid", ["unknown", "blank-service", "blank-type", "blank-reference", "repeated-exemption"])
def test_published_schemas_retain_typed_audit_settings(schema_name, invalid):
    from pathlib import Path

    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError as SchemaError

    schema = json.loads((Path(__file__).resolve().parents[3] / "contracts/schemas" / schema_name).read_text())
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/RuntimeIdentityResourceScope"})
    scope = authority(audit_scenario())["resource_scopes"][0]
    validator.validate(scope)
    rule = scope["audit_logs"][0]
    if invalid == "unknown":
        rule["credentials"] = "synthetic-sentinel"
    elif invalid == "repeated-exemption":
        rule["exempted_principal_refs"] *= 2
    elif invalid == "blank-reference":
        rule["exempted_principal_refs"] = [" "]
    else:
        rule["service" if invalid == "blank-service" else "log_type"] = " "
    with pytest.raises(SchemaError):
        validator.validate(scope)


def test_omitted_and_empty_audit_settings_add_no_recording_requirement():
    raw = cloud_scenario()
    before = Scenario.model_validate(raw).nodes["iam"].runtime.identity_authorities
    authority(raw)["resource_scopes"][0]["audit_logs"] = []
    after = Scenario.model_validate(raw).nodes["iam"].runtime.identity_authorities
    assert project_realization_concern("runtime-identity-authorities", before) == project_realization_concern(
        "runtime-identity-authorities", after
    )


@pytest.mark.parametrize("invalid", ["blank-service", "blank-type", "blank-reference", "repeated-exemption"])
def test_portable_audit_record_rejects_invalid_values(invalid):
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError as SchemaError
    from raes.runtime_configuration import RuntimeIdentityAuditLog

    rule = authority(audit_scenario())["resource_scopes"][0]["audit_logs"][0]
    if invalid == "repeated-exemption":
        rule["exempted_principal_refs"] *= 2
    elif invalid == "blank-reference":
        rule["exempted_principal_refs"] = [" "]
    else:
        rule["service" if invalid == "blank-service" else "log_type"] = " \t"
    with pytest.raises(SchemaError):
        Draft202012Validator(RuntimeIdentityAuditLog.model_json_schema()).validate(rule)


def test_scope_uniqueness_has_a_callable_portable_invariant():
    from importlib import import_module

    from raes.runtime_configuration import RuntimeIdentityResourceScope

    schema = RuntimeIdentityResourceScope.model_json_schema()
    invariant = schema["x-raes-invariants"][0]
    prefix = "raes.scenario."
    assert invariant["validator"].startswith(prefix)
    validator = import_module("raes.scenario")
    for token in invariant["validator"].removeprefix(prefix).split("."):
        validator = getattr(validator, token)
    assert invariant["id"] == "cloud-audit-scope-uniqueness"
    raw = audit_scenario()
    validator(raw)
    authority(raw)["resource_scopes"][0]["audit_logs"][1]["log_type"] = "DATA_READ"
    with pytest.raises(ValidationError):
        validator(raw)


@pytest.mark.parametrize("mutation", ["none", "omitted-rule", "changed-exemption"])
def test_raes_result_validation_detects_weakened_audit_configuration(mutation):
    from dataclasses import replace

    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_contracts.apparatus import RealizationObservationCapability
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.realization_observation import RealizationObservationDisclosure
    from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
    from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
    from raes_processor.planner import plan, realization_disclosure

    raw = audit_scenario()
    raw = {"name": "audit-result-contract", "nodes": {"iam": raw["nodes"]["iam"]}}
    for name in ("policies", "identity_uses", "access_observations"):
        authority(raw).pop(name)
    model = compile_runtime_model(parse_sdl(json.dumps(raw)))
    manifest = create_stub_manifest()
    declaration = manifest.realization_support[0]
    manifest = replace(
        manifest,
        realization_support=(
            replace(
                declaration,
                supported_exact_requirement_kinds=declaration.supported_exact_requirement_kinds
                | {"runtime-identity-authorities"},
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "runtime-identity-authorities": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.DAEMON_OBSERVED,
                    ),
                },
            ),
        ),
    )
    planned = plan(model, manifest)
    assert planned.is_valid
    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "runtime-identity-authorities"
    )
    operation = next(op for op in planned.provisioning.operations if op.address == "provision.node.iam")
    returned_payload = deepcopy(operation.payload)
    rules = returned_payload["spec"]["node"]["runtime"]["identity_authorities"][0]["resource_scopes"][0]["audit_logs"]
    if mutation == "omitted-rule":
        rules.pop()
    elif mutation == "changed-exemption":
        rules[0]["exempted_principal_refs"] = []
    snapshot = RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=returned_payload,
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
            )
        },
        realization_observations=(
            RealizationObservationDisclosure(
                address=requirement.address,
                field_path=requirement.field_path,
                domain=requirement.domain,
                requirement_kind=requirement.requirement_kind,
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.DAEMON_OBSERVED,
            ),
        ),
    )
    diagnostics, _ = realization_disclosure((requirement,), planned.provisioning, snapshot, manifest=manifest)
    assert bool(diagnostics) == (mutation != "none"), diagnostics


def test_provider_domain_names_do_not_select_a_backend_or_gcp_log_enum():
    raw = audit_scenario()
    for scope in authority(raw)["resource_scopes"]:
        scope["provider"] = "example-cloud"
    rule = authority(raw)["resource_scopes"][0]["audit_logs"][0]
    rule.update(service="ExampleNativeService", log_type="native.audit.read")
    scenario = parse_sdl(json.dumps(raw))
    projected = project_realization_concern(
        "runtime-identity-authorities", scenario.nodes["iam"].runtime.identity_authorities
    )
    scope = next(item for item in projected[0]["resource_scopes"] if item["scope_id"] == "project-a")
    assert scope["provider"] == "example-cloud"
    assert scope["audit_logs"][0]["service"] == "ExampleNativeService"
    assert scope["audit_logs"][0]["log_type"] == "native.audit.read"
