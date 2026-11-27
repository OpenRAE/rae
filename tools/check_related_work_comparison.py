#!/usr/bin/env python3
"""Validate the frozen, evidence-backed related-work comparison bundle."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError  # noqa: E402
from raes_contracts.operational_logging import run_application  # noqa: E402

from tools.policy.common import (  # noqa: E402
    PolicyFailure,
    load_bounded_json_object,
    safe_repo_path,
)

PROTOCOL_PATH = "docs/research/related-work-comparison/protocol-v1.json"
SNAPSHOT_PATH = "docs/research/related-work-comparison/extraction-snapshot-2026-07-13.json"
ANALYSIS_PATH = "docs/research/related-work-comparison/analysis-v1.json"
PUBLICATION_PATH = "docs/explain/sdl/related-work-comparison.md"
PUBLICATION_START = "<!-- related-work-comparison:start -->"
PUBLICATION_END = "<!-- related-work-comparison:end -->"
_HISTORICAL_PACKAGE_PREFIX = "implementations/python/packages/" + "a" + "ces_sdl"
_CURRENT_PACKAGE_PREFIX = "implementations/python/packages/raes"
_HISTORICAL_SYSTEM_ID = "a" + "ces"

EXPECTED_AXIS_IDS = {
    "expressive-breadth",
    "semantic-precision",
    "formal-analyzability",
    "concrete-syntax-soundness",
    "composition-versioning",
    "experiment-design",
    "participant-modeling",
    "provenance-evidence",
    "interoperability",
    "usability",
    "implementation-maturity",
    "governance-community",
}

_PROTOCOL_KEYS = {
    "protocol_id",
    "revision",
    "registered_at",
    "title",
    "purpose",
    "inclusion_criteria",
    "exclusion_criteria",
    "scope_strata",
    "systems",
    "axes",
    "cases",
    "analysis_rules",
    "amendment_log",
}
_STRATUM_KEYS = {"stratum_id", "label", "description"}
_SYSTEM_KEYS = {
    "system_id",
    "name",
    "version_label",
    "scope_stratum",
    "inclusion_rationale",
    "exclusion_rationale",
}
_AXIS_KEYS = {"axis_id", "label", "construct", "direction", "rubric"}
_CASE_KEYS = {
    "case_id",
    "kind",
    "title",
    "authored_requirement",
    "unit_of_observation",
    "applicability_rule",
    "permitted_assistance",
    "inputs",
    "expected_artifact",
    "criteria",
}
_CASE_CRITERIA_KEYS = {"success", "partial", "failure"}
_ANALYSIS_RULE_KEYS = {
    "primary_result",
    "pareto_scope",
    "missing_handling",
    "weighting_policy",
    "reversal_policy",
    "quality_claim_policy",
    "claim_evidence_policy",
}
_SNAPSHOT_KEYS = {
    "snapshot_id",
    "protocol_revision",
    "frozen_at",
    "assessor",
    "review_status",
    "limitations",
    "sources",
    "observations",
    "task_observations",
}
_SOURCE_KEYS = {
    "source_id",
    "system_id",
    "kind",
    "title",
    "locator",
    "version",
    "revision",
    "retrieved_at",
    "content_sha256",
    "artifact_path",
    "primary",
    "evidence_class",
    "license_note",
}
_OBSERVATION_KEYS = {
    "system_id",
    "axis_id",
    "applicability",
    "score",
    "measure",
    "extraction_method",
    "rationale",
    "evidence_refs",
    "confidence",
    "limitations",
    "review_status",
}
_TASK_OBSERVATION_KEYS = {
    "system_id",
    "case_id",
    "applicability",
    "outcome",
    "method",
    "rationale",
    "evidence_refs",
    "limitations",
}
_EVIDENCE_REF_KEYS = {"source_id", "locator"}
_ANALYSIS_KEYS = {
    "analysis_id",
    "protocol_revision",
    "snapshot_id",
    "generated_at",
    "score_method",
    "pareto_groups",
    "weight_profiles",
    "sensitivity",
    "claims",
}
_PARETO_KEYS = {
    "group_id",
    "scope_stratum",
    "system_ids",
    "axis_ids",
    "frontier_system_ids",
}
_WEIGHT_PROFILE_KEYS = {"profile_id", "scope_stratum", "weights", "totals", "ranking"}
_SENSITIVITY_KEYS = {
    "profile_ids",
    "ranking_reversal_observed",
    "winning_systems",
    "disclosure",
}
_CLAIM_KEYS = {
    "claim_id",
    "kind",
    "statement",
    "system_ids",
    "axis_ids",
    "evidence_status",
    "threats_to_validity",
    "falsification",
    "derivation",
}
_FALSIFICATION_KEYS = {
    "protocol",
    "objective_pass_criteria",
    "objective_fail_criteria",
    "allowed_evidence_classes",
    "disallowed_evidence_classes",
    "evidence_artifact_refs",
}
_CLAIM_DERIVATION_KEYS = {
    "no-overall-winner": {
        "kind",
        "scope_strata",
        "profile_winners",
        "ranking_reversal_observed",
    },
    "scope-qualified-breadth": {
        "kind",
        "scope_stratum",
        "axis_id",
        "system_scores",
        "max_score",
        "leading_system_ids",
    },
    "maturity-governance": {"kind", "comparisons"},
    "sensitivity": {"kind", "profile_winners", "ranking_reversal_observed"},
}
_CLAIM_EVIDENCE_STATUSES = {"untested", "partial", "demonstrated", "refuted"}

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
}
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_SYSTEMS = 32
_MAX_AXES = 32
_MAX_CASES = 64
_MAX_SOURCES = 512
_MAX_OBSERVATIONS = 4096
_MEASURE_BY_SCORE = {0: "absent", 1: "limited", 2: "substantial", 3: "strong"}


def _failure(rule_id: str, message: str, path: str | None = None) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _resolve_repository_artifact(repo_root: Path, artifact_path: str) -> Path | None:
    """Resolve an immutable evidence locator through the SDL package move."""

    resolved_path = artifact_path
    if artifact_path == _HISTORICAL_PACKAGE_PREFIX or artifact_path.startswith(f"{_HISTORICAL_PACKAGE_PREFIX}/"):
        resolved_path = f"{_CURRENT_PACKAGE_PREFIX}{artifact_path[len(_HISTORICAL_PACKAGE_PREFIX) :]}"
    return safe_repo_path(repo_root, resolved_path)


def load_bundle(
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Load the three frozen bundle artifacts with strict duplicate-key handling."""

    return (
        load_bounded_json_object(repo_root, PROTOCOL_PATH, max_bytes=_MAX_FILE_BYTES),
        load_bounded_json_object(repo_root, SNAPSHOT_PATH, max_bytes=_MAX_FILE_BYTES),
        load_bounded_json_object(repo_root, ANALYSIS_PATH, max_bytes=_MAX_FILE_BYTES),
    )


