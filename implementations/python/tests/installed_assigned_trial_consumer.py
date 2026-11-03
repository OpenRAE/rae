"""CI acceptance against an installed wheel or sdist-derived wheel, under -I."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import raes_runtime
from raes import admit_scenario_family, parse_sdl
from raes.participant_control_context import SDLControlContextConfigurationValidator
from raes_backend_stubs.stubs import create_stub_components
from raes_contracts.assigned_trial import TrialAssignmentControlModel, TrialAssignmentModel, TrialOutcomeModel
from raes_contracts.contracts import (
    AdmittedApparatusBindingModel,
    AdmittedTrialPlanInputRefsModel,
    AdmittedTrialPlanModel,
    BackendManifestV2Model,
    ExperimentCaptureSpecModel,
    ExperimentSpecModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    ParticipantImplementationManifestModel,
    ProcessorManifestV2Model,
    TrialExecutionAuthorityModel,
)
from raes_contracts.errors import ConflictError, EvidenceIntegrityError
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_processor.trial_compiler import TrialCompilationRequest
from raes_processor.trial_realization import TrialRealizationInputs, realize_admitted_trial_entry
from raes_processor.trial_scheduler import AllocatorGrant
from raes_runtime import RuntimeControlPlane, RuntimeTarget
from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding


def load_inputs(path: Path) -> tuple[TrialRealizationInputs, dict]:
    source = json.loads(path.read_text())
    manifests = {}
    for item in source["apparatus_manifests"]:
        model = ProcessorManifestV2Model if item["key"][0] == "processor" else BackendManifestV2Model
        manifests[tuple(item["key"])] = model.model_validate(item["value"])
    inputs = TrialRealizationInputs(
        plan=AdmittedTrialPlanModel.model_validate(source["plan"]),
        family=admit_scenario_family(parse_sdl(json.dumps(source["family"]))),
        experiment=ExperimentSpecModel.model_validate(source["experiment"]),
        task=ExperimentTaskModel.model_validate(source["task"]),
        capture_specs={
            key: ExperimentCaptureSpecModel.model_validate(value) for key, value in source["capture_specs"].items()
        },
        apparatus_manifests=manifests,
        realization_envelope=BackendRealizationEnvelopeModel.model_validate(source["realization_envelope"]),
        backend_key=tuple(source["backend_key"]),
    )
    return inputs, source["evidence_template"]


def target_and_services(inputs: TrialRealizationInputs, evidence: dict):
    realized = realize_admitted_trial_entry(
        inputs=inputs, plan_entry_id=next(iter(inputs.plan.entries)), target_name="trial"
    )
    manifest = realized.execution_plan.manifest
    target = RuntimeTarget(name="trial", manifest=manifest, **vars(create_stub_components(manifest=manifest)))
    support = runpy.run_path(str(Path(__file__).with_name("assigned_trial_consumer_support.py")))
    return target, support["TrialServices"](target, evidence_template=evidence)


def worker(fixture: Path, owner: str, assignment_path: Path) -> None:
    inputs, evidence = load_inputs(fixture)
    assignment = TrialAssignmentModel.from_json(assignment_path.read_bytes())
    target, services = target_and_services(inputs, evidence)
    services.pending = True
    with RuntimeControlPlane(target) as runtime:
        binding = runtime.bind_assigned_trial(assignment, inputs, services=services, identity=owner)
        while line := sys.stdin.readline():
            command = json.loads(line)
            if command["action"] == "wrong-entry":
                other = next(key for key in inputs.plan.entries if key != assignment.plan_entry_id)
                try:
                    binding.execute_trial(replace(binding.request, plan_entry_id=other), identity=owner)
                except ValueError, ConflictError:
                    print(json.dumps({"refused": True, "observed": len(services.observed)}), flush=True)
                    continue
                raise AssertionError("wrong-entry request was dispatched")
            if command["action"] == "duplicate":
                assert runtime.bind_assigned_trial(assignment, inputs, services=services, identity=owner) is binding
                if binding.outcome(identity=owner).progress == "completed":
                    binding.execute_trial(binding.request)
            if command["action"] == "finish":
                services.pending = False
                services.execution_fails = command.get("fail", False)
            control = None
            if "control" in command:
                control = TrialAssignmentControlModel.from_json(json.dumps(command["control"]))
            for _ in range(20):
                progress = binding.advance(identity=owner, control=control)
                if progress.state in {"completed", "pending", "indeterminate"}:
                    break
            print(
                json.dumps(
                    {
                        "outcome": binding.outcome(identity=owner).model_dump(mode="json"),
                        "observed": len(services.observed),
                        "events": services.events,
                    }
                ),
                flush=True,
            )


class OriginalProcessReader:
    """Trusted test owner reads original checked facts from its own child pipes.

    The harness launches the fixed installed runtime worker and owns each pipe.
    Production integrations must use their authenticated native evidence owners.
    A freely supplied result file or an asserted digest cannot replace that owner.
    """

    def __init__(self):
        self.originals = {}

    def verify_outcome(self, request, outcome):
        if self.originals.get(outcome.assignment_digest) != outcome:
            raise EvidenceIntegrityError("original installed execution facts differ")


def exchange(process, action: str, **fields):
    process.stdin.write(json.dumps({"action": action, **fields}) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise AssertionError(f"installed execution owner exited: {process.poll()}")
    return json.loads(line)


def accepted(runtime, experiment, reader, reply):
    outcome = TrialOutcomeModel.from_json(json.dumps(reply["outcome"]))
    reader.originals[outcome.assignment_digest] = outcome
    runtime.ingest_trial_outcome(experiment, outcome)
    return outcome


def start_worker(fixture, owner, assignment, directory):
    path = Path(directory) / (owner + ".json")
    path.write_text(assignment.model_dump_json())
    environment = {key: value for key in ("SYSTEMROOT", "WINDIR", "TMP", "TEMP") if (value := os.environ.get(key))}
    return subprocess.Popen(
        [sys.executable, "-I", str(Path(__file__).resolve()), "--worker", str(fixture), owner, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=environment,
    )


def replacement_request(inputs, source):
    """Reconstruct original compiler inputs; install the known local validator."""
    original = source["compilation_request"]
    return TrialCompilationRequest(
        family=inputs.family,
        experiment=inputs.experiment,
        task=inputs.task,
        input_refs=AdmittedTrialPlanInputRefsModel.model_validate(original["input_refs"]),
        apparatus=AdmittedApparatusBindingModel.model_validate(original["apparatus"]),
        execution_authority=TrialExecutionAuthorityModel.model_validate(original["execution_authority"]),
        realization_envelope=inputs.realization_envelope,
        apparatus_manifests=inputs.apparatus_manifests,
        capture_specs=inputs.capture_specs,
        participant_manifests={
            tuple(item["key"]): ParticipantImplementationManifestModel.model_validate(item["value"])
            for item in original["participant_manifests"]
        },
        participant_configuration_validators={
            tuple(key): SDLControlContextConfigurationValidator(inputs.family)
            for key in original["participant_validator_keys"]
        },
    )


def replacement_consumer(fixture):
    inputs, evidence = load_inputs(fixture)
    source = json.loads(fixture.read_text())
    request = replacement_request(inputs, source)
    support = runpy.run_path(str(Path(__file__).with_name("issue_1629_archive_fixture.py")))
    archive = support["TrialArchive"](run_template=source["run_template"])
    target, services = target_and_services(inputs, evidence)
    reader, processes = OriginalProcessReader(), []
    first = next(iter(inputs.plan.entries))
    assert len(inputs.plan.entries) == 1  # Authored before admission, never a worker slice.
    with (
        tempfile.TemporaryDirectory(prefix="assigned-trial-replacement-") as directory,
        RuntimeControlPlane(target) as runtime,
    ):
        experiment = runtime.admit_experiment(
            inputs,
            services=services,
            outcome_verifier=reader,
            replacement=ExperimentReplacementBinding(request, archive),
        )
        try:
            original = runtime.assign_trial(experiment, first, owner_id="original-owner")
            process = start_worker(fixture, "original-owner", original, directory)
            processes.append(process)
            accepted(runtime, experiment, reader, exchange(process, "finish", fail=True))
            progress = runtime.advance_trial(experiment, first)
            assert progress.state == "ready" and progress.plan_entry_id != first
            parent = archive.runs[(original.plan.entries[first].run_id, "1")].model_copy(deep=True)
            child = runtime.assign_trial(experiment, progress.plan_entry_id, owner_id="replacement-owner")
            assert child.experiment_id == experiment
            assert child.plan.replacement_origin.root_entry_id == first
            assert child.plan.replacement_origin.root_plan_digest == inputs.plan.plan_digest
            process = start_worker(fixture, "replacement-owner", child, directory)
            processes.append(process)
            completed = accepted(runtime, experiment, reader, exchange(process, "finish"))
            assert completed.progress == "completed"
            runtime.ingest_trial_outcome(experiment, completed)
            assert exchange(process, "duplicate")["observed"] == 1
            records = runtime.experiment_records(experiment)
            assert records.accounting.started_runs == 2
            assert records.accounting.unresolved_runs == 0
            assert {run.run_status for run in records.runs} == {"completed", "failed"}
            assert parent.run_id != child.plan.entries[child.plan_entry_id].run_id
            assert parent.run_status == "failed"
            assert parent.trial_provenance.plan_id == inputs.plan.plan_id
            assert archive.runs[(parent.run_id, "1")] == parent
            assert all(item.experiment_id == experiment for item in (original, child))
            assert not services.events
        finally:
            for process in processes:
                process.stdin.close()
                process.stdout.close()
                assert process.wait(timeout=30) == 0


def main(fixture: Path) -> None:
    assert Path(raes_runtime.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), raes_runtime.__file__
    inputs, evidence = load_inputs(fixture)
    target, services = target_and_services(inputs, evidence)
    reader = OriginalProcessReader()
    grant = AllocatorGrant(effective_parallelism=2, lease_evidence_refs=("lease:installed-synthetic-hosts",))
    entries = list(inputs.plan.entries)
    processes = []

    with (
        tempfile.TemporaryDirectory(prefix="assigned-trial-consumer-") as temporary,
        RuntimeControlPlane(target) as coordinator,
    ):
        experiment = coordinator.admit_experiment(inputs, services=services, outcome_verifier=reader)
        try:
            bindings = []
            for index, owner in enumerate(("worker-a", "worker-b")):
                assignment = coordinator.assign_trial(experiment, entries[index], owner_id=owner, grant=grant)
                process = start_worker(fixture, owner, assignment, temporary)
                processes.append(process)
                bindings.append(assignment)
            a, b = processes
            pending = exchange(a, "advance")
            accepted(coordinator, experiment, reader, pending)
            duplicate = exchange(a, "duplicate")
            assert duplicate["events"] == pending["events"]
            assert exchange(b, "wrong-entry")["refused"]
            complete_b = accepted(coordinator, experiment, reader, exchange(b, "finish"))
            coordinator.ingest_trial_outcome(experiment, complete_b)
            assert coordinator.experiment_records(experiment).accounting.unresolved_runs == 1
            assert exchange(b, "duplicate")["observed"] == 1
            # A lost delivery does not authorize a new assignment or refresh its deadline.
            assert coordinator.assign_trial(experiment, entries[0], owner_id="worker-a", grant=grant) == bindings[0]
            coordinator.cancel_experiment(experiment)
            control = coordinator.assigned_trial_control(experiment, bindings[0].content_digest)
            cancelled_a = exchange(a, "advance", control=control.model_dump(mode="json"))
            accepted(coordinator, experiment, reader, cancelled_a)
            records = coordinator.experiment_records(
                experiment,
                study=ExperimentStudyModel(
                    schema_version="experiment-study/v1",
                    study_id="installed-assigned-study",
                    study_version="1",
                    study_kind="collection",
                    title="Installed assigned trials",
                    owner="operator",
                    description="All started trials.",
                    purpose="Retain original execution facts.",
                    inclusion_criteria=["All started trials."],
                    membership={
                        "task": {
                            "role": "primary-task",
                            "target_ref": {
                                "ref_kind": "task",
                                "ref_id": inputs.task.task_id,
                                "ref_version": inputs.task.task_version,
                            },
                        }
                    },
                ),
            )
            assert records.accounting.started_runs == 2
            assert records.accounting.unresolved_runs == 0
            assert {run.run_status for run in records.runs} == {"completed", "aborted"}
            assert records.study is not None
            assert all(run.execution_accounting.attempts[0].evidence_records for run in records.runs)
            assert not services.events
        finally:
            for process in processes:
                process.stdin.close()
                process.stdout.close()
                assert process.wait(timeout=30) == 0
    replacement_consumer(fixture.with_name("assigned-trial-replacement-inputs.json"))
    print("Installed assigned-trial execution and replacement passed.")


if __name__ == "__main__":
    if sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
    else:
        main(Path(sys.argv[1]).resolve())
