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


def _private_refs(specification: Mapping) -> Iterator[tuple[str, int, str]]:
    for field in _REFERENCE_FIELDS:
        refs = specification.get(field, ())
        if not isinstance(refs, (list, tuple)):
            continue
        for index, ref in enumerate(refs):
            if isinstance(ref, str) and PRIVATE_NAMESPACE_SEGMENT in ref.split("."):
                yield field, index, ref


def _private_locations(document: Mapping) -> Iterator[tuple[tuple, str]]:
    specifications = document.get("behavior_specifications", {})
    if not isinstance(specifications, Mapping):
        return
    for name, specification in specifications.items():
        if isinstance(specification, BaseModel):
            specification = specification.model_dump(mode="python")
        if isinstance(specification, Mapping):
            for field, index, ref in _private_refs(specification):
                yield ("behavior_specifications", name, field, index), ref


def validate_authored_behavior_references(document: Mapping, *, generated_from: Mapping | None = None) -> None:
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
