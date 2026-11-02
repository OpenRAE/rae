"""Reconstruct the portable node context for the incumbent semantic validator."""

from collections.abc import Mapping

from pydantic import TypeAdapter
from raes import SDLValidationError
from raes.content import Content
from raes.nodes import Node
from raes.scenario import ExpandedScenario
from raes.stateful_resources import PersistentVolume
from raes.validator import SemanticValidator
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.errors import InvalidInputError

from ..compiler.stateful_resources import _environment_consumer_projections
from ..semantics.realization_concern_observations import typed_runtime_observation_shape
from .stateful_admission import _canonical_consumers, _validated_generated_artifact_payload


def _closed_spec(entry: object, *, required: frozenset[str] = frozenset()) -> Mapping[str, object]:
    spec = entry.payload.get("spec", {})
    if not isinstance(spec, Mapping) or not required <= spec.keys():
        raise ValueError("prepared node context requires closed resource specifications")
    return spec


def _typed_context(live: Mapping[str, object]) -> ExpandedScenario:
    """Rebuild the typed context; a malformed payload raises ValueError or ValidationError (E3)."""

    context = {
        "nodes": {},
        "infrastructure": {},
        "generated_artifacts": {},
        "persistent_volumes": {},
        "accounts": {},
        "content": {},
    }
    node_specs = {
        entry.address: _closed_spec(entry, required=frozenset({"node", "infrastructure"}))
        for entry in live.values()
        if entry.resource_type in {"node", "network"}
    }
    for entry in live.values():
        name = entry.payload.get("name")
        if entry.resource_type in {"node", "network"}:
            spec = node_specs[entry.address]
            context["nodes"][name] = typed_runtime_observation_shape(spec["node"], adapter=TypeAdapter(Node))
            context["infrastructure"][name] = spec["infrastructure"]
        elif entry.resource_type == "generated-artifact":
            spec = entry.payload.get("spec", {})
            artifact, _ = _validated_generated_artifact_payload(address=entry.address, spec=spec, node_specs=node_specs)
            context["generated_artifacts"][name] = artifact
        elif entry.resource_type == "persistent-volume":
            spec = _closed_spec(entry)
            context["persistent_volumes"][name] = PersistentVolume.model_validate(
                {**spec, "consumers": _canonical_consumers(spec.get("consumers", []))}
            )
        elif entry.resource_type == "account-placement":
            context["accounts"][name] = entry.payload.get("spec", {})
        elif entry.resource_type == "content-placement":
            context["content"][name] = Content.model_validate(entry.payload.get("spec", {}))
    return ExpandedScenario(name="prepared-node-context", **context)


def validate_prepared_node_semantics(live: Mapping[str, object]) -> None:
    """Check references and unresolved inputs without reconstructing author provenance.

    Raise ``InvalidInputError`` when the prepared context is malformed or fails native semantics.
    """

    try:
        scenario = _typed_context(live)
    except ValueError as exc:
        raise InvalidInputError("prepared node context failed typed validation") from exc
    try:
        SemanticValidator(scenario).validate_node_realization()
    except SDLValidationError as exc:
        raise InvalidInputError("prepared node context does not satisfy native semantics") from exc
    for entry in live.values():
        if entry.resource_type == "generated-artifact":
            required = _environment_consumer_projections(scenario, entry.payload["name"])
            granted = entry.payload["spec"].get("environment_consumers", [])
            if sorted(required, key=canonical_json_digest) != sorted(granted, key=canonical_json_digest):
                raise InvalidInputError("node selection cannot grant new generated-artifact delivery authority")
