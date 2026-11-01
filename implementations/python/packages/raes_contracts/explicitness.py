"""SEM-218 explicitness classes and provenance values."""

from enum import Enum


class ExplicitnessClass(str, Enum):
    """SEM-218 author-intent class for a declaration."""

    EXACT = "exact"
    CONSTRAINED = "constrained"
    OPEN = "open"


class ExplicitnessProvenance(str, Enum):
    """Where the classified value came from in the SDL lifecycle."""

    AUTHOR_DECLARED = "author-declared"
    PROCESSOR_DERIVED = "processor-derived"
    BACKEND_REALIZED = "backend-realized"


__all__ = ["ExplicitnessClass", "ExplicitnessProvenance"]
