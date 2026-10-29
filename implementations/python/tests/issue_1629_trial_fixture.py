"""Installed test owners with actual configuration readback and cleanup probes."""

from copy import deepcopy
from dataclasses import replace

from raes.canonical import canonical_sdl_digest
from raes_backend_stubs.manifest import load_stub_realization_envelope
from raes_backend_stubs.stubs import create_stub_components
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import TrialCleanupReceiptModel
from raes_contracts.runtime_state import ApplyResult
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import realize_admitted_trial_entry
from raes_runtime.registry import RuntimeTarget
from raes_runtime.runtime_trial_services import (
    TrialCaptureObservation,
    TrialCleanupObservation,
    TrialConfigurationObservation,
    TrialExecutionObservation,
    TrialRetryObservation,
)
from test_issue_1625_structural_variation import _family
from test_issue_1627_trial_unit import _evidence
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


class TrialServices:
    def __init__(self, target):
        self.settings, self.owned_evidence, self.events, self.observed = {}, {}, [], []
        self.live = {}
        self.cleanup_fails = False
        self.capture_fails = False
        self.execution_fails = False
        self.stopped = False
        self.pending = False
        self.forge_configuration = False
        self.idempotent_effects = False
        original = target.provisioner.apply

        def apply(plan, snapshot):
            result = original(plan, snapshot)
            if result.success:
                self.live = deepcopy(result.snapshot.entries)
                from raes_contracts.realization_observation import (
                    ObservedOperatingSystemIdentity,
                    RealizationObservationDisclosure,
                )
                from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope

                observations = tuple(
                    RealizationObservationDisclosure(
                        address=operation.address,
                        field_path="nodes." + self.live[operation.address].payload["node_name"] + ".operating-system",
                        domain="runtime-realization",
                        requirement_kind="operating-system",
                        verification_scope=RealizationVerificationScope.PRESENCE,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                        operating_system=ObservedOperatingSystemIdentity(
                            family=self.live[operation.address].payload["os_family"],
                            distribution=self.live[operation.address].payload["os_distribution"],
                            version=self.live[operation.address].payload["os_version"],
                        ),
                        operation_id=plan.operation_id,
                        envelope_digest=target.manifest.realization_envelope.digest,
                        configuration_digest=target.manifest.realization_envelope.configuration.configuration_digest,
                        observer_version="fixture-guest/v1",
                        sequence=index,
                        binding_verified=True,
                    )
                    for index, operation in enumerate(plan.operations)
                    if operation.resource_type == "node" and operation.address in self.live
                )
                result = replace(
                    result,
                    snapshot=result.snapshot.with_entries(
                        result.snapshot.entries,
                        realization_observations=(*result.snapshot.realization_observations, *observations),
                    ),
                )
            return result

        target.provisioner.apply = apply

    def admit(self, request):
        assert request.cleanup_plan.retry_policy.after_effect_policy in {
            "disallow",
            "reset",
            "idempotent",
            "compensate",
        }

    def evidence(self, request, phase, summary):
        evidence = _evidence(request, request.execution_attempt_id + ":" + phase)
        evidence = evidence.model_copy(
            update={
                "raw_content": evidence.raw_content.model_copy(
                    update={
                        "content_uri": None,
                        "content_checksum": None,
                        "payload_summary": summary,
                    }
                )
            }
        )
        self.owned_evidence[evidence.evidence_record_id] = evidence
        return evidence

    def configure(self, request, snapshot):
        self.events.append((request.run_id, "configure"))
        self.settings = {item.participant_address: deepcopy(item) for item in request.participant_configurations}
        actual = () if self.forge_configuration else tuple(self.settings.values())
        observed = TrialConfigurationObservation(
            configurations=actual,
            evidence=(
                self.evidence(request, "configuration", "Complete settings read back from the installed participant."),
            ),
        )
        return ApplyResult(True, snapshot), observed

    def observe(self, request, snapshot):
        if self.pending and not self.stopped:
            return TrialExecutionObservation(state="running", ceased=False, evidence=())
        values = tuple(
            (
                item.participant_address,
                tuple((value.target_id, value.value.value) for value in item.configuration.values),
            )
            for item in self.settings.values()
        )
        present = any("relay-47" in address for address in self.live)
        self.observed.append((request.run_id, present, values))
        return TrialExecutionObservation(
            state="failed" if self.execution_fails else "succeeded",
            ceased=True,
            evidence=(self.evidence(request, "execution", repr((present, values))),),
        )

    def capture(self, request, snapshot):
        self.events.append((request.run_id, "capture"))
        assert snapshot.entries == self.live
        return ApplyResult(True, snapshot), TrialCaptureObservation(
            complete=not self.capture_fails,
            evidence=(self.evidence(request, "capture", "Captured installed participant output before cleanup."),),
        )

    def cleanup(self, request, outcome, snapshot):
        self.events.append((request.run_id, "cleanup"))
        assert not self.live
        evidence = self.evidence(request, "cleanup", "Owned resources and participant state are absent.")
        self.settings.clear()
        receipt = TrialCleanupReceiptModel(
            receipt_id="cleanup:" + request.execution_attempt_id,
            cleanup_plan_ref=request.cleanup_plan.plan_id,
            plan_entry_id=request.plan_entry_id,
            run_id=request.run_id,
            execution_attempt_id=request.execution_attempt_id,
            trial_outcome=outcome,
            cleanup_status="failed" if self.cleanup_fails else "succeeded",
            obligation_results={
                key: {
                    "obligation_id": key,
                    "status": "failed" if self.cleanup_fails else "succeeded",
                    "evidence_refs": [evidence.evidence_record_id],
                }
                for key, obligation in request.cleanup_plan.cleanup_obligations.items()
                if {
                    "succeeded": "success",
                    "failed": "failure",
                    "cancelled": "cancellation",
                    "timed-out": "timeout",
                    "aborted": "abort",
                }[outcome]
                in obligation.triggers
            },
            clean_state_claim=None
            if self.cleanup_fails
            else {
                "disposition": "verified-clean",
                "boundary_refs": list(request.cleanup_plan.resource_boundaries),
                "evidence_refs": [evidence.evidence_record_id],
            },
        )
        return ApplyResult(True, snapshot), TrialCleanupObservation(
            receipt=receipt, evidence=(evidence,), idempotent_effects=self.idempotent_effects
        )

    def prepare_retry(self, request, snapshot):
        self.events.append((request.run_id, "retry-reset"))
        assert not self.live and not self.settings
        evidence = self.evidence(request, "retry", "Authored reset completed and initial state was verified.")
        return ApplyResult(True, snapshot), TrialRetryObservation(
            ready=True,
            verified_compensations=tuple(request.cleanup_plan.retry_policy.compensation_refs),
            evidence=(evidence,),
            obligation_results={
                key: {"obligation_id": key, "status": "succeeded", "evidence_refs": [evidence.evidence_record_id]}
                for key, value in request.cleanup_plan.cleanup_obligations.items()
                if "retry" in value.triggers
            },
        )

    def stop(self, request, cause, snapshot):
        self.stopped = True
        return ApplyResult(True, snapshot)

    def verify(self, request, observation):
        for evidence in observation.evidence:
            if self.owned_evidence.get(evidence.evidence_record_id) != evidence:
                raise ValueError("evidence is absent or changed at its owner")
        if observation.kind == "configuration" and observation.configurations != tuple(self.settings.values()):
            raise ValueError("configuration readback differs from installed state")
        if observation.kind == "cleanup" and (self.live or self.settings):
            raise ValueError("cleanup probes found residual resources")
