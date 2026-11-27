"""Select an operation's fixed context before entering its authority boundary."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from inspect import signature
from typing import TYPE_CHECKING, Concatenate

if TYPE_CHECKING:
    from .runtime_run_context import RuntimeRunContext


def run_operation[**P, R](
    method: Callable[Concatenate[RuntimeRunContext, P], R],
) -> Callable[Concatenate[RuntimeRunContext, P], R]:
    parameters = signature(method)
    reference_name = tuple(parameters.parameters)[1]

    @wraps(method)
    def routed(owner: RuntimeRunContext, *args: P.args, **kwargs: P.kwargs) -> R:
        engine = getattr(owner, "_engine", None)
        if engine is None or engine.owner is not owner:
            return method(owner, *args, **kwargs)
        reference = parameters.bind(owner, *args, **kwargs).arguments[reference_name]
        if isinstance(reference, str):
            operation_id = reference
        else:
            binding = getattr(reference, "binding", reference)
            operation_id = getattr(binding, "operation_id", None)
        with owner._runtime_call():
            context = engine.operation_context(operation_id)
            return method(context, *args, **kwargs)

    return routed
