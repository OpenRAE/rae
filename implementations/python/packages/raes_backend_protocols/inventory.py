"""Optional read-only producer protocol for negotiated descendant inventory."""

from typing import Protocol

from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot


class RuntimeInventoryReporter(Protocol):
    """Report materialized SDL without modifying infrastructure or the snapshot."""

    def refresh_inventory(self, request: ProvisioningPlan, predecessor: RuntimeSnapshot) -> ApplyResult:
        """Return the unchanged predecessor and a fresh materialization submission."""
        ...
