"""Lazy public runtime exports remain usable without a warm contract facade."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "statement",
    [
        "import raes_runtime.manager",
        "import raes_runtime.control_plane",
        "from raes_runtime import RuntimeManager",
        "from raes_runtime import RuntimeControlPlane",
        "from raes_runtime import BackendRegistry",
        "from raes_runtime import MixedRuntimeBinding",
        "from raes_runtime import ControlPlaneProfile",
        "from raes_runtime import RuntimeFactDispatchCommand",
    ],
)
def test_runtime_export_imports_in_a_fresh_process(statement):
    result = subprocess.run([sys.executable, "-c", statement], capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
