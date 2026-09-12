"""Execution-snapshot validation (v1) for the formal-semantic bundle."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path

from tools.formal_semantic_validation._replay import (
    _participant_test_refs,
    _replay_observation_matches,
    replay_case,
)
from tools.formal_semantic_validation._shape import (
    _closed_object,
    _failure,
    _is_sequence,
    _stable_ids,
    _string_list,
)
from tools.formal_semantic_validation._types import (
    _COMMAND_KEYS,
    _COMMIT_RE,
    _HISTORICAL_REVISION_FIELD,
    _OBSERVATION_KEYS,
    _PARTICIPANT_OBSERVATION_KEYS,
    _SNAPSHOT_KEYS,
    _JsonObject,
)
from tools.policy.common import PolicyFailure


def _observation_coverage_failures(
    repo_root: Path,
    snapshot: _JsonObject,
    cases_by_id: dict[str, Mapping[str, object]],
    failures: list[PolicyFailure],
    path: str,
    *,
    replay_cases: bool,
) -> None:
    observations = snapshot.get("observations")
    if not _is_sequence(observations):
        failures.append(
            _failure(
                "formal-validation-observations",
                "snapshot observations must be a list",
                path,
            )
        )
        observations = []
    observation_ids: list[object] = []
    for item in observations:
        accepted, case_id = _validate_snapshot_observation(
            repo_root,
            snapshot,
            cases_by_id,
            item,
            failures,
            path,
            replay_cases=replay_cases,
        )
        if accepted:
            observation_ids.append(case_id)
    if set(observation_ids) != set(cases_by_id) or len(observation_ids) != len(set(observation_ids)):
        failures.append(
            _failure(
                "formal-validation-observation-coverage",
                "snapshot must contain exactly one observation per corpus case",
                path,
            )
        )


def _participant_coverage_failures(
    protocol: _JsonObject,
    snapshot: _JsonObject,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    participant_observations = snapshot.get("participant_observations")
    if not _is_sequence(participant_observations):
        failures.append(
            _failure(
                "formal-validation-participant-observations",
                "participant observations must be a list",
                path,
            )
        )
        participant_observations = []
    obligation_ids = {
        item.get("obligation_id") for item in protocol.get("participant_obligations", []) if isinstance(item, Mapping)
    }
    obligations_by_id = {
        item.get("obligation_id"): item
        for item in protocol.get("participant_obligations", [])
        if isinstance(item, Mapping)
    }
    observed_obligations: list[object] = []
    for item in participant_observations:
        accepted, obligation_id = _validate_snapshot_participant_observation(
            snapshot,
            obligation_ids,
            obligations_by_id,
            item,
            failures,
            path,
        )
        if accepted:
            observed_obligations.append(obligation_id)
    if set(observed_obligations) != obligation_ids or len(observed_obligations) != len(set(observed_obligations)):
        failures.append(
            _failure(
                "formal-validation-participant-observation-coverage",
                "snapshot must contain exactly one observation per participant obligation",
                path,
            )
        )


@dataclasses.dataclass(frozen=True)
class _SnapshotScope:
    """Read-only inputs shared by the v1 snapshot validators."""

    repo_root: Path
    protocol: _JsonObject
    corpus: _JsonObject
    snapshot: _JsonObject
    cases_by_id: dict[str, Mapping[str, object]]


def _validate_snapshot(
    scope: _SnapshotScope,
    failures: list[PolicyFailure],
    path: str,
    *,
    replay_cases: bool = True,
) -> None:
    if not _closed_object(
        scope.snapshot,
        _SNAPSHOT_KEYS,
        rule_id="formal-validation-snapshot-shape",
        label="snapshot",
        failures=failures,
        path=path,
    ):
        return
    _validate_snapshot_header(scope.protocol, scope.corpus, scope.snapshot, failures, path)
    _validate_snapshot_commands(scope.protocol, scope.snapshot, failures, path)
    _observation_coverage_failures(
        scope.repo_root, scope.snapshot, scope.cases_by_id, failures, path, replay_cases=replay_cases
    )
    _participant_coverage_failures(scope.protocol, scope.snapshot, failures, path)


def _validate_snapshot_observation(
    repo_root: Path,
    snapshot: Mapping[str, object],
    cases_by_id: Mapping[str, Mapping[str, object]],
    item: object,
    failures: list[PolicyFailure],
    path: str,
    *,
    replay_cases: bool,
) -> tuple[bool, object]:
    if not _closed_object(
        item,
        _OBSERVATION_KEYS,
        rule_id="formal-validation-observation-shape",
        label="observation",
        failures=failures,
        path=path,
    ):
        return False, None
    case_id = item.get("case_id")
    case = cases_by_id.get(str(case_id))
    if case is None:
        failures.append(
            _failure(
                "formal-validation-observation-case",
                f"observation references unknown case {case_id!r}",
                path,
            )
        )
        return True, case_id
    if item.get("execution_id") != snapshot.get("execution_id") or item.get("configuration_id") != snapshot.get(
        "configuration_id"
    ):
        failures.append(
            _failure(
                "formal-validation-observation-join",
                f"observation {case_id!r} must bind the snapshot execution and configuration",
                path,
            )
        )
    expected_replayable = case.get("replay_mode") != "unsupported"
    if item.get("replayable") is not expected_replayable:
        failures.append(
            _failure(
                "formal-validation-observation-replayable",
                f"observation {case_id!r} misstates replayability",
                path,
            )
        )
    if not _string_list(item.get("evidence_refs")) or not _string_list(item.get("limitations")):
        failures.append(
            _failure(
                "formal-validation-observation-evidence",
                f"observation {case_id!r} needs evidence refs and limitations",
                path,
            )
        )
    _validate_snapshot_replay(repo_root, case, item, failures, path, replay_cases=replay_cases)
    return True, case_id


def _validate_snapshot_replay(
    repo_root: Path,
    case: Mapping[str, object],
    item: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
    *,
    replay_cases: bool,
) -> None:
    case_id = item.get("case_id")
    replayable = case.get("replay_mode") != "unsupported"
    if replayable and replay_cases:
        try:
            replayed = replay_case(repo_root, case)
        except (ValueError, OSError) as exc:
            failures.append(
                _failure(
                    "formal-validation-replay-error",
                    f"could not replay {case_id!r}: {exc}",
                    path,
                )
            )
        else:
            if not _replay_observation_matches(item, replayed):
                failures.append(
                    _failure(
                        "formal-validation-replay-drift",
                        f"observation {case_id!r} drifted from replay",
                        path,
                    )
                )
    elif not replayable and (
        item.get("actual_outcome") != "unsupported"
        or item.get("diagnostic_kind") is not None
        or item.get("result_digest") is not None
    ):
        failures.append(
            _failure(
                "formal-validation-unsupported-observation",
                f"unsupported observation {case_id!r} must not synthesize diagnostics or results",
                path,
            )
        )


def _validate_snapshot_participant_observation(
    snapshot: Mapping[str, object],
    obligation_ids: set[object],
    obligations_by_id: Mapping[object, object],
    item: object,
    failures: list[PolicyFailure],
    path: str,
) -> tuple[bool, object]:
    if not _closed_object(
        item,
        _PARTICIPANT_OBSERVATION_KEYS,
        rule_id="formal-validation-participant-observation-shape",
        label="participant observation",
        failures=failures,
        path=path,
    ):
        return False, None
    obligation_id = item.get("obligation_id")
    if obligation_id not in obligation_ids:
        failures.append(
            _failure(
                "formal-validation-participant-observation-join",
                f"unknown participant obligation {obligation_id!r}",
                path,
            )
        )
    if item.get("execution_id") != snapshot.get("execution_id"):
        failures.append(
            _failure(
                "formal-validation-participant-observation-join",
                "participant observation must bind the snapshot execution",
                path,
            )
        )
    obligation = obligations_by_id.get(obligation_id)
    expected_refs = (
        [obligation.get("positive_test_ref"), obligation.get("negative_test_ref")]
        if isinstance(obligation, Mapping)
        else []
    )
    if item.get("evidence_refs") != expected_refs:
        failures.append(
            _failure(
                "formal-validation-participant-observation-evidence",
                f"participant obligation {obligation_id!r} must bind its declared positive and negative refs",
                path,
            )
        )
    if item.get("positive_outcome") != "passed" or item.get("negative_outcome") != "passed":
        failures.append(
            _failure(
                "formal-validation-participant-result",
                f"participant obligation {obligation_id!r} did not preserve passing fixtures",
                path,
            )
        )
    if not _valid_participant_evidence(item):
        failures.append(
            _failure(
                "formal-validation-participant-observation-evidence",
                f"participant obligation {obligation_id!r} needs two evidence refs and limitations",
                path,
            )
        )
    return True, obligation_id


def _valid_participant_evidence(item: Mapping[str, object]) -> bool:
    evidence_refs = item.get("evidence_refs")
    return bool(
        _string_list(evidence_refs, nonempty=True) and len(evidence_refs) == 2 and _string_list(item.get("limitations"))
    )


def _validate_snapshot_header(
    protocol: Mapping[str, object],
    corpus: Mapping[str, object],
    snapshot: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if snapshot.get("protocol_revision") != protocol.get("revision") or snapshot.get("corpus_revision") != corpus.get(
        "revision"
    ):
        failures.append(
            _failure(
                "formal-validation-snapshot-revision",
                "snapshot must bind the selected protocol and corpus revisions",
                path,
            )
        )
    if snapshot.get("execution_status") != "complete":
        failures.append(
            _failure(
                "formal-validation-execution-status",
                "snapshot must preserve a complete execution",
                path,
            )
        )
    historical_revision = snapshot.get(_HISTORICAL_REVISION_FIELD)
    if not isinstance(historical_revision, str) or not _COMMIT_RE.fullmatch(historical_revision):
        failures.append(
            _failure(
                "formal-validation-revision-pin",
                "historical revision must be a full immutable Git commit",
                path,
            )
        )


def _validate_snapshot_commands(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    commands = snapshot.get("commands")
    if not _is_sequence(commands) or not commands:
        failures.append(
            _failure(
                "formal-validation-commands",
                "snapshot must record fixed-argv reproduction commands",
                path,
            )
        )
        return
    command_ids, unique_command_ids = _stable_ids(commands, "command_id")
    if not command_ids or not unique_command_ids:
        failures.append(_failure("formal-validation-commands", "command ids must be unique stable ids", path))
    for item in commands:
        _validate_snapshot_command(item, failures, path)
    _validate_snapshot_participant_command(protocol, commands, failures, path)


def _validate_snapshot_command(item: object, failures: list[PolicyFailure], path: str) -> None:
    if not _closed_object(
        item,
        _COMMAND_KEYS,
        rule_id="formal-validation-command-shape",
        label="command",
        failures=failures,
        path=path,
    ):
        return
    if not _string_list(item.get("argv")) or item.get("network") != "disabled":
        failures.append(
            _failure(
                "formal-validation-commands",
                f"command {item.get('command_id')!r} must use non-empty argv and disabled network",
                path,
            )
        )


def _validate_snapshot_participant_command(
    protocol: Mapping[str, object],
    commands: Sequence[object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    expected_argv = [
        "implementations/python/.venv/bin/pytest",
        "-q",
        *_participant_test_refs(protocol),
    ]
    participant_commands = [
        item for item in commands if isinstance(item, Mapping) and item.get("command_id") == "participant-fixtures"
    ]
    if len(participant_commands) != 1 or participant_commands[0].get("argv") != expected_argv:
        failures.append(
            _failure(
                "formal-validation-participant-command",
                "snapshot must bind the participant replay command to every declared positive and negative test ref",
                path,
            )
        )
