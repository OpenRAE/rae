"""Claim scope and stratum binding validation."""

from __future__ import annotations

from collections.abc import Mapping

from raes_contracts.errors import InvalidInputError

from tools.dsl_language_evaluation._claim_strata import (
    _expanded_strata,
    _expanded_strata_failures,
    _threshold_measures,
    _thresholds_by_dimension,
)
from tools.dsl_language_evaluation._keys import (
    _CLAIM_BINDING_KEYS,
    _CLAIM_SCOPE_KEYS,
    _MAX_CATALOG_ITEMS,
    MANIFEST_PATH,
)
from tools.dsl_language_evaluation._shape import (
    _bounded_list,
    _exact_keys,
    _failure,
    _protocol_records_by_id,
    _record_ids,
    _string_list,
    _valid_id,
)
from tools.policy.common import PolicyFailure


def _full_claim_scope(catalogs: Mapping[str, set[str]]) -> dict[str, set[str]]:
    return {
        "persona_ids": set(catalogs.get("persona_ids", set())),
        "task_ids": set(catalogs.get("task_ids", set())),
        "tooling_condition_ids": set(catalogs.get("condition_ids", set())),
        "variant_ids": set(catalogs.get("variant_ids", set())),
        "artifact_stage_ids": set(catalogs.get("stage_ids", set())),
        "dimension_ids": set(catalogs.get("dimension_ids", set())),
        "measure_ids": set(catalogs.get("measure_ids", set())),
    }


def _attempt_matches_scope(
    attempt: Mapping[str, object],
    scope: Mapping[str, set[str]],
) -> bool:
    return (
        attempt.get("task_id") in scope.get("task_ids", set())
        and attempt.get("persona_id") in scope.get("persona_ids", set())
        and attempt.get("tooling_condition_id") in scope.get("tooling_condition_ids", set())
        and attempt.get("variant_id") in scope.get("variant_ids", set())
    )


def _validate_claim_scope(
    protocol: Mapping[str, object],
    analysis: Mapping[str, object],
    catalogs: Mapping[str, set[str]],
    failures: list[PolicyFailure],
    *,
    path: str = "docs/research/dsl-language-evaluation/analysis-v1.json",
) -> dict[str, set[str]]:
    """Validate and resolve the exact catalog slice owned by one claim."""

    fallback = _full_claim_scope(catalogs)
    claim = analysis.get("claim")
    scope = claim.get("scope") if isinstance(claim, Mapping) else None
    if not _exact_keys(
        scope,
        _CLAIM_SCOPE_KEYS,
        failures,
        rule_id="dsl-evaluation-claim-scope",
        label="claim scope",
        path=path,
    ):
        return fallback

    resolved = _resolved_scope_fields(scope, catalogs, failures, path)
    _scope_task_failures(protocol, resolved, failures, path)
    _scope_threshold_failures(protocol, resolved, failures, path)
    return resolved


def _resolved_scope_fields(
    scope: Mapping[str, object],
    catalogs: Mapping[str, set[str]],
    failures: list[PolicyFailure],
    path: str,
) -> dict[str, set[str]]:
    catalog_fields = {
        "persona_ids": "persona_ids",
        "task_ids": "task_ids",
        "tooling_condition_ids": "condition_ids",
        "variant_ids": "variant_ids",
        "artifact_stage_ids": "stage_ids",
        "dimension_ids": "dimension_ids",
        "measure_ids": "measure_ids",
    }
    resolved: dict[str, set[str]] = {}
    for field, catalog_field in catalog_fields.items():
        values = _string_list(scope[field], non_empty=True)
        known = catalogs.get(catalog_field, set())
        if values is None or len(values) != len(set(values)) or not set(values).issubset(known):
            failures.append(
                _failure(
                    "dsl-evaluation-claim-scope",
                    f"claim scope {field} must be a non-empty unique subset of the protocol catalog",
                    path,
                )
            )
            resolved[field] = set(values or []) & known
        else:
            resolved[field] = set(values)
    return resolved


