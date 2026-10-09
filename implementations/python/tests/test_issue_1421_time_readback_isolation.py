"""Shared-time readback cannot rewrite accepted runtime state (issue #1421).

``RuntimeManager.read_time_state()`` asks the target time runtime for its state.
The runtime retains its accepted snapshot in isolation: a time runtime that
mutates the snapshot it is shown, by design or by accident, changes neither the
authoritative snapshot nor the agreement check that follows the readback.
"""

from __future__ import annotations

import dataclasses
from copy import deepcopy

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_runtime import RuntimeManager
from test_api_421_time_contracts import _scenario

_CLOCK = "time.clock.scenario-clock"


def _clear_entries(snapshot, honest):
    snapshot.entries.clear()
    return honest


def _forge_metadata(snapshot, honest):
    snapshot.metadata["forged"] = "by-time-runtime"
    return honest


def _forge_paused_clock(snapshot, honest):
    clock = honest.clocks[_CLOCK]
    forged = honest.model_copy(update={"clocks": {_CLOCK: clock.model_copy(update={"state": "paused"})}})
    snapshot.time_model_state = forged
    return forged


class _MutatingReadback:
    """Delegates to the stub time runtime; ``state`` also rewrites its argument."""

    def __init__(self, inner, mutate):
        self._inner = inner
        self._mutate = mutate

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def state(self, snapshot):
        return self._mutate(snapshot, self._inner.state(snapshot))


def _manager(mutate):
    base = create_stub_target()
    manager = RuntimeManager(dataclasses.replace(base, time_runtime=_MutatingReadback(base.time_runtime, mutate)))
    assert manager.apply(manager.plan(_scenario())).success
    return manager


@pytest.mark.parametrize("mutate", [_clear_entries, _forge_metadata], ids=["clear-entries", "forge-metadata"])
def test_readback_cannot_rewrite_the_authoritative_snapshot(mutate):
    manager = _manager(mutate)
    accepted = deepcopy(manager.snapshot)

    state = manager.read_time_state()

    assert manager.snapshot == accepted
    assert state == accepted.time_model_state


def test_clock_forged_into_the_argument_is_a_disagreeing_readback():
    manager = _manager(_forge_paused_clock)
    accepted = deepcopy(manager.snapshot)
    assert accepted.time_model_state.clocks[_CLOCK].state != "paused"

    with pytest.raises(ValueError, match="disagrees with the runtime snapshot"):
        manager.read_time_state()

    assert manager.snapshot == accepted
