"""Checks that apply to authored behavior references before composition."""

from collections.abc import Iterator, Mapping

from pydantic import BaseModel, ValidationError

from ._identifiers import PRIVATE_NAMESPACE_SEGMENT

_REFERENCE_FIELDS = (
    "participant_refs",
    "action_contract_refs",
    "observation_boundary_refs",
    "outcome_interpretation_rule_refs",
    "authority_scope_refs",
)
# Nested binding fields with the same authoring boundary (#301). The existing
# nested tool_affordances refs are tracked separately by issue #1498.
_TOOL_AFFORDANCE_REFERENCE_FIELDS = ("participant_refs",)


def _private_refs(
    specification: Mapping[str, object], fields: tuple[str, ...] = _REFERENCE_FIELDS
) -> Iterator[tuple[str, int, str]]:
    for field in fields:
        refs = specification.get(field, ())
        if not isinstance(refs, (list, tuple)):
            continue
        for index, ref in enumerate(refs):
            if isinstance(ref, str) and PRIVATE_NAMESPACE_SEGMENT in ref.split("."):
                yield field, index, ref


def _private_locations(document: Mapping[str, object]) -> Iterator[tuple[tuple[str | int, ...], str]]:
    specifications = document.get("behavior_specifications", {})
    if not isinstance(specifications, Mapping):
        return
    for name, specification in specifications.items():
        if isinstance(specification, BaseModel):
            specification = specification.model_dump(mode="python")
        if isinstance(specification, Mapping):
            for field, index, ref in _private_refs(specification):
                yield ("behavior_specifications", name, field, index), ref
            yield from _private_tool_affordance_locations(name, specification.get("tool_affordances"))


def _private_tool_affordance_locations(
    name: object, affordances: object
) -> Iterator[tuple[tuple[str | int, ...], str]]:
    if not isinstance(affordances, Mapping):
        return
    for key, affordance in affordances.items():
        if isinstance(affordance, BaseModel):
            affordance = affordance.model_dump(mode="python")
        if isinstance(affordance, Mapping):
            for field, index, ref in _private_refs(affordance, _TOOL_AFFORDANCE_REFERENCE_FIELDS):
                yield ("behavior_specifications", name, "tool_affordances", key, field, index), ref


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
                "type": "value_error",
                "loc": location,
                "input": ref,
                "ctx": {
                    "error": ValueError(
                        "authored qualified SDL identifier must not contain the reserved __private segment"
                    )
                },
            }
        )
    if errors:
        raise ValidationError.from_exception_data("Scenario", errors)
