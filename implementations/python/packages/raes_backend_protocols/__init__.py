"""Backend-facing protocol and capability declarations."""

from .domain_topology import DomainTopologyBinding as DomainTopologyBinding
from .operation_supervision import BackendOperationProvider as BackendOperationProvider
from .operation_supervision import require_operation_provider as require_operation_provider

__all__ = ["DomainTopologyBinding", "BackendOperationProvider", "require_operation_provider"]
