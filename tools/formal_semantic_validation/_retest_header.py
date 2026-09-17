"""Header validation for integrated formal-semantic retest snapshots."""

from __future__ import annotations

from collections.abc import Mapping

from tools.formal_semantic_validation._shape import _failure, _nonempty_string
from tools.formal_semantic_validation._types import _COMMIT_RE, _VERSION_KEYS
from tools.policy.common import PolicyFailure


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
