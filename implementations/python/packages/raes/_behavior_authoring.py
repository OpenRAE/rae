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


def _private_refs(specification: Mapping[str, object]) -> Iterator[tuple[str, int, str]]:
    for field in _REFERENCE_FIELDS:
        refs = specification.get(field, ())
        if not isinstance(refs, (list, tuple)):
            continue
        for index, ref in enumerate(refs):
            if isinstance(ref, str) and PRIVATE_NAMESPACE_SEGMENT in ref.split("."):
                yield field, index, ref


def _authoring_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return value if isinstance(value, Mapping) else {}


def _private_tool_locations(specification: Mapping[str, object]) -> Iterator[tuple[tuple[str | int, ...], str]]:
    for affordance_id, value in _authoring_mapping(specification.get("tool_affordances")).items():
        binding = _authoring_mapping(value)
        prefix = ("tool_affordances", affordance_id)
        tool_ref = binding.get("tool_ref")
        if isinstance(tool_ref, str) and PRIVATE_NAMESPACE_SEGMENT in tool_ref.split("."):
            yield (*prefix, "tool_ref"), tool_ref
        for field, index, ref in _private_refs(binding):
            yield (*prefix, field, index), ref


def _private_locations(document: Mapping[str, object]) -> Iterator[tuple[tuple[str | int, ...], str]]:
    for section in ("agents", "behavior_specifications"):
        for name, value in _authoring_mapping(document.get(section)).items():
            for slot, binding in _authoring_mapping(_authoring_mapping(value).get("control_context")).items():
                ref = _authoring_mapping(binding).get("declaration_ref")
                if isinstance(ref, str) and PRIVATE_NAMESPACE_SEGMENT in ref.split("."):
                    yield (section, name, "control_context", slot, "declaration_ref"), ref
    for name, value in _authoring_mapping(document.get("behavior_specifications")).items():
        specification = _authoring_mapping(value)
        prefix = ("behavior_specifications", name)
        for field, index, ref in _private_refs(specification):
            yield (*prefix, field, index), ref
        for location, ref in _private_tool_locations(specification):
            yield (*prefix, *location), ref


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
