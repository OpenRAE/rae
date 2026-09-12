"""Retest-snapshot validation (v2) for the integrated release."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path

from tools.formal_semantic_validation._production import (
    _ProductionObservationContext,
    _validate_production_evidence_observation,
)
from tools.formal_semantic_validation._replay import (
    _participant_test_refs,
    _replay_observation_matches,
    replay_case,
)
from tools.formal_semantic_validation._retest_participants import _validate_retest_participant_observations
from tools.formal_semantic_validation._shape import (
    _closed_object,
    _failure,
    _is_sequence,
    _nonempty_string,
    _stable_ids,
    _string_list,
)
from tools.formal_semantic_validation._types import (
    _COMMAND_KEYS,
    _COMMIT_RE,
    _OBSERVATION_V2_KEYS,
    _SHA256_RE,
    _SNAPSHOT_V2_KEYS,
    _VERSION_KEYS,
    PRODUCTION_EVIDENCE_REPLAY_MODES,
    EvidenceRelease,
)
from tools.policy.common import PolicyFailure


@dataclasses.dataclass(frozen=True)
class _RetestScope:
    """Read-only inputs shared by the v2 retest-snapshot validators."""

    repo_root: Path
    release: EvidenceRelease
    protocol: dict[str, object]
    corpus: dict[str, object]
    snapshot: dict[str, object]
    cases_by_id: dict[str, Mapping[str, object]]
    replay_current: bool = True


def _validate_retest_snapshot(
    scope: _RetestScope,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    release = scope.release
    protocol = scope.protocol
    corpus = scope.corpus
    snapshot = scope.snapshot
    cases_by_id = scope.cases_by_id
    if not _closed_object(
        snapshot,
        _SNAPSHOT_V2_KEYS
        | ({"source_state"} if release.manifest.get("revision") in {"4.0.0", "5.0.0", "6.0.0", "7.0.0"} else set()),
        rule_id="formal-validation-snapshot-shape",
        label="retest snapshot",
        failures=failures,
        path=path,
    ):
        return
    _validate_retest_header(protocol, corpus, snapshot, failures, path)
    command_ids, commands_by_id = _validate_retest_commands(protocol, snapshot, failures, path)

    release_artifacts = [item for item in release.manifest.get("artifacts", []) if isinstance(item, Mapping)]
    release_artifacts_by_path = {
        item.get("path"): item for item in release_artifacts if isinstance(item.get("path"), str)
    }
    expected_release_paths = _retest_observation_failures(
        scope, (release_artifacts_by_path, commands_by_id), failures, path
    )
    if release.manifest.get("revision") in {"4.0.0", "5.0.0", "6.0.0", "7.0.0"}:
        expected_release_paths.update(_retained_fixture_paths(cases_by_id))
    _validate_release_selection(scope, command_ids, expected_release_paths, failures, path)
    _validate_retest_participant_observations(protocol, snapshot, failures, path)


def _validate_release_selection(
    scope: _RetestScope, command_ids: set[object], expected_paths: set[str], failures: list[PolicyFailure], path: str
) -> None:
    required_commands = {
        case_id
        for case_id, case in scope.cases_by_id.items()
        if case.get("replay_mode") in PRODUCTION_EVIDENCE_REPLAY_MODES
    }
    if not command_ids.issuperset(required_commands):
        failures.append(
            _failure(
                "formal-validation-production-command",
                "every production evidence case needs one fixed command",
                path,
            )
        )
    selected_release_paths = {
        str(item.get("path"))
        for item in scope.release.manifest.get("artifacts", [])
        if isinstance(item, Mapping) and item.get("kind") in {"corpus-input", "production-evidence"}
    }
    if selected_release_paths != expected_paths:
        failures.append(
            _failure(
                "formal-validation-production-evidence-join",
                "the atomic release must select exactly every production input and evidence artifact",
                scope.release.manifest_path,
            )
        )


def _retained_fixture_paths(cases_by_id: Mapping[str, Mapping[str, object]]) -> set[str]:
    return {
        value
        for case in cases_by_id.values()
        for value in (case.get("fixture_path"), case.get("comparison_fixture_path"))
        if isinstance(value, str)
    }


def _retest_observation_failures(
    scope: _RetestScope,
    pins: tuple[Mapping[object, Mapping[str, object]], Mapping[object, object]],
    failures: list[PolicyFailure],
    path: str,
) -> set[str]:
    snapshot = scope.snapshot
    cases_by_id = scope.cases_by_id
    expected_release_paths: set[str] = set()
    observations = snapshot.get("observations")
    observation_ids, unique_observation_ids = _stable_ids(observations, "case_id")
    if not _is_sequence(observations) or not unique_observation_ids:
        failures.append(
            _failure(
                "formal-validation-observation-coverage",
                "retest observations must have unique case ids",
                path,
            )
        )
        observations = []
    for observation in observations:
        expected_release_paths.update(
            _validate_retest_observation(
                scope,
                pins,
                observation,
                failures,
                path,
            )
        )
    if observation_ids != set(cases_by_id) or len(observation_ids) != len(cases_by_id):
        failures.append(
            _failure(
                "formal-validation-observation-coverage",
                "retest snapshot must contain exactly one observation per v2 corpus case",
                path,
            )
        )
    return expected_release_paths


def _validate_retest_header(
    protocol: Mapping[str, object],
    corpus: Mapping[str, object],
    snapshot: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if (
        snapshot.get("protocol_revision") != protocol.get("revision")
        or snapshot.get("corpus_revision") != corpus.get("revision")
        or snapshot.get("execution_status") != "complete"
    ):
        failures.append(
            _failure(
                "formal-validation-snapshot-revision",
                "retest snapshot must bind the selected revisions and a complete execution",
                path,
            )
        )
    revision = snapshot.get("raes_revision")
    if not isinstance(revision, str) or not _COMMIT_RE.fullmatch(revision):
        failures.append(
            _failure(
                "formal-validation-revision-pin",
                "retest snapshot must pin a full RAES commit",
                path,
            )
        )
    versions = snapshot.get("versions")
    if (
        not isinstance(versions, Mapping)
        or set(versions) != _VERSION_KEYS
        or not all(_nonempty_string(value) for value in versions.values())
    ):
        failures.append(
            _failure(
                "formal-validation-version-disclosure",
                "retest snapshot must record the bounded output-affecting versions",
                path,
            )
        )


def _validate_retest_commands(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> tuple[set[object], dict[object, Mapping[str, object]]]:
    commands = snapshot.get("commands")
    command_ids, unique_command_ids = _stable_ids(commands, "command_id")
    commands_by_id = (
        {item.get("command_id"): item for item in commands if isinstance(item, Mapping)}
        if _is_sequence(commands)
        else {}
    )
    if not _is_sequence(commands) or not unique_command_ids:
        failures.append(
            _failure(
                "formal-validation-commands",
                "retest command ids must be a unique bounded list",
                path,
            )
        )
        commands = []
    for command in commands:
        _validate_retest_command(command, failures, path)
    _validate_retest_participant_command(protocol, commands_by_id, failures, path)
    return command_ids, commands_by_id


def _validate_retest_command(command: object, failures: list[PolicyFailure], path: str) -> None:
    if not _closed_object(
        command,
        _COMMAND_KEYS,
        rule_id="formal-validation-command-shape",
        label="retest command",
        failures=failures,
        path=path,
    ):
        return
    if not _string_list(command.get("argv")) or command.get("network") != "disabled":
        failures.append(
            _failure(
                "formal-validation-commands",
                f"command {command.get('command_id')!r} must use fixed argv with network disabled",
                path,
            )
        )


def _validate_retest_participant_command(
    protocol: Mapping[str, object],
    commands_by_id: Mapping[object, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    participant_command = commands_by_id.get("participant-fixtures")
    expected_argv = [
        "implementations/python/.venv/bin/pytest",
        "-q",
        *_participant_test_refs(protocol),
    ]
    if not isinstance(participant_command, Mapping) or participant_command.get("argv") != expected_argv:
        failures.append(
            _failure(
                "formal-validation-participant-command",
                "retest snapshot must retain the complete participant fixture command",
                path,
            )
        )


def _validate_retest_observation(
    scope: _RetestScope,
    replay_context: tuple[
        Mapping[object, Mapping[str, object]],
        Mapping[object, Mapping[str, object]],
    ],
    observation: object,
    failures: list[PolicyFailure],
    path: str,
) -> set[str]:
    expected_paths: set[str] = set()
    if not _closed_object(
        observation,
        _OBSERVATION_V2_KEYS,
        rule_id="formal-validation-observation-shape",
        label="retest observation",
        failures=failures,
        path=path,
    ):
        return expected_paths
    case_id = observation.get("case_id")
    case = scope.cases_by_id.get(str(case_id))
    if case is None:
        failures.append(
            _failure(
                "formal-validation-observation-case",
                f"observation references unknown case {case_id!r}",
                path,
            )
        )
    else:
        _validate_retest_observation_metadata(scope.snapshot, case, observation, failures, path)
        if case.get("replay_mode") in PRODUCTION_EVIDENCE_REPLAY_MODES:
            release_artifacts_by_path, commands_by_id = replay_context
            _validate_production_evidence_observation(
                _ProductionObservationContext(scope.repo_root, release_artifacts_by_path, scope.replay_current),
                case,
                observation,
                commands_by_id.get(case_id),
                failures,
                path,
            )
            expected_paths.update(
                value
                for value in (case.get("fixture_path"), observation.get("evidence_artifact_path"))
                if isinstance(value, str)
            )
        else:
            _validate_retained_retest_observation(
                scope.repo_root, case, observation, failures, path, replay_current=scope.replay_current
            )
    return expected_paths


def _validate_retest_observation_metadata(
    snapshot: Mapping[str, object],
    case: Mapping[str, object],
    observation: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    case_id = observation.get("case_id")
    if observation.get("execution_id") != snapshot.get("execution_id") or observation.get(
        "configuration_id"
    ) != snapshot.get("configuration_id"):
        failures.append(
            _failure(
                "formal-validation-observation-join",
                f"observation {case_id!r} must bind the retest execution and configuration",
                path,
            )
        )
    expected_replayable = case.get("replay_mode") != "unsupported"
    if observation.get("replayable") is not expected_replayable:
        failures.append(
            _failure(
                "formal-validation-observation-replayable",
                f"observation {case_id!r} misstates replayability",
                path,
            )
        )
    if not _string_list(observation.get("evidence_refs")) or not _string_list(observation.get("limitations")):
        failures.append(
            _failure(
                "formal-validation-observation-evidence",
                f"observation {case_id!r} needs evidence refs and explicit limitations",
                path,
            )
        )


def _validate_retained_retest_observation(
    repo_root: Path,
    case: Mapping[str, object],
    observation: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
    *,
    replay_current: bool = True,
) -> None:
    case_id = observation.get("case_id")
    evidence_fields = (
        "evidence_profile",
        "analysis_profile",
        "configuration_digest",
        "evidence_digest",
        "evidence_artifact_path",
        "evidence_artifact_sha256",
        "source_digest",
    )
    if any(observation.get(key) is not None for key in evidence_fields):
        failures.append(
            _failure(
                "formal-validation-production-evidence-join",
                f"retained case {case_id!r} must not synthesize a production envelope",
                path,
            )
        )
    if case.get("replay_mode") == "unsupported":
        _validate_unsupported_retest_observation(observation, failures, path)
        return
    if not replay_current:
        if not _historical_observation_matches(case, observation):
            failures.append(
                _failure("formal-validation-replay-drift", "historical outcome differs from its control", path)
            )
        return
    try:
        replayed = replay_case(repo_root, case)
    except (OSError, ValueError) as exc:
        failures.append(
            _failure(
                "formal-validation-replay-error",
                f"retained case {case_id!r} could not replay ({type(exc).__name__})",
                path,
            )
        )
    else:
        if not _replay_observation_matches(observation, replayed):
            failures.append(
                _failure(
                    "formal-validation-replay-drift",
                    f"retained case {case_id!r} drifted without a matching observation",
                    path,
                )
            )


def _historical_observation_matches(case: Mapping[str, object], observation: Mapping[str, object]) -> bool:
    digest = observation.get("result_digest")
    diagnostic_kind = observation.get("diagnostic_kind")
    return (
        observation.get("actual_outcome") == case.get("expected_outcome")
        and (digest is None or (isinstance(digest, str) and bool(_SHA256_RE.fullmatch(digest))))
        and (diagnostic_kind is None or isinstance(diagnostic_kind, str))
    )


def _validate_unsupported_retest_observation(
    observation: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if (
        observation.get("actual_outcome") != "unsupported"
        or observation.get("diagnostic_kind") is not None
        or observation.get("result_digest") is not None
    ):
        failures.append(
            _failure(
                "formal-validation-unsupported-observation",
                f"historical unsupported case {observation.get('case_id')!r} must remain unsupported",
                path,
            )
        )
