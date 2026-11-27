"""Exercise process limits and failure handling without running a proof tool."""

from __future__ import annotations

import sys
import tempfile

import pytest
from raes_contracts.errors import OperationalError


def test_process_environment_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.bounded_tool_process import run_bounded

    monkeypatch.setenv("ISSUE_973_PRIVATE", "must-not-pass")
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        run_bounded(
            [sys.executable, "-c", "import os; print(os.getenv('ISSUE_973_PRIVATE', 'absent'))"],
            stdout=output,
            stderr=errors,
        )
        output.seek(0)
        assert output.read() == b"absent\n"


@pytest.mark.parametrize(
    "program", ["import time; time.sleep(10)", "raise SystemExit(7)", "import os; os.write(1, b'x' * 65536)"]
)
def test_failed_or_over_budget_process_is_not_a_result(program: str) -> None:
    from tools.bounded_tool_process import run_bounded

    with (
        tempfile.TemporaryFile() as output,
        tempfile.TemporaryFile() as errors,
        pytest.raises(OperationalError, match="bounded-tool-failed"),
    ):
        run_bounded([sys.executable, "-c", program], stdout=output, stderr=errors, wall_seconds=0.1, file_bytes=1024)