def _exact_keys(
    value: object,
    expected: set[str],
    failures: list[PolicyFailure],
    *,
    rule_id: str,
    label: str,
    path: str,
) -> bool:
    if not isinstance(value, dict):
        failures.append(_failure(rule_id, f"{label} must be an object", path))
        return False
    actual = set(value)
    if actual != expected:
        failures.append(
            _failure(
                rule_id,
                f"{label} fields must exactly match {sorted(expected)}; got {sorted(actual)}",
                path,
            )
        )
        return False
    return True


def _bounded_list(
    value: object,
    limit: int,
    failures: list[PolicyFailure],
    *,
    rule_id: str,
    label: str,
    path: str,
) -> list[object]:
    if not isinstance(value, list):
        failures.append(_failure(rule_id, f"{label} must be a list", path))
        return []
    if len(value) > limit:
        failures.append(_failure(rule_id, f"{label} exceeds the {limit}-entry limit", path))
        return []
    return value


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _record_ids(
    records: Sequence[object],
    field: str,
    failures: list[PolicyFailure],
    *,
    rule_id: str,
    label: str,
    path: str,
) -> set[str]:
    ids: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get(field)
        if not _valid_id(value):
            failures.append(_failure(rule_id, f"{label} has invalid {field} {value!r}", path))
            continue
        if value in ids:
            duplicates.add(value)
        ids.add(value)
    if duplicates:
        failures.append(_failure(rule_id, f"duplicate {label} ids: {sorted(duplicates)}", path))
    return ids


def _validate_locator(locator: object, failures: list[PolicyFailure], source_id: object) -> None:
    if not isinstance(locator, str):
        failures.append(
            _failure(
                "related-work-source-locator",
                f"{source_id}: locator must be a string",
                SNAPSHOT_PATH,
            )
        )
        return
    try:
        parsed = urlsplit(locator)
    except ValueError:
        # urlsplit refuses a malformed authority, such as an unclosed IPv6 bracket.
        parsed = None
    if parsed is None or parsed.scheme != "https" or not parsed.netloc:
        failures.append(
            _failure(
                "related-work-source-locator",
                f"{source_id}: locator must be an absolute HTTPS URL",
                SNAPSHOT_PATH,
            )
        )
    if parsed is None:
        return
    if parsed.username is not None or parsed.password is not None:
        failures.append(
            _failure(
                "related-work-source-locator-secret",
                f"{source_id}: locator must not contain URI userinfo",
                SNAPSHOT_PATH,
            )
        )
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    sensitive = sorted(query_keys & _SENSITIVE_QUERY_KEYS)
    if sensitive:
        failures.append(
            _failure(
                "related-work-source-locator-secret",
                f"{source_id}: locator contains secret-bearing query keys {sensitive}",
                SNAPSHOT_PATH,
            )
        )


def _safe_external_artifact_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _bounded_text(value: object, *, maximum: int = 4000) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _bounded_text_list(value: object, *, maximum_items: int = 16) -> bool:
    return isinstance(value, list) and 0 < len(value) <= maximum_items and all(_bounded_text(item) for item in value)


def _validate_sources(
    repo_root: Path,
    sources: Sequence[object],
    system_ids: set[str],
    failures: list[PolicyFailure],
    *,
    validate_paths: bool,
) -> dict[str, Mapping[str, object]]:
    source_by_id: dict[str, Mapping[str, object]] = {}
    allowed_kinds = {
        "repository-internal",
        "git",
        "standard",
        "publication",
        "official-doc",
    }
    allowed_evidence_classes = {
        "executable",
        "normative",
        "documentation",
        "publication",
        "source-code",
    }
    for index, raw_source in enumerate(sources):
        label = f"sources[{index}]"
        if not _exact_keys(
            raw_source,
            _SOURCE_KEYS,
            failures,
            rule_id="related-work-source-shape",
            label=label,
            path=SNAPSHOT_PATH,
        ):
            continue
        source = raw_source
        source_id = source["source_id"]
        if not _valid_id(source_id):
            failures.append(
                _failure(
                    "related-work-source-id",
                    f"invalid source id {source_id!r}",
                    SNAPSHOT_PATH,
                )
            )
            continue
        if source_id in source_by_id:
            failures.append(
                _failure(
                    "related-work-source-id",
                    f"duplicate source id {source_id!r}",
                    SNAPSHOT_PATH,
                )
            )
            continue
        source_by_id[source_id] = source
        if source["system_id"] not in system_ids:
            failures.append(
                _failure(
                    "related-work-source-system",
                    f"{source_id}: unknown system {source['system_id']!r}",
                    SNAPSHOT_PATH,
                )
            )
        if source["kind"] not in allowed_kinds:
            failures.append(
                _failure(
                    "related-work-source-kind",
                    f"{source_id}: invalid source kind",
                    SNAPSHOT_PATH,
                )
            )
        if source["evidence_class"] not in allowed_evidence_classes:
            failures.append(
                _failure(
                    "related-work-source-kind",
                    f"{source_id}: invalid evidence class",
                    SNAPSHOT_PATH,
                )
            )
        if source["primary"] is not True:
            failures.append(
                _failure(
                    "related-work-source-primary",
                    f"{source_id}: comparison evidence must be primary",
                    SNAPSHOT_PATH,
                )
            )
        _validate_locator(source["locator"], failures, source_id)
        revision = source["revision"]
        if source["kind"] in {"git", "repository-internal"} and (
            not isinstance(revision, str) or not _GIT_REVISION_RE.fullmatch(revision)
        ):
            failures.append(
                _failure(
                    "related-work-source-pin",
                    f"{source_id}: Git evidence requires a full 40-hex commit",
                    SNAPSHOT_PATH,
                )
            )
        if source["kind"] in {"standard", "publication"} and (
            not isinstance(revision, str)
            or not revision.strip()
            or revision.casefold() in {"current", "head", "latest", "main", "master"}
        ):
            failures.append(
                _failure(
                    "related-work-source-pin",
                    f"{source_id}: standard/publication evidence requires an exact immutable revision",
                    SNAPSHOT_PATH,
                )
            )
        digest = source["content_sha256"]
        if digest is not None and (not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest)):
            failures.append(
                _failure(
                    "related-work-source-pin",
                    f"{source_id}: invalid SHA-256 digest",
                    SNAPSHOT_PATH,
                )
            )
        if source["kind"] == "official-doc" and (not isinstance(source["retrieved_at"], str) or digest is None):
            failures.append(
                _failure(
                    "related-work-source-pin",
                    f"{source_id}: mutable official documentation requires retrieval date and digest",
                    SNAPSHOT_PATH,
                )
            )
        artifact_path = source["artifact_path"]
        if source["kind"] in {"git", "repository-internal"}:
            if not _safe_external_artifact_path(artifact_path):
                failures.append(
                    _failure(
                        "related-work-source-path",
                        f"{source_id}: Git artifact path is missing or unsafe",
                        SNAPSHOT_PATH,
                    )
                )
            elif source["kind"] == "repository-internal" and validate_paths:
                resolved = _resolve_repository_artifact(repo_root, artifact_path)
                if resolved is None or not resolved.exists():
                    failures.append(
                        _failure(
                            "related-work-source-path",
                            f"{source_id}: internal artifact path does not exist",
                            str(artifact_path),
                        )
                    )
        elif artifact_path is not None:
            failures.append(
                _failure(
                    "related-work-source-path",
                    f"{source_id}: non-Git source must not claim a repository artifact path",
                    SNAPSHOT_PATH,
                )
            )
    return source_by_id


