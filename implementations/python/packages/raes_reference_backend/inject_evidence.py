"""Bounded associated-artifact evidence from independent native inject readback."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from raes_backend_protocols.inject_execution import InjectExecutionEvidence
from raes_contracts.associated_artifacts import (
    AssociatedArtifactValidationLimits,
    associated_artifact_set_digest,
    validate_associated_artifact_manifest,
)
from raes_contracts.canonical import canonical_json_bytes, canonical_json_digest
from raes_contracts.contracts import (
    AssociatedArtifactManifestModel,
    BackendOperationEffectsModel,
    InjectBindingOutcomeModel,
    OperationArtifactReferenceModel,
    backend_operation_request_digest,
)


def artifact_manifest(scenario, manifest_id, contents, created_at):
    artifacts = {
        key: {
            "artifact_id": key,
            "role": "result" if key.endswith("-result") else "observation",
            "media_type": "application/octet-stream",
            "uri": "urn:raes:inject:" + canonical_json_digest([manifest_id, key]),
            "checksum": {"algorithm": "sha256", "value": hashlib.sha256(value).hexdigest()},
            "size_bytes": len(value),
            "created_at": created_at,
            "source": "reference-oci-inject-v1",
            "sensitivity": "public",
        }
        for key, value in contents.items()
    }
    manifest = AssociatedArtifactManifestModel(
        schema_version="associated-artifact-manifest/v1",
        manifest_id=manifest_id,
        manifest_version="1",
        canonicalization_profile="associated-artifact-set/v1",
        scope="scenario",
        parent_ref={"ref_kind": "scenario", "ref_id": scenario.name},
        artifacts=artifacts,
        set_digest="sha256:" + "0" * 64,
    )
    manifest = manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})
    diagnostics = validate_associated_artifact_manifest(
        manifest,
        parent=scenario,
        artifact_readers={key: BytesIO(value) for key, value in contents.items()},
        limits=AssociatedArtifactValidationLimits(
            max_artifacts=32, max_artifact_bytes=65536, max_total_bytes=2 * 1024 * 1024
        ),
    )
    if diagnostics:
        raise ValueError("OCI inject artifact evidence could not be validated")
    return manifest


def manifest_reference(manifest):
    return OperationArtifactReferenceModel(
        contract_id="associated-artifact-manifest-v1",
        artifact_id=manifest.manifest_id,
        digest=canonical_json_digest(manifest.model_dump(mode="json")),
    )


def evidence_requirement(program):
    content = canonical_json_bytes(
        {
            "profile": "reference-oci-inject-readback/v1",
            "source": program.source_reference.model_dump(mode="json"),
            "probes": [
                {
                    "binding": probe.binding.model_dump(mode="json"),
                    "target_path": probe.path,
                    "before": "sha256:" + hashlib.sha256(probe.before).hexdigest(),
                    "after": "sha256:" + hashlib.sha256(probe.after).hexdigest(),
                }
                for probe in program.probes
            ],
        }
    )
    created_at = next(iter(program.source_manifest.artifacts.values())).created_at
    manifest = artifact_manifest(
        program.scenario,
        "inject-readback-requirement-" + hashlib.sha256(content).hexdigest(),
        {"readback-requirement": content},
        created_at,
    )
    return manifest_reference(manifest)


@dataclass(frozen=True)
class OciInjectReadback:
    bindings: tuple[InjectBindingOutcomeModel, ...]
    effects: BackendOperationEffectsModel
    result: OperationArtifactReferenceModel | None
    state: str
    manifest: AssociatedArtifactManifestModel
    evidence: InjectExecutionEvidence


def read_world_effect(native, program, occurrence, request, *, deadline):
    probes = {(probe.binding.binding, probe.binding.instance): probe for probe in program.probes}
    facts, contents, times = [], {}, []
    for index, binding in enumerate(occurrence.request.bindings):
        probe = probes[(binding.binding, binding.instance)]
        try:
            fact = native.observe(request, probe, program.source, deadline=deadline)
        except ValueError:
            fact = None
        ceased = fact is not None and fact.ceased
        applied = ceased and fact.readback == probe.after
        exit_code = None if fact is None else fact.exit_code
        finished_at = request.budget.started_at if fact is None else fact.finished_at
        times.append(finished_at)
        witness = {
            "profile": "reference-oci-inject-readback/v1",
            "request": backend_operation_request_digest(request),
            "binding": binding.model_dump(mode="json"),
            "source": program.source_reference.model_dump(mode="json"),
            "ceased": ceased,
            "expected_effect_read_back": applied,
            "exit_code": exit_code,
        }
        contents[f"binding-{index}-witness"] = canonical_json_bytes(witness)
        if applied:
            contents[f"binding-{index}-result"] = probe.after
        facts.append((binding, ceased, applied, exit_code, fact is not None and not ceased))
    manifest = artifact_manifest(
        program.scenario, "inject-result-" + backend_operation_request_digest(request)[7:], contents, max(times)
    )
    reference = manifest_reference(manifest)
    bindings = tuple(
        InjectBindingOutcomeModel(
            binding=binding,
            effects=BackendOperationEffectsModel(
                effect="complete" if applied else "unknown", cessation_established=ceased, evidence_refs=(reference,)
            ),
            readback=reference if applied else None,
        )
        for binding, ceased, applied, _, _ in facts
    )
    all_applied, all_ceased = all(item[2] for item in facts), all(item[1] for item in facts)
    state = "indeterminate"
    if all_applied and all_ceased:
        state = "succeeded" if all(item[3] == 0 for item in facts) else "failed"
    elif any(item[4] for item in facts):
        state = "running"
    effects = BackendOperationEffectsModel(
        effect="complete" if all_applied else "unknown", cessation_established=all_ceased, evidence_refs=(reference,)
    )
    evidence = InjectExecutionEvidence(
        manifest=manifest, contents=tuple({"artifact_id": key, "content": value} for key, value in contents.items())
    )
    return OciInjectReadback(bindings, effects, reference if all_applied else None, state, manifest, evidence)
