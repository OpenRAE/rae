"""Value-bearing author demand separate from apparatus selection."""

from dataclasses import dataclass

from .addressing import require_compiled_address
from .bounded_domains import DomainDescriptor
from .compute_substrate import validate_compute_substrate_constraint


@dataclass(frozen=True)
class PlannedRealizationConstraint:
    """Portable author demand carried independently of a backend choice."""

    address: str
    field_path: str
    concern: str
    posture: str
    value_domain: DomainDescriptor | None
    governing_scope: str
    provenance: str

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        if self.concern != "compute-substrate":
            raise ValueError("planned realization constraint concern is unsupported")
        if self.posture not in {"open", "constrained", "exact"}:
            raise ValueError("planned realization constraint posture is invalid")
        validate_compute_substrate_constraint(self.posture, self.value_domain)