def _validate_evidence_refs(
    refs: object,
    *,
    system_id: object,
    source_by_id: Mapping[str, Mapping[str, object]],
    failures: list[PolicyFailure],
    rule_id: str,
    label: str,
) -> None:
    if not isinstance(refs, list) or not refs:
        failures.append(
            _failure(
                rule_id,
                f"{label}: at least one primary-source reference is required",
                SNAPSHOT_PATH,
            )
        )
        return
    for index, raw_ref in enumerate(refs):
        if not _exact_keys(
            raw_ref,
            _EVIDENCE_REF_KEYS,
            failures,
            rule_id=rule_id,
            label=f"{label}.evidence_refs[{index}]",
            path=SNAPSHOT_PATH,
        ):
            continue
        source = source_by_id.get(raw_ref["source_id"])
        if source is None or source.get("primary") is not True:
            failures.append(
                _failure(
                    rule_id,
                    f"{label}: unknown or non-primary source {raw_ref['source_id']!r}",
                    SNAPSHOT_PATH,
                )
            )
        elif source.get("system_id") != system_id:
            failures.append(
                _failure(
                    rule_id,
                    f"{label}: source {raw_ref['source_id']!r} belongs to another system",
                    SNAPSHOT_PATH,
                )
            )
        locator = raw_ref["locator"]
        if not isinstance(locator, str) or not locator.strip() or len(locator) > 500:
            failures.append(
                _failure(
                    rule_id,
                    f"{label}: evidence locator must be bounded and exact",
                    SNAPSHOT_PATH,
                )
            )


def _validate_observations(
    observations: Sequence[object],
    system_ids: set[str],
    axis_ids: set[str],
    source_by_id: Mapping[str, Mapping[str, object]],
    failures: list[PolicyFailure],
) -> dict[tuple[str, str], int | None]:
    scores: dict[tuple[str, str], int | None] = {}
    executable_classes = {"executable"}
    for index, raw_observation in enumerate(observations):
        label = f"observations[{index}]"
        if not _exact_keys(
            raw_observation,
            _OBSERVATION_KEYS,
            failures,
            rule_id="related-work-observation-shape",
            label=label,
            path=SNAPSHOT_PATH,
        ):
            continue
        observation = raw_observation
        system_id = observation["system_id"]
        axis_id = observation["axis_id"]
        key = (system_id, axis_id)
        if system_id not in system_ids or axis_id not in axis_ids:
            failures.append(
                _failure(
                    "related-work-observation-reference",
                    f"{label}: unknown system or axis",
                    SNAPSHOT_PATH,
                )
            )
            continue
        if key in scores:
            failures.append(
                _failure(
                    "related-work-observations-rectangular",
                    f"duplicate observation {key}",
                    SNAPSHOT_PATH,
                )
            )
            continue
        applicability = observation["applicability"]
        score = observation["score"]
        measure = observation["measure"]
        if applicability == "out-of-scope":
            if score is not None or measure != "not-applicable":
                failures.append(
                    _failure(
                        "related-work-observation-score",
                        f"{label}: out-of-scope cells require null score and not-applicable measure",
                        SNAPSHOT_PATH,
                    )
                )
        elif applicability == "applicable":
            if not isinstance(score, int) or score not in _MEASURE_BY_SCORE or measure != _MEASURE_BY_SCORE.get(score):
                failures.append(
                    _failure(
                        "related-work-observation-score",
                        f"{label}: applicable cells require a 0..3 score and matching measure",
                        SNAPSHOT_PATH,
                    )
                )
        else:
            failures.append(
                _failure(
                    "related-work-observation-score",
                    f"{label}: invalid applicability",
                    SNAPSHOT_PATH,
                )
            )
        scores[key] = score if isinstance(score, int) else None
        if not _bounded_text(observation["rationale"]):
            failures.append(
                _failure(
                    "related-work-observation-rationale",
                    f"{label}: a bounded reproducible scoring rationale is required",
                    SNAPSHOT_PATH,
                )
            )
        if not _bounded_text_list(observation["limitations"]):
            failures.append(
                _failure(
                    "related-work-observation-limitations",
                    f"{label}: at least one bounded limitation is required",
                    SNAPSHOT_PATH,
                )
            )
        _validate_evidence_refs(
            observation["evidence_refs"],
            system_id=system_id,
            source_by_id=source_by_id,
            failures=failures,
            rule_id="related-work-observation-evidence",
            label=label,
        )
        if system_id == _HISTORICAL_SYSTEM_ID and axis_id in {
            "concrete-syntax-soundness",
            "implementation-maturity",
        }:
            evidence_classes = {
                source_by_id[ref["source_id"]]["evidence_class"]
                for ref in observation["evidence_refs"]
                if isinstance(ref, dict) and ref.get("source_id") in source_by_id
            }
            if not evidence_classes & executable_classes:
                failures.append(
                    _failure(
                        "related-work-raes-executable-evidence",
                        f"{label}: RAES delivery claims require executable evidence",
                        SNAPSHOT_PATH,
                    )
                )
    expected = {(system_id, axis_id) for system_id in system_ids for axis_id in axis_ids}
    if set(scores) != expected:
        missing = sorted(expected - set(scores))
        unexpected = sorted(set(scores) - expected)
        failures.append(
            _failure(
                "related-work-observations-rectangular",
                f"observations must cover every system × axis cell; missing={missing[:10]}, unexpected={unexpected[:10]}",
                SNAPSHOT_PATH,
            )
        )
    return scores


