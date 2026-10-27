"""Lazy access to schema assembly, which depends on completed SDL models."""


def schema_bundle() -> dict[str, dict[str, object]]:
    """Load SDL-dependent schema assembly only when a bundle is requested."""
    from .bundle import schema_bundle as build_bundle

    return build_bundle()
