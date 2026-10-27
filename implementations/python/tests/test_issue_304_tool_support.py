"""API-414 declarations never substitute for apparatus support or execution."""

from raes_backend_stubs.stubs import create_stub_manifest
from raes_processor.manifest import reference_processor_manifest_payload
from raes_processor.planner import plan
from tool_profile_support import compiled


def test_reference_processor_declares_tool_profile_semantics():
    capabilities = reference_processor_manifest_payload()["capabilities"]
    assert capabilities.get("participant_tools") is not None
    declaration = capabilities["participant_tools"]
    assert declaration["semantic_versions"] == ["participant-tool-profile/v1"]
    assert {entry["feature"] for entry in declaration["feature_support"]} == {
        "tool_affordances",
        "scoped_tool_affordances",
    }


def test_planning_rejects_undeclared_tool_support_without_authored_feature_refs():
    model = compiled()
    assert all(not spec.backend_feature_support_refs for spec in model.behavior_specifications.values())
    result = plan(model, create_stub_manifest())
    assert not result.is_valid
    assert any(d.code == "participant.tool-support-insufficient" for d in result.diagnostics)


def supported_manifest(*, level="exact", max_bindings=None, max_participants=None, scoped=True):
    from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_payload
    from raes_contracts.contracts import BackendManifestV2Model

    payload = backend_manifest_payload(create_stub_manifest())
    runtime = payload["capabilities"]["participant_runtime"]
    runtime["tool_profiles"] = {
        "semantic_versions": ["participant-tool-profile/v1"],
        "max_bindings_per_profile": max_bindings,
        "max_participants_per_binding": max_participants,
    }
    features = ["tool_affordances", "scoped_tool_affordances"] if scoped else ["tool_affordances"]
    runtime["feature_support"] = [e for e in runtime["feature_support"] if e["feature"] not in features]
    runtime["supported_behavior_features"] += features
    for feature in features:
        constraints = []
        if max_bindings is not None:
            constraints.append("tool_profiles.max_bindings_per_profile")
        if max_participants is not None:
            constraints.append("tool_profiles.max_participants_per_binding")
        runtime["feature_support"].append(
            {
                "feature": feature,
                "support_level": level,
                "constraint_refs": constraints,
                "limitation_refs": ["limitations.tool-capacity"] if level != "exact" else [],
                "disclosure_refs": ["disclosures.tool-capacity"] if level != "exact" else [],
                "evidence_refs": ["evidence.synthetic.tool-probe"],
            }
        )
    return backend_manifest_from_v2_model(BackendManifestV2Model.model_validate(payload))


def test_supported_profile_is_admitted():
    result = plan(compiled(), supported_manifest())
    assert result.is_valid, result.diagnostics


def test_capacity_is_evaluated_for_honest_bounded_support():
    inside = plan(compiled(), supported_manifest(level="bounded", max_bindings=2, max_participants=1))
    assert inside.is_valid, inside.diagnostics
    outside = plan(compiled(), supported_manifest(level="bounded", max_bindings=1))
    assert not outside.is_valid
    assert any(d.code == "participant.tool-support-insufficient" for d in outside.diagnostics)


def test_scoped_profile_requires_independent_scoped_support():
    result = plan(compiled(), supported_manifest(scoped=False))
    assert not result.is_valid
    assert any(d.code == "participant.tool-support-insufficient" for d in result.diagnostics)


def test_selected_processor_cannot_borrow_backend_claims():
    from raes_contracts.contracts import ProcessorManifestV2Model

    payload = reference_processor_manifest_payload()
    payload["capabilities"].pop("participant_tools", None)
    processor = ProcessorManifestV2Model.model_validate(payload)
    result = plan(compiled(), supported_manifest(), processor_manifest=processor)
    assert not result.is_valid
    assert any(d.code == "processor.tool-support-insufficient" for d in result.diagnostics)


