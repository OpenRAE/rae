"""Value-free run/instantiation scope identity for planning (issue #1276).

Extracted from :mod:`raes_contracts.planning` so the planning module stays under
the ADR-015 source-size cap. The scope identity is a distinct subdomain: it names
*which* realization a plan is computed for without ever carrying a generated
secret. ``planning`` re-exports these names for backward compatibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _validate_optional_run_id(run_id: str | None, *, owner: str) -> None:
    """Validate a value-free run/instance scope identity when present (issue #1276)."""

    if run_id is None:
        return
    if not run_id.strip() or _RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError(f"{owner} run_id must be a bounded non-empty scope identity when present")


@dataclass(frozen=True)
class PlanScope:
    """Identity of the realization a plan is computed for.

    ``target_name`` selects the backend target the plan is reconciled against,
    while ``run_id`` names the authoritative run scope (``run:<id>`` authority) and
    ``instantiation_id`` names the unique instantiation coordinate; together the
    run/instantiation pair lets per-run / per-instantiation generated values
    reconcile against the correct scope (issue #1276). Both identifiers are
    value-free scope identities, never the generated secret. Bundling the three
    keeps the planning entry points cohesive rather than threading loose optional
    identifiers through every signature.
    """

    target_name: str | None = None
    run_id: str | None = None
    instantiation_id: str | None = None

    def __post_init__(self) -> None:
        _validate_optional_run_id(self.run_id, owner="PlanScope run_id")
        _validate_optional_run_id(self.instantiation_id, owner="PlanScope instantiation_id")


__all__ = ["PlanScope"]
