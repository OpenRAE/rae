"""Canonical identity validation and coordinate planning for trial compilation."""

from __future__ import annotations

from raes import canonical_sdl_digest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import TrialCoordinateModel

from .models import CompilationFailure, TrialCompilationRequest
from .profiles import admitted_profiles, coordinate_projection, replicate_id

_RUN_PLAN_ADDRESS = "/run_plan"
_CAPTURE_SPEC_REFS_ADDRESS = "/input_refs/capture_spec_refs"


def _fail(code: str, address: str, message: str) -> CompilationFailure:
    return CompilationFailure(code, address, message)


def _validate_primary_input_refs(request: TrialCompilationRequest) -> None:
    refs = request.input_refs
    family_digest = canonical_sdl_digest(request.family).value
    authoring_digest = canonical_json_digest(request.experiment.model_dump(mode="json"))
    task_digest = canonical_json_digest(request.task.model_dump(mode="json"))
    if refs.scenario_family_ref.ref_id != request.family.name or refs.scenario_family_ref.ref_digest != family_digest:
        raise _fail(
            "scenario-family-ref-mismatch",
            "/input_refs/scenario_family_ref",
            "scenario family reference does not match the admitted expanded family",
        )
    if (
        refs.authoring_input_ref.ref_id != request.experiment.spec_id
        or refs.authoring_input_ref.ref_version != request.experiment.spec_version
        or refs.authoring_input_ref.ref_digest != authoring_digest
    ):
        raise _fail(
            "authoring-input-ref-mismatch",
            "/input_refs/authoring_input_ref",
            "authoring input reference does not match the admitted experiment",
        )
    if (
        refs.task_ref != request.experiment.task_ref
        or refs.task_ref.ref_id != request.task.task_id
        or refs.task_ref.ref_version != request.task.task_version
        or refs.task_digest != task_digest
    ):
        raise _fail(
            "task-ref-mismatch",
            "/input_refs/task_ref",
            "task reference or digest does not match the admitted task",
        )


def _validate_binding_input_ref(request: TrialCompilationRequest) -> None:
    refs = request.input_refs
    descriptors = request.experiment.binding_descriptors
    descriptor_ref = refs.binding_descriptor_set_ref
    if descriptors is None and descriptor_ref is not None:
        raise _fail(
            "binding-set-ref-unexpected",
            "/input_refs/binding_descriptor_set_ref",
            "an unbound experiment must not carry a binding descriptor set reference",
        )
    if descriptors is not None:
        descriptor_digest = canonical_json_digest(descriptors.model_dump(mode="json"))
        if descriptor_ref is None or descriptor_ref.ref_digest != descriptor_digest:
            raise _fail(
                "binding-set-ref-mismatch",
                "/input_refs/binding_descriptor_set_ref",
                "binding descriptor set reference does not match the admitted descriptor set",
            )


def _validate_capture_inputs(request: TrialCompilationRequest) -> None:
    experiment_refs = request.experiment.capture_spec_refs
    expected_keys = {(reference.ref_id, reference.ref_version) for reference in experiment_refs}
    payload_keys = {
        (capture_spec.capture_spec_id, capture_spec.spec_version) for capture_spec in request.capture_specs.values()
    }
    if (
        len(payload_keys) != len(request.capture_specs)
        or any(key != capture_spec.capture_spec_id for key, capture_spec in request.capture_specs.items())
        or expected_keys != payload_keys
    ):
        raise _fail(
            "capture-spec-payload-mismatch",
            _CAPTURE_SPEC_REFS_ADDRESS,
            "capture specification references do not resolve exactly to the supplied payloads",
        )

    pinned = {
        (reference.ref_id, reference.ref_version, reference.ref_digest)
        for reference in request.input_refs.capture_spec_refs
    }
    expected_pins = {
        (
            capture_spec.capture_spec_id,
            capture_spec.spec_version,
            canonical_json_digest(capture_spec.model_dump(mode="json")),
        )
        for capture_spec in request.capture_specs.values()
    }
    if pinned != expected_pins:
        raise _fail(
            "capture-spec-ref-mismatch",
            _CAPTURE_SPEC_REFS_ADDRESS,
            "capture specification digests do not match the admitted payloads",
        )

    requirement_ids = [
        requirement.requirement_id
        for capture_spec in request.capture_specs.values()
        for requirement in capture_spec.capture_requirements.values()
    ]
    if len(set(requirement_ids)) != len(requirement_ids):
        raise _fail(
            "capture-requirement-ambiguous",
            _CAPTURE_SPEC_REFS_ADDRESS,
            "capture requirement identities must be unique across admitted capture specifications",
        )
    task_requirements = {reference.ref_id for reference in request.task.evaluation_protocol.observation_requirements}
    task_requirements.update(
        reference.ref_id
        for metric in request.task.evaluation_protocol.metric_definitions.values()
        for reference in metric.evidence_requirements
    )
    missing = sorted(task_requirements.difference(requirement_ids))
    if missing:
        raise _fail(
            "task-capture-requirement-missing",
            "/task/evaluation_protocol",
            "task evidence requirements do not resolve to admitted capture requirements",
        )