def test_tool_free_scenario_retains_legacy_support():
    from raes import parse_sdl
    from raes_processor.compiler import compile_runtime_model

    result = plan(compile_runtime_model(parse_sdl("name: no-tools")), create_stub_manifest())
    assert result.is_valid


def test_static_conformance_does_not_promote_declaration_to_execution():
    from dataclasses import replace

    from raes_backend_stubs.stubs import create_stub_target
    from raes_conformance.conformance.profiles import BackendCapabilityProfile
    from raes_conformance.conformance.target import _participant_feature_cases

    base = create_stub_target()
    manifest = replace(
        base.manifest,
        capabilities=replace(base.manifest.capabilities, participant_runtime=supported_manifest().participant_runtime),
    )
    target = replace(base, manifest=manifest)
    cases = _participant_feature_cases(target, BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE)
    tool_cases = [case for case in cases if case.capability_feature in {"tool_affordances", "scoped_tool_affordances"}]
    assert len(tool_cases) == 2
    assert all(case.declared_support_level == "exact" for case in tool_cases)
    assert all(case.effective_support_level is None for case in tool_cases)
    assert all(case.execution_basis == "fixture-only" for case in tool_cases)
    assert all(case.manifest_digest and case.manifest_digest.startswith("sha256:") for case in tool_cases)


def test_unknown_constraint_cannot_be_accepted_as_exact_support():
    import pytest
    from raes_backend_protocols.manifest import backend_manifest_payload
    from raes_contracts.contracts import BackendManifestV2Model

    payload = backend_manifest_payload(supported_manifest())
    runtime = payload["capabilities"]["participant_runtime"]
    entry = next(e for e in runtime["feature_support"] if e["feature"] == "tool_affordances")
    entry["constraint_refs"] = ["constraints.unresolved-secret-restriction"]
    with pytest.raises(ValueError):
        BackendManifestV2Model.model_validate(payload)


def test_trial_compilation_checks_selected_processor_and_backend_before_sealing():
    from raes import parse_sdl_file
    from raes.scenario import ExpandedScenario
    from raes.validator import SemanticValidator
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from test_sce_002_trial_realization import _request_with_processor
    from tool_profile_support import TOOLKIT

    request = _request_with_processor()
    payload = request.family.model_dump(
        mode="python", by_alias=True, exclude_unset=True, exclude={"expansion_provenance"}
    )
    tools = parse_sdl_file(TOOLKIT).model_dump(mode="python", by_alias=True, exclude_unset=True)
    for section in (
        "nodes",
        "content",
        "entities",
        "agents",
        "action_contracts",
        "observation_boundaries",
        "behavior_specifications",
    ):
        payload.setdefault(section, {}).update(tools[section])
    family = ExpandedScenario.model_validate(payload)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    result = compile_admitted_trial_plan(request.with_family(family))
    assert result.plan is None
    assert any("tool-support" in d.code for d in result.diagnostics), result.diagnostics


def test_runtime_rechecks_backend_support_after_plan_diagnostics_are_removed():
    from dataclasses import replace

    from raes_backend_stubs.stubs import create_stub_target
    from raes_runtime.manager import RuntimeManager

    target = create_stub_target()
    manager = RuntimeManager(target)
    snapshot = manager.snapshot
    prepared = plan(compiled(), target.manifest, snapshot)
    result = manager.apply(replace(prepared, diagnostics=[]))
    assert not result.success
    assert result.snapshot == snapshot
    assert any(d.code == "participant.tool-support-insufficient" for d in result.diagnostics)


def test_disclosed_weak_support_is_not_an_implicit_downgrade():
    result = plan(compiled(), supported_manifest(level="disclosed_weak"))
    assert not result.is_valid
    assert any(d.code == "participant.tool-support-insufficient" for d in result.diagnostics)


