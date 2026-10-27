"""API-414 revision and evaluated capacity coordinates; no native authority."""

from collections.abc import Collection, Iterable
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from ..manifest_authority import PARTICIPANT_TOOL_FEATURES
from ..vocabulary import ParticipantFeatureSupportLevel
from .base import ContractModel
from .feature_support import ParticipantFeatureSupportModel
from .validators import _validate_unique_string_values

TOOL_PROFILE_SEMANTICS = "participant-tool-profile/v1"
_TOOL_LIMIT_FIELDS = ("max_bindings_per_profile", "max_participants_per_binding")
Capacity = Annotated[int, Field(strict=True, ge=1)]


class ParticipantToolProfilesModel(ContractModel):
    """Exact semantic revisions and machine-evaluated capacity, not prose limits."""

    model_config = ConfigDict(revalidate_instances="always")

    semantic_versions: list[Literal["participant-tool-profile/v1"]] = Field(
        min_length=1, json_schema_extra={"uniqueItems": True}
    )
    max_bindings_per_profile: Capacity | None = None
    max_participants_per_binding: Capacity | None = None

    @model_validator(mode="after")
    def _unique_versions(self) -> "ParticipantToolProfilesModel":
        _validate_unique_string_values("semantic_versions", self.semantic_versions)
        return self

    def capacity_refs(self) -> set[str]:
        return {f"tool_profiles.{name}" for name in _TOOL_LIMIT_FIELDS if getattr(self, name) is not None}


def validate_tool_feature_support(
    profiles: ParticipantToolProfilesModel | None,
    entries: Iterable[ParticipantFeatureSupportModel],
    supported_features: Collection[str],
) -> None:
    """Join the existing strength claims to their owning version and limits."""

    tool_entries = {entry.feature: entry for entry in entries if entry.feature in PARTICIPANT_TOOL_FEATURES}
    positive = {name for name, entry in tool_entries.items() if entry.support_level != "unsupported"}
    if positive and profiles is None:
        raise ValueError("positive tool support requires tool_profiles semantic versions")
    if profiles is not None and "tool_affordances" not in positive:
        raise ValueError("tool_profiles requires positive tool_affordances support")
    if positive != set(supported_features).intersection(PARTICIPANT_TOOL_FEATURES):
        raise ValueError("tool support presence and strength declarations must agree")
    if "scoped_tool_affordances" in positive and "tool_affordances" not in positive:
        raise ValueError("scoped tool support requires tool_affordances support")
    for entry in tool_entries.values():
        for refs in (entry.constraint_refs, entry.limitation_refs, entry.disclosure_refs, entry.evidence_refs):
            if any(not ref.strip() for ref in refs):
                raise ValueError("tool support references must contain non-whitespace text")
        if entry.support_level != ParticipantFeatureSupportLevel.UNSUPPORTED and (
            profiles is None or not set(entry.constraint_refs).issubset(profiles.capacity_refs())
        ):
            raise ValueError("tool support has an unevaluated constraint reference")
        if entry.support_level == ParticipantFeatureSupportLevel.BOUNDED:
            if (
                profiles is None
                or not profiles.capacity_refs()
                or set(entry.constraint_refs) != profiles.capacity_refs()
            ):
                raise ValueError("bounded tool support requires only the declared typed capacity constraints")


class ProcessorParticipantToolsModel(ParticipantToolProfilesModel):
    """Processor preservation claims use the existing API-407 support model."""

    feature_support: list[ParticipantFeatureSupportModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _tool_support(self) -> "ProcessorParticipantToolsModel":
        names = [entry.feature for entry in self.feature_support]
        _validate_unique_string_values("feature_support", names)
        if not set(names).issubset(PARTICIPANT_TOOL_FEATURES):
            raise ValueError("processor participant_tools accepts only governed tool features")
        positive = {entry.feature for entry in self.feature_support if entry.support_level != "unsupported"}
        validate_tool_feature_support(self, self.feature_support, positive)
        return self