def validate_input_identities(request: TrialCompilationRequest) -> None:
    """Validate every caller-supplied identity against its admitted payload."""

    _validate_primary_input_refs(request)
    _validate_binding_input_ref(request)
    _validate_capture_inputs(request)
    refs = request.input_refs
    if request.apparatus.realization_envelope != request.realization_envelope.identity:
        raise _fail(
            "realization-envelope-ref-mismatch",
            "/apparatus/realization_envelope",
            "apparatus realization-envelope identity does not match the supplied carrier",
        )
    if refs.study_ref is not None or refs.associated_artifact_set_ref is not None:
        raise _fail(
            "referenced-input-payload-required",
            "/input_refs",
            "optional study or associated-artifact references require their exact typed payloads",
        )


def coordinates(request: TrialCompilationRequest) -> list[TrialCoordinateModel]:
    """Produce the bounded canonical logical coordinates."""

    run_plan = request.experiment.run_plan
    if run_plan.allocation is None:
        count = run_plan.target_run_count or 0
        if count == 0:
            raise _fail(
                "coordinate-set-empty", _RUN_PLAN_ADDRESS, "run allocation produced no logical trial coordinates"
            )
        if count > request.limits.max_coordinates:
            raise _fail(
                "coordinate-limit-exceeded",
                _RUN_PLAN_ADDRESS,
                "logical trial coordinates exceed the compilation limit",
            )
        return [TrialCoordinateModel(replicate_id=replicate_id(ordinal)) for ordinal in range(1, count + 1)]

    per_condition = run_plan.allocation.target_runs_per_condition
    condition_count = len(run_plan.allocation.compared_conditions)
    if condition_count == 0 or per_condition == 0:
        raise _fail("coordinate-set-empty", _RUN_PLAN_ADDRESS, "run allocation produced no logical trial coordinates")
    if condition_count > request.limits.max_coordinates // per_condition:
        raise _fail(
            "coordinate-limit-exceeded",
            _RUN_PLAN_ADDRESS,
            "logical trial coordinates exceed the compilation limit",
        )
    output: list[TrialCoordinateModel] = []
    for condition_id in sorted(run_plan.allocation.compared_conditions):
        output.extend(
            TrialCoordinateModel(condition_id=condition_id, replicate_id=replicate_id(ordinal))
            for ordinal in range(1, per_condition + 1)
        )
    return output


def plan_intent(request: TrialCompilationRequest, planned_coordinates: list[TrialCoordinateModel]) -> dict[str, object]:
    """Return the complete plan-identity projection."""

    return {
        "profiles": admitted_profiles().model_dump(mode="json"),
        "input_refs": request.input_refs.model_dump(mode="json"),
        "apparatus": request.apparatus.model_dump(mode="json"),
        "execution_authority": request.execution_authority.model_dump(mode="json"),
        "coordinates": [coordinate_projection(coordinate) for coordinate in planned_coordinates],
    }


def visit_indices(
    coordinate_count: int,
    coordinate_partitions: tuple[tuple[int, ...], ...] | None,
) -> tuple[int, ...]:
    """Validate and flatten the requested coordinate traversal."""

    if coordinate_partitions is None:
        return tuple(range(coordinate_count))
    flattened = tuple(index for partition in coordinate_partitions for index in partition)
    if sorted(flattened) != list(range(coordinate_count)):
        raise _fail(
            "coordinate-partitions-invalid",
            _RUN_PLAN_ADDRESS,
            "coordinate partitions must cover every canonical coordinate exactly once",
        )
    return flattened


__all__ = ["coordinates", "plan_intent", "validate_input_identities", "visit_indices"]
