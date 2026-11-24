"""Installed test owners with actual configuration readback and cleanup probes."""

from dataclasses import replace

from assigned_trial_consumer_support import TrialServices as TrialServices
from raes.canonical import canonical_sdl_digest
from raes_backend_stubs.manifest import load_stub_realization_envelope
from raes_backend_stubs.stubs import create_stub_components
from raes_contracts.canonical import canonical_json_digest
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import realize_admitted_trial_entry
from raes_runtime.registry import RuntimeTarget
from test_issue_1625_structural_variation import _family
from test_issue_1666_factorial_compilation import _treatment_request, _with_design
from test_sce_002_trial_realization import _realization_inputs, _request_with_processor


def factorial_inputs(transform=None):
    request, processor = _treatment_request(), _request_with_processor()
    family_payload = request.family.model_dump(mode="python", by_alias=True, exclude_unset=True)
    # The installed stub realizes compute-node presence. It does not claim the
    # runtime-inventory capabilities used by the compiler-only fixture.
    family_payload["nodes"] = {
        name: {
            "type": "compute",
            "os": "linux",
            "os_distribution": "ubuntu",
            "os_version": "22.04",
            "architecture": "x86_64",
            "resources": {"ram": "1 gib", "cpu": 1},
        }
        for name in ("primary", "relay-47")
    }
    family_payload["content"] = {"payload": {"type": "file", "target": "primary", "path": "${payload_path}"}}
    family_payload["variation_points"]["deployment-shape"]["alternatives"]["instrumented"].pop("inventory")
    request = request.with_family(_family(family_payload))
    design = request.experiment.model_dump(mode="json")
    for levels in design["factorial_design"]["level_effects"].values():
        for effect in levels.values():
            for selection in effect.get("selections", []):
                selection["scenario_family_digest"] = canonical_sdl_digest(request.family).value
    request = _with_design(request, design)
    request = replace(
        request,
        apparatus_manifests=processor.apparatus_manifests,
        apparatus=processor.apparatus.model_copy(
            update={"participant_manifest_refs": request.apparatus.participant_manifest_refs}
        ),
    )
    envelope = load_stub_realization_envelope()
    backend_key = ("backend", "backend-a", "1", "backend-manifest/v2")
    manifest = request.apparatus_manifests[backend_key].model_copy(update={"realization_envelope": envelope.identity})
    refs = [
        ref.model_copy(update={"ref_digest": canonical_json_digest(manifest.model_dump(mode="json"))})
        if ref.subject_ref.ref_kind == "backend"
        else ref
        for ref in request.apparatus.manifest_refs
    ]
    request = replace(
        request,
        realization_envelope=envelope,
        apparatus_manifests={**request.apparatus_manifests, backend_key: manifest},
        apparatus=request.apparatus.model_copy(
            update={"realization_envelope": envelope.identity, "manifest_refs": refs}
        ),
    )
    if transform is not None:
        request = transform(request)
    compiled = compile_admitted_trial_plan(request)
    assert compiled.plan is not None, compiled.diagnostics
    inputs = _realization_inputs(request, compiled.plan, request.task)
    first = realize_admitted_trial_entry(inputs=inputs, plan_entry_id=next(iter(compiled.plan.entries)))
    manifest = first.execution_plan.manifest
    components = create_stub_components(manifest=manifest)
    provider = None
    if manifest.operation_supervision is not None:
        from issue_1629_provider_fixture import TrialProvider

        provider = TrialProvider()
    target = RuntimeTarget(name="trial", manifest=manifest, **{**vars(components), "operation_provider": provider})
    return request, inputs, target
