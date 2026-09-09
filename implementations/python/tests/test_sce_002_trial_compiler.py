"""Deterministic admitted-trial compiler tests for SCE-002."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path

import pytest
import raes_processor.trial_compiler.compiler as trial_compiler_module
from hypothesis import given, settings
from hypothesis import strategies as st
from paths import REPO_ROOT
from raes.canonical import canonical_sdl_digest
from raes.scenario import ExpandedScenario, Scenario
from raes.validator import SemanticValidator
from raes.variation import ParameterVariationPoint
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.contracts import (
    AdmittedApparatusBindingModel,
    AdmittedParticipantManifestReferenceModel,
    AdmittedTrialPlanInputRefsModel,
    BackendManifestV2Model,
    CleanStateRequirementModel,
    CleanupObligationModel,
    CleanupResourceBoundaryModel,
    ExperimentBackendReferenceModel,
    ExperimentCaptureSpecModel,
    ExperimentManifestReferenceModel,
    ExperimentReferenceModel,
    ExperimentScenarioFamilyReferenceModel,
    ExperimentSpecModel,
    ExperimentTaskModel,
    ParticipantImplementationManifestModel,
    TrialCleanupTemplateModel,
    TrialCompilationLimitsModel,
    TrialCoordinateModel,
    TrialExecutionAuthorityModel,
)
from raes_contracts.random_stream_engine import BoundedIntegerBatchResult, BoundedIntegerDraw
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_contracts.realization_envelope_carrier import realization_envelope_digest
from raes_processor.capture_admission import compile_capture_spec_demands
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan
from raes_processor.trial_compiler.domains import canonical_domain_outcomes
from raes_processor.trial_compiler.models import CompilationFailure
from raes_processor.trial_compiler.profiles import (
    coordinate_projection,
    derive_identity,
    replicate_id,
)

_EXPERIMENT_FIXTURE = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "experiment-core"
    / "experiment-authoring-input-v1"
    / "valid"
    / "reference.json"
)
_TASK_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / "experiment-task-v1" / "valid" / "reference.json"
)
_CAPTURE_SPEC_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / "experiment-capture-spec-v1" / "valid" / "reference.json"
)
_ENVELOPE_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "realization-envelope" / "realization-envelope-v1" / "valid" / "generic.json"
)
_BACKEND_MANIFEST_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "backend-manifest" / "backend-manifest-v2" / "valid" / "stub.json"
)
_PARTICIPANT_MANIFEST_FIXTURE = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "participant-implementation-manifest"
    / "participant-implementation-manifest-v1"
    / "valid"
    / "reference.json"
)
_PROFILE_FIXTURE = REPO_ROOT / "contracts" / "fixtures" / "plans" / "trial-compiler-v1" / "identity-vectors.json"


def _family() -> ExpandedScenario:
    payload: dict[str, object] = {
        "name": "compiler-family",
        "variables": {
            "payload_path": {
                "type": "string",
                "default": "/opt/a",
                "allowed_values": ["/opt/a", "/opt/b"],
            }
        },
        "nodes": {
            "primary": {
                "type": "compute",
                "os": "linux",
                "resources": {"ram": "1 gib", "cpu": 1},
            }
        },
        "content": {
            "payload": {
                "type": "file",
                "target": "primary",
                "path": "${payload_path}",
            }
        },
        "variation_points": {
            "payload-path": {
                "kind": "parameter",
                "target": {"kind": "variable", "variable": "payload_path"},
                "domain": {"kind": "enum", "values": ["/opt/b", "/opt/a"]},
            }
        },
    }
    authored = Scenario.model_validate(payload)
    SemanticValidator(authored).validate()
    expanded = ExpandedScenario.model_validate(payload)
    expanded._set_semantic_validated(True)
    return expanded


def _product_family() -> ExpandedScenario:
    payload = _family().model_dump(mode="python", by_alias=True)
    payload["variables"]["payload_mode"] = {
        "type": "string",
        "default": "fast",
        "allowed_values": ["fast", "safe"],
    }
    payload["variation_points"]["payload-mode"] = {
        "kind": "parameter",
        "target": {"kind": "variable", "variable": "payload_mode"},
        "domain": {"kind": "enum", "values": ["safe", "fast"]},
    }
    expanded = ExpandedScenario.model_validate(payload)
    SemanticValidator(expanded).validate()
    expanded._set_semantic_validated(True)
    return expanded


def _spec(*, run_count: int = 2, sample: bool = False) -> ExperimentSpecModel:
    payload = json.loads(_EXPERIMENT_FIXTURE.read_text(encoding="utf-8"))
    payload["intended_scenario_ref"] = {"ref_kind": "scenario", "ref_id": "compiler-family"}
    payload["factors"] = {}
    run_plan = payload["run_plan"]
    run_plan.pop("allocation")
    run_plan["target_run_count"] = run_count
    run_plan["red_variant_selections"] = {}
    run_plan["stochastic_controls"] = []
    if sample:
        run_plan["stochastic_controls"] = [
            {
                "control_id": "sample-control",
                "role": "sampling",
                "executable_binding": {
                    "profile_ref": {
                        "ref_kind": "profile",
                        "ref_id": "blake3-xof-v1",
                        "ref_version": "random-stream-profile/v1",
                    },
                    "namespace": "compiler-sampling",
                    "root_entropy": {
                        "kind": "public-seed",
                        "encoding": "hex-fixed-width",
                        "value": "01" * 32,
                    },
                },
            }
        ]
        run_plan["selection_policies"] = {
            "sample-path": {
                "kind": "sample",
                "policy_id": "sample-path",
                "purpose": "nuisance-variation",
                "point_ref": "payload-path",
                "algorithm_profile": "uniform-index-v1",
                "distribution": "uniform",
                "replacement": "with-replacement",
                "sample_count": run_count,
                "output_bound": run_count,
                "stochastic_control_ref": "sample-control",
            }
        }
    else:
        run_plan["selection_policies"] = {
            "enumerate-path": {
                "kind": "enumerate",
                "policy_id": "enumerate-path",
                "purpose": "nuisance-variation",
                "point_ref": "payload-path",
                "output_bound": run_count,
            }
        }
    return ExperimentSpecModel.model_validate(payload)


def _stratified_spec() -> ExperimentSpecModel:
    payload = json.loads(_EXPERIMENT_FIXTURE.read_text(encoding="utf-8"))
    payload["intended_scenario_ref"] = {"ref_kind": "scenario", "ref_id": "compiler-family"}
    run_plan = payload["run_plan"]
    run_plan["stochastic_controls"] = []
    run_plan["red_variant_selections"] = {}
    allocation = run_plan["allocation"]
    allocation["target_runs_per_condition"] = 1
    run_plan["selection_policies"] = {
        "stratified-path": {
            "kind": "stratified",
            "policy_id": "stratified-path",
            "purpose": "controlled-factor",
            "point_ref": "payload-path",
            "balance": "equal",
            "outcomes": {
                "aggressive": {"kind": "literal", "value": "/opt/a"},
                "stealthy": {"kind": "literal", "value": "/opt/b"},
            },
            "strata": {
                "cond-aggressive": {
                    "stratum_id": "cond-aggressive",
                    "outcome_ref": "aggressive",
                    "factor_id": "red-tactic",
                    "factor_level_id": "aggressive",
                    "condition_id": "cond-aggressive",
                    "output_count": 1,
                },
                "cond-stealthy": {
                    "stratum_id": "cond-stealthy",
                    "outcome_ref": "stealthy",
                    "factor_id": "red-tactic",
                    "factor_level_id": "stealthy",
                    "condition_id": "cond-stealthy",
                    "output_count": 1,
                },
            },
            "output_bound": 2,
        }
    }
    return ExperimentSpecModel.model_validate(payload)


def _bound_spec() -> ExperimentSpecModel:
    payload = json.loads(_EXPERIMENT_FIXTURE.read_text(encoding="utf-8"))
    payload["intended_scenario_ref"] = {"ref_kind": "scenario", "ref_id": "compiler-family"}
    run_plan = payload["run_plan"]
    run_plan["stochastic_controls"] = []
    run_plan["red_variant_selections"] = {}
    run_plan["allocation"]["target_runs_per_condition"] = 1
    for condition_id, assignment in run_plan["allocation"]["condition_assignments"].items():
        assignment.pop("required_parameters")
        assignment["required_refs"] = [
            {
                "ref_kind": "profile",
                "ref_id": f"protocol.{condition_id}",
            }
        ]
    run_plan["selection_policies"] = {
        "enumerate-path": {
            "kind": "enumerate",
            "policy_id": "enumerate-path",
            "purpose": "nuisance-variation",
            "point_ref": "payload-path",
            "output_bound": 2,
            "binding_descriptor_refs": ["binding-aggressive", "binding-stealthy"],
        }
    }
    payload["binding_semantics"] = "explicit-required"
    payload["binding_descriptors"] = {
        "schema_version": "experiment-binding-descriptors/v1",
        "descriptors": [
            {
                "binding_id": f"binding-{level}",
                "source_factor_id": "red-tactic",
                "source_factor_level_id": level,
                "source_condition_id": condition_id,
                "target": {
                    "plane": "scenario",
                    "scenario_family_id": "compiler-family",
                    "variation_point_id": "payload-path",
                    "target_id": "variables.payload_path",
                },
                "value_type": "string",
                "value": {"kind": "literal", "value": value},
                "owner": {
                    "contract_id": "sdl-authoring-input-v1",
                    "contract_version": "1",
                    "validator_id": "raes-selected-scenario",
                    "validator_version": "1",
                },
            }
            for condition_id, level, value in (
                ("cond-aggressive", "aggressive", "/opt/a"),
                ("cond-stealthy", "stealthy", "/opt/b"),
            )
        ],
    }
    return ExperimentSpecModel.model_validate(payload)


def _execution_authority() -> TrialExecutionAuthorityModel:
    return TrialExecutionAuthorityModel(
        attempt_timeout_seconds=600,
        on_timeout="cleanup-and-fail",
        on_cancellation="cleanup-and-fail",
        cleanup=TrialCleanupTemplateModel(
            clean_state=CleanStateRequirementModel(
                mode="fresh",
                boundary_refs=["range"],
                verification_probe_refs=["probe:fresh"],
            ),
            resource_boundaries={
                "range": CleanupResourceBoundaryModel(
                    boundary_id="range",
                    resource_kind="range-instance",
                    owner_ref="apparatus:range",
                    resource_refs=["range:compiler-fixture"],
                )
            },
            cleanup_obligations={
                "destroy": CleanupObligationModel(
                    obligation_id="destroy",
                    boundary_refs=["range"],
                    action_kind="destroy",
                    triggers=["success", "failure", "cancellation", "timeout", "abort"],
                    requirement="required",
                    idempotency="idempotent",
                    verification_probe_refs=["probe:absent"],
                    timeout_seconds=120,
                )
            },
            retry_policy={"max_attempts": 1, "after_effect_policy": "disallow"},
        ),
    )


def _request(*, run_count: int = 2, sample: bool = False) -> TrialCompilationRequest:
    family = _family()
    family_digest = canonical_sdl_digest(family).value
    experiment = _spec(run_count=run_count, sample=sample)
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text(encoding="utf-8"))
    capture_payload = json.loads(_CAPTURE_SPEC_FIXTURE.read_text(encoding="utf-8"))
    capture_requirement = next(iter(capture_payload["capture_requirements"].values()))
    capture_payload["capture_requirements"] = {
        "auth-log-evidence": {
            **capture_requirement,
            "requirement_id": "auth-log-evidence",
        }
    }
    capture_spec = ExperimentCaptureSpecModel.model_validate(capture_payload)
    authoring_digest = canonical_json_digest(experiment.model_dump(mode="json"))
    envelope = BackendRealizationEnvelopeModel.model_validate_json(_ENVELOPE_FIXTURE.read_text(encoding="utf-8"))
    manifest_payload = json.loads(_BACKEND_MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    manifest_payload["identity"] = {"name": "backend-a", "version": "1"}
    manifest_payload["supported_contract_versions"].append("realization-envelope-v1")
    manifest_payload["realization_envelope"] = envelope.identity.model_dump(mode="json")
    manifest_payload["capabilities"]["provisioner"]["operating_systems"] = [
        {"family": "linux", "distribution": "ubuntu", "versions": ["22.04"]}
    ]
    manifest_payload["capabilities"]["observation"]["capture_offers"] = [
        {
            "offer_id": "compiler-fixture-auth-log-evidence",
            "offer_version": "1.0.0",
            "output_contract": capture_requirement["output_contract"],
            "field_selectors": capture_requirement["field_selectors"],
            "artifact_roles": capture_requirement["required_artifact_roles"],
            "media_types": capture_requirement["expected_media_types"],
            "capture_kind": capture_requirement["capture_kind"],
            "source_classes": ["experiment-capture-spec"],
            "source_refs": [],
            "scopes": [capture_requirement["capture_scope"]],
            "channel_kinds": [],
            "channel_refs": [capture_requirement["channel_ref"]["ref_id"]],
            "window_kinds": ["run"],
            "integrity_modes": capture_requirement["integrity_requirements"],
            "sensitivity": capture_requirement["sensitivity"],
            "availability": "available",
            "fidelity": "complete",
            "disclosure": "full",
            "retention_policy_refs": [capture_requirement["retention_policy"]],
            "export_policy": "not-required",
        }
    ]
    manifest_payload["realization_support"][0]["observation_capabilities"]["operating-system"] = {
        "verification_scope": "presence",
        "observation_strength": "guest-observed",
    }
    manifest = BackendManifestV2Model.model_validate(manifest_payload)
    manifest_ref = ExperimentManifestReferenceModel(
        ref_kind="manifest",
        ref_id="backend-a",
        ref_version="backend-manifest/v2",
        ref_digest=canonical_json_digest(manifest.model_dump(mode="json")),
        subject_ref=ExperimentBackendReferenceModel(ref_kind="backend", ref_id="backend-a", ref_version="1"),
    )
    apparatus = AdmittedApparatusBindingModel(
        manifest_refs=[manifest_ref],
        realization_envelope=envelope.identity,
        capability_refs=(
            sorted(experiment.apparatus_intent.required_capabilities) if experiment.apparatus_intent is not None else []
        ),
    )
    refs = AdmittedTrialPlanInputRefsModel(
        authoring_input_ref=ExperimentReferenceModel(
            ref_kind="authoring-input",
            ref_id=experiment.spec_id,
            ref_version=experiment.spec_version,
            ref_digest=authoring_digest,
        ),
        task_ref=experiment.task_ref,
        task_digest=canonical_json_digest(task.model_dump(mode="json")),
        scenario_family_ref=ExperimentScenarioFamilyReferenceModel(
            ref_kind="scenario-family",
            ref_id=family.name,
            ref_version="expanded-scenario-family/v1",
            ref_digest=family_digest,
        ),
        capture_spec_refs=[
            ExperimentReferenceModel(
                ref_kind="capture-spec",
                ref_id=capture_spec.capture_spec_id,
                ref_version=capture_spec.spec_version,
                ref_digest=canonical_json_digest(capture_spec.model_dump(mode="json")),
            )
        ],
    )
    return TrialCompilationRequest(
        family=family,
        experiment=experiment,
        task=task,
        input_refs=refs,
        apparatus=apparatus,
        realization_envelope=envelope,
        execution_authority=_execution_authority(),
        apparatus_manifests={
            ("backend", "backend-a", "1", "backend-manifest/v2"): manifest,
        },
        capture_specs={capture_spec.capture_spec_id: capture_spec},
    )


def _with_envelope(
    request: TrialCompilationRequest,
    envelope: BackendRealizationEnvelopeModel,
) -> TrialCompilationRequest:
    key = ("backend", "backend-a", "1", "backend-manifest/v2")
    manifest = request.apparatus_manifests[key].model_copy(
        update={"realization_envelope": envelope.identity},
    )
    manifest_ref = request.apparatus.manifest_refs[0].model_copy(
        update={"ref_digest": canonical_json_digest(manifest.model_dump(mode="json"))},
    )
    apparatus = request.apparatus.model_copy(
        update={
            "manifest_refs": [manifest_ref],
            "realization_envelope": envelope.identity,
        }
    )
    return replace(
        request,
        apparatus=apparatus,
        realization_envelope=envelope,
        apparatus_manifests={key: manifest},
    )


def _with_participant_manifest(
    request: TrialCompilationRequest,
) -> TrialCompilationRequest:
    manifest = ParticipantImplementationManifestModel.model_validate_json(
        _PARTICIPANT_MANIFEST_FIXTURE.read_text(encoding="utf-8")
    )
    participant_address = "participants.red"
    reference = AdmittedParticipantManifestReferenceModel(
        participant_address=participant_address,
        implementation_name=manifest.identity.name,
        implementation_version=manifest.identity.version,
        manifest_version=manifest.schema_version,
        manifest_digest=canonical_json_digest(manifest.model_dump(mode="json")),
    )
    key = (
        participant_address,
        manifest.identity.name,
        manifest.identity.version,
        manifest.schema_version,
    )
    apparatus = request.apparatus.model_copy(
        update={"participant_manifest_refs": [reference]},
    )
    return replace(
        request,
        apparatus=apparatus,
        participant_manifests={key: manifest},
    )


def _compile_bytes(request: TrialCompilationRequest) -> bytes:
    result = compile_admitted_trial_plan(request)
    assert result.diagnostics == ()
    assert result.plan is not None
    return canonical_json_bytes(result.plan.model_dump(mode="json"))


def test_capture_specs_are_required_digest_bound_trial_inputs() -> None:
    request = _request()
    demands = compile_capture_spec_demands(tuple(request.capture_specs.values()))
    assert [(demand.demand_id, demand.output_contract) for demand in demands] == [
        ("auth-log-evidence", "participant-behavior-history-event-stream-v1")
    ]

    missing = compile_admitted_trial_plan(replace(request, capture_specs={}))
    assert missing.plan is None
    assert [diagnostic.code for diagnostic in missing.diagnostics] == ["trial-compiler.capture-spec-payload-mismatch"]

    capture_spec = next(iter(request.capture_specs.values()))
    changed_requirement = next(iter(capture_spec.capture_requirements.values())).model_copy(
        update={"output_contract": "unsupported-evidence-contract-v1"}
    )
    changed_spec = capture_spec.model_copy(
        update={"capture_requirements": {changed_requirement.requirement_id: changed_requirement}}
    )
    changed_ref = request.input_refs.capture_spec_refs[0].model_copy(
        update={"ref_digest": canonical_json_digest(changed_spec.model_dump(mode="json"))}
    )
    changed_request = replace(
        request,
        capture_specs={changed_spec.capture_spec_id: changed_spec},
        input_refs=request.input_refs.model_copy(update={"capture_spec_refs": [changed_ref]}),
    )

    unsupported = compile_admitted_trial_plan(changed_request)
    assert unsupported.plan is None
    assert any(diagnostic.code == "capture.output-contract-mismatch" for diagnostic in unsupported.diagnostics)


def test_capture_spec_digest_pin_must_match_the_supplied_payload() -> None:
    request = _request()
    changed_ref = request.input_refs.capture_spec_refs[0].model_copy(update={"ref_digest": "sha256:" + "0" * 64})

    result = compile_admitted_trial_plan(
        replace(
            request,
            input_refs=request.input_refs.model_copy(update={"capture_spec_refs": [changed_ref]}),
        )
    )

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["trial-compiler.capture-spec-ref-mismatch"]


def test_capture_requirement_identities_must_be_unique_across_specs() -> None:
    request = _request()
    capture_spec = next(iter(request.capture_specs.values()))
    copied_spec = capture_spec.model_copy(update={"capture_spec_id": "capture-spec-copy"})
    copied_experiment_ref = request.experiment.capture_spec_refs[0].model_copy(
        update={"ref_id": copied_spec.capture_spec_id}
    )
    changed_experiment = request.experiment.model_copy(
        update={
            "capture_spec_refs": [
                request.experiment.capture_spec_refs[0],
                copied_experiment_ref,
            ]
        }
    )
    copied_input_ref = request.input_refs.capture_spec_refs[0].model_copy(
        update={
            "ref_id": copied_spec.capture_spec_id,
            "ref_digest": canonical_json_digest(copied_spec.model_dump(mode="json")),
        }
    )
    changed_authoring_ref = request.input_refs.authoring_input_ref.model_copy(
        update={"ref_digest": canonical_json_digest(changed_experiment.model_dump(mode="json"))}
    )

    result = compile_admitted_trial_plan(
        replace(
            request,
            experiment=changed_experiment,
            input_refs=request.input_refs.model_copy(
                update={
                    "authoring_input_ref": changed_authoring_ref,
                    "capture_spec_refs": [
                        request.input_refs.capture_spec_refs[0],
                        copied_input_ref,
                    ],
                }
            ),
            capture_specs={
                capture_spec.capture_spec_id: capture_spec,
                copied_spec.capture_spec_id: copied_spec,
            },
        )
    )

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["trial-compiler.capture-requirement-ambiguous"]


def test_task_evidence_requirements_must_resolve_to_capture_requirements() -> None:
    request = _request()
    capture_spec = next(iter(request.capture_specs.values()))
    requirement = next(iter(capture_spec.capture_requirements.values())).model_copy(
        update={"requirement_id": "other-evidence"}
    )
    changed_spec = capture_spec.model_copy(update={"capture_requirements": {requirement.requirement_id: requirement}})
    changed_ref = request.input_refs.capture_spec_refs[0].model_copy(
        update={"ref_digest": canonical_json_digest(changed_spec.model_dump(mode="json"))}
    )

    result = compile_admitted_trial_plan(
        replace(
            request,
            input_refs=request.input_refs.model_copy(update={"capture_spec_refs": [changed_ref]}),
            capture_specs={changed_spec.capture_spec_id: changed_spec},
        )
    )

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["trial-compiler.task-capture-requirement-missing"]


def test_capture_admission_uses_each_selected_scenario_value() -> None:
    request = _request()
    family_payload = request.family.model_dump(
        mode="python",
        by_alias=True,
        exclude_unset=True,
        exclude={"expansion_provenance"},
    )
    family_payload["variables"]["capture_channel"] = {
        "type": "string",
        "default": "log",
        "allowed_values": ["log"],
    }
    family_payload["evidence_requirements"] = {
        "selected-action-log": {
            "description": "Capture the selected participant action log.",
            "source_class": "participant_action",
            "scope": "run",
            "window": "task",
            "channel": "${capture_channel}",
            "artifact_role": "observation",
            "media_types": ["application/json"],
            "sensitivity": "plain",
            "redaction": "none",
            "integrity": "checksum",
            "retention": "study_lifetime",
            "loss_disclosure": "required",
            "output_contract": "participant-behavior-history-event-stream-v1",
            "field_selectors": ["/0/action_contract_address"],
        }
    }
    family = ExpandedScenario.model_validate(family_payload)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)

    key = ("backend", "backend-a", "1", "backend-manifest/v2")
    manifest_payload = request.apparatus_manifests[key].model_dump(mode="json")
    manifest_payload["capabilities"]["observation"]["capture_offers"].append(
        {
            "offer_id": "selected-action-log",
            "offer_version": "1.0.0",
            "output_contract": "participant-behavior-history-event-stream-v1",
            "field_selectors": ["/0/action_contract_address"],
            "artifact_roles": ["observation"],
            "media_types": ["application/json"],
            "capture_kind": "log",
            "source_classes": ["participant_action"],
            "source_refs": [],
            "scopes": ["run"],
            "scope_refs": [],
            "channel_kinds": ["backend-log"],
            "channel_refs": [],
            "window_kinds": ["task"],
            "integrity_modes": ["checksum"],
            "sensitivity": "plain",
            "availability": "available",
            "fidelity": "complete",
            "disclosure": "full",
            "retention_policy_refs": ["study_lifetime"],
            "export_policy": "not-required",
            "redaction_policy": None,
        }
    )
    manifest = BackendManifestV2Model.model_validate(manifest_payload)
    manifest_ref = request.apparatus.manifest_refs[0].model_copy(
        update={"ref_digest": canonical_json_digest(manifest.model_dump(mode="json"))},
    )
    selected_request = replace(
        request.with_family(family),
        apparatus=request.apparatus.model_copy(update={"manifest_refs": [manifest_ref]}),
        apparatus_manifests={key: manifest},
    )

    result = compile_admitted_trial_plan(selected_request)

    assert result.diagnostics == ()
    assert result.plan is not None


def _product_request() -> TrialCompilationRequest:
    request = _request(run_count=4)
    family = _product_family()
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["selection_policies"] = {
        "enumerate-mode": {
            "kind": "enumerate",
            "policy_id": "enumerate-mode",
            "purpose": "nuisance-variation",
            "point_ref": "payload-mode",
            "output_bound": 2,
        },
        "enumerate-path": {
            "kind": "enumerate",
            "policy_id": "enumerate-path",
            "purpose": "nuisance-variation",
            "point_ref": "payload-path",
            "output_bound": 2,
        },
        "product": {
            "kind": "product",
            "policy_id": "product",
            "purpose": "nuisance-variation",
            "policy_refs": ["enumerate-path", "enumerate-mode"],
            "output_bound": 4,
        },
    }
    request = request.with_experiment(ExperimentSpecModel.model_validate(payload))
    return request.with_family(family)


def test_enumeration_compiles_canonical_coordinates_and_leaf_origins() -> None:
    result = compile_admitted_trial_plan(_request())

    assert result.diagnostics == ()
    assert result.plan is not None
    entries = sorted(result.plan.entries.values(), key=lambda entry: entry.coordinate.replicate_id or "")
    assert [entry.coordinate.replicate_id for entry in entries] == ["replicate-000001", "replicate-000002"]
    assert [entry.selections[0].origin_policy_id for entry in entries] == [
        "enumerate-path",
        "enumerate-path",
    ]
    assert [entry.selections[0].outcome.value for entry in entries] == ["/opt/a", "/opt/b"]


def test_v1_coordinate_and_identity_conformance_vectors() -> None:
    vectors = json.loads(_PROFILE_FIXTURE.read_text(encoding="utf-8"))

    for case in vectors["coordinates"]:
        coordinate = TrialCoordinateModel(
            condition_id=case.get("condition_id"),
            replicate_id=replicate_id(case["replicate_ordinal"]),
        )
        assert coordinate_projection(coordinate) == case["expected_projection"]
    for case in vectors["identities"]:
        assert derive_identity(case["kind"], case["projection"]) == case["expected"]


def test_identical_inputs_are_byte_identical_across_threads() -> None:
    request = _request()

    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(_compile_bytes, [request] * 8))

    assert len(set(outputs)) == 1


def test_identical_inputs_are_byte_identical_across_spawned_processes() -> None:
    request = _request()

    with ProcessPoolExecutor(max_workers=2, mp_context=get_context("spawn")) as pool:
        outputs = list(pool.map(_compile_bytes, [request] * 4))

    assert len(set(outputs)) == 1


def test_partition_and_resume_visit_order_cannot_change_plan_bytes() -> None:
    request = _request()
    canonical = _compile_bytes(request)

    outputs = []
    for partitions in (((0, 1),), ((0,), (1,)), ((1,), (0,))):
        result = compile_admitted_trial_plan(request, coordinate_partitions=partitions)
        assert result.plan is not None
        outputs.append(canonical_json_bytes(result.plan.model_dump(mode="json")))

    assert outputs == [canonical, canonical, canonical]


def test_partition_order_drives_coordinate_admission(monkeypatch) -> None:
    visited: list[str | None] = []
    validate_selected_scenario = trial_compiler_module._validate_selected_scenario

    def record_visit(request, row, coordinate):
        visited.append(coordinate.replicate_id)
        return validate_selected_scenario(request, row, coordinate)

    monkeypatch.setattr(trial_compiler_module, "_validate_selected_scenario", record_visit)

    result = compile_admitted_trial_plan(
        _request(),
        coordinate_partitions=((1,), (0,)),
    )

    assert result.plan is not None
    assert visited == ["replicate-000002", "replicate-000001"]


def test_reversed_partition_order_cannot_change_coordinate_failure_diagnostic() -> None:
    request = _request()
    payload = json.loads(_ENVELOPE_FIXTURE.read_text(encoding="utf-8"))
    payload["expression"]["domains"] = {
        "windows-only": {
            "kind": "enum",
            "values": ["windows"],
        }
    }
    payload["expression"]["bindings"] = [
        {
            "path": "nodes.primary.os",
            "scope": "field",
            "posture": "constrained",
            "domain": "windows-only",
        }
    ]
    payload["digest"] = realization_envelope_digest(payload)
    request = _with_envelope(request, BackendRealizationEnvelopeModel.model_validate(payload))

    canonical = compile_admitted_trial_plan(request)
    reversed_partitions = compile_admitted_trial_plan(
        request,
        coordinate_partitions=((1,), (0,)),
    )

    assert canonical == reversed_partitions
    assert canonical.plan is None
    assert canonical.diagnostics[0].address.endswith("replicate-000001")


def test_fixed_policy_broadcasts_to_every_coordinate() -> None:
    request = _request(run_count=3)
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["selection_policies"] = {
        "fixed-path": {
            "kind": "fixed",
            "policy_id": "fixed-path",
            "purpose": "fixed-configuration",
            "point_ref": "payload-path",
            "outcome": {"kind": "literal", "value": "/opt/a"},
            "output_bound": 1,
        }
    }

    result = compile_admitted_trial_plan(request.with_experiment(ExperimentSpecModel.model_validate(payload)))

    assert result.plan is not None
    assert {entry.selections[0].outcome.value for entry in result.plan.entries.values()} == {"/opt/a"}


def test_product_enumeration_has_canonical_cartesian_order() -> None:
    result = compile_admitted_trial_plan(_product_request())

    assert result.plan is not None
    rows = sorted(result.plan.entries.values(), key=lambda entry: entry.coordinate.replicate_id or "")
    assert [tuple(selection.outcome.value for selection in entry.selections) for entry in rows] == [
        ("fast", "/opt/a"),
        ("fast", "/opt/b"),
        ("safe", "/opt/a"),
        ("safe", "/opt/b"),
    ]


def test_shuffled_family_and_policy_maps_do_not_change_product_plan_bytes() -> None:
    request = _product_request()
    canonical = _compile_bytes(request)
    family_payload = request.family.model_dump(
        mode="python",
        by_alias=True,
        exclude_unset=True,
        exclude={"expansion_provenance"},
    )
    family_payload["variables"] = dict(reversed(list(family_payload["variables"].items())))
    family_payload["variation_points"] = dict(reversed(list(family_payload["variation_points"].items())))
    shuffled_family = ExpandedScenario.model_validate(family_payload)
    SemanticValidator(shuffled_family).validate()
    shuffled_family._set_semantic_validated(True)
    experiment_payload = request.experiment.model_dump(mode="json")
    policies = experiment_payload["run_plan"]["selection_policies"]
    experiment_payload["run_plan"]["selection_policies"] = dict(reversed(list(policies.items())))
    shuffled = request.with_family(shuffled_family).with_experiment(
        ExperimentSpecModel.model_validate(experiment_payload)
    )

    assert _compile_bytes(shuffled) == canonical


def test_equal_strata_join_exact_condition_coordinates() -> None:
    request = _request().with_experiment(_stratified_spec())

    result = compile_admitted_trial_plan(request)

    assert result.plan is not None
    by_condition = {
        entry.coordinate.condition_id: entry.selections[0].outcome.value for entry in result.plan.entries.values()
    }
    assert by_condition == {
        "cond-aggressive": "/opt/a",
        "cond-stealthy": "/opt/b",
    }


def test_authoritative_binding_is_admitted_once_with_selection_origin() -> None:
    experiment = _bound_spec()
    request = _request().with_experiment(experiment)
    descriptor_ref = ExperimentReferenceModel(
        ref_kind="other",
        ref_id="compiler-bindings",
        ref_version="experiment-binding-descriptors/v1",
        ref_digest=canonical_json_digest(experiment.binding_descriptors.model_dump(mode="json")),
    )
    request = replace(
        request,
        input_refs=request.input_refs.model_copy(update={"binding_descriptor_set_ref": descriptor_ref}),
    )

    result = compile_admitted_trial_plan(request)

    assert result.plan is not None
    for entry in result.plan.entries.values():
        assert len(entry.bindings) == 1
        assert entry.bindings[0].origin == "selection"
        assert entry.bindings[0].descriptor.source_condition_id == entry.coordinate.condition_id


def test_sample_stream_for_existing_coordinate_is_stable_when_trial_count_changes() -> None:
    two = compile_admitted_trial_plan(_request(run_count=2, sample=True))
    three = compile_admitted_trial_plan(_request(run_count=3, sample=True))

    assert two.plan is not None
    assert three.plan is not None
    two_by_coordinate = {entry.coordinate.replicate_id: entry for entry in two.plan.entries.values()}
    three_by_coordinate = {entry.coordinate.replicate_id: entry for entry in three.plan.entries.values()}
    for coordinate in ("replicate-000001", "replicate-000002"):
        assert two_by_coordinate[coordinate].selections == three_by_coordinate[coordinate].selections
        assert two_by_coordinate[coordinate].stochastic_draws == three_by_coordinate[coordinate].stochastic_draws


def test_sample_profile_identity_and_version_are_exact_pins() -> None:
    request = _request(sample=True)
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["stochastic_controls"][0]["executable_binding"]["profile_ref"]["ref_version"] = (
        "random-stream-profile/v2"
    )

    result = compile_admitted_trial_plan(
        request.with_experiment(ExperimentSpecModel.model_validate(payload)),
    )

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.sample-profile-mismatch"


@settings(max_examples=20, deadline=None)
@given(st.binary(min_size=32, max_size=32))
def test_sampled_values_are_always_in_domain_and_recorded_once(seed: bytes) -> None:
    request = _request(sample=True)
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["stochastic_controls"][0]["executable_binding"]["root_entropy"]["value"] = seed.hex()

    result = compile_admitted_trial_plan(request.with_experiment(ExperimentSpecModel.model_validate(payload)))

    assert result.plan is not None
    for entry in result.plan.entries.values():
        assert len(entry.selections) == 1
        assert entry.selections[0].outcome.value in {"/opt/a", "/opt/b"}
        assert len(entry.stochastic_draws) == 1


def test_bounded_draw_exhaustion_is_atomic_and_reproducible(monkeypatch) -> None:
    def exhausted_batch(*, requests, **_kwargs):
        return BoundedIntegerBatchResult(
            draws=tuple(
                BoundedIntegerDraw(
                    value=None,
                    rejection_attempts=128,
                    rejection_exhausted=True,
                )
                for _ in requests
            ),
            diagnostic=None,
        )

    monkeypatch.setattr(
        "raes_processor.trial_compiler.policies.draw_bounded_integer_batch",
        exhausted_batch,
    )
    request = _request(sample=True)

    first = compile_admitted_trial_plan(request)
    second = compile_admitted_trial_plan(request)

    assert first == second
    assert first.plan is None
    assert first.diagnostics[0].code == "trial-compiler.sample-rejection-exhausted"


def test_ambiguous_policy_roots_fail_atomically_with_bounded_safe_diagnostic() -> None:
    request = _request()
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["selection_policies"]["second-root"] = {
        "kind": "enumerate",
        "policy_id": "second-root",
        "purpose": "nuisance-variation",
        "point_ref": "payload-path",
        "output_bound": 2,
    }
    request = request.with_experiment(ExperimentSpecModel.model_validate(payload))

    result = compile_admitted_trial_plan(request)

    assert result.plan is None
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "trial-compiler.policy-roots-ambiguous"
    assert "/opt/a" not in result.diagnostics[0].message
    assert "/opt/b" not in result.diagnostics[0].message


def test_coordinate_limit_failure_is_atomic_and_precedes_materialization(monkeypatch) -> None:
    monkeypatch.setattr(
        "raes_processor.trial_compiler.inputs.replicate_id",
        lambda _ordinal: pytest.fail("coordinates were materialized before their cardinality was admitted"),
    )
    request = replace(
        _request(),
        limits=TrialCompilationLimitsModel(max_coordinates=1),
    )

    first = compile_admitted_trial_plan(request)
    second = compile_admitted_trial_plan(request)

    assert first == second
    assert first.plan is None
    assert first.diagnostics[0].code == "trial-compiler.coordinate-limit-exceeded"


def test_domain_limit_precedes_integer_interval_materialization(monkeypatch) -> None:
    point = ParameterVariationPoint.model_validate(
        {
            "kind": "parameter",
            "target": {"kind": "variable", "variable": "integer_value"},
            "domain": {
                "kind": "numeric-interval",
                "numeric_type": "integer",
                "lower": 0,
                "upper": 1_000_000,
            },
        }
    )
    monkeypatch.setattr(
        "raes_processor.trial_compiler.domains.LiteralBindingValueModel",
        lambda **_kwargs: pytest.fail("domain outcomes were materialized before their cardinality was admitted"),
    )

    with pytest.raises(CompilationFailure) as raised:
        canonical_domain_outcomes(point, maximum=2)

    assert raised.value.code == "domain-limit-exceeded"


def test_product_limit_precedes_cartesian_materialization(monkeypatch) -> None:
    monkeypatch.setattr(
        "raes_processor.trial_compiler.policies.product",
        lambda *_args: pytest.fail("Cartesian rows were materialized before their cardinality was admitted"),
    )
    request = replace(
        _product_request(),
        limits=TrialCompilationLimitsModel(max_product_outputs=3),
    )

    result = compile_admitted_trial_plan(request)

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.product-limit-exceeded"


def test_selected_scenario_must_be_a_member_of_exact_envelope() -> None:
    request = _request()
    payload = json.loads(_ENVELOPE_FIXTURE.read_text(encoding="utf-8"))
    payload["expression"]["domains"] = {"windows-only": {"kind": "enum", "values": ["windows"]}}
    payload["expression"]["bindings"] = [
        {
            "path": "nodes.primary.os",
            "scope": "field",
            "posture": "constrained",
            "domain": "windows-only",
        }
    ]
    payload["digest"] = realization_envelope_digest(payload)
    envelope = BackendRealizationEnvelopeModel.model_validate(payload)

    result = compile_admitted_trial_plan(_with_envelope(request, envelope))

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.realization-envelope-membership-rejected"


def test_realization_envelope_content_digest_changes_sealed_plan_identity() -> None:
    request = _request()
    changed_payload = json.loads(_ENVELOPE_FIXTURE.read_text(encoding="utf-8"))
    topology = next(claim for claim in changed_payload["concerns"] if claim["concern"] == "topology")
    topology["mechanism"] = "alternate-trusted-topology-mechanism"
    changed_payload["digest"] = realization_envelope_digest(changed_payload)
    changed = _with_envelope(
        request,
        BackendRealizationEnvelopeModel.model_validate(changed_payload),
    )

    original_result = compile_admitted_trial_plan(request)
    changed_result = compile_admitted_trial_plan(changed)

    assert original_result.plan is not None
    assert changed_result.plan is not None
    assert original_result.plan.plan_id != changed_result.plan.plan_id


def test_required_apparatus_capabilities_must_be_admitted() -> None:
    request = _request()

    result = compile_admitted_trial_plan(
        replace(
            request,
            apparatus=request.apparatus.model_copy(update={"capability_refs": []}),
        )
    )

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.apparatus-capability-missing"


def test_apparatus_capability_claims_must_come_from_digest_bound_manifests() -> None:
    request = _request()
    apparatus = request.apparatus.model_copy(
        update={"capability_refs": [*request.apparatus.capability_refs, "self-asserted-capability"]}
    )

    result = compile_admitted_trial_plan(replace(request, apparatus=apparatus))

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.apparatus-capability-unproven"


def test_every_selected_apparatus_ref_requires_exact_concrete_manifest_content() -> None:
    request = _request()

    missing = compile_admitted_trial_plan(replace(request, apparatus_manifests={}))
    mismatched_ref = request.apparatus.manifest_refs[0].model_copy(update={"ref_digest": "sha256:" + "0" * 64})
    mismatched = compile_admitted_trial_plan(
        replace(
            request,
            apparatus=request.apparatus.model_copy(update={"manifest_refs": [mismatched_ref]}),
        )
    )

    assert missing.plan is None
    assert missing.diagnostics[0].code == "trial-compiler.apparatus-manifest-payload-missing"
    assert mismatched.plan is None
    assert mismatched.diagnostics[0].code == "trial-compiler.apparatus-manifest-digest-mismatch"


def test_required_apparatus_manifest_digest_must_match_selected_content() -> None:
    request = _request()
    experiment_payload = request.experiment.model_dump(mode="json")
    required_ref = request.apparatus.manifest_refs[0].model_copy(update={"ref_digest": "sha256:" + "f" * 64})
    experiment_payload["apparatus_intent"] = {
        "required_manifest_refs": [required_ref.model_dump(mode="json")],
    }
    request = request.with_experiment(ExperimentSpecModel.model_validate(experiment_payload))

    result = compile_admitted_trial_plan(request)

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.apparatus-manifest-missing"


def test_participant_manifest_authority_is_digest_bound_into_plan_identity() -> None:
    request = _request()
    with_participant = _with_participant_manifest(request)

    without_result = compile_admitted_trial_plan(request)
    with_result = compile_admitted_trial_plan(with_participant)

    assert without_result.plan is not None
    assert with_result.plan is not None
    assert without_result.plan.plan_id != with_result.plan.plan_id
    assert all(
        entry.apparatus.participant_manifest_refs == with_participant.apparatus.participant_manifest_refs
        for entry in with_result.plan.entries.values()
    )


def test_participant_manifest_authority_requires_exact_payload_and_digest() -> None:
    request = _with_participant_manifest(_request())
    bad_reference = request.apparatus.participant_manifest_refs[0].model_copy(
        update={"manifest_digest": "sha256:" + "0" * 64}
    )

    missing = compile_admitted_trial_plan(replace(request, participant_manifests={}))
    mismatched = compile_admitted_trial_plan(
        replace(
            request,
            apparatus=request.apparatus.model_copy(update={"participant_manifest_refs": [bad_reference]}),
        )
    )

    assert missing.plan is None
    assert missing.diagnostics[0].code == "trial-compiler.participant-manifest-payload-missing"
    assert mismatched.plan is None
    assert mismatched.diagnostics[0].code == "trial-compiler.participant-manifest-digest-mismatch"


def test_backend_allowlist_applies_to_every_selected_backend() -> None:
    request = _request()
    manifest_payload = request.apparatus_manifests[("backend", "backend-a", "1", "backend-manifest/v2")].model_dump(
        mode="json"
    )
    manifest_payload["identity"] = {"name": "backend-b", "version": "1"}
    backend_b = BackendManifestV2Model.model_validate(manifest_payload)
    backend_b_ref = ExperimentManifestReferenceModel(
        ref_kind="manifest",
        ref_id="backend-b",
        ref_version="backend-manifest/v2",
        ref_digest=canonical_json_digest(backend_b.model_dump(mode="json")),
        subject_ref=ExperimentBackendReferenceModel(
            ref_kind="backend",
            ref_id="backend-b",
            ref_version="1",
        ),
    )
    experiment_payload = request.experiment.model_dump(mode="json")
    experiment_payload["apparatus_intent"] = {
        "allowed_backend_refs": [
            {
                "ref_kind": "backend",
                "ref_id": "backend-a",
                "ref_version": "1",
            }
        ],
        "required_manifest_refs": [request.apparatus.manifest_refs[0].model_dump(mode="json")],
    }
    experiment = ExperimentSpecModel.model_validate(experiment_payload)
    request = request.with_experiment(experiment)
    request = replace(
        request,
        apparatus=request.apparatus.model_copy(
            update={"manifest_refs": [*request.apparatus.manifest_refs, backend_b_ref]}
        ),
        apparatus_manifests={
            **request.apparatus_manifests,
            ("backend", "backend-b", "1", "backend-manifest/v2"): backend_b,
        },
    )

    result = compile_admitted_trial_plan(request)

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.apparatus-identity-not-allowed"


def test_compilation_has_no_filesystem_side_effect(tmp_path: Path) -> None:
    before = tuple(tmp_path.iterdir())

    _compile_bytes(_request())

    assert tuple(tmp_path.iterdir()) == before
