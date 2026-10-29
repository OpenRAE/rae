"""Immutable archive owner used by the public runtime replacement tests."""

import json

from paths import REPO_ROOT
from raes_contracts.contracts import ExperimentRunModel


class TrialArchive:
    def __init__(self):
        self.runs = {}
        self.lose_ack = False

    def build_run(self, request, realization, results):
        entry = request.plan.entries[request.plan_entry_id]
        payload = json.loads(
            (REPO_ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json").read_text()
        )
        outcome = results[-1].cleanup_receipt.trial_outcome
        payload.update(
            run_id=request.run_id,
            run_version="1",
            run_status="completed" if outcome == "succeeded" else "failed",
            outcome_status="succeeded" if outcome == "succeeded" else "failed",
            scenario_snapshot_ref={
                "ref_kind": "scenario-snapshot",
                "ref_id": "fixture-family",
                "ref_version": "raes-sdl-instantiated-snapshot/v2",
                "ref_digest": realization.snapshot_digest,
            },
            trial_provenance={
                "plan_id": request.plan.plan_id,
                "plan_digest": request.plan.plan_digest,
                "plan_entry_id": entry.plan_entry_id,
                "entry_digest": entry.entry_digest,
                "admitted_run_id": entry.run_id,
                "coordinate": entry.coordinate.model_dump(),
                "instantiated_scenario_digest": realization.snapshot_digest,
                "processor_plan_refs": [item.model_dump() for item in realization.processor_plan_refs],
                "execution_attempts": [
                    {
                        "execution_attempt_id": result.cleanup_receipt.execution_attempt_id,
                        "cleanup_receipt_ref": result.cleanup_receipt.receipt_id,
                        "operation_refs": [item.operation_id for item in result.operation_receipts],
                    }
                    for result in results
                ],
                "terminal_attempt_id": results[-1].cleanup_receipt.execution_attempt_id,
            },
            stochastic_controls=[item.model_dump() for item in request.plan.stochastic_controls.values()]
            or [{"control_id": "deterministic", "role": "other"}],
            stochastic_draws=[item.model_dump() for item in entry.stochastic_draws],
            realized_selections=[item.treatment.model_dump() for item in entry.selections if item.treatment],
        )
        configurations = {item.participant_address: item for item in entry.participant_configurations}
        payload["realized_bindings"] = [
            {
                "descriptor": binding.descriptor.model_dump(),
                "origin": binding.origin,
                "configuration_digest": configurations[
                    binding.descriptor.target.participant_address
                ].configuration_digest,
            }
            for binding in entry.bindings
        ]
        provenance = payload["participant_implementation_provenance"]
        provenance["run_id"] = request.run_id
        configuration = entry.participant_configurations[0]
        provenance["participant_implementations"][0].update(
            participant_address=configuration.participant_address,
            implementation_identity=configuration.configuration.implementation_identity.model_dump(),
            manifest_ref=configuration.manifest_ref,
            manifest_digest=configuration.manifest_digest,
            configuration_ref="configuration:admitted",
            configuration_digest=configuration.configuration_digest,
        )
        return ExperimentRunModel.model_validate(payload)

    def write_run(self, run):
        key = (run.run_id, run.run_version)
        prior = self.runs.setdefault(key, run.model_copy(deep=True))
        assert prior == run, "immutable archive version changed"
        if self.lose_ack:
            self.lose_ack = False
            raise OSError("archive acknowledgement lost")

    def read_run(self, run_id, run_version):
        return self.runs[(run_id, run_version)].model_copy(deep=True)
