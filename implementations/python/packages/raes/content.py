"""Content models — data placed into scenario systems.

Adapted from CyRIS ``copy_content`` and ``emulate_traffic_capture``
patterns. Represents files, datasets (email collections, DB records,
pcap files), and directory structures that exist within scenario
nodes as part of the environment state.

Examples: phishing lure emails in an Exchange mailbox, synthetic
customer records in a database, planted credentials in shared
directories, CTF flag files.
"""

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator
from raes_contracts.domain_profiles import DomainProfileBindingModel
from raes_contracts.profile_selections import profile_selection_binding

from ._base import SDLModel, normalize_enum_value, parse_bool_or_var
from ._identifiers import PortableIdentifier
from ._source import Source
from .runtime_values import reject_duplicates


class ContentType(str, Enum):
    """Kind of content placed into a system."""

    FILE = "file"
    DATASET = "dataset"
    DIRECTORY = "directory"


class ContentItem(SDLModel):
    """A single item within a dataset (e.g., one email, one record)."""

    name: PortableIdentifier
    display_name: str = ""
    tags: list[str] = Field(default_factory=list)
    description: str = ""


class ServiceMaterializationRequirements(SDLModel):
    """Exact portable operation, ownership, and readback requirements."""

    operation: Literal["ensure-owned-items"] = "ensure-owned-items"
    conflict_policy: Literal["reject-unowned-collision"] = "reject-unowned-collision"
    readback: Literal["canonical-content-digest"] = "canonical-content-digest"


class _ServiceMaterializationBase(SDLModel):
    """References and ownership shared by every closed service profile."""

    target_service_ref: str = Field(min_length=1)
    shared_service_relationship_ref: str = ""
    ordering_content_refs: list[str] = Field(default_factory=list)
    readback_assertion_refs: list[str] = Field(min_length=1)
    evidence_requirement_refs: list[str] = Field(min_length=1)
    observation_boundary_refs: list[str] = Field(min_length=1)

    @field_validator(
        "ordering_content_refs",
        "readback_assertion_refs",
        "evidence_requirement_refs",
        "observation_boundary_refs",
    )
    @classmethod
    def validate_references(cls, values: list[str], info: ValidationInfo) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError(f"{info.field_name} entries must be non-empty")
        reject_duplicates(
            values,
            label=info.field_name,
            container_label=info.field_name,
            skip_empty=False,
        )
        return values


class ServiceMaterialization(_ServiceMaterializationBase):
    """Portable control contract for placing content through a named service."""

    interface_profile: Literal["service-content"] = "service-content"
    profile_version: Literal["1"] = "1"
    requirements: ServiceMaterializationRequirements


class SearchIndexFieldSemantic(str, Enum):
    """Portable top-level search-index field behavior."""

    EXACT_MATCH = "exact-token"
    FULL_TEXT = "full-text"
    INTEGER = "integer"
    TEMPORAL = "temporal"
    BOOLEAN = "boolean"


class ServiceSearchIndexSchemaRequirements(SDLModel):
    """Exact portable search-index schema operation and readback."""

    operation: Literal["ensure-search-index-field-schema"] = "ensure-search-index-field-schema"
    conflict_policy: Literal["reject-unowned-collision"] = "reject-unowned-collision"
    readback: Literal["canonical-portable-field-schema-digest"] = "canonical-portable-field-schema-digest"
    field_semantics: dict[PortableIdentifier, SearchIndexFieldSemantic] = Field(min_length=1)


class ServiceSearchIndexSchemaMaterialization(_ServiceMaterializationBase):
    """Portable desired field schema for a named service-owned search index."""

    interface_profile: Literal["service-search-index-schema"]
    profile_version: Literal["1"] = "1"
    requirements: ServiceSearchIndexSchemaRequirements


ServiceMaterializationProfile = (
    Annotated[
        ServiceMaterialization | ServiceSearchIndexSchemaMaterialization,
        Field(discriminator="interface_profile"),
    ]
    | DomainProfileBindingModel
)


class Content(SDLModel):
    """Data or files placed into a scenario node.

    Supports three forms:

    - ``file``: A single file at a specific path, optionally with inline text.
    - ``dataset``: A collection of related items (emails, records, pcaps)
      delivered via a source package or listed as items.
    - ``directory``: A directory structure placed at a destination path.
    """

    type: ContentType
    description: str = ""
    target: str = ""
    path: str = ""
    destination: str = ""
    text: str | None = None
    source: Source | None = None
    format: str = ""
    items: list[ContentItem] = Field(default_factory=list)
    sensitive: bool | str = False
    tags: list[str] = Field(default_factory=list)
    service_materialization: ServiceMaterializationProfile | None = None

    @model_validator(mode="before")
    @classmethod
    def default_service_materialization_profile(cls, value: object) -> object:
        """Preserve the original service-content default across discrimination."""
        if not isinstance(value, dict):
            return value
        binding = value.get("service_materialization")
        if not isinstance(binding, dict):
            return value
        if profile_selection_binding(binding) is not None or "interface_profile" in binding:
            return value
        normalized = dict(value)
        normalized["service_materialization"] = {
            "interface_profile": "service-content",
            **binding,
        }
        return normalized

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: str) -> str:
        return normalize_enum_value(v)

    @field_validator("sensitive", mode="before")
    @classmethod
    def parse_sensitive(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="sensitive")

    def _validate_search_index_schema_content(self) -> bool:
        if not isinstance(
            self.service_materialization,
            ServiceSearchIndexSchemaMaterialization,
        ):
            return False
        if self.type != ContentType.DATASET:
            raise ValueError("Search-index schema materialization requires dataset content")
        if self.source is not None or self.items:
            raise ValueError("Search-index schema materialization must not carry source or items")
        return True

    def _validate_ordinary_dataset_content(self, *, is_search_index_schema: bool) -> None:
        if self.type != ContentType.DATASET or is_search_index_schema:
            return
        if not (self.source or self.items):
            raise ValueError("Dataset content requires either 'source' or non-empty 'items'")

    @model_validator(mode="after")
    def validate_type_requirements(self) -> "Content":
        """Require the minimum anchors needed to describe real content."""
        if not self.target:
            raise ValueError("Content requires 'target'")

        if self.type == ContentType.FILE and not self.path:
            raise ValueError("File content requires 'path'")

        is_search_index_schema = self._validate_search_index_schema_content()
        self._validate_ordinary_dataset_content(
            is_search_index_schema=is_search_index_schema,
        )

        if self.type == ContentType.DIRECTORY and not self.destination:
            raise ValueError("Directory content requires 'destination'")

        return self
