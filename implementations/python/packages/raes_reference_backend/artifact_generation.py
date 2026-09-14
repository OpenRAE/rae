"""Installed digest generator and private in-process consumer projections."""

import hashlib

from raes_contracts.artifact_generation import DigestArtifactParameters
from raes_contracts.planning import ChangeAction, ProvisioningPlan


def generated_artifact_projections(plan: ProvisioningPlan) -> dict[tuple[str, str, str], bytes]:
    projections = {}
    for operation in plan.operations:
        if operation.resource_type != "generated-artifact" or operation.action is ChangeAction.DELETE:
            continue
        bindings = [item for item in operation.profile_bindings if item.owner.context == "artifact-generation"]
        if len(bindings) != 1:
            raise ValueError("Reference generation requires exactly one typed generator selection")
        parameters = DigestArtifactParameters.model_validate(bindings[0].value)
        generated = hashlib.sha256(parameters.seed.encode("utf-8")).hexdigest().encode("ascii")
        projections.update(_consumer_projections(operation, generated))
    return projections


def _consumer_projections(operation: object, generated: bytes) -> dict[tuple[str, str, str], bytes]:
    projections = {}
    spec = operation.payload["spec"]
    outputs = {item["name"]: item for item in spec["outputs"]}
    if spec.get("environment_consumers"):
        raise ValueError("Reference digest generator implements mount delivery only")
    for consumer in spec["consumers"]:
        if consumer["access_mode"] != "read_only" or not consumer.get("selected_outputs"):
            raise ValueError("Reference generation requires an explicit read-only consumer projection")
        for selected in consumer["selected_outputs"]:
            output = outputs[selected]
            if output.get("disposition") == "producer_private":
                raise ValueError("A consumer cannot receive a producer-private output")
            projections[(operation.address, consumer["target_address"], selected)] = generated
    return projections
