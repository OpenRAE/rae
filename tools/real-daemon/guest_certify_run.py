#!/usr/bin/env python3
"""Fixed-argv guest-certified evidence runner (issue #1222).

The AWS guest-certification script used to splice ``RUN_ID`` and paths into a
remote ``python -c`` string inside ``sudo bash -lc '...'``. That nested
shell/Python interpolation ran before any validation and was injection-prone.

This committed entrypoint reads its inputs from the environment instead, so the
shell never builds Python source from data. ``run_id`` is validated by
``run_libvirt_evidence_run`` before any path is constructed from it. The runner
is invoked on the instance with a fixed argument vector; it is never executed as
part of the hermetic verification graph.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    from raes_operations.libvirt_evidence_run import (
        LibvirtEvidenceRunConfig,
        run_libvirt_evidence_run,
    )
    from raes_operations.run_artifacts import is_valid_run_id_label

    run_id = os.environ.get("RAES_GUEST_RUN_ID", "")
    if not is_valid_run_id_label(run_id):
        print("error: RAES_GUEST_RUN_ID is not a safe run-id label", file=sys.stderr)
        return 2
    try:
        scenario = Path(os.environ["RAES_GUEST_SCENARIO"]).resolve()
        project_dir = Path(os.environ["RAES_GUEST_PROJECT_DIR"]).resolve()
    except KeyError as exc:
        print(f"error: missing required environment variable {exc}", file=sys.stderr)
        return 2
    connection_uri = os.environ.get("RAES_GUEST_CONNECTION_URI", "qemu:///system")

    report = run_libvirt_evidence_run(
        scenario_path=scenario,
        project_dir=project_dir,
        run_id=run_id,
        config=LibvirtEvidenceRunConfig(evidence_source_mode="guest-certified", connection_uri=connection_uri),
    )
    print(report.render())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
