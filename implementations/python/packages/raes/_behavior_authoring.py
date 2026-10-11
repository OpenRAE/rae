"""Checks that apply to authored behavior references before composition."""

from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from ._identifiers import PRIVATE_NAMESPACE_SEGMENT

_REFERENCE_FIELDS = (
    "participant_refs",
    "action_contract_refs",
    "observation_boundary_refs",
    "outcome_interpretation_rule_refs",
    "authority_scope_refs",
)


def validate_authored_behavior_references(document: Mapping, *, generated_from: Mapping | None = None) -> None:
    """Keep generated private identities out of public authoring input.

    ExpandedScenario deliberately does not call this check: a module's own
    references to non-exported declarations acquire this segment legitimately.
    Binding may retain those exact refs, but parameters cannot mint new ones.
    """

    specifications = document.get("behavior_specifications", {})
    if not isinstance(specifications, Mapping):
        return
    errors = []
    generated_specs = generated_from.get("behavior_specifications", {}) if generated_from is not None else {}
    for name, specification in specifications.items():
        if isinstance(specification, BaseModel):
            specification = specification.model_dump(mode="python")
        if not isinstance(specification, Mapping):
            continue
        for field in _REFERENCE_FIELDS:
            refs = specification.get(field, ())
            if not isinstance(refs, (list, tuple)):
                continue
            for index, ref in enumerate(refs):
                if isinstance(ref, str) and PRIVATE_NAMESPACE_SEGMENT in ref.split("."):
                    original_refs = generated_specs.get(name, {}).get(field, ())
                    if index < len(original_refs) and original_refs[index] == ref:
                        continue
                    errors.append(
                        {
                            "type": "value_error",
                            "loc": ("behavior_specifications", name, field, index),
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