def _validate_task_observations(
    task_observations: Sequence[object],
    system_ids: set[str],
    case_ids: set[str],
    source_by_id: Mapping[str, Mapping[str, object]],
    failures: list[PolicyFailure],
) -> None:
    seen: set[tuple[str, str]] = set()
    for index, raw_observation in enumerate(task_observations):
        label = f"task_observations[{index}]"
        if not _exact_keys(
            raw_observation,
            _TASK_OBSERVATION_KEYS,
            failures,
            rule_id="related-work-task-observation-shape",
            label=label,
            path=SNAPSHOT_PATH,
        ):
            continue
        observation = raw_observation
        system_id = observation["system_id"]
        case_id = observation["case_id"]
        key = (system_id, case_id)
        if system_id not in system_ids or case_id not in case_ids or key in seen:
            failures.append(
                _failure(
                    "related-work-task-observations-rectangular",
                    f"{label}: unknown or duplicate system/case pair {key}",
                    SNAPSHOT_PATH,
                )
            )
            continue
        seen.add(key)
        if observation["applicability"] not in {"applicable", "out-of-scope"}:
            failures.append(
                _failure(
                    "related-work-task-observation-outcome",
                    f"{label}: invalid applicability",
                    SNAPSHOT_PATH,
                )
            )
        if observation["outcome"] not in {
            "supported",
            "partial",
            "unsupported",
            "not-applicable",
            "not-evaluated",
        }:
            failures.append(
                _failure(
                    "related-work-task-observation-outcome",
                    f"{label}: invalid outcome",
                    SNAPSHOT_PATH,
                )
            )
        if observation["method"] not in {"repository-execution", "source-walkthrough"}:
            failures.append(
                _failure(
                    "related-work-task-observation-outcome",
                    f"{label}: invalid method",
                    SNAPSHOT_PATH,
                )
            )
        if not _bounded_text(observation["rationale"]):
            failures.append(
                _failure(
                    "related-work-task-observation-rationale",
                    f"{label}: a bounded reproducible case rationale is required",
                    SNAPSHOT_PATH,
                )
            )
        if not _bounded_text_list(observation["limitations"]):
            failures.append(
                _failure(
                    "related-work-task-observation-limitations",
                    f"{label}: at least one bounded limitation is required",
                    SNAPSHOT_PATH,
                )
            )
        _validate_evidence_refs(
            observation["evidence_refs"],
            system_id=system_id,
            source_by_id=source_by_id,
            failures=failures,
            rule_id="related-work-task-observation-evidence",
            label=label,
        )
    expected = {(system_id, case_id) for system_id in system_ids for case_id in case_ids}
    if seen != expected:
        failures.append(
            _failure(
                "related-work-task-observations-rectangular",
                f"task observations must cover every system × case pair; missing={sorted(expected - seen)[:10]}",
                SNAPSHOT_PATH,
            )
        )


def _pareto_frontier(
    system_ids: Sequence[str],
    axis_ids: Sequence[str],
    scores: Mapping[tuple[str, str], int | None],
) -> list[str]:
    frontier: list[str] = []
    for candidate in system_ids:
        dominated = False
        for challenger in system_ids:
            if challenger == candidate:
                continue
            candidate_scores = [scores.get((candidate, axis_id)) for axis_id in axis_ids]
            challenger_scores = [scores.get((challenger, axis_id)) for axis_id in axis_ids]
            if any(value is None for value in candidate_scores + challenger_scores):
                continue
            if all(right >= left for left, right in zip(candidate_scores, challenger_scores, strict=True)) and any(
                right > left for left, right in zip(candidate_scores, challenger_scores, strict=True)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier)


