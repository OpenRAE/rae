"""Orchestration-authority runtime inventory family (RuntimeOrchestrationAuthority).

SCN-010 §5.6. A node whose defining logical state is the authority to *spawn*
containers/workloads through a control interface (e.g. a SOAR orchestrator or an
analyzer engine holding ``docker.sock`` read-write). ``RuntimeControlInterface``
(``runtime_mounts.py``) types the docker.sock *shell* — a present read-write unix
socket — but carries no field for what the holder is authorized to *do*; this
family carries the spawn contract (engine + scope + spawn templates + lifecycle
policy + realized children) referencing that shell by ``control_interface_ref``.

``control_interface_ref`` is the ``control_interface_id`` of a same-node
``RuntimeControlInterface`` (resolved by ``validator.py``); this surface never
imports or duplicates ``RuntimeControlInterface``. A partial description can
record privileged posture without knowing the interface. This grants no
execution authority; selected operations require separately admitted capability,
access and a resolvable interface before mutation.
"""

from enum import Enum

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, parse_int_or_var
from .runtime_values import parse_runtime_enum_or_var, require_symbol

__all__ = [
    "RuntimeOrchestrationAuthority",
    "RuntimeOrchestrationEngine",
    "RuntimeOrchestrationLifecyclePolicy",
    "RuntimeOrchestrationPrivilegeClass",
    "RuntimeOrchestrationRealizedChild",
    "RuntimeOrchestrationScope",
    "RuntimeOrchestrationSpawnTemplate",
]


class RuntimeOrchestrationEngine(str, Enum):
    """Open taxonomy for the orchestration engine/runtime family.

    Open taxonomy: carries both ``unknown`` and ``other`` per the DSL-139
    enum-sentinel rule.
    """

    DOCKER = "docker"
    CONTAINERD = "containerd"
    PODMAN = "podman"
    KUBERNETES = "kubernetes"
    CRI_O = "cri_o"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeOrchestrationPrivilegeClass(str, Enum):
    """Open taxonomy for the privilege an orchestration authority commands.

    ``host_root_equivalent`` denotes an authority whose spawn surface is
    equivalent to host root (e.g. a read-write ``docker.sock`` holder);
    ``namespaced`` denotes a privilege-scoped/rootless authority. Open
    taxonomy: carries both ``unknown`` and ``other``.
    """

    HOST_ROOT_EQUIVALENT = "host_root_equivalent"
    NAMESPACED = "namespaced"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeOrchestrationScope(SDLModel):
    """The organizational/environment scope an orchestration authority governs."""

    organization_ref: str = ""
    environment_name: str = ""
    description: str = ""


class RuntimeOrchestrationSpawnTemplate(SDLModel):
    """A template the authority is authorized to instantiate (image + purpose)."""

    template_id: str
    image_ref: str = ""
    purpose: str = ""
    description: str = ""

    @field_validator("template_id")
    @classmethod
    def validate_template_id(cls, v: str) -> str:
        return require_symbol(v, field_name="template_id")


class RuntimeOrchestrationLifecyclePolicy(SDLModel):
    """The lifecycle posture applied to children the authority spawns."""

    timeout: str = ""
    cleanup: str = ""
    execution_timeout: str = ""
    description: str = ""


class RuntimeOrchestrationRealizedChild(SDLModel):
    """An observed, realized child workload spawned by the authority."""

    workload_id: str
    image_ref: str = ""
    count: int | str | None = None
    evidence_ref: str = ""
    description: str = ""

    @field_validator("workload_id")
    @classmethod
    def validate_workload_id(cls, v: str) -> str:
        return require_symbol(v, field_name="workload_id")

    @field_validator("count", mode="before")
    @classmethod
    def parse_count(cls, v: object) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name="count") if v is not None else v


class RuntimeOrchestrationAuthority(SDLModel):
    """Node-scoped runtime inventory for a container-spawn control authority.

    ``control_interface_ref`` is the ``control_interface_id`` of a same-node
    ``RuntimeControlInterface`` (the docker.sock shell), resolved by
    ``validator.py`` — referenced, never duplicated. The privilege classification
    is descriptive and does not select or authorize a privileged operation.
    """

    orchestration_authority_id: str
    control_interface_ref: str = ""
    engine: GovernedVocabulary[RuntimeOrchestrationEngine] = RuntimeOrchestrationEngine.UNKNOWN
    engine_api_version: str = ""
    name: str = ""
    scope: RuntimeOrchestrationScope | None = None
    spawn_templates: list[RuntimeOrchestrationSpawnTemplate] = Field(default_factory=list)
    lifecycle_policy: RuntimeOrchestrationLifecyclePolicy | None = None
    realized_children: list[RuntimeOrchestrationRealizedChild] = Field(default_factory=list)
    privilege_class: GovernedVocabulary[RuntimeOrchestrationPrivilegeClass] = RuntimeOrchestrationPrivilegeClass.UNKNOWN
    description: str = ""

    @field_validator("orchestration_authority_id")
    @classmethod
    def validate_orchestration_authority_id(cls, v: str) -> str:
        return require_symbol(v, field_name="orchestration_authority_id")

    @field_validator("engine", mode="before")
    @classmethod
    def normalize_engine(cls, v: RuntimeOrchestrationEngine | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeOrchestrationEngine, field_name="engine")

    @field_validator("privilege_class", mode="before")
    @classmethod
    def normalize_privilege_class(cls, v: RuntimeOrchestrationPrivilegeClass | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeOrchestrationPrivilegeClass, field_name="privilege_class")

    @model_validator(mode="after")
    def validate_orchestration_authority(self) -> "RuntimeOrchestrationAuthority":
        self._reject_duplicate_local_ref_ids()
        return self

    # ------------------------------------------------------------------ #
    # Local stable-id uniqueness
    # ------------------------------------------------------------------ #

    def _reject_duplicate_local_ref_ids(self) -> None:
        entries: list[tuple[str, str]] = [("orchestration_authority_id", self.orchestration_authority_id)]
        for label, collection_name in (
            ("template_id", "spawn_templates"),
            ("workload_id", "realized_children"),
        ):
            entries.extend((label, getattr(item, label)) for item in getattr(self, collection_name))

        seen: dict[str, str] = {}
        for label, value in entries:
            prior = seen.get(value)
            if prior is not None:
                raise ValueError(
                    f"Duplicate runtime orchestration stable id '{value}' in authority "
                    f"'{self.orchestration_authority_id}' across {prior} and {label}"
                )
            seen[value] = label
