"""Target-bound run identity for negotiated materialization probes (issue #1667)."""

from __future__ import annotations

from uuid import uuid4

from raes_contracts.materialization import MATERIALIZATION_ATTESTATION_CONTRACT
from raes_contracts.planning import PlanScope
from raes_runtime.registry import RuntimeTarget


def materialization_probe_scope(target: RuntimeTarget) -> PlanScope | None:
    """Return a fresh target-bound run identity for a negotiated materialization producer.

    Negotiated reporting binds a plan to its admitted source and a run identity.
    Each probe receives a new bounded identity, so a backend never reuses native
    state from another qualification run. The identity is also a safe archive
    label. Targets that do not negotiate the contract keep the unscoped plan.
    """

    if MATERIALIZATION_ATTESTATION_CONTRACT not in target.manifest.supported_contract_versions:
        return None
    return PlanScope(target_name=target.name, run_id=f"target-conformance-{uuid4().hex}")


__all__ = ["materialization_probe_scope"]
