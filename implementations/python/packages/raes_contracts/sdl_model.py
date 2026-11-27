"""The base class of authored SDL models.

Contract models that carry authored values, such as evidence requirements and
inject deliveries, extend the same class as the SDL language models.
"""

from pydantic import BaseModel, ConfigDict


class SDLModel(BaseModel):
    """Base for all SDL Pydantic models."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


__all__ = ["SDLModel"]
