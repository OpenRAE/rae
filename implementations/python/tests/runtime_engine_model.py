"""Finite S7 model; evidence inputs are assumptions, not physical proof."""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Engine:
    contexts: tuple[str, ...] = ()
    bindings: tuple[tuple[str, str], ...] = ()
    reservation: str | None = None
    retired: frozenset[str] = frozenset()


def open_context(engine, context):
    if context in engine.contexts:
        raise ValueError("fixed context already exists")
    return replace(engine, contexts=(*engine.contexts, context))


def dispatch(engine, operation, context):
    if context not in engine.contexts or context in engine.retired:
        raise ValueError("context is unavailable")
    bound = dict(engine.bindings).get(operation)
    if bound is not None:
        if bound != context:
            raise ValueError("operation binding is immutable")
        return engine
    if engine.reservation not in (None, context):
        raise ValueError("another context reserves the resources")
    return replace(engine, reservation=context, bindings=(*engine.bindings, (operation, context)))


def retire(engine, context, *, unknown, active_callback, verified_clean):
    if context not in engine.contexts or unknown or active_callback or not verified_clean:
        raise ValueError("verified release is absent")
    return replace(
        engine,
        retired=engine.retired | {context},
        reservation=None if engine.reservation == context else engine.reservation,
    )