def test_version_claim_and_mutated_capacity_fail_closed():
    import pytest
    from raes_backend_protocols.manifest import backend_manifest_payload
    from raes_contracts.contracts import BackendManifestV2Model

    manifest = supported_manifest(max_bindings=2)
    payload = backend_manifest_payload(manifest)
    payload["capabilities"]["participant_runtime"]["tool_profiles"]["semantic_versions"] = [
        "participant-tool-profile/v99"
    ]
    with pytest.raises(ValueError):
        BackendManifestV2Model.model_validate(payload)
    manifest.participant_runtime.tool_profiles.max_bindings_per_profile = -1
    result = plan(compiled(), manifest)
    assert not result.is_valid
    assert any(d.code == "participant.tool-support-insufficient" for d in result.diagnostics)


def test_positive_support_requires_versions_presence_evidence_and_contracts():
    import copy

    import pytest
    from raes_backend_protocols.manifest import backend_manifest_payload
    from raes_contracts.contracts import BackendManifestV2Model

    original = backend_manifest_payload(supported_manifest())
    for mutation in ("versions", "presence", "evidence", "contracts"):
        payload = copy.deepcopy(original)
        runtime = payload["capabilities"]["participant_runtime"]
        entry = next(e for e in runtime["feature_support"] if e["feature"] == "tool_affordances")
        if mutation == "versions":
            runtime.pop("tool_profiles")
        elif mutation == "presence":
            runtime["supported_behavior_features"].remove("tool_affordances")
        elif mutation == "evidence":
            entry["evidence_refs"] = []
        else:
            payload["supported_contract_versions"].remove("participant-behavior-history-event-stream-v1")
        with pytest.raises(ValueError):
            BackendManifestV2Model.model_validate(payload)


def test_portable_diagnostic_does_not_echo_private_claim_values():
    from raes_contracts.diagnostics import DiagnosticModel, portable_diagnostic_payload

    manifest = supported_manifest()
    manifest.participant_runtime.tool_profiles.semantic_versions[:] = ["private.token.canary"]
    diagnostics = plan(compiled(), manifest).diagnostics
    assert any(d.code == "participant.tool-support-insufficient" for d in diagnostics)
    for diagnostic in diagnostics:
        payload = portable_diagnostic_payload(diagnostic)
        DiagnosticModel.model_validate(payload)
        assert "private.token.canary" not in str(payload)


def test_tool_support_rejects_blank_evidence_reference():
    import pytest
    from raes_backend_protocols.manifest import backend_manifest_payload
    from raes_contracts.contracts import BackendManifestV2Model

    payload = backend_manifest_payload(supported_manifest())
    entry = next(
        e
        for e in payload["capabilities"]["participant_runtime"]["feature_support"]
        if e["feature"] == "tool_affordances"
    )
    entry["evidence_refs"] = ["   "]
    with pytest.raises(ValueError):
        BackendManifestV2Model.model_validate(payload)


def test_false_declaration_is_kept_separate_from_failed_observed_probe():
    from dataclasses import replace

    from raes_backend_stubs.stubs import create_stub_target
    from raes_conformance.conformance.profiles import BackendCapabilityProfile
    from raes_conformance.conformance.report import (
        BackendConformanceReport,
        _bounded_conformance_claim,
        backend_conformance_report_payload,
    )
    from raes_conformance.conformance.target import _participant_feature_cases
    from raes_conformance.conformance.target_probes import _drive_participant_episode_probe
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime.control_plane import RuntimeControlPlane

    base = create_stub_target()

    class SilentRuntime:
        def __getattr__(self, name):
            return getattr(base.participant_runtime, name)

        def initialize(self, request, snapshot):
            return ApplyResult(success=True, snapshot=snapshot)

    manifest = replace(
        base.manifest,
        capabilities=replace(base.manifest.capabilities, participant_runtime=supported_manifest().participant_runtime),
    )
    target = replace(base, manifest=manifest, participant_runtime=SilentRuntime())
    profile = BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE
    declared = _participant_feature_cases(target, profile)
    with RuntimeControlPlane(target) as plane:
        observed = _drive_participant_episode_probe(plane, participant_address="participant.conformance")
    assert any(not case.passed for case in observed)
    cases = (*declared, *observed)
    report = BackendConformanceReport(
        profile=profile.value,
        passed=False,
        cases=cases,
        claim=_bounded_conformance_claim(profile=profile.value, cases=cases, left_carrier_ref="backend-target:stub"),
    )
    payload = backend_conformance_report_payload(report)
    tool_cases = [case for case in payload["cases"] if case.get("capability_feature") == "tool_affordances"]
    assert tool_cases[0]["declared_support_level"] == "exact"
    assert tool_cases[0]["effective_support_level"] is None
    assert not payload["native_conformance"]
    assert not payload["passed"]


