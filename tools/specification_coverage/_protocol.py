"""Preregistered-protocol validation for the specification-coverage bundle."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.policy.common import PolicyFailure, safe_repo_path
from tools.specification_coverage._keys import (
    _CARRIER_KEYS,
    _EXECUTION_RULE_KEYS,
    _PROTOCOL_KEYS,
    _REQUEST_KEYS,
    _SHA256_RE,
    _SOURCE_KEYS,
    _STAGE_KEYS,
    _STRATUM_KEYS,
    EXPECTED_CLASSIFICATIONS,
    EXPECTED_STRATA,
    PROTOCOL_PATH,
)
from tools.specification_coverage._primitives import (
    _bounded_list,
    _bounded_text,
    _exact_keys,
    _failure,
    _hashable,
    _member,
    _record_ids,
    _sha256,
    _valid_id,
    _validate_https_locator,
)
from tools.specification_coverage._protocol_concepts import (
    _request_concept_join_failures,
    _validated_concepts,
)

_HEADER_TEXT_FIELDS = (
    "protocol_id",
    "revision",
    "registered_at",
    "title",
    "claim",
    "research_question",
    "objective_pass_criteria",
    "objective_fail_criteria",
)


def _protocol_header_failures(protocol: dict[str, object], failures: list[PolicyFailure], path: str) -> None:
    for field in _HEADER_TEXT_FIELDS:
        if not _bounded_text(protocol.get(field)):
            failures.append(_failure("specification-coverage-protocol-shape", f"{field} is invalid", path))
    classification_rules = protocol.get("classification_rules")
    if not isinstance(classification_rules, dict) or set(classification_rules) != EXPECTED_CLASSIFICATIONS:
        failures.append(
            _failure(
                "specification-coverage-classifications",
                f"classification rules must be exactly {sorted(EXPECTED_CLASSIFICATIONS)}",
                path,
            )
        )


def _validated_strata(
    protocol: dict[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> tuple[list[object], set[str]]:
    strata = _bounded_list(
        protocol.get("coverage_strata"),
        failures,
        rule_id="specification-coverage-strata",
        label="coverage_strata",
        path=path,
    )
    for index, stratum in enumerate(strata):
        _exact_keys(
            stratum,
            _STRATUM_KEYS,
            failures,
            rule_id="specification-coverage-strata",
            label=f"coverage_strata[{index}]",
            path=path,
        )
    stratum_ids = _record_ids(
        strata,
        "stratum_id",
        failures,
        rule_id="specification-coverage-strata",
        label="coverage_strata",
        path=path,
    )
    if stratum_ids != EXPECTED_STRATA:
        failures.append(
            _failure(
                "specification-coverage-strata",
                f"coverage strata must be exactly {sorted(EXPECTED_STRATA)}; got {sorted(stratum_ids)}",
                path,
            )
        )
    return strata, stratum_ids


def _validated_stage_ids(protocol: dict[str, object], failures: list[PolicyFailure], path: str) -> set[str]:
    stages = _bounded_list(
        protocol.get("artifact_stages"),
        failures,
        rule_id="specification-coverage-stage-catalog",
        label="artifact_stages",
        path=path,
    )
    for index, stage in enumerate(stages):
        _exact_keys(
            stage,
            _STAGE_KEYS,
            failures,
            rule_id="specification-coverage-stage-catalog",
            label=f"artifact_stages[{index}]",
            path=path,
        )
    return _record_ids(
        stages,
        "stage_id",
        failures,
        rule_id="specification-coverage-stage-catalog",
        label="artifact_stages",
        path=path,
    )


def _source_entry_failures(
    repo_root: Path,
    source: dict[str, object],
    stratum_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if not _member(source.get("stratum_id"), stratum_ids):
        failures.append(_failure("specification-coverage-sources", "source has unknown stratum", path))
    if not _validate_https_locator(source.get("locator")):
        failures.append(
            _failure(
                "specification-coverage-source-locator",
                f"source {source.get('source_id')!r} has an unsafe or secret-bearing locator",
                path,
            )
        )
    sha = source.get("content_sha256")
    if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha):
        failures.append(_failure("specification-coverage-sources", "source digest is invalid", path))
    _source_artifact_failures(repo_root, source, sha, failures, path)


def _source_artifact_failures(
    repo_root: Path,
    source: dict[str, object],
    sha: object,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    artifact_path = source.get("artifact_path")
    if artifact_path is None:
        return
    resolved = safe_repo_path(repo_root, artifact_path) if isinstance(artifact_path, str) else None
    if resolved is None or not resolved.is_file():
        failures.append(
            _failure(
                "specification-coverage-source-path",
                "source path is unsafe or missing",
                path,
            )
        )
    elif isinstance(sha, str) and _SHA256_RE.fullmatch(sha) and _sha256(resolved) != sha:
        failures.append(
            _failure(
                "specification-coverage-source-digest",
                "source digest is stale",
                artifact_path,
            )
        )


def _validated_sources(
    repo_root: Path,
    protocol: dict[str, object],
    stratum_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> tuple[list[object], set[str]]:
    sources = _bounded_list(
        protocol.get("sources"),
        failures,
        rule_id="specification-coverage-sources",
        label="sources",
        path=path,
    )
    for index, source in enumerate(sources):
        if _exact_keys(
            source,
            _SOURCE_KEYS,
            failures,
            rule_id="specification-coverage-sources",
            label=f"sources[{index}]",
            path=path,
        ):
            _source_entry_failures(repo_root, source, stratum_ids, failures, path)
    source_ids = _record_ids(
        sources,
        "source_id",
        failures,
        rule_id="specification-coverage-sources",
        label="sources",
        path=path,
    )
    return sources, source_ids


def _stratum_floor_failures(
    strata: list[object],
    sources: list[object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    counts = Counter(
        source.get("stratum_id")
        for source in sources
        if isinstance(source, dict) and _hashable(source.get("stratum_id"))
    )
    for stratum in strata:
        if not isinstance(stratum, dict):
            continue
        minimum = stratum.get("minimum_sources")
        stratum_id = stratum.get("stratum_id")
        count = counts[stratum_id] if _hashable(stratum_id) else 0
        if not isinstance(minimum, int) or minimum < 1 or count < minimum:
            failures.append(
                _failure(
                    "specification-coverage-strata",
                    f"stratum {stratum.get('stratum_id')!r} does not meet its source floor",
                    path,
                )
            )


def _request_entry_failures(
    request: dict[str, object],
    sources: list[object],
    source_ids: set[str],
    stratum_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    refs = request.get("source_refs")
    if not isinstance(refs, list) or not refs or not all(_member(ref, source_ids) for ref in refs):
        failures.append(
            _failure(
                "specification-coverage-requests",
                "request source refs are invalid",
                path,
            )
        )
    if not _member(request.get("stratum_id"), stratum_ids):
        failures.append(
            _failure(
                "specification-coverage-requests",
                "request has unknown stratum",
                path,
            )
        )
    _request_source_mismatch_failures(request, refs, sources, failures, path)


def _request_source_mismatch_failures(
    request: dict[str, object],
    refs: object,
    sources: list[object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    for ref in refs if isinstance(refs, list) else []:
        source = next(
            (item for item in sources if isinstance(item, dict) and item.get("source_id") == ref),
            None,
        )
        if source is not None and source.get("stratum_id") != request.get("stratum_id"):
            failures.append(
                _failure(
                    "specification-coverage-requests",
                    "request/source stratum mismatch",
                    path,
                )
            )


def _validated_requests(
    protocol: dict[str, object],
    sources: list[object],
    source_ids: set[str],
    stratum_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> tuple[list[object], set[str]]:
    requests = _bounded_list(
        protocol.get("requests"),
        failures,
        rule_id="specification-coverage-requests",
        label="requests",
        path=path,
    )
    for index, request in enumerate(requests):
        if _exact_keys(
            request,
            _REQUEST_KEYS,
            failures,
            rule_id="specification-coverage-requests",
            label=f"requests[{index}]",
            path=path,
        ):
            _request_entry_failures(request, sources, source_ids, stratum_ids, failures, path)
    request_ids = _record_ids(
        requests,
        "request_id",
        failures,
        rule_id="specification-coverage-requests",
        label="requests",
        path=path,
    )
    return requests, request_ids


def _validated_carriers(
    protocol: dict[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> tuple[set[str], dict[str, dict[str, object]]]:
    carriers = _bounded_list(
        protocol.get("carriers"),
        failures,
        rule_id="specification-coverage-carriers",
        label="carriers",
        path=path,
    )
    for index, carrier in enumerate(carriers):
        _exact_keys(
            carrier,
            _CARRIER_KEYS,
            failures,
            rule_id="specification-coverage-carriers",
            label=f"carriers[{index}]",
            path=path,
        )
    carrier_ids = _record_ids(
        carriers,
        "carrier_id",
        failures,
        rule_id="specification-coverage-carriers",
        label="carriers",
        path=path,
    )
    carriers_by_id = {
        item["carrier_id"]: item for item in carriers if isinstance(item, dict) and _valid_id(item.get("carrier_id"))
    }
    return carrier_ids, carriers_by_id


def _execution_rule_failures(protocol: dict[str, object], failures: list[PolicyFailure], path: str) -> None:
    rules = protocol.get("execution_rules")
    if (
        _exact_keys(
            rules,
            _EXECUTION_RULE_KEYS,
            failures,
            rule_id="specification-coverage-execution-rules",
            label="execution_rules",
            path=path,
        )
        and rules.get("normal_execution_network_access") is not False
    ):
        failures.append(
            _failure(
                "specification-coverage-execution-rules",
                "normal execution must be offline",
                path,
            )
        )


def _validate_protocol(
    repo_root: Path,
    protocol: dict[str, object],
    failures: list[PolicyFailure],
) -> dict[str, object]:
    path = PROTOCOL_PATH
    if not _exact_keys(
        protocol,
        _PROTOCOL_KEYS,
        failures,
        rule_id="specification-coverage-protocol-shape",
        label="protocol",
        path=path,
    ):
        return {}
    _protocol_header_failures(protocol, failures, path)
    strata, stratum_ids = _validated_strata(protocol, failures, path)
    stage_ids = _validated_stage_ids(protocol, failures, path)
    sources, source_ids = _validated_sources(repo_root, protocol, stratum_ids, failures, path)
    _stratum_floor_failures(strata, sources, failures, path)
    requests, request_ids = _validated_requests(protocol, sources, source_ids, stratum_ids, failures, path)
    carrier_ids, carriers_by_id = _validated_carriers(protocol, failures, path)
    concepts, concept_ids = _validated_concepts(
        protocol, request_ids, carrier_ids, carriers_by_id, stage_ids, failures, path
    )
    _request_concept_join_failures(requests, concepts, concept_ids, failures, path)
    _execution_rule_failures(protocol, failures, path)
    return {
        "stratum_ids": stratum_ids,
        "stage_ids": stage_ids,
        "source_ids": source_ids,
        "request_ids": request_ids,
        "carrier_ids": carrier_ids,
        "carriers": carriers_by_id,
        "concept_ids": concept_ids,
        "concepts": {
            item["concept_id"]: item
            for item in concepts
            if isinstance(item, dict) and _valid_id(item.get("concept_id"))
        },
    }
