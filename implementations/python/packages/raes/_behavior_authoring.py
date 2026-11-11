"""Checks that apply to authored behavior references before composition."""

from collections.abc import Iterator, Mapping

from pydantic import BaseModel, ValidationError
from raes_contracts.identifiers import PRIVATE_NAMESPACE_SEGMENT, identifier_refusal

_REFERENCE_FIELDS = (
    "participant_refs",
    "action_contract_refs",
    "observation_boundary_refs",
    "outcome_interpretation_rule_refs",
    "authority_scope_refs",
)
_REFERENCE_PATHS = (
    (("behavior_specifications", "*"), _REFERENCE_FIELDS),
    (
        ("agents", "*"),
        (
            "affiliations",
            "actions",
            "observation_boundaries",
            "starting_accounts",
            "allowed_subnets",
            "starting_assertions",
            "authority_anchors",
            "operating_scope",
        ),
    ),
    (("agents", "*", "initial_knowledge"), ("hosts", "subnets", "services", "accounts")),
    (("agents", "*", "interactive_access", "*"), ("target_ref", "account_ref")),
    (("agents", "*", "control_context", "*"), ("declaration_ref",)),
    (("behavior_specifications", "*", "control_context", "*"), ("declaration_ref",)),
    (
        ("behavior_specifications", "*", "tool_affordances", "*"),
        ("participant_refs", "action_contract_refs", "observation_boundary_refs", "tool_ref"),
    ),
    (
        ("behavior_specifications", "*", "participant_inject_deliveries", "*"),
        (
            "participant_ref",
            "inject_ref",
            "observation_boundary_ref",
            "source_item_ref",
            "result_item_ref",
            "controller_ref",
            "temporal_constraint_refs",
            "evidence_requirement_refs",
            "control_authority_scope_refs",
            "control_evidence_refs",
        ),
    ),
    (
        ("behavior_specifications", "*", "participant_inject_deliveries", "*", "occurrence"),
        ("event_ref", "script_ref", "story_ref"),
    ),
)


def _private_refs(
    specification: Mapping[str, object], fields: tuple[str, ...]
) -> Iterator[tuple[tuple[str | int, ...], str]]:
    for field in fields:
        refs = specification.get(field, ())
        if isinstance(refs, str):
            values = [((field,), refs)]
        elif isinstance(refs, (list, tuple)):
            values = [((field, index), ref) for index, ref in enumerate(refs)]
        else:
            continue
        for location, ref in values:
            if isinstance(ref, str) and PRIVATE_NAMESPACE_SEGMENT in ref.split("."):
                yield location, ref


def _authoring_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return value if isinstance(value, Mapping) else {}


def _private_locations(document: Mapping[str, object]) -> Iterator[tuple[tuple[str | int, ...], str]]:
    for path, fields in _REFERENCE_PATHS:
        for location, record in _records_at_path(document, path):
            for relative, ref in _private_refs(record, fields):
                yield (*location, *relative), ref


def _records_at_path(
    value: object, path: tuple[str, ...], location: tuple[str | int, ...] = ()
) -> Iterator[tuple[tuple[str | int, ...], Mapping[str, object]]]:
    value = _authoring_mapping(value)
    if not path:
        yield location, value
        return
    children = value.items() if path[0] == "*" else ((path[0], value.get(path[0])),)
    for key, child in children:
        yield from _records_at_path(child, path[1:], (*location, key))


def validate_authored_behavior_references(
    document: Mapping[str, object], *, generated_from: Mapping[str, object] | None = None
) -> None:
    """Reject authored private refs while retaining exact composition output.

    ExpandedScenario deliberately does not call this check: a module's own
    references to non-exported declarations acquire this segment legitimately.
    Binding may retain those exact refs, but parameters cannot mint new ones.
    """

    generated = dict(_private_locations(generated_from)) if generated_from is not None else {}
    errors = []
    for location, ref in _private_locations(document):
        if generated.get(location) == ref:
            continue
        errors.append(
            {
                "type": identifier_refusal(
                    "authored qualified SDL identifier must not contain the reserved __private segment"
                ),
                "loc": location,
                "input": ref,
            }
        )
    if errors:
        raise ValidationError.from_exception_data("Scenario", errors)
