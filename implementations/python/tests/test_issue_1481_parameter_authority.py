"""Public configurable runtime leaves retain portable, enforceable authority.

Module fixtures are from OpenRAE/env-packs PR #433, revision
1a551321c00fa36e0e50674639ad214929a4ef2d (the issue's reproduction).
Capability declarations are synthetic planning fixtures, not execution claims.
"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaValidationError
from pydantic import ValidationError
from raes import instantiate_scenario, parse_sdl, parse_sdl_file
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.scenario import InstantiatedScenario
from raes_contracts.contracts import ProvisioningPlanModel, schema_bundle
from raes_contracts.plan_projection import provisioning_plan_model
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.semantics.realization_concerns import project_realization_concern
from raes_runtime.control_plane_api_models import _provisioning_plan
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture

CASES = [
    ("application-api-service", "api_base_path", "/custom/v3", "application", "runtime-applications"),
    ("postgresql-database", "database_name", "customer_data", "database", "runtime-database-services"),
    ("reverse-proxy-api-gateway", "route_prefix", "/team/api", "gateway", "runtime-applications"),
    ("smtp-imap-mail-service", "mail_domain", "example.test", "mail", "runtime-mail-services"),
]


def test_empty_derivation_provenance_preserves_legacy_serialization():
    from raes.phase_contracts import ExpansionProvenance, InstantiationProvenance

    for provenance in (
        ExpansionProvenance(),
        InstantiationProvenance(
            authored_digest={"profile": "raes-sdl-semantic/v2", "algorithm": "sha256", "value": "sha256:" + "0" * 64}
        ),
    ):
        model = type(provenance)
        assert provenance.parameter_derivations == ()
        assert "parameter_derivations" not in provenance.model_dump(mode="json")
        assert model.model_validate(provenance.model_dump(mode="json")) == provenance


def _composed(tmp_path, case, mode="provided", *, finite=False, interpolate=False):
    kit, parameter, selected, node, kind = case
    source = yaml.safe_load((Path(__file__).parent / "data" / "issue_1481" / f"{kit}.sdl.yaml").read_text())
    definition = source["variables"][parameter]
    if not finite:
        definition.pop("allowed_values")
    if mode == "required":
        definition.pop("default")
        definition["required"] = True
    if mode == "literal":
        # The literal control bypasses substitution only at runtime leaves.
        runtime = yaml.safe_dump(source["nodes"][node]["runtime"])
        source["nodes"][node]["runtime"] = yaml.safe_load(runtime.replace("${" + parameter + "}", selected))
    if interpolate:
        for mailbox in source["nodes"][node]["runtime"]["mail_services"][0]["mailboxes"]:
            mailbox["address"] = mailbox["address"].split("@")[0] + "@${mail_domain}"
    source["realization"]["default"] = "closed"
    module = tmp_path / "module.yaml"
    module.write_text(yaml.safe_dump(source))
    root = tmp_path / "root.yaml"
    parameters = {} if mode == "default" else {parameter: selected}
    if finite and mode != "default":
        parameters[parameter] = definition["allowed_values"][0]
    root.write_text(
        yaml.safe_dump(
            {
                "name": "parameter-regression",
                "imports": [{"path": "module.yaml", "namespace": "kit", "version": "2.0.0", "parameters": parameters}],
            }
        )
    )
    return instantiate_scenario(parse_sdl_file(root)), kind, "kit." + node


def _planned(scenario):
    _, _, manifest = _fixture({"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]})
    model = compile_runtime_model(scenario)
    execution = plan(model, manifest)
    return model, execution, manifest


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
@pytest.mark.parametrize("mode", ["provided", "required", "default", "literal"])
def test_configurable_module_runtime_parameters_plan(tmp_path, case, mode):
    scenario, kind, node = _composed(tmp_path, case, mode)
    # Independent phase admission must retain the same meaning.
    restored = InstantiatedScenario.model_validate_json(scenario.model_dump_json())
    model, execution, _ = _planned(restored)
    assert execution.is_valid, [(d.code, d.message) for d in execution.diagnostics]
    records = [r for r in restored.explicitness.values() if r.variables and r.path.startswith(f"nodes.{node}.runtime")]
    if mode != "literal":
        assert records
        assert all(r.classification is ExplicitnessClass.CONSTRAINED for r in records)
        assert all(r.provenance is ExplicitnessProvenance.PROCESSOR_DERIVED for r in records)
    authority = next(a for a in execution.provisioning.realization_authority if a.requirement_kind == kind)
    assert authority.constraint_document is not None
    portable = _provisioning_plan(
        ProvisioningPlanModel.model_validate_json(provisioning_plan_model(execution.provisioning).model_dump_json())
    )
    assert next(a for a in portable.realization_authority if a.requirement_kind == kind) == authority
    Draft202012Validator(schema_bundle()["instantiated-scenario-v1"]).validate(scenario.model_dump(mode="json"))


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_whole_field_finite_controls_still_plan(tmp_path, case):
    scenario, _, _ = _composed(tmp_path, case, finite=True)
    _, execution, _ = _planned(scenario)
    assert execution.is_valid, execution.diagnostics


@pytest.mark.parametrize("finite", [False, True])
@pytest.mark.parametrize("mode", ["provided", "required", "default"])
def test_mailbox_interpolation_preserves_composed_addresses_and_authority(tmp_path, finite, mode):
    scenario, kind, node = _composed(tmp_path, CASES[-1], mode, finite=finite, interpolate=True)
    service = scenario.nodes[node].runtime.mail_services[0]
    domain = service.domains[0].name
    assert [m.address for m in service.mailboxes] == ["operator@" + domain, "service@" + domain]
    _, execution, _ = _planned(scenario)
    assert execution.is_valid, [(d.code, d.message) for d in execution.diagnostics]
    authority = next(a for a in execution.provisioning.realization_authority if a.requirement_kind == kind)
    fields = authority.constraint_document.root.items[0].fields
    assert fields["mailboxes"].items[0].fields["address"].kind == ("domain" if finite else "literal")
    address = fields["mailboxes"].items[0].fields["address"]
    if finite:
        assert set(address.domain.values) == {"operator@alternate.test", "operator@environment.test"}
    else:
        assert address.value == "operator@" + domain
        assert address.origin.value == "processor"
    runtime = scenario.nodes[node].runtime.model_dump(mode="json")["mail_services"]
    assert evaluate_realization_constraint(
        authority.constraint_document, project_realization_concern(kind, runtime, recursive=True)
    ).conformant
    altered = deepcopy(runtime)
    altered[0]["mailboxes"][0]["address"] = "intruder@" + domain
    assert not evaluate_realization_constraint(
        authority.constraint_document, project_realization_concern(kind, altered, recursive=True)
    ).conformant


@pytest.mark.parametrize("tamper", ["output", "binding", "identity", "input_type", "literal", "pointer"])
def test_portable_derivation_rejects_inconsistent_evidence(tmp_path, tamper):
    scenario, _, node = _composed(tmp_path, CASES[-1], interpolate=True)
    payload = scenario.model_dump(mode="json")
    provenance = payload["instantiation_provenance"]
    derivation = next(
        d for d in provenance["parameter_derivations"] if d["field_pointer"].endswith("/mailboxes/0/address")
    )
    reference = next(s for s in derivation["segments"] if s["kind"] == "parameter")
    if tamper == "output":
        payload["nodes"][node]["runtime"]["mail_services"][0]["mailboxes"][0]["address"] = "changed@example.test"
    elif tamper == "binding":
        next(b for b in provenance["imports"][0]["bindings"] if b["parameter"] == ["mail_domain"])["value"] = (
            "changed.test"
        )
    elif tamper == "identity":
        reference["parameter"] = ["kit", "missing"]
    elif tamper == "input_type":
        reference["variable_type"] = "integer"
    elif tamper == "literal":
        derivation["segments"][0]["value"] = "operator@${missing}"
    else:
        derivation["field_pointer"] += "/missing"
    with pytest.raises(ValidationError):
        InstantiatedScenario.model_validate(payload)


@pytest.mark.parametrize("omit", ["support", "observation"])
def test_configurable_leaf_does_not_bypass_backend_admission(tmp_path, omit):
    scenario, kind, _ = _composed(tmp_path, CASES[0])
    model, _, manifest = _planned(scenario)
    declarations = []
    for declaration in manifest.realization_support:
        updates = (
            {"supported_constraint_kinds": declaration.supported_constraint_kinds - {kind}}
            if omit == "support"
            else {
                "observation_capabilities": {k: v for k, v in declaration.observation_capabilities.items() if k != kind}
            }
        )
        declarations.append(replace(declaration, **updates))
    execution = plan(model, replace(manifest, realization_support=tuple(declarations)))
    assert not execution.is_valid
    assert any(kind in d.message for d in execution.diagnostics)


def test_runtime_rejects_backend_change_to_selected_database_binding(tmp_path):
    scenario, kind, node = _composed(tmp_path, CASES[1])
    # The node-only callback fixture cannot apply content/account operations.
    # Reuse the kit's runtime demand through the same compiler/admission path.
    source = yaml.safe_load(
        (Path(__file__).parent / "data" / "issue_1481" / "postgresql-database.sdl.yaml").read_text()
    )
    runtime = source["nodes"]["database"]["runtime"]
    scenario = instantiate_scenario(
        parse_sdl(
            yaml.safe_dump(
                {
                    "name": "selected-database",
                    "variables": {"database_name": {"type": "string", "default": "customer_data"}},
                    "nodes": {
                        "host": {
                            "type": "compute",
                            "services": source["nodes"]["database"]["services"],
                            "runtime": runtime,
                        }
                    },
                }
            )
        )
    )
    node = "host"
    _, execution, manifest = _planned(scenario)
    assert execution.is_valid, execution.diagnostics
    portable = _provisioning_plan(
        ProvisioningPlanModel.model_validate_json(provisioning_plan_model(execution.provisioning).model_dump_json())
    )
    runtime = scenario.nodes[node].runtime.model_dump(mode="json")
    result = _apply(portable, manifest, runtime)
    assert result.success, result.diagnostics
    runtime["database_services"][0]["databases"][0]["name"] = "unauthorized_database"
    result = _apply(portable, manifest, runtime)
    assert not result.success
    assert result.snapshot.entries == {}
    assert result.changed_addresses == []
    assert result.diagnostics[0].code == "runtime.backend-contract-invalid"


@pytest.mark.parametrize(
    "case, value", list(zip(CASES, ["/tenant/v8", "billing_2026", "/org/v4", "customer.example"], strict=True))
)
def test_additional_non_catalog_values_are_configurable(tmp_path, case, value):
    scenario, _, _ = _composed(tmp_path, (*case[:2], value, *case[3:]))
    _, execution, _ = _planned(scenario)
    assert execution.is_valid, execution.diagnostics


def test_nested_import_derivations_rewrite_every_parameter_identity(tmp_path):
    _, kind, node = _composed(tmp_path, CASES[-1], interpolate=True)
    wrapper = yaml.safe_load((tmp_path / "root.yaml").read_text())
    wrapper.update(
        {
            "version": "2.0.0",
            "module": {"id": "fixtures/wrapper", "version": "2.0.0", "parameters": [], "exports": {"nodes": [node]}},
        }
    )
    (tmp_path / "wrapper.yaml").write_text(yaml.safe_dump(wrapper))
    (tmp_path / "nested.yaml").write_text(
        yaml.safe_dump(
            {"name": "nested", "imports": [{"path": "wrapper.yaml", "namespace": "outer", "version": "2.0.0"}]}
        )
    )
    scenario = instantiate_scenario(parse_sdl_file(tmp_path / "nested.yaml"))
    derivations = scenario.instantiation_provenance.parameter_derivations
    assert derivations
    assert all(d.field_pointer.startswith("/nodes/outer.kit.mail/") for d in derivations)
    assert all(
        s.parameter == ("outer", "kit", "mail_domain") for d in derivations for s in d.segments if s.kind == "parameter"
    )
    _, execution, _ = _planned(InstantiatedScenario.model_validate_json(scenario.model_dump_json()))
    assert execution.is_valid, execution.diagnostics


@pytest.mark.parametrize("finite", [False, True])
def test_repeated_interpolation_tokens_keep_correlated_binding(finite):
    definition = {"type": "string", "default": "alpha"}
    if finite:
        definition["allowed_values"] = ["alpha", "beta"]
    scenario = instantiate_scenario(
        parse_sdl(
            yaml.safe_dump(
                {
                    "name": "repeated-input",
                    "variables": {"prefix": definition},
                    "nodes": {
                        "host": {
                            "type": "compute",
                            "runtime": {
                                "database_services": [
                                    {
                                        "database_service_id": "db",
                                        "engine": "sqlite",
                                        "databases": [{"database_id": "data", "name": "${prefix}-${prefix}"}],
                                    }
                                ]
                            },
                        }
                    },
                }
            )
        )
    )
    _, execution, _ = _planned(scenario)
    assert execution.is_valid, execution.diagnostics
    authority = next(
        a for a in execution.provisioning.realization_authority if a.requirement_kind == "runtime-database-services"
    )
    runtime = scenario.nodes["host"].runtime.model_dump(mode="json")["database_services"]
    for name, accepted in [("alpha-alpha", True), ("beta-beta", finite), ("alpha-beta", False)]:
        runtime[0]["databases"][0]["name"] = name
        projection = project_realization_concern("runtime-database-services", runtime, recursive=True)
        assert evaluate_realization_constraint(authority.constraint_document, projection).conformant is accepted


def test_classified_parameter_alternatives_remain_unpublished():
    scenario = instantiate_scenario(
        parse_sdl("""
