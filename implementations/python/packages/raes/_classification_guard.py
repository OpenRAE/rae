"""Bounded diagnostics for removed classification syntax at typed SDL ingress."""

from collections.abc import Mapping
from typing import ClassVar

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from ._base import SDLModel

CLASSIFICATION_MIGRATION_CODE = "sdl.classification-migration-required"
CLASSIFICATION_MIGRATION_MESSAGE = (
    "Explicit classification migration is required; use migrate_sdl_classifications() "
    "with authored assertion context and pinned scheme snapshots. "
    "See docs/migration/external-classifications.md."
)


class LegacyClassificationGuard(SDLModel):
    """Reject historical fields without including their values in diagnostics."""

    legacy_classification_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_classifications(cls, value: object) -> object:
        if isinstance(value, Mapping) and any(field in value for field in cls.legacy_classification_fields):
            raise PydanticCustomError(CLASSIFICATION_MIGRATION_CODE, CLASSIFICATION_MIGRATION_MESSAGE)
        return value
