"""Offline finite participant-crossing verification in the installed closure."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import nox

    from tools.nox_support.runner import SessionReporter


def run_machine_check(session: nox.Session, reporter: SessionReporter, *, publish: bool = False) -> None:
    module = "implementations.formal.participant_crossing.machine_check"
    entrypoint = [module + "_publication"] if publish else [module, "verify"]
    reporter.run(
        "machine check / complete finite replay",
        lambda: session.run(
            "uv",
            "run",
            "--offline",
            "--no-sync",
            "--project",
            "implementations/python",
            "--frozen",
            "python",
            "-m",
            *entrypoint,
            external=True,
            env={
                "PYTHONPATH": "implementations/python/packages:.",
                "UV_PYTHON_DOWNLOADS": "never",
            },
        ),
    )
