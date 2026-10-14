"""A second ledger or direct manager cannot reuse an actively owned backend."""

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager


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