def test_tool_profile_requires_each_selected_participant_role():
    from dataclasses import replace

    manifest = supported_manifest()
    capability = replace(
        manifest.participant_runtime,
        supported_participant_roles=manifest.participant_runtime.supported_participant_roles - {"white"},
    )
    manifest = replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=capability))
    result = plan(compiled(), manifest)
    assert not result.is_valid
    assert any(d.code == "participant.tool-support-insufficient" for d in result.diagnostics)


def test_imported_profiles_keep_independent_capacity():
    from raes import parse_sdl_file
    from raes_processor.compiler import compile_runtime_model
    from tool_profile_support import FIXTURES

    model = compile_runtime_model(parse_sdl_file(FIXTURES / "imports-profile-twice.sdl.yaml"))
    assert len(model.tool_affordances) == 2
    result = plan(model, supported_manifest(max_bindings=1))
    assert result.is_valid, result.diagnostics


def test_new_wire_coordinates_have_schema_and_model_shape_parity():
    import copy

    from jsonschema import Draft202012Validator
    from raes_backend_protocols.manifest import backend_manifest_payload
    from raes_contracts.contracts import schema_bundle

    validator = Draft202012Validator(schema_bundle()["backend-manifest-v2"])
    original = backend_manifest_payload(supported_manifest(max_bindings=2))
    assert validator.is_valid(original)
    for field, value in (
        ("semantic_versions", ["participant-tool-profile/v99"]),
        ("semantic_versions", []),
        ("max_bindings_per_profile", 0),
        ("max_participants_per_binding", True),
    ):
        payload = copy.deepcopy(original)
        payload["capabilities"]["participant_runtime"]["tool_profiles"][field] = value
        assert not validator.is_valid(payload)


def test_public_manifest_emitter_revalidates_mutated_tool_coordinates():
    import pytest
    from raes_backend_protocols.manifest import backend_manifest_payload

    manifest = supported_manifest(max_bindings=2)
    manifest.participant_runtime.tool_profiles.max_bindings_per_profile = -1
    with pytest.raises(ValueError):
        backend_manifest_payload(manifest)


def test_processor_capacity_is_independent_of_unbounded_backend_support():
    from raes_contracts.contracts import ProcessorManifestV2Model

    payload = reference_processor_manifest_payload()
    payload["capabilities"]["participant_tools"]["max_bindings_per_profile"] = 1
    processor = ProcessorManifestV2Model.model_validate(payload)
    result = plan(compiled(), supported_manifest(), processor_manifest=processor)
    assert not result.is_valid
    assert any(d.code == "processor.tool-support-insufficient" for d in result.diagnostics)
    assert all(d.code != "participant.tool-support-insufficient" for d in result.diagnostics)


def test_unsupported_claims_still_validate_their_references():
    import pytest
    from raes_backend_protocols.manifest import backend_manifest_payload
    from raes_contracts.contracts import BackendManifestV2Model

    payload = backend_manifest_payload(create_stub_manifest())
    runtime = payload["capabilities"]["participant_runtime"]
    entry = next(e for e in runtime["feature_support"] if e["feature"] == "tool_affordances")
    assert entry["support_level"] == "unsupported"
    entry["disclosure_refs"] = ["   "]
    with pytest.raises(ValueError):
        BackendManifestV2Model.model_validate(payload)
