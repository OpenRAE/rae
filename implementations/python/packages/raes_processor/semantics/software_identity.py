"""Identity selection for the legacy exact-package software refinement."""

from collections.abc import Mapping, Sequence

from raes.runtime_configuration import RuntimeConfiguration


def package_collection_identity(packages: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    """Use architecture when needed to disambiguate exact package coordinates.

    Unique manager/name rows retain the incumbent identity, including delegated
    architecture. Repeated coordinates require explicit architecture; ambiguity
    is rejected by the bounded collection normalizer, never matched by position.
    """

    coordinates = {(item.get("manager"), item.get("name")) for item in packages}
    return ("manager", "name", "architecture") if len(coordinates) != len(packages) else ("manager", "name")


def validate_returned_software_references(payload: Mapping[str, object]) -> None:
    """Check cross-collection links without reading unrelated runtime families."""

    runtime = payload
    for key in ("spec", "node", "runtime"):
        if not isinstance(runtime, Mapping):
            return
        runtime = runtime.get(key)
    if isinstance(runtime, Mapping) and runtime.get("software_components"):
        RuntimeConfiguration.model_validate(
            {
                key: runtime[key]
                for key in (
                    "software_components",
                    "packages",
                    "repository_state",
                )
                if key in runtime
            }
        )
