"""Synthetic installed owners used by source and distribution acceptance tests."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from raes_contracts.contracts import ExperimentEvidenceRecordModel, TrialCleanupReceiptModel
from raes_contracts.runtime_state import ApplyResult
from raes_runtime.runtime_trial_services import (
    TrialCaptureObservation,
    TrialCleanupObservation,
    TrialConfigurationObservation,
    TrialExecutionObservation,
    TrialRetryObservation,
)


class TrialServices:
    def __init__(self, target, *, evidence_template=None):
        self.evidence_template = evidence_template
        if self.evidence_template is None:
            path = (
                Path(__file__).resolve().parents[3]
                / "contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/reference.json"
            )
            self.evidence_template = json.loads(path.read_text())
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
        payload = deepcopy(self.evidence_template)
        payload["run_ref"]["ref_id"] = request.run_id
        payload["evidence_record_id"] = request.execution_attempt_id + ":" + phase
        evidence = ExperimentEvidenceRecordModel.model_validate(payload)
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
