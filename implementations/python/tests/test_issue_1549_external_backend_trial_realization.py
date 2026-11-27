"""Issue #1549: admit externally owned backends through exact manifests."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from paths import REPO_ROOT
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ApparatusIdentityModel,
    BackendCompatibilityModel,
    BackendManifestV2Model,
    ExperimentBackendReferenceModel,
    ExperimentManifestReferenceModel,
    ExperimentProcessorReferenceModel,
    ProcessorCompatibilityModel,
    ProcessorManifestV2Model,
    processor_backend_manifests_are_mutually_compatible,
)
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_processor.manifest import (
    create_reference_processor_manifest,
    reference_processor_manifest_model,
    reference_processor_manifest_payload,
    reference_processor_manifest_v2_model,
)
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan
from raes_processor.trial_realization import TrialRealizationInputs, realize_admitted_trial_entry
from test_sce_002_trial_compiler import _request

_CAPTURE = json.loads(
    (
        REPO_ROOT
        / "implementations"
        / "python"
        / "tests"
        / "data"
        / "boundary_captures"
        / "lilrae-aptl-backend-manifest.json"
    ).read_text(encoding="utf-8")
)
_COMPATIBILITY_CODE = "trial-compiler.apparatus-compatibility-rejected"


def _manifest_ref(
    manifest: BackendManifestV2Model | ProcessorManifestV2Model,
) -> ExperimentManifestReferenceModel:
    if isinstance(manifest, BackendManifestV2Model):
        subject = ExperimentBackendReferenceModel(
            ref_kind="backend",
            ref_id=manifest.identity.name,
            ref_version=manifest.identity.version,
        )
    else:
        subject = ExperimentProcessorReferenceModel(
            ref_kind="processor",
            ref_id=manifest.identity.name,
            ref_version=manifest.identity.version,
        )
    return ExperimentManifestReferenceModel(
        ref_kind="manifest",
        ref_id=manifest.identity.name,
        ref_version=manifest.schema_version,
        ref_digest=canonical_json_digest(manifest.model_dump(mode="json")),
        subject_ref=subject,
    )


def _with_manifests(
    request: TrialCompilationRequest,
    backend: BackendManifestV2Model,
    processor: ProcessorManifestV2Model,
    envelope: BackendRealizationEnvelopeModel,
) -> TrialCompilationRequest:
    manifests = {
        ("backend", backend.identity.name, backend.identity.version, backend.schema_version): backend,
        ("processor", processor.identity.name, processor.identity.version, processor.schema_version): processor,
    }
    apparatus = request.apparatus.model_copy(
        update={
            "manifest_refs": [_manifest_ref(backend), _manifest_ref(processor)],
            "realization_envelope": envelope.identity,
        }
    )
    return replace(
        request,
        apparatus=apparatus,
        apparatus_manifests=manifests,
        realization_envelope=envelope,
    )


def _external_request() -> TrialCompilationRequest:
    request = _request()
    original_backend = next(
        manifest for manifest in request.apparatus_manifests.values() if isinstance(manifest, BackendManifestV2Model)
    )
    backend = original_backend.model_copy(
        update={"identity": ApparatusIdentityModel(name="external-owned", version="1")}
    )
    processor = reference_processor_manifest_v2_model(
        version="test",
        compatible_backends={backend.identity.name},
    )
    return _with_manifests(request, backend, processor, request.realization_envelope)


def _replace_manifest(
    request: TrialCompilationRequest,
    replacement: BackendManifestV2Model | ProcessorManifestV2Model,
) -> TrialCompilationRequest:
    manifests = {
        key: replacement
        if key[0] == ("backend" if isinstance(replacement, BackendManifestV2Model) else "processor")
        else value
        for key, value in request.apparatus_manifests.items()
    }
    references = [
        _manifest_ref(replacement)
        if reference.subject_ref is not None
        and reference.subject_ref.ref_kind
        == ("backend" if isinstance(replacement, BackendManifestV2Model) else "processor")
        else reference
        for reference in request.apparatus.manifest_refs
    ]
    return replace(
        request,
        apparatus=request.apparatus.model_copy(update={"manifest_refs": references}),
        apparatus_manifests=manifests,
    )


def test_reference_processor_establishes_compatibility_with_captured_aptl_manifest() -> None:
    backend = BackendManifestV2Model.model_validate(_CAPTURE["backend_manifest"])
    compatible_backends = {backend.identity.name, "another-external-backend"}
    processor = reference_processor_manifest_v2_model(
        version="test",
        compatible_backends=compatible_backends,
    )

    assert processor.compatibility.backends == ["another-external-backend", "aptl"]
    assert create_reference_processor_manifest(
        version="test",
        compatible_backends=compatible_backends,
    ).compatible_backends == frozenset(compatible_backends)
    assert (
        reference_processor_manifest_model(
            version="test",
            compatible_backends=compatible_backends,
        )
        == processor
    )
    assert reference_processor_manifest_payload(
        version="test",
        compatible_backends=compatible_backends,
    ) == processor.model_dump(mode="json")
    assert processor_backend_manifests_are_mutually_compatible(processor, backend)


def test_trial_realization_accepts_an_external_backend_manifest() -> None:
    request = _external_request()
    result = compile_admitted_trial_plan(request)

    assert result.diagnostics == ()
    assert result.plan is not None
    entry = next(iter(result.plan.entries.values()))
    backend_key = next(key for key in request.apparatus_manifests if key[0] == "backend")
    realized = realize_admitted_trial_entry(
        inputs=TrialRealizationInputs(
            plan=result.plan,
            family=request.family,
            experiment=request.experiment,
            task=request.task,
            capture_specs=request.capture_specs,
            apparatus_manifests=request.apparatus_manifests,
            realization_envelope=request.realization_envelope,
            backend_key=backend_key,
        ),
        plan_entry_id=entry.plan_entry_id,
    )

    assert realized.execution_plan.is_valid


@pytest.mark.parametrize("direction", ["processor", "backend"])
def test_trial_compiler_rejects_each_incompatible_manifest_direction(direction: str) -> None:
    request = _external_request()
    if direction == "processor":
        processor = next(
            manifest
            for manifest in request.apparatus_manifests.values()
            if isinstance(manifest, ProcessorManifestV2Model)
        ).model_copy(update={"compatibility": ProcessorCompatibilityModel(backends=["other-backend"])})
        request = _replace_manifest(request, processor)
    else:
        backend = next(
            manifest
            for manifest in request.apparatus_manifests.values()
            if isinstance(manifest, BackendManifestV2Model)
        ).model_copy(update={"compatibility": BackendCompatibilityModel(processors=["other-processor"])})
        request = _replace_manifest(request, backend)

    result = compile_admitted_trial_plan(request)

    assert result.plan is None
    assert [(diagnostic.code, diagnostic.message) for diagnostic in result.diagnostics] == [
        (
            _COMPATIBILITY_CODE,
            "selected processor and backend manifests are not mutually compatible",
        )
    ]


def test_captured_aptl_manifest_remains_subject_to_capability_admission() -> None:
    request = _request()
    backend = BackendManifestV2Model.model_validate(_CAPTURE["backend_manifest"])
    envelope = BackendRealizationEnvelopeModel.model_validate(_CAPTURE["realization_envelope"])
    processor = reference_processor_manifest_v2_model(
        version="test",
        compatible_backends={backend.identity.name},
    )

    result = compile_admitted_trial_plan(_with_manifests(request, backend, processor, envelope))

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["capture.offer-missing"]


def test_external_backend_digest_substitution_still_fails_closed() -> None:
    request = _external_request()
    backend_ref = next(
        reference for reference in request.apparatus.manifest_refs if reference.subject_ref.ref_kind == "backend"
    )
    stale_ref = backend_ref.model_copy(update={"ref_digest": "sha256:" + "0" * 64})
    references = [stale_ref if reference is backend_ref else reference for reference in request.apparatus.manifest_refs]

    result = compile_admitted_trial_plan(
        replace(request, apparatus=request.apparatus.model_copy(update={"manifest_refs": references}))
    )

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "trial-compiler.apparatus-manifest-digest-mismatch"
    ]
