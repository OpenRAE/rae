"""Whole-bundle validation joining protocol, corpus, snapshot, and analysis."""

from __future__ import annotations

from pathlib import Path

from tools.formal_semantic_validation._analysis import _AnalysisContext, _validate_analysis
from tools.formal_semantic_validation._corpus import _validate_corpus
from tools.formal_semantic_validation._protocol import _validate_protocol
from tools.formal_semantic_validation._shape import _closed_object
from tools.formal_semantic_validation._snapshot import _SnapshotScope, _validate_snapshot
from tools.formal_semantic_validation._types import _MANIFEST_KEYS, MANIFEST_PATH, _JsonObject
from tools.policy.common import PolicyFailure


def validate_bundle(
    repo_root: Path,
    manifest: _JsonObject,
    protocol: _JsonObject,
    corpus: _JsonObject,
    snapshot: _JsonObject,
    analysis: _JsonObject,
    *,
    replay_cases: bool = True,
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    if not _closed_object(
        manifest,
        _MANIFEST_KEYS,
        rule_id="formal-validation-manifest-shape",
        label="manifest",
        failures=failures,
        path=MANIFEST_PATH,
    ):
        return failures
    protocol_path = str(manifest.get("protocol_path"))
    corpus_path = str(manifest.get("corpus_path"))
    snapshot_path = str(manifest.get("snapshot_path"))
    analysis_path = str(manifest.get("analysis_path"))
    _validate_protocol(repo_root, protocol, failures, protocol_path)
    cases_by_id = _validate_corpus(repo_root, protocol, corpus, failures, corpus_path)
    _validate_snapshot(
        _SnapshotScope(
            repo_root=repo_root,
            protocol=protocol,
            corpus=corpus,
            snapshot=snapshot,
            cases_by_id=cases_by_id,
        ),
        failures,
        snapshot_path,
        replay_cases=replay_cases,
    )
    _validate_analysis(_AnalysisContext(repo_root, analysis_path), protocol, corpus, snapshot, analysis, failures)
    return failures
