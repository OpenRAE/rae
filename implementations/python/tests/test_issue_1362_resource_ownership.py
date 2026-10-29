"""A second ledger or direct manager cannot reuse an actively owned backend."""

import pytest
from raes_backend_stubs.stubs import create_stub_target
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
        with pytest.raises(RuntimeError, match="closed"):
            manager.apply(planned)
        with pytest.raises(RuntimeError, match="closed"):
            manager.pause_time("time.clock.test")


def test_direct_manager_close_retains_components_until_a_physical_callback_returns():
    from concurrent.futures import ThreadPoolExecutor

    from raes import parse_sdl

    target = create_stub_target()
    planned = plan_for_target(target, parse_sdl("name: manager-drain"))
    original = target.provisioner.apply

    def assert_owned():
        with pytest.raises(RuntimeError, match="callbacks remain active"):
            manager.close()
        with pytest.raises(RuntimeError, match="runtime owner"):
            RuntimeControlPlane(target)

    def apply(plan, snapshot):
        # The callback stays active until the concurrent ownership checks finish.
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(assert_owned).result()
        return original(plan, snapshot)

    target.provisioner.apply = apply
    manager = RuntimeManager(target)
    assert manager.apply(planned).success
    manager.close()
    with RuntimeControlPlane(target):
        pass


def test_another_store_and_direct_manager_cannot_bypass_backend_ownership():
    target = create_stub_target()
    plane = RuntimeControlPlane(target)
    try:
        with pytest.raises(RuntimeError):
            RuntimeControlPlane(target)
        with pytest.raises(RuntimeError):
            RuntimeManager(target)
    finally:
        plane.close()
    replacement = RuntimeControlPlane(target)
    replacement.close()
