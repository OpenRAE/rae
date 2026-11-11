"""Processor capability coordinates for the published v2 manifest."""

from __future__ import annotations

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..manifest_authority import (
    PROCESSOR_SUPPORTED_SDL_VERSION_IDS,
    validate_processor_supported_sdl_versions,
)
from ..vocabulary import ProcessorFeature
from .base import ContractModel, NonEmptyString
from .participant_tool_support import ProcessorParticipantToolsModel


class ProcessorCapabilitiesV2Model(ContractModel):
    supported_sdl_versions: list[NonEmptyString] = Field(min_length=1)
    supported_features: list[ProcessorFeature] = Field(min_length=1)
    participant_tools: ProcessorParticipantToolsModel | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def _validate_declared_authority(self) -> ProcessorCapabilitiesV2Model:
        validate_processor_supported_sdl_versions(self.supported_sdl_versions)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["properties"]["supported_sdl_versions"]["items"]["enum"] = list(PROCESSOR_SUPPORTED_SDL_VERSION_IDS)
        return json_schema