name: protected-input
variables:
  payload: {type: string, default: selected-fixture, allowed_values: [selected-fixture, unselected-fixture]}
nodes:
  host:
    type: compute
    runtime:
      environment:
        - {name: TOKEN, value: 'prefix-${payload}', value_classification: secret_fixture}
""")
    )
    assert scenario.instantiation_provenance.parameter_derivations == ()
    assert "unselected-fixture" not in scenario.instantiation_provenance.model_dump_json()
    _, execution, _ = _planned(scenario)
    assert not execution.is_valid
    assert any(d.code == "realization.authority-bound-unavailable" for d in execution.diagnostics)


def test_unenumerated_whole_field_binding_retains_owner_normalization():
    scenario = instantiate_scenario(
        parse_sdl("""
name: normalized-binding
variables:
  engine: {type: string, default: postfix-dovecot}
nodes:
  host:
    type: compute
    runtime:
      mail_services:
        - {mail_service_id: mail, engine: '${engine}'}
""")
    )
    restored = InstantiatedScenario.model_validate_json(scenario.model_dump_json())
    _, execution, _ = _planned(restored)
    assert execution.is_valid, execution.diagnostics


def test_finite_interpolation_image_respects_relation_work_budgets():
    from raes.parameter_derivations import (
        ParameterDerivation,
        ParameterLiteralSegment,
        ParameterReferenceSegment,
        finite_derivation_image,
    )
    from raes_contracts.realization_structure import DEFAULT_REALIZATION_CONSTRAINT_LIMITS

    limit = DEFAULT_REALIZATION_CONSTRAINT_LIMITS.max_members
    derivation = ParameterDerivation(
        field_pointer="/nodes/host/runtime/database_services/0/version",
        segments=(
            ParameterLiteralSegment(kind="literal", value="v-"),
            ParameterReferenceSegment(
                kind="parameter",
                parameter=("revision",),
                variable_type="integer",
                allowed_values=tuple(range(limit + 1)),
            ),
        ),
    )
    with pytest.raises(ValueError, match="member budget"):
        finite_derivation_image(derivation)


@pytest.mark.parametrize("segment_kind", ["literal", "parameter"])
def test_derivation_segment_type_tags_are_required_by_schema_and_runtime(tmp_path, segment_kind):
    scenario, _, _ = _composed(tmp_path, CASES[-1], interpolate=True)
    payload = scenario.model_dump(mode="json")
    derivation = next(
        d
        for d in payload["instantiation_provenance"]["parameter_derivations"]
        if d["field_pointer"].endswith("/mailboxes/0/address")
    )
    del next(s for s in derivation["segments"] if s["kind"] == segment_kind)["kind"]
    with pytest.raises(ValidationError):
        InstantiatedScenario.model_validate(payload)
    validator = Draft202012Validator(schema_bundle()["instantiated-scenario-v1"])
    with pytest.raises(SchemaValidationError):
        validator.validate(payload)