def _weighted_totals(
    system_ids: Sequence[str],
    weights: Mapping[str, object],
    scores: Mapping[tuple[str, str], int | None],
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for system_id in system_ids:
        total = 0
        for axis_id, raw_weight in weights.items():
            weight = raw_weight if isinstance(raw_weight, int) else 0
            score = scores.get((system_id, axis_id))
            if score is not None:
                total += score * weight
        totals[system_id] = total
    return totals


def _ranking(totals: Mapping[str, int]) -> list[str]:
    return sorted(totals, key=lambda system_id: (-totals[system_id], system_id))


def _count_word(value: int) -> str:
    return {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
    }.get(value, str(value))


def _expected_claim_derivations(
    system_by_id: Mapping[str, Mapping[str, object]],
    scores: Mapping[tuple[str, str], int | None],
    profile_winner_by_id: Mapping[str, str],
) -> dict[str, dict[str, object]]:
    scope_strata = sorted({str(system["scope_stratum"]) for system in system_by_id.values()})
    scenario_system_ids = sorted(
        system_id for system_id, system in system_by_id.items() if system["scope_stratum"] == "scenario-authoring"
    )
    breadth_scores = {system_id: scores.get((system_id, "expressive-breadth")) for system_id in scenario_system_ids}
    numeric_breadth_scores = [score for score in breadth_scores.values() if isinstance(score, int)]
    max_breadth_score = max(numeric_breadth_scores) if numeric_breadth_scores else None
    breadth_leaders = sorted(system_id for system_id, score in breadth_scores.items() if score == max_breadth_score)

    comparison_specs = [
        ("cacao-v2", "governance-community", _HISTORICAL_SYSTEM_ID),
        ("cyber-fom", "governance-community", _HISTORICAL_SYSTEM_ID),
        ("cyborg", "implementation-maturity", _HISTORICAL_SYSTEM_ID),
        ("ocr-sdl", "implementation-maturity", _HISTORICAL_SYSTEM_ID),
    ]
    comparisons = [
        {
            "axis_id": axis_id,
            "left_system_id": left_system_id,
            "left_score": scores.get((left_system_id, axis_id)),
            "operator": "greater-than",
            "right_system_id": right_system_id,
            "right_score": scores.get((right_system_id, axis_id)),
        }
        for left_system_id, axis_id, right_system_id in comparison_specs
    ]
    all_profile_winners = dict(sorted(profile_winner_by_id.items()))
    selected_profile_winners = {
        profile_id: profile_winner_by_id.get(profile_id)
        for profile_id in (
            "breadth-and-composition",
            "formal-rigor",
            "maturity-and-governance",
        )
    }
    return {
        "no-overall-winner": {
            "kind": "scope-and-sensitivity",
            "scope_strata": scope_strata,
            "profile_winners": all_profile_winners,
            "ranking_reversal_observed": len(set(all_profile_winners.values())) > 1,
        },
        "scope-qualified-breadth": {
            "kind": "axis-maximum",
            "scope_stratum": "scenario-authoring",
            "axis_id": "expressive-breadth",
            "system_scores": breadth_scores,
            "max_score": max_breadth_score,
            "leading_system_ids": breadth_leaders,
        },
        "maturity-governance": {
            "kind": "cell-comparisons",
            "comparisons": comparisons,
        },
        "sensitivity": {
            "kind": "profile-winners",
            "profile_winners": selected_profile_winners,
            "ranking_reversal_observed": len(set(selected_profile_winners.values())) > 1,
        },
    }


def _expected_claim_statement(
    kind: str,
    derivation: Mapping[str, object],
    system_by_id: Mapping[str, Mapping[str, object]],
) -> str:
    def system_name(system_id: object) -> str:
        system = system_by_id.get(str(system_id), {})
        name = system.get("name")
        return name if isinstance(name, str) else str(system_id)

    if kind == "no-overall-winner":
        scope_count = len(derivation["scope_strata"])
        profile_count = len(derivation["profile_winners"])
        return (
            f"No overall winner is supported: the {_count_word(scope_count)} declared scope strata are analyzed "
            f"separately, and the scenario-authoring first-ranked system changes across the "
            f"{_count_word(profile_count)} declared weight profiles."
        )
    if kind == "scope-qualified-breadth":
        system_scores = derivation["system_scores"]
        leaders = derivation["leading_system_ids"]
        leader_name = system_name(leaders[0]) if isinstance(leaders, list) and len(leaders) == 1 else "No system"
        return (
            f"Within the {_count_word(len(system_scores))}-system scenario-authoring stratum and this frozen "
            f"rubric, {leader_name} is the sole expressive-breadth leader at level {derivation['max_score']}. "
            "This is the broadest combined surface observed in this corpus; `highest quality` is not supported, "
            "and standardization or maturity do not follow from breadth."
        )
    if kind == "maturity-governance":
        comparisons = {
            comparison["left_system_id"]: comparison
            for comparison in derivation["comparisons"]
            if isinstance(comparison, dict)
        }
        historical_level = comparisons["cacao-v2"]["right_score"]
        return (
            f"Against {system_name(_HISTORICAL_SYSTEM_ID)}'s recorded level {historical_level}, "
            f"{system_name('cacao-v2')} and "
            f"{system_name('cyber-fom')} each record level {comparisons['cacao-v2']['left_score']} for governance "
            f"and community, while {system_name('cyborg')} records level {comparisons['cyborg']['left_score']} "
            f"and {system_name('ocr-sdl')} level {comparisons['ocr-sdl']['left_score']} for implementation "
            "maturity. These are axis-specific evidence comparisons, not cross-scope overall rankings or "
            "adoption claims."
        )
    if kind == "sensitivity":
        winners = derivation["profile_winners"]
        return (
            "Across the declared scenario-authoring profiles, breadth and composition ranks "
            f"{system_name(winners['breadth-and-composition'])} first, formal rigor ranks "
            f"{system_name(winners['formal-rigor'])} first, and maturity and governance ranks "
            f"{system_name(winners['maturity-and-governance'])} first; this observed reversal prohibits a "
            "weight-independent winner claim."
        )
    return ""


def _validate_claim_evidence_gate(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    analysis: Mapping[str, object],
    raw_claim: Mapping[str, object],
    label: str,
    failures: list[PolicyFailure],
) -> None:
    issues: list[str] = []
    status = raw_claim["evidence_status"]
    if not isinstance(status, str) or status not in _CLAIM_EVIDENCE_STATUSES:
        issues.append(f"unknown ADR-021 evidence status {status!r}")
    elif status != "partial":
        issues.append("corpus-bounded public claims must retain evidence_status='partial'")
    if not _bounded_text_list(raw_claim["threats_to_validity"]):
        issues.append("threats_to_validity must be a non-empty bounded text list")

    falsification = raw_claim["falsification"]
    if not isinstance(falsification, dict) or set(falsification) != _FALSIFICATION_KEYS:
        issues.append(f"falsification fields must exactly match {sorted(_FALSIFICATION_KEYS)}")
    else:
        if not _bounded_text(falsification["protocol"]):
            issues.append("falsification protocol must be non-empty bounded text")
        for field in ("objective_pass_criteria", "objective_fail_criteria"):
            if not _bounded_text_list(falsification[field]):
                issues.append(f"{field} must be a non-empty bounded text list")
        allowed = falsification["allowed_evidence_classes"]
        disallowed = falsification["disallowed_evidence_classes"]
        if not _bounded_text_list(allowed) or not _bounded_text_list(disallowed):
            issues.append("allowed and disallowed evidence classes must be non-empty bounded text lists")
        else:
            allowed_set = set(allowed)
            disallowed_set = set(disallowed)
            source_classes = {
                source.get("evidence_class")
                for source in snapshot.get("sources", [])
                if isinstance(source, dict) and isinstance(source.get("evidence_class"), str)
            }
            if not source_classes.issubset(allowed_set):
                issues.append(f"allowed evidence omits frozen source classes {sorted(source_classes - allowed_set)}")
            if allowed_set & disallowed_set:
                issues.append("allowed and disallowed evidence classes overlap")
        expected_artifacts = [
            protocol.get("revision"),
            snapshot.get("snapshot_id"),
            analysis.get("analysis_id"),
        ]
        if falsification["evidence_artifact_refs"] != expected_artifacts:
            issues.append(f"named evidence artifacts must exactly match {expected_artifacts}")
    if issues:
        failures.append(
            _failure(
                "related-work-claim-evidence-gate",
                f"{label}: " + "; ".join(issues),
                ANALYSIS_PATH,
            )
        )


def _validate_analysis(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    analysis: Mapping[str, object],
    system_by_id: Mapping[str, Mapping[str, object]],
    axis_ids: set[str],
    scores: Mapping[tuple[str, str], int | None],
    failures: list[PolicyFailure],
) -> None:
    if not _exact_keys(
        analysis,
        _ANALYSIS_KEYS,
        failures,
        rule_id="related-work-analysis-shape",
        label="analysis",
        path=ANALYSIS_PATH,
    ):
        return
    if analysis["protocol_revision"] != protocol.get("revision") or analysis["snapshot_id"] != snapshot.get(
        "snapshot_id"
    ):
        failures.append(
            _failure(
                "related-work-analysis-join",
                "analysis does not identify the loaded protocol and snapshot",
                ANALYSIS_PATH,
            )
        )
    pareto_groups = _bounded_list(
        analysis["pareto_groups"],
        _MAX_SYSTEMS,
        failures,
        rule_id="related-work-pareto-shape",
        label="pareto_groups",
        path=ANALYSIS_PATH,
    )
    for index, raw_group in enumerate(pareto_groups):
        label = f"pareto_groups[{index}]"
        if not _exact_keys(
            raw_group,
            _PARETO_KEYS,
            failures,
            rule_id="related-work-pareto-shape",
            label=label,
            path=ANALYSIS_PATH,
        ):
            continue
        system_ids = raw_group["system_ids"]
        group_axis_ids = raw_group["axis_ids"]
        if not isinstance(system_ids, list) or not isinstance(group_axis_ids, list):
            failures.append(
                _failure(
                    "related-work-pareto-shape",
                    f"{label}: ids must be lists",
                    ANALYSIS_PATH,
                )
            )
            continue
        if any(system_id not in system_by_id for system_id in system_ids) or any(
            axis_id not in axis_ids for axis_id in group_axis_ids
        ):
            failures.append(
                _failure(
                    "related-work-pareto-shape",
                    f"{label}: unknown system or axis",
                    ANALYSIS_PATH,
                )
            )
            continue
        if any(system_by_id[system_id]["scope_stratum"] != raw_group["scope_stratum"] for system_id in system_ids):
            failures.append(
                _failure(
                    "related-work-pareto-scope",
                    f"{label}: mixed scope strata",
                    ANALYSIS_PATH,
                )
            )
        if any(scores.get((system_id, axis_id)) is None for system_id in system_ids for axis_id in group_axis_ids):
            failures.append(
                _failure(
                    "related-work-pareto-scope",
                    f"{label}: includes out-of-scope cells",
                    ANALYSIS_PATH,
                )
            )
            continue
        expected_frontier = _pareto_frontier(system_ids, group_axis_ids, scores)
        if raw_group["frontier_system_ids"] != expected_frontier:
            failures.append(
                _failure(
                    "related-work-pareto-drift",
                    f"{label}: recorded frontier does not match {expected_frontier}",
                    ANALYSIS_PATH,
                )
            )

    profiles = _bounded_list(
        analysis["weight_profiles"],
        _MAX_CASES,
        failures,
        rule_id="related-work-weight-shape",
        label="weight_profiles",
        path=ANALYSIS_PATH,
    )
    profile_ids: list[str] = []
    winners: list[str] = []
    profile_winner_by_id: dict[str, str] = {}
    for index, raw_profile in enumerate(profiles):
        label = f"weight_profiles[{index}]"
        if not _exact_keys(
            raw_profile,
            _WEIGHT_PROFILE_KEYS,
            failures,
            rule_id="related-work-weight-shape",
            label=label,
            path=ANALYSIS_PATH,
        ):
            continue
        profile_id = raw_profile["profile_id"]
        profile_ids.append(profile_id)
        weights = raw_profile["weights"]
        if (
            not isinstance(weights, dict)
            or set(weights) != axis_ids
            or any(not isinstance(weight, int) or weight < 0 or weight > 10 for weight in weights.values())
        ):
            failures.append(
                _failure(
                    "related-work-weight-shape",
                    f"{label}: weights must cover all axes with bounded non-negative integers",
                    ANALYSIS_PATH,
                )
            )
            continue
        if not any(weights.values()):
            failures.append(
                _failure(
                    "related-work-weight-shape",
                    f"{label}: at least one weight is required",
                    ANALYSIS_PATH,
                )
            )
            continue
        systems = sorted(
            system_id
            for system_id, system in system_by_id.items()
            if system["scope_stratum"] == raw_profile["scope_stratum"]
        )
        expected_totals = _weighted_totals(systems, weights, scores)
        expected_ranking = _ranking(expected_totals)
        if raw_profile["totals"] != expected_totals or raw_profile["ranking"] != expected_ranking:
            failures.append(
                _failure(
                    "related-work-weight-drift",
                    f"{label}: totals/ranking do not match recomputation",
                    ANALYSIS_PATH,
                )
            )
        if expected_ranking:
            winners.append(expected_ranking[0])
            profile_winner_by_id[profile_id] = expected_ranking[0]

    sensitivity = analysis["sensitivity"]
    if _exact_keys(
        sensitivity,
        _SENSITIVITY_KEYS,
        failures,
        rule_id="related-work-sensitivity-shape",
        label="sensitivity",
        path=ANALYSIS_PATH,
    ):
        expected_winners = sorted(set(winners))
        reversal = len(expected_winners) > 1
        if (
            sensitivity["profile_ids"] != profile_ids
            or sensitivity["winning_systems"] != expected_winners
            or sensitivity["ranking_reversal_observed"] is not reversal
        ):
            failures.append(
                _failure(
                    "related-work-sensitivity-drift",
                    "sensitivity record hides or misstates recomputed profile reversals",
                    ANALYSIS_PATH,
                )
            )

    claims = _bounded_list(
        analysis["claims"],
        _MAX_CASES,
        failures,
        rule_id="related-work-claim-shape",
        label="claims",
        path=ANALYSIS_PATH,
    )
    expected_derivations = _expected_claim_derivations(system_by_id, scores, profile_winner_by_id)
    claim_kinds: set[str] = set()
    claim_ids: set[str] = set()
    for index, raw_claim in enumerate(claims):
        label = f"claims[{index}]"
        if not _exact_keys(
            raw_claim,
            _CLAIM_KEYS,
            failures,
            rule_id="related-work-claim-shape",
            label=label,
            path=ANALYSIS_PATH,
        ):
            continue
        claim_id = raw_claim["claim_id"]
        kind = raw_claim["kind"]
        if not _valid_id(claim_id) or claim_id in claim_ids:
            failures.append(
                _failure(
                    "related-work-claim-shape",
                    f"{label}: claim_id must be unique and use the closed id grammar",
                    ANALYSIS_PATH,
                )
            )
        else:
            claim_ids.add(claim_id)
        if not isinstance(kind, str) or kind not in expected_derivations:
            failures.append(
                _failure(
                    "related-work-claim-shape",
                    f"{label}: unknown claim kind {kind!r}",
                    ANALYSIS_PATH,
                )
            )
            continue
        claim_kinds.add(kind)
        statement = raw_claim["statement"]
        if not isinstance(statement, str):
            failures.append(
                _failure(
                    "related-work-claim-shape",
                    f"{label}: statement must be text",
                    ANALYSIS_PATH,
                )
            )
            continue
        _validate_claim_evidence_gate(protocol, snapshot, analysis, raw_claim, label, failures)

        raw_derivation = raw_claim["derivation"]
        expected_derivation = expected_derivations[kind]
        expected_derivation_keys = _CLAIM_DERIVATION_KEYS[kind]
        if not isinstance(raw_derivation, dict) or set(raw_derivation) != expected_derivation_keys:
            failures.append(
                _failure(
                    "related-work-claim-derivation",
                    f"{label}: derivation fields must exactly match {sorted(expected_derivation_keys)}",
                    ANALYSIS_PATH,
                )
            )
        elif raw_derivation != expected_derivation:
            failures.append(
                _failure(
                    "related-work-claim-derivation",
                    f"{label}: derivation does not match recomputed observations and profiles",
                    ANALYSIS_PATH,
                )
            )

        expected_statement = _expected_claim_statement(kind, expected_derivation, system_by_id)
        if statement != expected_statement:
            failures.append(
                _failure(
                    "related-work-claim-derivation",
                    f"{label}: statement is not the canonical rendering of its recomputed derivation",
                    ANALYSIS_PATH,
                )
            )

        expected_system_ids: set[str]
        expected_axis_ids: set[str]
        if kind == "no-overall-winner":
            expected_system_ids = set(system_by_id)
            expected_axis_ids = set(axis_ids)
        elif kind == "scope-qualified-breadth":
            expected_system_ids = set(expected_derivation["system_scores"])
            expected_axis_ids = {str(expected_derivation["axis_id"])}
        elif kind == "maturity-governance":
            comparisons = expected_derivation["comparisons"]
            expected_system_ids = {
                str(comparison[field]) for comparison in comparisons for field in ("left_system_id", "right_system_id")
            }
            expected_axis_ids = {str(comparison["axis_id"]) for comparison in comparisons}
        else:
            profile_winners = expected_derivation["profile_winners"]
            expected_system_ids = {str(system_id) for system_id in profile_winners.values()}
            expected_axis_ids = set(axis_ids)
        raw_system_ids = raw_claim["system_ids"]
        raw_axis_ids = raw_claim["axis_ids"]
        valid_raw_system_ids = isinstance(raw_system_ids, list) and all(
            isinstance(system_id, str) for system_id in raw_system_ids
        )
        valid_raw_axis_ids = isinstance(raw_axis_ids, list) and all(
            isinstance(axis_id, str) for axis_id in raw_axis_ids
        )
        if (
            not valid_raw_system_ids
            or len(raw_system_ids) != len(set(raw_system_ids))
            or set(raw_system_ids) != expected_system_ids
            or not valid_raw_axis_ids
            or len(raw_axis_ids) != len(set(raw_axis_ids))
            or set(raw_axis_ids) != expected_axis_ids
        ):
            failures.append(
                _failure(
                    "related-work-claim-derivation",
                    f"{label}: declared systems and axes do not match the recomputed derivation",
                    ANALYSIS_PATH,
                )
            )
        folded = statement.casefold()
        if "highest quality" in folded and "not supported" not in folded:
            failures.append(
                _failure(
                    "related-work-claim-overreach",
                    f"{label}: highest-quality claim is not supported",
                    ANALYSIS_PATH,
                )
            )
    required_claim_kinds = {
        "no-overall-winner",
        "scope-qualified-breadth",
        "maturity-governance",
        "sensitivity",
    }
    if not required_claim_kinds.issubset(claim_kinds):
        failures.append(
            _failure(
                "related-work-claim-coverage",
                f"claims must distinguish {sorted(required_claim_kinds)}",
                ANALYSIS_PATH,
            )
        )


def _display_score(score: int | None) -> str:
    return "oos" if score is None else str(score)


def _current_project_name(value: str) -> str:
    """Render frozen predecessor evidence with the current RAES project name."""

    predecessor_name = "A" + "CES"
    return re.sub(rf"\b{predecessor_name}\b", "RAES", value)


def render_publication(
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    analysis: Mapping[str, object],
) -> str:
    """Render the mechanically checked reader-facing matrix and bounded conclusions."""

    systems = protocol["systems"]
    axes = protocol["axes"]
    observations = snapshot["observations"]
    score_by_key = {(item["system_id"], item["axis_id"]): item["score"] for item in observations}
    system_ids = [system["system_id"] for system in systems]
    system_name_by_id = {system["system_id"]: _current_project_name(system["name"]) for system in systems}
    lines = [
        PUBLICATION_START,
        f"Frozen snapshot: `{snapshot['snapshot_id']}` under protocol `{protocol['revision']}`.",
        "Scores are axis-specific ordinal evidence levels: 0 absent, 1 limited, 2 substantial, 3 strong;",
        "`oos` means the axis is outside the system's declared scope and is never treated as zero.",
        "",
        "| Axis | " + " | ".join(_current_project_name(system["name"]) for system in systems) + " |",
        "| --- | " + " | ".join("---" for _ in systems) + " |",
    ]
    for axis in axes:
        cells = [_display_score(score_by_key.get((system_id, axis["axis_id"]))) for system_id in system_ids]
        lines.append(f"| {axis['label']} | " + " | ".join(cells) + " |")
    lines.extend(["", "### Evidence-bounded findings", ""])
    for claim in analysis["claims"]:
        lines.append(
            f"- **{claim['kind'].replace('-', ' ').title()}.** Evidence status: "
            f"`{claim['evidence_status']}`. {_current_project_name(claim['statement'])}"
        )
    lines.extend(["", "### Sensitivity of scenario-authoring rankings", ""])
    lines.append("| Weight profile | First-ranked system | Recorded totals |")
    lines.append("| --- | --- | --- |")
    for profile in analysis["weight_profiles"]:
        totals = ", ".join(
            f"{system_name_by_id[system_id]}={profile['totals'][system_id]}" for system_id in profile["ranking"]
        )
        lines.append(f"| `{profile['profile_id']}` | {system_name_by_id[profile['ranking'][0]]} | {totals} |")
    lines.extend(["", "### RAES delivery limits retained in the matrix", ""])
    axis_by_id = {axis["axis_id"]: axis["label"] for axis in axes}
    for observation in observations:
        if observation["system_id"] != _HISTORICAL_SYSTEM_ID or observation["score"] == 3:
            continue
        limitation = observation["limitations"][0] if observation["limitations"] else observation["rationale"]
        lines.append(
            f"- **{axis_by_id[observation['axis_id']]} ({_display_score(observation['score'])}).** {limitation}"
        )
    lines.extend(
        [
            "",
            "Cell rationales, exact source locators, task walkthroughs, and source digests are in the",
            "[frozen extraction snapshot](../../research/related-work-comparison/extraction-snapshot-2026-07-13.json).",
            PUBLICATION_END,
        ]
    )
    return "\n".join(lines)


def _validate_publication(
    repo_root: Path,
    protocol: Mapping[str, object],
    snapshot: Mapping[str, object],
    analysis: Mapping[str, object],
    failures: list[PolicyFailure],
) -> None:
    path = safe_repo_path(repo_root, PUBLICATION_PATH)
    prose = path.read_text(encoding="utf-8") if path is not None and path.is_file() else ""
    expected = render_publication(protocol, snapshot, analysis)
    if expected not in prose:
        failures.append(
            _failure(
                "related-work-publication-drift",
                "reader-facing matrix and conclusions do not match the frozen bundle",
                PUBLICATION_PATH,
            )
        )


def validate_bundle(
    repo_root: Path,
    protocol: dict[str, object],
    snapshot: dict[str, object],
    analysis: dict[str, object],
    *,
    validate_paths: bool = True,
) -> list[PolicyFailure]:
    """Validate closed shapes, joins, evidence, analysis recomputation, and publication parity."""

    failures: list[PolicyFailure] = []
    if not _exact_keys(
        protocol,
        _PROTOCOL_KEYS,
        failures,
        rule_id="related-work-protocol-shape",
        label="protocol",
        path=PROTOCOL_PATH,
    ):
        return failures
    strata = _bounded_list(
        protocol["scope_strata"],
        _MAX_SYSTEMS,
        failures,
        rule_id="related-work-protocol-shape",
        label="scope_strata",
        path=PROTOCOL_PATH,
    )
    systems = _bounded_list(
        protocol["systems"],
        _MAX_SYSTEMS,
        failures,
        rule_id="related-work-protocol-shape",
        label="systems",
        path=PROTOCOL_PATH,
    )
    axes = _bounded_list(
        protocol["axes"],
        _MAX_AXES,
        failures,
        rule_id="related-work-protocol-shape",
        label="axes",
        path=PROTOCOL_PATH,
    )
    cases = _bounded_list(
        protocol["cases"],
        _MAX_CASES,
        failures,
        rule_id="related-work-protocol-shape",
        label="cases",
        path=PROTOCOL_PATH,
    )
    stratum_ids = _record_ids(
        strata,
        "stratum_id",
        failures,
        rule_id="related-work-protocol-id",
        label="scope stratum",
        path=PROTOCOL_PATH,
    )
    system_ids = _record_ids(
        systems,
        "system_id",
        failures,
        rule_id="related-work-protocol-id",
        label="system",
        path=PROTOCOL_PATH,
    )
    axis_ids = _record_ids(
        axes,
        "axis_id",
        failures,
        rule_id="related-work-protocol-id",
        label="axis",
        path=PROTOCOL_PATH,
    )
    case_ids = _record_ids(
        cases,
        "case_id",
        failures,
        rule_id="related-work-protocol-id",
        label="case",
        path=PROTOCOL_PATH,
    )
    if axis_ids != EXPECTED_AXIS_IDS:
        failures.append(
            _failure(
                "related-work-axis-set",
                f"protocol axes must exactly match {sorted(EXPECTED_AXIS_IDS)}; got {sorted(axis_ids)}",
                PROTOCOL_PATH,
            )
        )
    for index, stratum in enumerate(strata):
        _exact_keys(
            stratum,
            _STRATUM_KEYS,
            failures,
            rule_id="related-work-protocol-shape",
            label=f"scope_strata[{index}]",
            path=PROTOCOL_PATH,
        )
    system_by_id: dict[str, Mapping[str, object]] = {}
    for index, raw_system in enumerate(systems):
        if not _exact_keys(
            raw_system,
            _SYSTEM_KEYS,
            failures,
            rule_id="related-work-protocol-shape",
            label=f"systems[{index}]",
            path=PROTOCOL_PATH,
        ):
            continue
        system_by_id[raw_system["system_id"]] = raw_system
        if raw_system["scope_stratum"] not in stratum_ids:
            failures.append(
                _failure(
                    "related-work-system-stratum",
                    f"{raw_system['system_id']}: unknown scope stratum",
                    PROTOCOL_PATH,
                )
            )
        name = raw_system["name"]
        if not isinstance(name, str) or "/" in name or name.endswith("*"):
            failures.append(
                _failure(
                    "related-work-composite-system",
                    f"{raw_system['system_id']}: system identities must not be composite",
                    PROTOCOL_PATH,
                )
            )
    for index, raw_axis in enumerate(axes):
        if not _exact_keys(
            raw_axis,
            _AXIS_KEYS,
            failures,
            rule_id="related-work-protocol-shape",
            label=f"axes[{index}]",
            path=PROTOCOL_PATH,
        ):
            continue
        if (
            raw_axis["direction"] != "higher-is-stronger-evidence"
            or not isinstance(raw_axis["rubric"], dict)
            or set(raw_axis["rubric"]) != {"0", "1", "2", "3"}
        ):
            failures.append(
                _failure(
                    "related-work-axis-rubric",
                    f"{raw_axis['axis_id']}: invalid ordinal rubric",
                    PROTOCOL_PATH,
                )
            )
    case_kinds: set[str] = set()
    for index, raw_case in enumerate(cases):
        if not _exact_keys(
            raw_case,
            _CASE_KEYS,
            failures,
            rule_id="related-work-protocol-shape",
            label=f"cases[{index}]",
            path=PROTOCOL_PATH,
        ):
            continue
        case_kinds.add(raw_case["kind"])
        _exact_keys(
            raw_case["criteria"],
            _CASE_CRITERIA_KEYS,
            failures,
            rule_id="related-work-protocol-shape",
            label=f"cases[{index}].criteria",
            path=PROTOCOL_PATH,
        )
    if not {"authoring-task", "negative-case"}.issubset(case_kinds):
        failures.append(
            _failure(
                "related-work-case-coverage",
                "protocol requires representative authoring tasks and negative cases",
                PROTOCOL_PATH,
            )
        )
    _exact_keys(
        protocol["analysis_rules"],
        _ANALYSIS_RULE_KEYS,
        failures,
        rule_id="related-work-protocol-shape",
        label="analysis_rules",
        path=PROTOCOL_PATH,
    )
    if not isinstance(protocol["amendment_log"], list):
        failures.append(
            _failure(
                "related-work-protocol-shape",
                "amendment_log must be a list",
                PROTOCOL_PATH,
            )
        )

    if not _exact_keys(
        snapshot,
        _SNAPSHOT_KEYS,
        failures,
        rule_id="related-work-snapshot-shape",
        label="snapshot",
        path=SNAPSHOT_PATH,
    ):
        return failures
    if snapshot["protocol_revision"] != protocol["revision"]:
        failures.append(
            _failure(
                "related-work-snapshot-join",
                "snapshot protocol revision mismatch",
                SNAPSHOT_PATH,
            )
        )
    sources = _bounded_list(
        snapshot["sources"],
        _MAX_SOURCES,
        failures,
        rule_id="related-work-snapshot-shape",
        label="sources",
        path=SNAPSHOT_PATH,
    )
    observations = _bounded_list(
        snapshot["observations"],
        _MAX_OBSERVATIONS,
        failures,
        rule_id="related-work-snapshot-shape",
        label="observations",
        path=SNAPSHOT_PATH,
    )
    task_observations = _bounded_list(
        snapshot["task_observations"],
        _MAX_OBSERVATIONS,
        failures,
        rule_id="related-work-snapshot-shape",
        label="task_observations",
        path=SNAPSHOT_PATH,
    )
    source_by_id = _validate_sources(repo_root, sources, system_ids, failures, validate_paths=validate_paths)
    scores = _validate_observations(observations, system_ids, axis_ids, source_by_id, failures)
    _validate_task_observations(task_observations, system_ids, case_ids, source_by_id, failures)
    _validate_analysis(protocol, snapshot, analysis, system_by_id, axis_ids, scores, failures)
    _validate_publication(repo_root, protocol, snapshot, analysis, failures)
    return failures


def evaluate(repo_root: Path = REPO_ROOT) -> list[PolicyFailure]:
    try:
        protocol, snapshot, analysis = load_bundle(repo_root)
    except (OSError, InvalidInputError) as exc:
        return [_failure("related-work-bundle-invalid", str(exc))]
    return validate_bundle(repo_root, protocol, snapshot, analysis)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit failures as JSON")
    parser.add_argument(
        "--render-publication",
        action="store_true",
        help="Print the expected generated publication block",
    )
    args = parser.parse_args()
    try:
        protocol, snapshot, analysis = load_bundle(REPO_ROOT)
    except (OSError, InvalidInputError) as exc:
        failures = [_failure("related-work-bundle-invalid", str(exc))]
    else:
        if args.render_publication:
            print(render_publication(protocol, snapshot, analysis))
            return 0
        failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)
    if args.json:
        print(json.dumps([failure.__dict__ for failure in failures], indent=2, sort_keys=True))
    else:
        for failure in failures:
            print(failure.render())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
