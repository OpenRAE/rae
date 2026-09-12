"""Portable pre-mutation checks for plan-owned realization authority."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from typing import cast

from .bounded_domains import scalar_in_domain
from .canonical import JsonValue, canonical_json_digest
from .diagnostics import Diagnostic
from .planning import (
    ChangeAction,
    ProvisioningPlan,
    RealizationAuthorityBound,
    RealizationAuthorityMode,
    ResolvedRealizationAuthority,
    planned_realization_authority,
)
from .realization_structure import structure_matches

_MISSING_REALIZATION_SELECTION = object()
_CLOSED_NEUTRAL_VALUES_BY_REQUIREMENT_KIND = {
    "runtime-restart-policy": frozenset({"unknown"}),
}


def _planned_pointer_value(value: object, pointer: str) -> object:
    current = value
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return _MISSING_REALIZATION_SELECTION
    return current


def _process_resource_limit_identity_payload(value: object) -> JsonValue | None:
    payload: JsonValue | None = None
    if isinstance(value, Mapping):
        resource = value.get("resource", _MISSING_REALIZATION_SELECTION)
        subject = value.get("subject", _MISSING_REALIZATION_SELECTION)
        scope = value.get("scope", _MISSING_REALIZATION_SELECTION)
        if (
            resource is not _MISSING_REALIZATION_SELECTION
            and scope is not _MISSING_REALIZATION_SELECTION
            and isinstance(subject, Mapping)
        ):
            payload = _process_resource_limit_identity_mapping(resource, subject, scope)
    return payload


def _process_resource_limit_identity_mapping(
    resource: object,
    subject: Mapping[object, object],
    scope: object,
) -> JsonValue | None:
    subject_keys = (
        "name",
        "pid",
        "parent_pid",
        "command",
        "command_redacted",
        "role",
        "user",
        "group",
        "working_directory",
    )
    payload = None
    if all(key in subject for key in subject_keys):
        payload = cast(
            JsonValue,
            {
                "resource": resource,
                "subject": {key: subject[key] for key in subject_keys},
                "scope": scope,
            },
        )
    return payload


def _process_resource_limit_identity_digest(value: object) -> str | None:
    """Derive the portable process-limit identity from its projected record."""

    payload = _process_resource_limit_identity_payload(value)
    digest = None
    if payload is not None:
        with suppress(TypeError, ValueError):
            digest = canonical_json_digest(payload)
    return digest


def _planned_bound_value(
    selected: object,
    authority: ResolvedRealizationAuthority,
    bound: RealizationAuthorityBound,
) -> object:
    target = selected
    if bound.identity_digest is not None:
        if authority.requirement_kind != "process-resource-limits" or not isinstance(selected, list):
            return _MISSING_REALIZATION_SELECTION
        target = next(
            (item for item in selected if _process_resource_limit_identity_digest(item) == bound.identity_digest),
            _MISSING_REALIZATION_SELECTION,
        )
    return _planned_pointer_value(target, bound.value_pointer)


def planned_realization_selection_diagnostics(plan: ProvisioningPlan) -> list[Diagnostic]:
    """Reject plan values that an adapter may not send to its side-effect driver.

    This is the portable adapter-side complement to registry completeness and
    manifest admission. It deliberately consumes the total authority lookup so
    every concrete value interpreted before mutation is checked against the
    plan-owned closed/constrained boundary.
    """

    operations = {
        operation.address: operation for operation in plan.operations if operation.action is not ChangeAction.DELETE
    }
    diagnostic = None
    for candidate in plan.realization_authority:
        diagnostic = _planned_authority_selection_diagnostic(plan, candidate, operations)
        if diagnostic is not None:
            break
    return [diagnostic] if diagnostic is not None else []


def _planned_authority_selection_diagnostic(
    plan: ProvisioningPlan,
    candidate: ResolvedRealizationAuthority,
    operations: Mapping[str, object],
) -> Diagnostic | None:
    authority = planned_realization_authority(plan, candidate.address, candidate.requirement_kind)
    operation = operations.get(candidate.address)
    selected = (
        _planned_pointer_value(getattr(operation, "payload", None), authority.payload_pointer)
        if authority is not None and operation is not None
        else _MISSING_REALIZATION_SELECTION
    )
    invalid = authority is not None and _planned_selection_is_invalid(selected, authority)
    return _invalid_realization_selection(authority) if invalid and authority is not None else None


def _planned_selection_is_invalid(selected: object, authority: ResolvedRealizationAuthority) -> bool:
    invalid = False
    if authority.structure is not None and (
        selected is _MISSING_REALIZATION_SELECTION
        or not structure_matches(authority.structure, selected, selected, observed=False)
    ):
        return True
    if selected is not _MISSING_REALIZATION_SELECTION:
        if authority.mode is RealizationAuthorityMode.CLOSED:
            typed_neutral_values = _CLOSED_NEUTRAL_VALUES_BY_REQUIREMENT_KIND.get(
                authority.requirement_kind,
                frozenset(),
            )
            invalid = selected not in (None, "", [], {}) and not any(
                selected == value for value in typed_neutral_values
            )
        elif authority.mode is RealizationAuthorityMode.CONSTRAINED:
            invalid = any(
                (value := _planned_bound_value(selected, authority, bound)) is _MISSING_REALIZATION_SELECTION
                or not scalar_in_domain(value, bound.domain)
                for bound in authority.bounds
            )
    return invalid


def _invalid_realization_selection(authority: ResolvedRealizationAuthority) -> Diagnostic:
    return Diagnostic(
        code="realization.authority-selection-invalid",
        domain=authority.domain,
        address=authority.address,
        message=(
            "Provisioning adapter cannot materialize a plan value outside resolved "
            f"authority for '{authority.requirement_kind}'."
        ),
    )


__all__ = ["planned_realization_selection_diagnostics"]
