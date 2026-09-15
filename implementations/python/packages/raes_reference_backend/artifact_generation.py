"""Installed digest generator and private in-process consumer projections."""

import hashlib

from raes_contracts.artifact_generation import DigestArtifactParameters
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_contracts.random_value_generation import render_random_value


def _generated_bytes(operation: object) -> bytes:
    spec = operation.payload["spec"]
    if spec.get("generator") == "random_value":
        # Backend-owned cryptographically secure realization of the recipe
        # (issue #1276). Generation runs only for the create/update reconciliation
        # transition (see generated_artifact_projections), so a resume/retry that
        # reconciles as UNCHANGED retains the existing value for the active scope.
        recipe = spec.get("random_value")
        if not isinstance(recipe, dict):
            raise ValueError("random_value generated artifact is missing its recipe")
        return render_random_value(recipe).encode("utf-8")
    bindings = [item for item in operation.profile_bindings if item.owner.context == "artifact-generation"]
    if len(bindings) != 1:
        raise ValueError("Reference generation requires exactly one typed generator selection")
    parameters = DigestArtifactParameters.model_validate(bindings[0].value)
    return hashlib.sha256(parameters.seed.encode("utf-8")).hexdigest().encode("ascii")


def generated_artifact_projections(plan: ProvisioningPlan) -> dict[tuple[str, str, str], bytes]:
    projections = {}
    for operation in plan.operations:
        # Only the create/update reconciliation transition generates; an UNCHANGED
        # op retains the backend-owned active value, and DELETE revokes it. This
        # keeps a per_run/once value stable across resume/retry within its scope
        # while a new authoritative scope reconciles as an update (issue #1276).
        if operation.resource_type != "generated-artifact" or operation.action not in (
            ChangeAction.CREATE,
            ChangeAction.UPDATE,
        ):
            continue
        projections.update(_consumer_projections(operation, _generated_bytes(operation)))
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
