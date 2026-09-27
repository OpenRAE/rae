"""Authored trial execution choices reach backend admission (issue #1361)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from paths import REPO_ROOT
from pydantic import ValidationError
from raes import canonical_instantiated_sdl_digest, select_scenario_family
from raes_backend_protocols.capabilities import OperationSupervisionCapabilities
from raes_backend_protocols.cleanup_admission import require_execution_authority_capability
from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_v2_model
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedMixedCompositionBindingModel,
    BackendManifestV2Model,
    ExecutionRetryPolicyModel,
    ExperimentManifestReferenceModel,
    ExperimentProcessorReferenceModel,
    ExperimentReferenceModel,
    OperationSupervisionCapabilitiesModel,
    ProcessorManifestV2Model,
    TrialExecutionAuthorityModel,
    required_operation_guarantees,
    seal_admitted_trial_entry,
    seal_admitted_trial_plan,
    seal_mixed_composition_profile,
)
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan
from raes_processor.trial_compiler.profiles import realization_assignment_key
from test_issue_1014_mixed_composition_contracts import _alternative_profile
from test_issue_1015_mixed_staged_trial_admission import _mixed_request, _profile_context
from test_sce_002_trial_compiler import _request

_BACKEND_KEY = ("backend", "backend-a", "1", "backend-manifest/v2")
_PROCESSOR_MANIFEST_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "processor-manifest" / "processor-manifest-v2" / "valid" / "reference.json"
)


def _authority(
    request: TrialCompilationRequest,
    *,
    on_timeout: str = "cleanup-and-fail",
    max_attempts: int = 1,
    after_effect_policy: str = "disallow",
) -> TrialExecutionAuthorityModel:
    authority = request.execution_authority
    cleanup = authority.cleanup.model_copy(
        update={
            "retry_policy": ExecutionRetryPolicyModel(
                max_attempts=max_attempts, after_effect_policy=after_effect_policy
            )
        }
    )
    return authority.model_copy(update={"on_timeout": on_timeout, "cleanup": cleanup})


def _with_guarantees(request: TrialCompilationRequest, guarantees: list[str]) -> TrialCompilationRequest:
    payload = request.apparatus_manifests[_BACKEND_KEY].model_dump(mode="json")
    payload["supported_contract_versions"] = sorted(
        {*payload["supported_contract_versions"], *BACKEND_OPERATION_CONTRACT_IDS}
    )
    payload["capabilities"]["operation_supervision"] = {"name": "fixture-supervision", "guarantees": guarantees}
    manifest = BackendManifestV2Model.model_validate(payload)
    manifest_ref = request.apparatus.manifest_refs[0].model_copy(
        update={"ref_digest": canonical_json_digest(manifest.model_dump(mode="json"))}
    )
    apparatus = request.apparatus.model_copy(update={"manifest_refs": [manifest_ref]})
    return replace(request, apparatus=apparatus, apparatus_manifests={_BACKEND_KEY: manifest})


@pytest.mark.parametrize(
    ("on_timeout", "max_attempts", "after_effect_policy", "expected"),
    [
        ("cleanup-and-fail", 1, "disallow", ()),
        ("abort", 1, "idempotent", ()),
        ("cancel", 1, "disallow", ("cancellation",)),
        ("abort", 2, "disallow", ("cessation-evidence", "effect-observation")),
        ("abort", 3, "idempotent", ("cessation-evidence",)),
        ("cancel", 2, "disallow", ("cancellation", "cessation-evidence", "effect-observation")),
    ],
)
def test_guarantees_are_derived_from_authored_choices_only(
    on_timeout: str, max_attempts: int, after_effect_policy: str, expected: tuple[str, ...]
) -> None:
    policy = ExecutionRetryPolicyModel(max_attempts=max_attempts, after_effect_policy=after_effect_policy)

    assert required_operation_guarantees(on_timeout, policy) == expected


def test_default_choices_compile_without_guarantees_or_serialized_field() -> None:
    result = compile_admitted_trial_plan(_request())

    assert result.plan is not None
    for entry in result.plan.entries.values():
        assert entry.execution_controls.required_guarantees == ()
        assert "required_guarantees" not in entry.execution_controls.model_dump(mode="json")


def test_backend_without_declared_guarantee_is_rejected_before_any_plan() -> None:
    request = _request()
    request = replace(request, execution_authority=_authority(request, on_timeout="cancel"))

    result = compile_admitted_trial_plan(request)

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["trial-compiler.execution-authority-unsupported"]
    assert result.diagnostics[0].address == "/execution_authority"


def test_backend_missing_one_of_several_guarantees_is_rejected() -> None:
    request = _with_guarantees(_request(), ["cessation-evidence"])
    request = replace(request, execution_authority=_authority(request, max_attempts=2))

    result = compile_admitted_trial_plan(request)

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.execution-authority-unsupported"


def test_supporting_backend_admits_and_the_plan_carries_the_compiled_requirement() -> None:
    request = _with_guarantees(_request(), ["cancellation", "cessation-evidence", "effect-observation"])
    request = replace(request, execution_authority=_authority(request, on_timeout="cancel", max_attempts=2))

    result = compile_admitted_trial_plan(request)

    assert result.plan is not None
    for entry in result.plan.entries.values():
        assert entry.execution_controls.required_guarantees == (
            "cancellation",
            "cessation-evidence",
            "effect-observation",
        )


def test_every_mixed_composition_backend_must_honour_the_choices() -> None:
    mixed = _mixed_request()
    rejected = replace(mixed, execution_authority=_authority(mixed, on_timeout="cancel"))

    result = compile_admitted_trial_plan(rejected)

    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.execution-authority-unsupported"

    supported = _mixed_request(base_request=_with_guarantees(_request(run_count=2), ["cancellation"]))
    admitted = compile_admitted_trial_plan(
        replace(supported, execution_authority=_authority(supported, on_timeout="cancel"))
    )

    assert admitted.plan is not None
    assert {entry.execution_controls.required_guarantees for entry in admitted.plan.entries.values()} == {
        ("cancellation",)
    }


def _processor_only_mixed_request() -> TrialCompilationRequest:
    """A mixed realization whose every component is a processor, so no backend is selected."""

    request = _request()
    request = request.with_experiment(request.experiment.model_copy(update={"apparatus_intent": None}))
    pure = compile_admitted_trial_plan(request).plan
    assert pure is not None
    processor = ProcessorManifestV2Model.model_validate_json(_PROCESSOR_MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    processor_ref = ExperimentManifestReferenceModel(
        ref_kind="manifest",
        ref_id=processor.identity.name,
        ref_version=processor.schema_version,
        ref_digest=canonical_json_digest(processor.model_dump(mode="json")),
        subject_ref=ExperimentProcessorReferenceModel(
            ref_kind="processor", ref_id=processor.identity.name, ref_version=processor.identity.version
        ),
    )
    assignments, profiles, contexts, profile_refs = {}, {}, {}, []
    for entry in pure.entries.values():
        outcomes = {selection.variation_point_id: selection.outcome for selection in entry.selections}
        fields = _alternative_profile().model_dump(mode="python", exclude={"profile_digest"})
        fields["profile_id"] = f"profile:{entry.coordinate.condition_id}:{entry.coordinate.replicate_id}"
        for component_id, component in fields["components"].items():
            component["apparatus_identity_ref"] = f"apparatus:{component_id}"
            component["manifest_ref"] = processor_ref.model_dump(mode="python")
            component["realization_envelope"] = request.realization_envelope.identity.model_dump(mode="python")
        fields["scenario_snapshot_ref"] = ExperimentReferenceModel(
            ref_kind="scenario-snapshot",
            ref_id=f"snapshot:compiler-family:{entry.coordinate.replicate_id}",
            ref_version="instantiated-scenario-snapshot/v1",
            ref_digest=canonical_instantiated_sdl_digest(select_scenario_family(request.family, outcomes)).value,
        )
        profile = seal_mixed_composition_profile(**fields)
        profile_ref = ExperimentReferenceModel(
            ref_kind="profile",
            ref_id=profile.profile_id,
            ref_version=profile.profile_revision,
            ref_digest=profile.profile_digest,
        )
        assignments[realization_assignment_key(entry.coordinate)] = AdmittedMixedCompositionBindingModel(
            profile_ref=profile_ref
        )
        profiles[profile.profile_id] = profile
        contexts[profile.profile_id] = _profile_context(profile)
        profile_refs.append(profile_ref)
    processor_key = ("processor", processor.identity.name, processor.identity.version, processor.schema_version)
    return replace(
        request,
        input_refs=request.input_refs.model_copy(update={"mixed_composition_profile_refs": profile_refs}),
        realization_assignments=assignments,
        mixed_profiles=profiles,
        mixed_profile_contexts=contexts,
        mixed_realization_envelopes={request.realization_envelope.identity.envelope_id: request.realization_envelope},
        apparatus_manifests={**request.apparatus_manifests, processor_key: processor},
    )


def test_realization_without_any_selected_backend_is_refused() -> None:
    result = compile_admitted_trial_plan(_processor_only_mixed_request())

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["trial-compiler.execution-authority-unsupported"]


def test_sealed_plan_rejects_guarantees_that_contradict_its_choices() -> None:
    plan = compile_admitted_trial_plan(_request()).plan
    assert plan is not None
    entry = next(iter(plan.entries.values()))
    entry_fields = {name: getattr(entry, name) for name in type(entry).model_fields if name != "entry_digest"}
    entry_fields["execution_controls"] = entry.execution_controls.model_copy(
        update={"required_guarantees": ("cancellation",)}
    )
    resealed = seal_admitted_trial_entry(**entry_fields)
    plan_fields = {name: getattr(plan, name) for name in type(plan).model_fields if name != "plan_digest"}
    plan_fields["entries"] = {**plan.entries, resealed.plan_entry_id: resealed}

    with pytest.raises(ValidationError, match="required_guarantees must equal"):
        seal_admitted_trial_plan(**plan_fields)


def test_required_guarantees_are_canonical() -> None:
    plan = compile_admitted_trial_plan(_request()).plan
    assert plan is not None
    controls = next(iter(plan.entries.values())).execution_controls
    unsorted = {**controls.model_dump(mode="json"), "required_guarantees": ["effect-observation", "cancellation"]}

    with pytest.raises(ValidationError, match="unique and sorted"):
        type(controls).model_validate(unsorted)


def test_manifest_declaration_requires_the_operation_contract_family() -> None:
    payload = _request().apparatus_manifests[_BACKEND_KEY].model_dump(mode="json")
    payload["capabilities"]["operation_supervision"] = {"name": "fixture", "guarantees": ["cancellation"]}

    with pytest.raises(ValidationError, match="backend operation contract family"):
        BackendManifestV2Model.model_validate(payload)


@pytest.mark.parametrize("guarantees", [[], ["cancellation", "cancellation"], ["rollback"]])
def test_manifest_declaration_is_closed_and_non_empty(guarantees: list[str]) -> None:
    with pytest.raises(ValidationError):
        OperationSupervisionCapabilitiesModel(name="fixture", guarantees=guarantees)


def test_manifest_declaration_round_trips_through_the_internal_manifest() -> None:
    request = _with_guarantees(_request(), ["effect-observation", "cancellation"])
    model = request.apparatus_manifests[_BACKEND_KEY].model_copy(update={"realization_envelope": None})
    model = BackendManifestV2Model.model_validate(
        {
            **model.model_dump(mode="json", exclude={"realization_envelope"}),
            "supported_contract_versions": [
                contract for contract in model.supported_contract_versions if contract != "realization-envelope-v1"
            ],
        }
    )

    manifest = backend_manifest_from_v2_model(model)

    assert manifest.operation_supervision == OperationSupervisionCapabilities(
        name="fixture-supervision", guarantees=frozenset({"cancellation", "effect-observation"})
    )
    assert backend_manifest_v2_model(manifest).capabilities.operation_supervision == (
        model.capabilities.operation_supervision.model_copy(
            update={"guarantees": ["cancellation", "effect-observation"]}
        )
    )


def test_admission_also_enforces_the_cleanup_plan_capability() -> None:
    request = _request()
    plan = compile_admitted_trial_plan(request).plan
    assert plan is not None
    cleanup = next(iter(plan.cleanup_plans.values()))
    payload = request.apparatus_manifests[_BACKEND_KEY].model_dump(mode="json", exclude={"realization_envelope"})
    payload["supported_contract_versions"] = [
        contract
        for contract in payload["supported_contract_versions"]
        if contract not in {"trial-cleanup-plan-v1", "trial-cleanup-receipt-v1", "realization-envelope-v1"}
    ]
    payload["capabilities"]["cleanup"] = None
    manifest = backend_manifest_from_v2_model(BackendManifestV2Model.model_validate(payload))

    with pytest.raises(ValueError, match="cleanup capabilities"):
        require_execution_authority_capability(manifest, cleanup_plan=cleanup, required_guarantees=())
