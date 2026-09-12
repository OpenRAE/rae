"""One local-only resource registry for profile schema resolution."""

from typing import NoReturn

from jsonschema_specifications import REGISTRY as META_SCHEMAS
from referencing import Registry
from referencing.exceptions import NoSuchResource
from referencing.jsonschema import DRAFT202012, SchemaRegistry


def _deny_retrieval(uri: str) -> NoReturn:
    raise NoSuchResource(ref=uri)


# Only installed specification resources are preloaded. The callback must never
# delegate to the validator's default HTTP/file retrieval behavior.
_OFFLINE_REGISTRY: SchemaRegistry = Registry(retrieve=_deny_retrieval).with_resources(META_SCHEMAS.items())


def profile_schema_registry(schema: dict[str, object] | None = None) -> SchemaRegistry:
    """Bind the admitted document locally, without discovering other resources."""

    if schema is None:
        return _OFFLINE_REGISTRY
    return _OFFLINE_REGISTRY.with_resource(str(schema["$id"]), DRAFT202012.create_resource(schema))
