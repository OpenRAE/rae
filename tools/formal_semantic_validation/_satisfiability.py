"""Historical satisfiability supplement loading and validation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from tools.formal_semantic_validation._shape import (
    _closed_object,
    _failure,
    _is_sequence,
    _nonempty_string,
    _sha256_file,
    _stable_ids,
    _string_list,
)
from tools.formal_semantic_validation._types import (
    _COMMAND_KEYS,
    _CURRENT_SATISFIABILITY_PROFILE,
    _HISTORICAL_CLI,
    _HISTORICAL_SATISFIABILITY_ANALYSIS_PROFILE,
    _HISTORICAL_SATISFIABILITY_EXECUTION_PROFILE,
    _HISTORICAL_SATISFIABILITY_PROFILE,
    _SATISFIABILITY_ANALYSIS_KEYS,
    _SATISFIABILITY_CASE_KEYS,
    _SATISFIABILITY_CONTROL_OUTCOMES,
    _SATISFIABILITY_OBSERVATION_KEYS,
    _SATISFIABILITY_SNAPSHOT_KEYS,
    _SHA256_RE,
    MANIFEST_PATH,
    _JsonObject,
)
from tools.policy.common import PolicyFailure, safe_repo_path


def validate_satisfiability_analysis(
    repo_root: Path,
    manifest: _JsonObject,
    snapshot: _JsonObject,
    analysis: _JsonObject,
    *,
    replay_current: bool = True,
) -> list[PolicyFailure]:
    """Recompute the finite-profile control matrix and replay every envelope."""

    failures: list[PolicyFailure] = []
    path = str(manifest.get("satisfiability_analysis_path"))
    snapshot_path = str(manifest.get("satisfiability_snapshot_path"))
    _manifest_revision_failures(manifest, failures)
    if not _closed_object(
        analysis,
        _SATISFIABILITY_ANALYSIS_KEYS,
        rule_id="formal-satisfiability-analysis-shape",
        label="satisfiability analysis",
        failures=failures,
        path=path,
    ):
        return failures
    snapshot_shape_valid = _closed_object(
        snapshot,
        _SATISFIABILITY_SNAPSHOT_KEYS,
        rule_id="formal-satisfiability-snapshot-shape",
        label="satisfiability execution snapshot",
        failures=failures,
        path=snapshot_path,
    )
    _satisfiability_scope_failures(analysis, failures, path)
    cases = None
    if snapshot_shape_valid:
        _satisfiability_join_failures(snapshot, analysis, failures, path, snapshot_path)
        cases = _validated_satisfiability_cases(analysis, failures, path)
    if cases is not None:
        cases_by_id = _cases_by_id(cases)
        _satisfiability_command_failures(snapshot, cases_by_id, analysis, failures, snapshot_path)
        observations_by_case = _satisfiability_observations(snapshot, cases_by_id, failures, snapshot_path)
        _satisfiability_case_failures(
            repo_root,
            cases,
            snapshot,
            observations_by_case,
            failures,
            path,
            snapshot_path,
            replay_current=replay_current,
        )
    return failures


def _manifest_revision_failures(manifest: _JsonObject, failures: list[PolicyFailure]) -> None:
    if manifest.get("revision") != "2.0.0":
        failures.append(
            _failure(
                "formal-satisfiability-manifest-revision",
                "the satisfiability supplement requires bundle revision 2.0.0",
                MANIFEST_PATH,
            )
        )


def _cases_by_id(cases: list[object]) -> dict[object, Mapping[str, object]]:
    return {
        item.get("case_id"): item
        for item in cases
        if isinstance(item, Mapping) and _nonempty_string(item.get("case_id"))
    }


def _satisfiability_scope_failures(analysis: _JsonObject, failures: list[PolicyFailure], path: str) -> None:
    if (
        analysis.get("profile") != _HISTORICAL_SATISFIABILITY_ANALYSIS_PROFILE
        or analysis.get("revision") != "1.0.0"
        or analysis.get("issue_number") != 826
        or analysis.get("requirement_uid") != "ASR-530"
        or analysis.get("analysis_profile") != _HISTORICAL_SATISFIABILITY_PROFILE
        or analysis.get("claim_class_id") != "constraint-satisfiability"
    ):
        failures.append(
            _failure(
                "formal-satisfiability-scope",
                "the supplement must remain bound to issue 826, ASR-530, and the v1 finite-domain profile",
                path,
            )
        )


def _snapshot_binding_valid(snapshot: _JsonObject, analysis: _JsonObject) -> bool:
    return (
        snapshot.get("profile") == _HISTORICAL_SATISFIABILITY_EXECUTION_PROFILE
        and snapshot.get("revision") == "1.0.0"
        and snapshot.get("execution_id") == analysis.get("execution_id")
        and snapshot.get("revision") == analysis.get("snapshot_revision")
        and snapshot.get("analysis_profile") == analysis.get("analysis_profile")
        and _nonempty_string(snapshot.get("captured_at"))
        and _nonempty_string(snapshot.get("solver_configuration_digest"))
        and snapshot.get("deviations") == []
    )


def _satisfiability_join_failures(
    snapshot: _JsonObject,
    analysis: _JsonObject,
    failures: list[PolicyFailure],
    path: str,
    snapshot_path: str,
) -> None:
    if not _snapshot_binding_valid(snapshot, analysis):
        failures.append(
            _failure(
                "formal-satisfiability-snapshot-join",
                "the execution snapshot must bind the analysis, profile, configuration, and no-deviation run",
                snapshot_path,
            )
        )
    if (
        analysis.get("evidence_status") != "demonstrated"
        or not _nonempty_string(analysis.get("scope"))
        or not _string_list(analysis.get("limitations"))
    ):
        failures.append(
            _failure(
                "formal-satisfiability-disclosure",
                "the bounded demonstrated result requires a scope and non-empty limitations",
                path,
            )
        )


def _validated_satisfiability_cases(
    analysis: _JsonObject,
    failures: list[PolicyFailure],
    path: str,
) -> list[object] | None:
    cases = analysis.get("cases")
    if not _is_sequence(cases) or len(cases) != len(_SATISFIABILITY_CONTROL_OUTCOMES):
        failures.append(
            _failure(
                "formal-satisfiability-control-coverage",
                "the supplement requires exactly one positive, negative, and unsupported control",
                path,
            )
        )
        return None
    controls = [item.get("control") for item in cases if isinstance(item, Mapping)]
    case_ids, unique_case_ids = _stable_ids(cases, "case_id")
    if (
        set(controls) != set(_SATISFIABILITY_CONTROL_OUTCOMES)
        or len(controls) != len(set(controls))
        or len(case_ids) != len(cases)
        or not unique_case_ids
    ):
        failures.append(
            _failure(
                "formal-satisfiability-control-coverage",
                "controls and case ids must be complete, unique, and stable",
                path,
            )
        )
    return list(cases)


def _satisfiability_command_failures(
    snapshot: _JsonObject,
    cases_by_id: dict[object, Mapping[str, object]],
    analysis: _JsonObject,
    failures: list[PolicyFailure],
    snapshot_path: str,
) -> None:
    commands = snapshot.get("commands")
    command_ids, unique_command_ids = _stable_ids(commands, "command_id")
    if not _is_sequence(commands) or command_ids != set(cases_by_id) or not unique_command_ids:
        failures.append(
            _failure(
                "formal-satisfiability-snapshot-commands",
                "the snapshot requires one fixed-argv command per satisfiability case",
                snapshot_path,
            )
        )
        commands = []
    for command in commands:
        if not _closed_object(
            command,
            _COMMAND_KEYS,
            rule_id="formal-satisfiability-command-shape",
            label="satisfiability command",
            failures=failures,
            path=snapshot_path,
        ):
            continue
        case = cases_by_id.get(command.get("command_id"))
        expected_argv = [
            _HISTORICAL_CLI,
            "processor",
            "satisfiability",
            case.get("fixture_path") if isinstance(case, Mapping) else None,
            "--profile",
            analysis.get("analysis_profile"),
        ]
        if command.get("argv") != expected_argv or command.get("network") != "disabled":
            failures.append(
                _failure(
                    "formal-satisfiability-snapshot-commands",
                    f"command {command.get('command_id')!r} drifted from its fixed offline invocation",
                    snapshot_path,
                )
            )


def _satisfiability_observations(
    snapshot: _JsonObject,
    cases_by_id: dict[object, Mapping[str, object]],
    failures: list[PolicyFailure],
    snapshot_path: str,
) -> dict[object, Mapping[str, object]]:
    observations = snapshot.get("observations")
    observation_ids, unique_observation_ids = _stable_ids(observations, "case_id")
    if not _is_sequence(observations) or observation_ids != set(cases_by_id) or not unique_observation_ids:
        failures.append(
            _failure(
                "formal-satisfiability-snapshot-coverage",
                "the snapshot requires one observation per satisfiability case",
                snapshot_path,
            )
        )
        observations = []
    observations_by_case: dict[object, Mapping[str, object]] = {}
    for observation in observations:
        if not _closed_object(
            observation,
            _SATISFIABILITY_OBSERVATION_KEYS,
            rule_id="formal-satisfiability-observation-shape",
            label="satisfiability observation",
            failures=failures,
            path=snapshot_path,
        ):
            continue
        observations_by_case[observation.get("case_id")] = observation
        if (
            observation.get("evidence_profile") != "scenario-satisfiability-evidence/v1"
            or observation.get("replayable") is not True
            or not _nonempty_string(observation.get("limitation"))
        ):
            failures.append(
                _failure(
                    "formal-satisfiability-snapshot-disclosure",
                    f"observation {observation.get('case_id')!r} lacks replay or limitation disclosure",
                    snapshot_path,
                )
            )
    return observations_by_case


def _normalized_case_digest_matches(evidence: object, item: Mapping[str, object], case_id: object) -> bool:
    return evidence.normalized_model_digest == item.get("expected_normalized_model_digest")


def _observation_drifted(
    observation: Mapping[str, object] | None,
    evidence: object,
    snapshot: _JsonObject,
    case_id: object,
) -> bool:
    if observation is None:
        return True
    observation_normalized_digest_matches = (
        observation.get("normalized_model_digest") == evidence.normalized_model_digest
    )
    solver_digest_matches = snapshot.get("solver_configuration_digest") == evidence.solver_configuration_digest
    return (
        observation.get("actual_outcome") != evidence.outcome.value
        or observation.get("source_byte_digest") != evidence.source.byte_digest
        or not observation_normalized_digest_matches
        or not solver_digest_matches
    )


def _control_evidence_failures(
    control: object,
    evidence: object,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if control == "positive" and evidence.witness is None:
        failures.append(
            _failure(
                "formal-satisfiability-evidence-shape",
                "positive control lacks a witness",
                path,
            )
        )
    elif control == "negative" and evidence.unsat_core is None:
        failures.append(
            _failure(
                "formal-satisfiability-evidence-shape",
                "negative control lacks a core",
                path,
            )
        )
    elif control == "unsupported" and (evidence.unsupported is None or not evidence.diagnostics):
        failures.append(
            _failure(
                "formal-satisfiability-evidence-shape",
                "unsupported control lacks its fail-closed disclosure",
                path,
            )
        )


def _satisfiability_case_entry_failures(
    repo_root: Path,
    item: Mapping[str, object],
    snapshot: _JsonObject,
    observations_by_case: dict[object, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
    snapshot_path: str,
    *,
    replay_current: bool = True,
) -> None:
    from raes_processor.satisfiability import (
        analyze_scenario_file,
        replay_satisfiability_evidence,
    )

    case_id = item.get("case_id")
    control = item.get("control")
    expected_for_control = _SATISFIABILITY_CONTROL_OUTCOMES.get(str(control))
    if expected_for_control is None or item.get("expected_outcome") != expected_for_control:
        failures.append(
            _failure(
                "formal-satisfiability-replay-drift",
                f"case {case_id!r} does not preserve its control outcome",
                path,
            )
        )
    fixture_value = item.get("fixture_path")
    fixture = safe_repo_path(repo_root, str(fixture_value)) if _nonempty_string(fixture_value) else None
    if fixture is None or not fixture.is_file():
        failures.append(
            _failure(
                "formal-satisfiability-case-path",
                f"case {case_id!r} has a missing or unsafe fixture",
                path,
            )
        )
        return
    if not _nonempty_string(item.get("limitation")):
        failures.append(
            _failure(
                "formal-satisfiability-case-limit",
                f"case {case_id!r} must record a limitation",
                path,
            )
        )
    if not replay_current:
        observation = observations_by_case.get(case_id, {})
        digest = item.get("expected_normalized_model_digest")
        if (
            not isinstance(digest, str)
            or not digest.startswith("sha256:")
            or not _SHA256_RE.fullmatch(digest[7:])
            or observation.get("normalized_model_digest") != digest
            or observation.get("actual_outcome") != expected_for_control
            or observation.get("source_byte_digest") != "sha256:" + _sha256_file(fixture)
        ):
            failures.append(
                _failure(
                    "formal-satisfiability-snapshot-drift",
                    "historical control or source digest join is invalid",
                    snapshot_path,
                )
            )
        return
    try:
        evidence = analyze_scenario_file(fixture, profile=_CURRENT_SATISFIABILITY_PROFILE)
        replay_satisfiability_evidence(fixture, evidence)
    except (OSError, ValueError, RuntimeError) as exc:
        failures.append(
            _failure(
                "formal-satisfiability-replay-error",
                f"case {case_id!r} could not complete production replay ({type(exc).__name__})",
                path,
            )
        )
        return
    if evidence.outcome.value != item.get("expected_outcome") or not _normalized_case_digest_matches(
        evidence, item, case_id
    ):
        failures.append(
            _failure(
                "formal-satisfiability-replay-drift",
                f"case {case_id!r} drifted from its frozen outcome or normalized model",
                path,
            )
        )
    if _observation_drifted(observations_by_case.get(case_id), evidence, snapshot, case_id):
        failures.append(
            _failure(
                "formal-satisfiability-snapshot-drift",
                f"case {case_id!r} drifted from its execution snapshot",
                snapshot_path,
            )
        )
    _control_evidence_failures(control, evidence, failures, path)


def _satisfiability_case_failures(
    repo_root: Path,
    cases: list[object],
    snapshot: _JsonObject,
    observations_by_case: dict[object, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
    snapshot_path: str,
    *,
    replay_current: bool = True,
) -> None:
    for item in cases:
        if not _closed_object(
            item,
            _SATISFIABILITY_CASE_KEYS,
            rule_id="formal-satisfiability-case-shape",
            label="satisfiability case",
            failures=failures,
            path=path,
        ):
            continue
        _satisfiability_case_entry_failures(
            repo_root,
            item,
            snapshot,
            observations_by_case,
            failures,
            path,
            snapshot_path,
            replay_current=replay_current,
        )
