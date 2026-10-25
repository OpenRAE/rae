"""Shared immutable phase-record base and type-sensitive JSON scalar equality."""

import re

from pydantic import ConfigDict

from ._base import SDLModel

JSONScalar = str | int | float | bool
JSON_POINTER_RE = re.compile(r"^(?:/(?:[^~/]|~[01])*)*$")


class FrozenPhaseModel(SDLModel):
    """Closed immutable value object used inside portable phase artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def json_value_equal(left: JSONScalar, right: JSONScalar) -> bool:
    """Compare JSON scalars without Python's True == 1 collapse."""

    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right
