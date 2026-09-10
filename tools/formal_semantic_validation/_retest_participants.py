"""Participant observation checks shared by integrated retest snapshots."""

from collections.abc import Mapping

from tools.formal_semantic_validation._shape import _closed_object, _failure, _is_sequence, _stable_ids, _string_list
from tools.formal_semantic_validation._types import _PARTICIPANT_OBSERVATION_KEYS
from tools.policy.common import PolicyFailure


def _validate_retest_participant_observations(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    obligations = {
        item.get("obligation_id"): item
        for item in protocol.get("participant_obligations", [])
        if isinstance(item, Mapping)
    }
    observations = snapshot.get("participant_observations")
    observation_ids, unique = _stable_ids(observations, "obligation_id")
    if not _is_sequence(observations) or not unique or observation_ids != set(obligations):
        failures.append(
            _failure(
                "formal-validation-participant-observation-coverage",
                "retest snapshot must retain every participant obligation exactly once",
                path,
            )
        )
        return
    for observation in observations:
        if not _closed_object(
            observation,
            _PARTICIPANT_OBSERVATION_KEYS,
            rule_id="formal-validation-participant-observation-shape",
            label="participant observation",
            failures=failures,
            path=path,
        ):
            continue
        _retest_participant_observation_failures(observation, obligations, snapshot, failures, path)


def _retest_participant_observation_failures(
    observation: Mapping[str, object],
    obligations: Mapping[object, Mapping[str, object]],
    snapshot: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    obligation = obligations.get(observation.get("obligation_id"))
    expected_refs = (
        [
            obligation.get("positive_test_ref"),
            obligation.get("negative_test_ref"),
        ]
        if isinstance(obligation, Mapping)
        else []
    )
    if (
        observation.get("execution_id") != snapshot.get("execution_id")
        or observation.get("evidence_refs") != expected_refs
        or observation.get("positive_outcome") != "passed"
        or observation.get("negative_outcome") != "passed"
        or not _string_list(observation.get("limitations"))
    ):
        failures.append(
            _failure(
                "formal-validation-participant-observation-join",
                f"participant observation {observation.get('obligation_id')!r} is stale",
                path,
            )
        )
