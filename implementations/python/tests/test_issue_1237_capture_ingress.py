"""The same capture failures remain closed at every pre-effect ingress."""

from __future__ import annotations

from dataclasses import replace

import pytest
from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendManifestV2Model, ExperimentTaskModel
from raes_contracts.contracts.admitted_trial_plan import seal_admitted_trial_entry, seal_admitted_trial_plan
from raes_contracts.plan_effects import plan_can_mutate
from raes_contracts.planning import PlanScope
from raes_processor.capture_admission import compile_capture_spec_demands
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import instantiate_admitted_trial_entry, realize_admitted_trial_entry
from raes_runtime.control_plane import RuntimeControlPlane
from test_sce_002_trial_realization import _BACKEND_KEY, _TASK_FIXTURE, _realization_inputs, _request_with_processor

CAPTURE_FAILURES = {
    "availability": ("unavailable", "availability-insufficient"),
    "fidelity": ("lossy", "fidelity-insufficient"),
    "field_selectors": (["/not-promised"], "field-selector-missing"),
    "integrity_modes": (["signature"], "integrity-mismatch"),
    "window_kinds": (["manual"], "window-mismatch"),
    "scopes": (["participant"], "scope-mismatch"),
    "channel_refs": (["different-channel"], "channel-ref-mismatch"),
    "retention_policy_refs": (["different-retention"], "retention-mismatch"),
}


def _with_offer_change(request, name, value):
    payload = request.apparatus_manifests[_BACKEND_KEY].model_dump(mode="json")
    payload["capabilities"]["observation"]["capture_offers"][0][name] = value
    manifest = BackendManifestV2Model.model_validate(payload)
    references = [
        reference.model_copy(update={"ref_digest": canonical_json_digest(payload)})
        if reference.subject_ref.ref_kind == "backend"
        else reference
        for reference in request.apparatus.manifest_refs
    ]
    return replace(
        request,
        apparatus=request.apparatus.model_copy(update={"manifest_refs": references}),
        apparatus_manifests={**request.apparatus_manifests, _BACKEND_KEY: manifest},
    )


def _reseal_apparatus(admitted, apparatus):
    # A well-formed self-digest is not proof of capability admission. Re-seal
    # every layer so realization must actually recheck the capture invariant.
    entries = {}
    for key, entry in admitted.entries.items():
        payload = {name: value for name, value in entry if name != "entry_digest"}
        payload["apparatus"] = apparatus
        entries[key] = seal_admitted_trial_entry(**payload)
    payload = {name: value for name, value in admitted if name not in {"plan_digest", "entries"}}
    return seal_admitted_trial_plan(**payload, entries=entries)


@pytest.mark.parametrize("failure", [None, *CAPTURE_FAILURES])
def test_capture_invariant_across_planning_compilation_realization_and_runtime(failure: str | None) -> None:
    request = _request_with_processor()
    accepted = compile_admitted_trial_plan(request)
    assert accepted.plan is not None
    assert accepted.diagnostics == ()
    admitted = accepted.plan
    entry_id = next(iter(admitted.entries))
    instantiated = instantiate_admitted_trial_entry(plan=admitted, plan_entry_id=entry_id, family=request.family)
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_bytes())
    if failure is not None:
        unsupported, diagnostic = CAPTURE_FAILURES[failure]
        request = _with_offer_change(request, failure, unsupported)
        admitted = _reseal_apparatus(admitted, request.apparatus)
    runtime_manifest = backend_manifest_from_v2_model_with_envelope(
        request.apparatus_manifests[_BACKEND_KEY],
        request.realization_envelope,
    )
    target = replace(create_stub_target(), manifest=runtime_manifest, time_runtime=None)
    runtime_model = replace(
        compile_runtime_model(instantiated),
        capture_demands=compile_capture_spec_demands(tuple(request.capture_specs.values())),
    )
    execution = plan(runtime_model, runtime_manifest, scope=PlanScope(target_name=target.name))
    compilation = compile_admitted_trial_plan(request)
    inputs = _realization_inputs(request, admitted, task)
    control_plane = RuntimeControlPlane(target)
    if failure is None:
        assert execution.is_valid
        assert compilation.plan is not None
        assert realize_admitted_trial_entry(inputs=inputs, plan_entry_id=entry_id).execution_plan.is_valid
        control_plane.register_planner_produced_plan(execution)
        assert control_plane.is_planner_authorized_plan(execution.provisioning)
    else:
        assert not execution.is_valid
        assert compilation.plan is None
        assert any(item.code == f"capture.{diagnostic}" for item in execution.diagnostics)
        assert any(item.code == f"capture.{diagnostic}" for item in compilation.diagnostics)
        with pytest.raises(ValueError, match="processor planning failed"):
            realize_admitted_trial_entry(inputs=inputs, plan_entry_id=entry_id)
        with pytest.raises(ValueError, match="invalid composite"):
            control_plane.register_planner_produced_plan(execution)
        assert execution.provisioning.operations
        for phase in ("provisioning", "orchestration", "evaluation"):
            submitted = getattr(execution, phase)
            if not submitted.operations and not plan_can_mutate(submitted):
                continue
            receipt = getattr(control_plane, f"submit_{phase}")(submitted)
            assert not receipt.accepted
        assert control_plane.snapshot.entries == {}
