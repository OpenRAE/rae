"""Runtime and archive ownership for one target-adapter probe (issue #1667)."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from raes_contracts.planning import PlanScope
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget


class ProbeRuntimeOwner:
    """Own the probe run scope, its temporary archive, and every runtime that holds it.

    A negotiated materialization producer gets a private temporary archive and the
    matching ``run:<id>`` control-plane scope. The archive is removed only after
    every runtime that received it confirms closure. A runtime that cannot drain
    its backend calls keeps ownership, so the archive stays for a late publication.
    """

    def __init__(self, scope: PlanScope | None) -> None:
        self._scope = scope
        self._archive_root: Path | None = None
        self._runtimes: list[RuntimeControlPlane] = []

    @property
    def materialization_required(self) -> bool:
        return self._scope is not None

    def runtime(self, target: RuntimeTarget, **options: Any) -> RuntimeControlPlane:
        """Open a control plane that carries this probe's run scope and archive owner."""

        if self._scope is not None:
            if self._archive_root is None:
                self._archive_root = Path(mkdtemp(prefix="raes-target-conformance-"))
            options["materialization_archive"] = RunMaterializationArchive(self._archive_root)
            options["run_scope"] = f"run:{self._scope.run_id}"
        control_plane = RuntimeControlPlane(target, **options)
        self._runtimes.append(control_plane)
        return control_plane

    def close(self) -> None:
        """Confirm every runtime closed, then remove the archive.

        ``RuntimeControlPlane.close()`` is idempotent after success and raises
        while backend calls remain unresolved. That failure propagates and keeps
        the archive in place.
        """

        for control_plane in self._runtimes:
            control_plane.close()
        if self._archive_root is not None:
            shutil.rmtree(self._archive_root)
            self._archive_root = None


__all__ = ["ProbeRuntimeOwner"]
