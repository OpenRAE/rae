"""Reconstruct the portable node context for the incumbent semantic validator."""

from collections.abc import Mapping

from pydantic import TypeAdapter
from raes import SDLValidationError
from raes.nodes import Node
from raes.scenario import ExpandedScenario
from raes.stateful_resources import PersistentVolume
from raes.validator import SemanticValidator
from raes_contracts.canonical import canonical_json_digest

from ..compiler.stateful_resources import _environment_consumer_projections
from ..semantics.realization_concern_observations import typed_runtime_observation_shape
from .stateful_admission import _canonical_consumers, _validated_generated_artifact_payload


def validate_prepared_node_semantics(live: Mapping[str, object]) -> None:
    """Check references and unresolved inputs without reconstructing author provenance."""

    context = {"nodes": {}, "infrastructure": {}, "generated_artifacts": {}, "persistent_volumes": {}, "accounts": {}}
    node_specs = {
        entry.address: entry.payload["spec"] for entry in live.values() if entry.resource_type in {"node", "network"}
    }
    for entry in live.values():
        name = entry.payload.get("name")
        spec = entry.payload.get("spec", {})
        if entry.resource_type in {"node", "network"}:
            context["nodes"][name] = typed_runtime_observation_shape(spec["node"], adapter=TypeAdapter(Node))
            context["infrastructure"][name] = spec["infrastructure"]
        elif entry.resource_type == "generated-artifact":
            artifact, _ = _validated_generated_artifact_payload(address=entry.address, spec=spec, node_specs=node_specs)
            context["generated_artifacts"][name] = artifact
        elif entry.resource_type == "persistent-volume":
            context["persistent_volumes"][name] = PersistentVolume.model_validate(
                {**spec, "consumers": _canonical_consumers(spec.get("consumers", []))}
            )
        elif entry.resource_type == "account-placement":
            context["accounts"][name] = spec
    scenario = ExpandedScenario(name="prepared-node-context", **context)
    try:
        SemanticValidator(scenario).validate_node_realization()
    except SDLValidationError:
        raise ValueError("prepared node context does not satisfy native semantics") from None
    for entry in live.values():
        if entry.resource_type == "generated-artifact":
            required = _environment_consumer_projections(scenario, entry.payload["name"])
            granted = entry.payload["spec"].get("environment_consumers", [])
            if sorted(required, key=canonical_json_digest) != sorted(granted, key=canonical_json_digest):
                raise ValueError("node selection cannot grant new generated-artifact delivery authority")
