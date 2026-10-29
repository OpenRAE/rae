"""Bind trusted observation inputs to the retained plan and runtime facts."""

from contextlib import ExitStack, contextmanager

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    BackendManifestV2Model,
    ExperimentRunEvidenceInputs,
    ProcessorManifestV2Model,
    validate_experiment_apparatus_context_against_manifests,
    validate_experiment_run_against_task,
)


def validate_observed_apparatus(experiment, metadata):
    if metadata.apparatus_context is None:
        return
    manifests = experiment.inputs.apparatus_manifests.values()
    processors = [item for item in manifests if isinstance(item, ProcessorManifestV2Model)]
    backends = [item for item in manifests if isinstance(item, BackendManifestV2Model)]
    if len(processors) != 1 or len(backends) != 1:
        raise ValueError("record apparatus requires exact admitted processor and backend manifests")
    try:
        validate_experiment_apparatus_context_against_manifests(
            metadata.apparatus_context,
            processors[0],
            backends[0],
            processor_manifest_digest=canonical_json_digest(processors[0].model_dump(mode="json")),
            backend_manifest_digest=canonical_json_digest(backends[0].model_dump(mode="json")),
        )
    except ValueError:
        raise ValueError("record apparatus does not match admitted manifests") from None


@contextmanager
def record_evidence(experiment, source, run, reader):
    capture = next(
        (
            item.observation
            for item in source.observations
            if item.execution_attempt_id == source.attempts[-1].execution_attempt_id
            and item.observation.kind == "capture"
        ),
        None,
    )
    if capture is None or not capture.complete:
        raise ValueError("trial capture is incomplete")
    if reader is None:
        yield None
        return
    evidence = reader(run.model_copy(deep=True))
    if not isinstance(evidence, ExperimentRunEvidenceInputs):
        raise ValueError("record evidence requires its typed input context")
    with ExitStack() as cleanup:
        seen = set()
        for stream in evidence.artifact_readers.values():
            if id(stream) not in seen:
                cleanup.callback(stream.close)
                seen.add(id(stream))
        if evidence.capture_specs != experiment.inputs.capture_specs:
            raise ValueError("record evidence capture specifications differ from admission")
        retained = {}
        for decision in source.observations:
            for item in decision.observation.evidence:
                key = (item.evidence_record_id, item.record_version)
                if key in retained and retained[key] != item:
                    raise ValueError("retained evidence identity has conflicting content")
                retained[key] = item
        if any(
            key != item.evidence_record_id or retained.get((key, item.record_version)) != item
            for key, item in evidence.evidence_records.items()
        ):
            raise ValueError("record evidence does not match retained runtime observations")
        yield evidence


def with_record_evidence(experiment, pairs, reader, check):
    # The worker owns acquired streams through validation, even after a caller timeout.
    def invoke():
        try:
            with ExitStack() as cleanup:
                evidence = {
                    run.run_id: cleanup.enter_context(record_evidence(experiment, source, run, reader))
                    for source, run in pairs
                }
                return check(evidence)
        except Exception:
            # Ordinary installed-provider failures must not abort record retention.
            # Process-control exceptions remain outside this boundary.
            raise ValueError("record evidence operation failed") from None

    return experiment.engine._execution_adapter.call(
        "control", invoke, timeout_ms=experiment.engine._supervision.observation_ms
    )


def validate_run_evidence(experiment, source, run, reader):
    return with_record_evidence(
        experiment,
        ((source, run),),
        reader,
        lambda evidence: validate_experiment_run_against_task(
            experiment.inputs.task, run, evidence=evidence[run.run_id]
        ),
    )
