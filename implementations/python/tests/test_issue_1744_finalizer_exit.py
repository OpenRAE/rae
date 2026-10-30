"""Issue 1744: a runtime that its caller does not close does not block interpreter exit."""

import gc
import subprocess
import sys
import textwrap
import threading

import pytest
from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

_PRELUDE = """
import logging
logging.basicConfig(level=logging.ERROR)
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import PlanScope
from raes_runtime.manager import RuntimeManager
from raes_runtime.operation_execution_adapter import LocalExecutionAdapter
SDL = parse_sdl("name: exit\\nnodes:\\n  server:\\n    type: compute\\n")
"""


@pytest.mark.parametrize(
    "script",
    [
        pytest.param("adapter = LocalExecutionAdapter()\n", id="adapter"),
        pytest.param(
            "manager = RuntimeManager(create_stub_target())\n"
            "manager.plan(SDL, run_scope=PlanScope(run_id='exit'))\n",
            id="manager",
        ),
        pytest.param(
            "manager = RuntimeManager(create_stub_target())\n"
            "run = manager.open_run(run_scope='run:exit')\n"
            "run.plan(SDL, run_scope=PlanScope(run_id='exit'))\n",
            id="run-context",
        ),
    ],
)
def test_an_unclosed_runtime_does_not_block_interpreter_exit(script: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_PRELUDE) + script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "finalizer" not in result.stderr


def _portal_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == "runtime-execution"]


def test_a_collected_unclosed_adapter_stops_its_portal_thread() -> None:
    before = _portal_threads()
    adapter = LocalExecutionAdapter()
    [thread] = [thread for thread in _portal_threads() if thread not in before]

    del adapter
    gc.collect()

    assert not thread.is_alive()


def test_a_closed_adapter_stops_its_portal_thread_once() -> None:
    before = _portal_threads()
    adapter = LocalExecutionAdapter()
    [thread] = [thread for thread in _portal_threads() if thread not in before]

    assert adapter.close(timeout_ms=1000)
    assert adapter.close(timeout_ms=1000)

    assert not thread.is_alive()
