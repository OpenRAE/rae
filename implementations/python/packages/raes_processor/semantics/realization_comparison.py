"""Bounded portable values for processor realization comparisons."""

from pydantic_core import to_jsonable_python
from raes_contracts.canonical import jsonable_fallback
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import PLAN_VALUE_LIMITS


def portable_realization_value(value: object) -> object:
    """Project admitted carriers through the preparation transport codec."""

    if not validate_realization_value(value, limits=PLAN_VALUE_LIMITS, python_carriers=True).conformant:
        raise ValueError("Realization comparison requires a bounded portable value.")
    return to_jsonable_python(value, fallback=jsonable_fallback)
