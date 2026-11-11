"""Provider-neutral deployment tenancy, placement, and shared-service intent."""

from enum import Enum

from pydantic import Field, field_validator
from raes_contracts.sdl_model import SDLModel
from raes_contracts.variable_references import WholeFieldVariableReference, parse_enum_or_var


class EndpointPersona(str, Enum):
    """Scenario function of a compute endpoint, separate from login/participant roles."""

    WORKFORCE = "workforce"
    ENGINEERING = "engineering"
    PRIVILEGED_ADMIN = "privileged_admin"
    PARTICIPANT = "participant"
    SERVICE = "service"
    CARRIER = "carrier"


class DeploymentTenant(SDLModel):
    """Stable portable deployment-tenant identity."""

    description: str = ""


class CrossTenantIsolation(str, Enum):
    """Default cell posture for access from another tenant."""

    DEFAULT_DENY = "default_deny"


class DeploymentCell(SDLModel):
    """One tenant-owned failure/isolation cell with explicit node membership."""

    tenant_ref: str = Field(min_length=1)
    node_refs: list[str] = Field(min_length=1)
    cross_tenant_isolation: CrossTenantIsolation | WholeFieldVariableReference

    @field_validator("cross_tenant_isolation", mode="before")
    @classmethod
    def normalize_isolation(cls, value: str) -> CrossTenantIsolation | WholeFieldVariableReference:
        return parse_enum_or_var(value, CrossTenantIsolation, field_name="cross_tenant_isolation")

    @field_validator("node_refs")
    @classmethod
    def validate_node_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("node_refs must contain non-empty references")
        if len(values) != len(set(values)):
            raise ValueError("node_refs must be unique")
        return values


class KernelBoundary(str, Enum):
    """Kernel/trust boundary requested between logical node and carrier."""

    SHARED_KERNEL = "shared_kernel"
    SEPARATE_KERNEL = "separate_kernel"


class RelationshipCarrierPlacement(SDLModel):
    """Typed logical-node-to-carrier placement intent."""

    kernel_boundary: KernelBoundary | WholeFieldVariableReference

    @field_validator("kernel_boundary", mode="before")
    @classmethod
    def normalize_kernel_boundary(cls, value: str) -> KernelBoundary | WholeFieldVariableReference:
        return parse_enum_or_var(value, KernelBoundary, field_name="kernel_boundary")


class TenantIsolationMode(str, Enum):
    """Shared-service tenant isolation posture."""

    NONE = "none"
    STATELESS = "stateless"
    TENANT_PARTITIONED = "tenant_partitioned"


class WorkloadAuthenticationMode(str, Enum):
    """Workload authentication posture at a shared-service boundary."""

    NONE = "none"
    SHARED_CREDENTIAL = "shared_credential"
    WORKLOAD_IDENTITY = "workload_identity"
    TENANT_SCOPED_WORKLOAD_IDENTITY = "tenant_scoped_workload_identity"


class StateOwner(str, Enum):
    """Owner of mutable state or reset generation."""

    NONE = "none"
    CONSUMER_TENANT = "consumer_tenant"
    SHARED_SERVICE = "shared_service"


class RelationshipSharedService(SDLModel):
    """Typed tenant-to-existing-service policy binding."""

    tenant_isolation: TenantIsolationMode | WholeFieldVariableReference
    workload_authentication: WorkloadAuthenticationMode | WholeFieldVariableReference
    mutable_state_refs: list[str] = Field(default_factory=list)
    mutable_state_owner: StateOwner | WholeFieldVariableReference
    reset_generation_owner: StateOwner | WholeFieldVariableReference

    @field_validator("tenant_isolation", mode="before")
    @classmethod
    def normalize_tenant_isolation(cls, value: str) -> TenantIsolationMode | WholeFieldVariableReference:
        return parse_enum_or_var(value, TenantIsolationMode, field_name="tenant_isolation")

    @field_validator("workload_authentication", mode="before")
    @classmethod
    def normalize_workload_authentication(cls, value: str) -> WorkloadAuthenticationMode | WholeFieldVariableReference:
        return parse_enum_or_var(value, WorkloadAuthenticationMode, field_name="workload_authentication")

    @field_validator("mutable_state_owner", "reset_generation_owner", mode="before")
    @classmethod
    def normalize_owner(cls, value: str) -> StateOwner | WholeFieldVariableReference:
        return parse_enum_or_var(value, StateOwner, field_name="state_owner")

    @field_validator("mutable_state_refs")
    @classmethod
    def validate_state_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("mutable_state_refs must contain non-empty references")
        if len(values) != len(set(values)):
            raise ValueError("mutable_state_refs must be unique")
        return values


__all__ = [
    "CrossTenantIsolation",
    "DeploymentCell",
    "DeploymentTenant",
    "EndpointPersona",
    "KernelBoundary",
    "RelationshipCarrierPlacement",
    "RelationshipSharedService",
    "StateOwner",
    "TenantIsolationMode",
    "WorkloadAuthenticationMode",
]
