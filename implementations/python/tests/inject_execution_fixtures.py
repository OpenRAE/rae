"""Executing filesystem fixture; not evidence of concrete OCI backend conformance."""

import hashlib
from dataclasses import replace

from raes import parse_sdl
from raes_backend_protocols.inject_execution import InjectExecutionEvidence, ResolvedInjectOutcome
from raes_contracts.associated_artifacts import associated_artifact_set_digest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AssociatedArtifactManifestModel,
    BackendOperationCapabilitiesModel,
    InjectOccurrenceModel,
    InjectOccurrenceOutcomeModel,
    InjectTriggerRequestModel,
    inject_occurrence_reference,
)
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.versions import INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from test_issue_1362_provider_execution import Provider, target
from test_issue_1423_inject_occurrence_contracts import ENVIRONMENT_SDL


def reference(artifact_id, contract_id="associated-artifact-manifest-v1", content=None):
    return {
        "contract_id": contract_id,
        "artifact_id": artifact_id,
        "digest": canonical_json_digest(artifact_id if content is None else content),
    }


class ExecutingFixture(Provider):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.content = b"authored world content\n"
        self.revoked = False
        self.claim = None
        self.bad_readback = False

    def operation_capabilities(self):
        return BackendOperationCapabilitiesModel(
            backend_id="stub",
            revision=canonical_json_digest("fixture-v1"),
            supported_operation_kinds=("orchestration",),
            guarantees=("cessation-evidence", "effect-observation"),
        )

    def admit(self, request, context, operation_id, revision, snapshot):
        from raes_runtime.inject_execution import InjectAdmission

        claim = InjectOccurrenceModel(
            operation_id=operation_id,
            request=request,
            admission=context,
            store_revision=str(revision),
            order={"scope": request.run_scope, "predecessor": request.expected_head, "position": 1},
            scenario=reference(self.scenario.name, "instantiated-scenario-v1"),
            source=reference("fixture-source"),
            realization=reference("fixture-realization", "backend-manifest-v2"),
            admission_evidence=(reference("fixture-admission"),),
            evidence_requirements=(reference("fixture-requirement"),),
        )
        self.claim = claim
        return InjectAdmission(plan=self.plan.orchestration, occurrence=claim)

    def revalidate(self, occurrence, snapshot):
        if self.revoked:
            raise ValueError("fixture admission revoked")

    def start_operation(self, request):
        assert request.command == inject_occurrence_reference(self.claim)
        self.request = request
        self.starts += 1
        self.path.write_bytes(self.content)
        return self.report(request, {"kind": "acknowledgement", "disposition": "accepted"})

    def observe_operation(self, control):
        data = self.path.read_bytes()
        manifest = AssociatedArtifactManifestModel(
            schema_version="associated-artifact-manifest/v1",
            manifest_id="fixture-readback",
            manifest_version="1",
            canonicalization_profile="associated-artifact-set/v1",
            scope="scenario",
            parent_ref={"ref_kind": "scenario", "ref_id": self.scenario.name},
            set_digest="sha256:" + "0" * 64,
            artifacts={
                "world-result": {
                    "artifact_id": "world-result",
                    "role": "result",
                    "media_type": "application/octet-stream",
                    "uri": "urn:raes:fixture:world-result",
                    "checksum": {"algorithm": "sha256", "value": hashlib.sha256(data).hexdigest()},
                    "size_bytes": len(data),
                    "created_at": "2026-10-15T00:00:00Z",
                    "source": "executing-filesystem-fixture",
                    "sensitivity": "public",
                }
            },
        )
        manifest = manifest.model_copy(update={"set_digest": associated_artifact_set_digest(manifest)})
        self.evidence = InjectExecutionEvidence(
            manifest=manifest, contents=({"artifact_id": "world-result", "content": data},)
        )
        readback = reference("fixture-readback", content=manifest.model_dump(mode="json"))
        self.readback = readback
        return self.report(
            self.request,
            {
                "kind": "outcome",
                "proposed_state": "succeeded",
                "effects": {"effect": "complete", "cessation_established": True, "evidence_refs": [readback]},
                "satisfaction": "satisfied",
                "release_gates_satisfied": True,
                "cancellation_established": False,
                "result": readback,
            },
        )

    def validate_effects(self, request, response):
        return (
            not self.bad_readback
            and self.path.read_bytes() == self.content
            and response.message.result == type(response.message.result).model_validate(self.readback)
        )

    def resolve_result(self, *args):
        raise AssertionError("an artifact effect must not be disguised as a native snapshot")

    def resolve_outcome(self, occurrence, request, response):
        outcome = InjectOccurrenceOutcomeModel(
            occurrence=inject_occurrence_reference(occurrence),
            response=response,
            effect="effect-applied",
            bindings=tuple(
                {"binding": item, "effects": response.message.effects, "readback": response.message.result}
                for item in occurrence.request.bindings
            ),
        )
        return ResolvedInjectOutcome(outcome, self.evidence)


def fixture_target(provider):
    original = target(provider)
    return replace(
        original,
        manifest=replace(
            original.manifest,
            supported_contract_versions=tuple(
                dict.fromkeys([*original.manifest.supported_contract_versions, *INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS])
            ),
        ),
    )


def fixture_plan(target):
    source = ENVIRONMENT_SDL.replace(
        "description: Release the staged maintenance notice.", "source: {name: fixture-source, version: '1'}"
    )
    scenario = parse_sdl(source)
    return plan(compile_runtime_model(scenario), target.manifest), scenario


def trigger_request(execution_plan):
    return InjectTriggerRequestModel(
        request_key="trigger-key-1",
        occurrence_id="world-occurrence-1",
        target_scope="target:stub",
        run_scope="run:default",
        plan={
            "contract_id": "orchestration-plan-v1",
            "artifact_id": "fixture-plan",
            "digest": runtime_plan_digest(execution_plan.orchestration),
        },
        inject="orchestration.inject.release",
        bindings=(
            {
                "binding": "orchestration.inject-binding.host.release",
                "node": "provision.node.host",
                "instance": "host-instance",
                "revision": "host-revision",
            },
        ),
        placement={"kind": "independent"},
        expected_head="inject-order:genesis",
    )
