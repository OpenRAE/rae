"""A second ledger or direct manager cannot reuse an actively owned backend."""

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import ConflictError, OperationalError
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager
from runtime_plan_fixtures import plan_for_target


def test_direct_manager_close_releases_components_and_refuses_later_effects():
    from raes import parse_sdl

    target = create_stub_target()
    planned = plan_for_target(target, parse_sdl("name: manager-close"))
    manager = RuntimeManager(target)
    manager.close()
    with RuntimeControlPlane(target):
        with pytest.raises(OperationalError, match="closed"):
            manager.apply(planned)
        with pytest.raises(OperationalError, match="closed"):
            manager.pause_time("time.clock.test")


def test_direct_manager_close_retains_components_until_a_physical_callback_returns():
    from threading import Event, Thread

    from raes import parse_sdl

    target = create_stub_target()
    planned = plan_for_target(target, parse_sdl("name: manager-drain"))
    started, release = Event(), Event()
    original = target.provisioner.apply
    results = []

    def apply(plan, snapshot):
        started.set()
        assert release.wait(3)
        return original(plan, snapshot)

    target.provisioner.apply = apply
    manager = RuntimeManager(target)
    worker = Thread(target=lambda: results.append(manager.apply(planned)))
    worker.start()
    try:
        assert started.wait(1)
        with pytest.raises(ConflictError, match="callbacks remain active"):
            manager.close()
        with pytest.raises(ConflictError, match="runtime owner"):
            RuntimeControlPlane(target)
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert results[0].success
    manager.close()
    with RuntimeControlPlane(target):
        pass


def test_another_store_and_direct_manager_cannot_bypass_backend_ownership():
    target = create_stub_target()
    plane = RuntimeControlPlane(target)
    try:
        with pytest.raises(ConflictError):
            RuntimeControlPlane(target)
        with pytest.raises(ConflictError):
            RuntimeManager(target)
    finally:
        plane.close()
    replacement = RuntimeControlPlane(target)
    replacement.close()
