"""Content-backed installed owners for the record producer acceptance tests."""

import io
from dataclasses import replace
from datetime import UTC, datetime

from issue_1629_archive_fixture import TrialArchive
from issue_1629_trial_fixture import TrialServices
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentCaptureSpecModel, ExperimentRunEvidenceInputs, ExperimentTaskModel
from raes_runtime import ExperimentRunMetadata
from raes_runtime.runtime_trial_services import TrialCaptureObservation
from test_issue_1112_capture_admission import _evidence_bundle


def record_request(request):
    task = request.task.model_dump(mode="json")
    task["scenario_ref"] = {"ref_kind": "scenario", "ref_id": request.family.name}
    task["apparatus_constraints"] = {"notes": ["Use the admitted installed test apparatus."]}
    spec = next(iter(request.capture_specs.values())).model_dump(mode="json")
    spec["capture_windows"][0].update(starts_at="2020-01-01T00:00:00Z", ends_at="2100-01-01T00:00:00Z")
    task = ExperimentTaskModel.model_validate(task)
    spec = ExperimentCaptureSpecModel.model_validate(spec)
    refs = request.input_refs.model_copy(
        update={
            "task_digest": canonical_json_digest(task.model_dump(mode="json")),
            "capture_spec_refs": [
                ref.model_copy(update={"ref_digest": canonical_json_digest(spec.model_dump(mode="json"))})
                for ref in request.input_refs.capture_spec_refs
            ],
        }
    )
    return replace(request, task=task, input_refs=refs, capture_specs={spec.capture_spec_id: spec})


class ContentServices(TrialServices):
    def capture(self, request, snapshot):
        result, _ = super().capture(request, snapshot)
        _, _, _, record, self.content = _evidence_bundle()
        record = record.model_copy(
            update={
                "evidence_record_id": request.execution_attempt_id + ":content",
                "captured_at": datetime.now(UTC).isoformat(),
                "run_ref": record.run_ref.model_copy(update={"ref_id": request.run_id, "ref_version": "1"}),
            }
        )
        self.record = record
        self.owned_evidence[record.evidence_record_id] = record
        return result, TrialCaptureObservation(complete=True, evidence=(record,))


def metadata_for(runtime, experiment_id, source):
    experiment = runtime._experiments[experiment_id]
    entry = source.plan.entries[source.attempts[0].plan_entry_id]
    slot = next(
        slot
        for slot in experiment._slots(runtime._store.load_runtime_decisions())
        if slot.entry.run_id == source.run_id
    )
    unit = experiment._unit(slot, source.attempts[-1], None)
    legacy = TrialArchive().build_run(unit.request, source.realization, (unit.result(),))
    context = legacy.apparatus_context.model_dump(mode="json")
    context["components"] = {}
    context["selected_manifests"] = [item.model_dump(mode="json") for item in entry.apparatus.manifest_refs]
    for reference in entry.apparatus.manifest_refs:
        subject = reference.subject_ref
        context["components"][subject.ref_kind] = {
            "component_kind": subject.ref_kind,
            "identity": {"name": subject.ref_id, "version": subject.ref_version},
            "manifest_ref": reference.model_dump(mode="json"),
            "observed": True,
        }
    _, template, _, _, _ = _evidence_bundle()
    artifact = template.evidence_artifacts[0]
    record = experiment.services.owned_evidence[source.attempts[-1].execution_attempt_id + ":content"]
    return ExperimentRunMetadata(
        outcome_status=template.outcome_status,
        apparatus_context=context,
        participant_implementation_provenance=legacy.participant_implementation_provenance,
        parameter_set=legacy.parameter_set,
        evidence_artifacts=(artifact,),
        result_summaries=template.result_summaries,
        traceability={
            "capture_spec_refs": [
                {"ref_kind": "capture-spec", "ref_id": item.ref_id, "ref_version": item.ref_version}
                for item in source.plan.input_refs.capture_spec_refs
            ],
            "evidence_record_refs": [
                {
                    "ref_kind": "evidence-record",
                    "ref_id": record.evidence_record_id,
                    "ref_version": record.record_version,
                }
            ],
        },
    )


def readers(inputs, services):
    def read(run):
        identity = run.execution_accounting.attempts[-1].execution_attempt_id + ":content"
        record = services.owned_evidence[identity]
        return ExperimentRunEvidenceInputs(
            inputs.capture_specs,
            {record.evidence_record_id: record},
            {"auth-log-evidence": io.BytesIO(services.content)},
        )

    return read


class RuntimeArchive(TrialArchive):
    """Build actual portable records from live test owners and observations."""

    def __init__(self, runtime):
        super().__init__()
        self.runtime = runtime
        self.experiment_id = self.failed_run_id = None
        self.sources, self.studies = [], {}

    def build_run(self, request, realization, results):
        from raes_runtime.runtime_experiment_records import _source
        from raes_runtime.runtime_record_assembly import assemble_run
        from raes_runtime.runtime_trial_decisions import TrialAttemptDecision

        experiment = self.runtime._experiments[self.experiment_id]
        records = self.runtime._store.load_runtime_decisions()
        slot = next(item for item in experiment._slots(records) if item.entry.run_id == request.run_id)
        attempts = tuple(
            sorted(
                (
                    item
                    for item in records
                    if isinstance(item, TrialAttemptDecision) and item.plan_entry_id == slot.entry.plan_entry_id
                ),
                key=lambda item: item.attempt,
            )
        )
        source = _source(experiment, slot, attempts)
        facts = metadata_for(self.runtime, self.experiment_id, source)
        # This test evaluation owner explicitly evaluates the selected trial negatively.
        outcome = "failed" if request.run_id == self.failed_run_id else "succeeded"
        return assemble_run(source, facts.model_copy(update={"outcome_status": outcome}))

    def write_sources(self, source):
        self.sources.append(source)

    def write_study(self, study):
        prior = self.studies.setdefault((study.study_id, study.study_version), study.model_copy(deep=True))
        assert prior == study

    def read_study(self, study_id, version):
        return self.studies[(study_id, version)].model_copy(deep=True)
