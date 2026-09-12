"""Apply owning field normalization when comparing retained variable bindings."""

from collections.abc import Mapping

from pydantic import BaseModel


def normalize_capability_binding(scenario: BaseModel, pointer: str, value: object) -> object:
    """Normalize through the leaf's model without rewriting retained provenance.

    Revalidating the owner applies its existing aliases and scalar coercion
    rules. Identity equality remains the caller's responsibility; this helper
    neither changes a constraint nor interprets an extension's meaning.
    """
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    owner: object = scenario
    for part in parts[:-1]:
        if isinstance(owner, BaseModel):
            owner = getattr(owner, part)
        elif isinstance(owner, Mapping):
            owner = owner[part]
        elif isinstance(owner, (list, tuple)):
            owner = owner[int(part)]
        else:
            return value
    # Root metadata has no scalar capability normalization and revalidating it
    # would recurse through this same provenance check.
    if owner is scenario or not isinstance(owner, BaseModel) or parts[-1] not in type(owner).model_fields:
        return value
    payload = owner.model_dump(mode="python", by_alias=True)
    payload[parts[-1]] = value
    normalized = type(owner).model_validate(payload).model_dump(mode="json", by_alias=True)
    return normalized[parts[-1]]