def _scope_task_failures(
    protocol: Mapping[str, object],
    resolved: Mapping[str, set[str]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    tasks = _protocol_records_by_id(protocol, "tasks", "task_id")
    measures = _protocol_records_by_id(protocol, "measures", "measure_id")
    joins = (
        ("persona_ids", "persona_ids"),
        ("tooling_condition_ids", "tooling_condition_ids"),
        ("variant_ids", "variant_ids"),
        ("artifact_stage_ids", "artifact_stage_ids"),
    )
    for task_id in resolved["task_ids"]:
        task = tasks.get(task_id, {})
        if any(
            not (set(_string_list(task.get(task_field), non_empty=True) or []) & resolved[scope_field])
            for task_field, scope_field in joins
        ):
            failures.append(
                _failure(
                    "dsl-evaluation-claim-scope",
                    f"{task_id}: claim scope must retain an eligible persona, condition, variant, and stage",
                    path,
                )
            )
        if not any(
            task_id in (_string_list(measures[measure_id].get("task_ids"), non_empty=True) or [])
            for measure_id in resolved["measure_ids"]
            if measure_id in measures
        ):
            failures.append(
                _failure(
                    "dsl-evaluation-claim-scope",
                    f"{task_id}: claim scope has no applicable measure",
                    path,
                )
            )


def _scope_threshold_failures(
    protocol: Mapping[str, object],
    resolved: Mapping[str, set[str]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    thresholds = _thresholds_by_dimension(protocol)
    for dimension_id in resolved["dimension_ids"]:
        required_measures = _threshold_measures(thresholds.get(dimension_id))
        if not required_measures or not required_measures.issubset(resolved["measure_ids"]):
            failures.append(
                _failure(
                    "dsl-evaluation-claim-scope",
                    f"{dimension_id}: claim scope must include every threshold measure",
                    path,
                )
            )


def _validate_claim_binding(
    protocol: Mapping[str, object],
    analysis: Mapping[str, object],
    claim_binding: object,
    scope: Mapping[str, set[str]],
    failures: list[PolicyFailure],
    *,
    path: str,
) -> list[dict[str, object]]:
    """Bind one stable claim to its immutable scope and reporting strata."""

    if not _exact_keys(
        claim_binding,
        _CLAIM_BINDING_KEYS,
        failures,
        rule_id="dsl-evaluation-claim-binding",
        label="claim binding",
        path=path,
    ):
        return []
    assert isinstance(claim_binding, dict)
    _claim_identity_failures(analysis, claim_binding, failures, path)
    _bound_scope_failures(claim_binding, scope, failures, path)

    groups = _bounded_list(
        claim_binding["strata"],
        16,
        failures,
        rule_id="dsl-evaluation-claim-strata",
        label="claim binding strata",
        path=path,
    )
    group_ids = _record_ids(
        groups,
        "group_id",
        failures,
        rule_id="dsl-evaluation-claim-strata",
        label="claim stratum group",
        path=path,
    )
    expanded = _expanded_strata(protocol, scope, groups, failures, path)
    _expanded_strata_failures(groups, group_ids, expanded, failures, path)
    if len(expanded) > _MAX_CATALOG_ITEMS:
        failures.append(
            _failure(
                "dsl-evaluation-claim-strata",
                f"claim binding expands beyond {_MAX_CATALOG_ITEMS} strata",
                path,
            )
        )
        return expanded[:_MAX_CATALOG_ITEMS]
    return expanded


def _claim_identity_failures(
    analysis: Mapping[str, object],
    claim_binding: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    claim = analysis.get("claim")
    claim_id = claim.get("claim_id") if isinstance(claim, Mapping) else None
    if not _valid_id(claim_binding["claim_id"]) or claim_binding["claim_id"] != claim_id:
        failures.append(
            _failure(
                "dsl-evaluation-claim-binding",
                "manifest claim binding must name the analysis claim_id exactly",
                path,
            )
        )


def _bound_scope_failures(
    claim_binding: Mapping[str, object],
    scope: Mapping[str, set[str]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    bound_scope = claim_binding["scope"]
    if not _exact_keys(
        bound_scope,
        _CLAIM_SCOPE_KEYS,
        failures,
        rule_id="dsl-evaluation-claim-binding",
        label="claim binding scope",
        path=path,
    ):
        return
    assert isinstance(bound_scope, dict)
    for field in _CLAIM_SCOPE_KEYS:
        values = _string_list(bound_scope[field], non_empty=True)
        if values is None or len(values) != len(set(values)) or set(values) != scope.get(field, set()):
            failures.append(
                _failure(
                    "dsl-evaluation-claim-binding",
                    f"analysis claim scope {field} must exactly match its manifest binding",
                    path,
                )
            )


def resolve_claim_strata(
    protocol: Mapping[str, object],
    analysis: Mapping[str, object],
    claim_binding: Mapping[str, object],
) -> list[dict[str, object]]:
    """Resolve a validated manifest binding for recomputation and fixtures."""

    catalogs = {
        "persona_ids": set(_protocol_records_by_id(protocol, "personas", "persona_id")),
        "task_ids": set(_protocol_records_by_id(protocol, "tasks", "task_id")),
        "condition_ids": set(_protocol_records_by_id(protocol, "tooling_conditions", "condition_id")),
        "variant_ids": set(_protocol_records_by_id(protocol, "variants", "variant_id")),
        "stage_ids": set(_protocol_records_by_id(protocol, "artifact_stages", "stage_id")),
        "dimension_ids": set(_protocol_records_by_id(protocol, "dimensions", "dimension_id")),
        "measure_ids": set(_protocol_records_by_id(protocol, "measures", "measure_id")),
    }
    failures: list[PolicyFailure] = []
    scope = _validate_claim_scope(protocol, analysis, catalogs, failures, path=MANIFEST_PATH)
    strata = _validate_claim_binding(
        protocol,
        analysis,
        claim_binding,
        scope,
        failures,
        path=MANIFEST_PATH,
    )
    if failures:
        raise InvalidInputError("; ".join(f"{failure.rule_id}: {failure.message}" for failure in failures))
    return strata
