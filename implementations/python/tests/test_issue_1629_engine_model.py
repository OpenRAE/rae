"""Bounded two-context exploration of the S7 immutable authority invariants."""

from itertools import product

import pytest
from runtime_engine_model import Engine, dispatch, open_context, retire


def test_opening_and_replaying_contexts_never_retarget_an_operation():
    for first, second in (("a", "b"), ("b", "a")):
        engine = open_context(Engine(), first)
        engine = dispatch(engine, "operation", first)
        engine = open_context(engine, second)
        assert dict(engine.bindings)["operation"] == first
        assert dispatch(engine, "operation", first) == engine
        with pytest.raises(ValueError):
            dispatch(engine, "operation", second)
        with pytest.raises(ValueError):
            dispatch(engine, "other-operation", second)
        released = retire(engine, first, unknown=False, active_callback=False, verified_clean=True)
        next_run = dispatch(released, "other-operation", second)
        assert dict(next_run.bindings) == {"operation": first, "other-operation": second}
        assert next_run.reservation == second


@pytest.mark.parametrize("unknown,active,clean", list(product((False, True), repeat=3)))
def test_only_verified_quiescent_cleanup_releases_other_run(unknown, active, clean):
    engine = dispatch(open_context(open_context(Engine(), "a"), "b"), "operation", "a")
    if unknown or active or not clean:
        with pytest.raises(ValueError):
            retire(engine, "a", unknown=unknown, active_callback=active, verified_clean=clean)
        with pytest.raises(ValueError):
            dispatch(engine, "other", "b")
    else:
        released = retire(engine, "a", unknown=unknown, active_callback=active, verified_clean=clean)
        assert dispatch(released, "other", "b").reservation == "b"
