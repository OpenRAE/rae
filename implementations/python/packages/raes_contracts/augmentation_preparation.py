"""Pure prospective effects, bound to the existing source and operation identities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from ._base import ContractModel
from .canonical import canonical_json_digest
from .json_ingress import parse_bounded_json_object
from .materialization import MATERIALIZATION_MAX_BYTES, MaterializationDigest
from .observation_demand import SemanticScope
from .realization_structure import validate_realization_value
from .runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

if TYPE_CHECKING:
    from .contracts import BackendManifestV2Model
    from .planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
    from .runtime_state import RuntimeSnapshot

RequirementReference = Annotated[
    str, Field(min_length=1, max_length=4096, pattern=r"^(?:backend-operational|/(?:[^~]|~[01])*)$")
]


class AugmentationEffect(ContractModel):
    """Explain an existing materialization difference, never duplicate world values."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    field_pointer: SemanticScope
    requirement_refs: tuple[RequirementReference, ...] = Field(min_length=1, max_length=64)
    affected_scopes: tuple[SemanticScope, ...] = Field(min_length=1, max_length=256)


class AugmentationPreparation(ContractModel):
    """Read-only complete prospective common SDL content, not an attestation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_id: Literal["backend-augmentation-scope-v1"] = "backend-augmentation-scope-v1"
    coverage_profile: Literal["raes-materialization-effects/v1"] = "raes-materialization-effects/v1"
    binding_digest: MaterializationDigest
    content: str = Field(min_length=1, max_length=MATERIALIZATION_MAX_BYTES)
    effects: tuple[AugmentationEffect, ...] = Field(default=(), max_length=4096)

    @model_validator(mode="after")
    def _bounded_content(self) -> AugmentationPreparation:
        if sum(1 + len(effect.requirement_refs) + len(effect.affected_scopes) for effect in self.effects) > 16384:
            raise ValueError("prospective scope resolution exceeds the aggregate work budget")
        value = parse_bounded_json_object(self.content, max_bytes=MATERIALIZATION_MAX_BYTES)
        if not validate_realization_value(value, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant:
            raise ValueError("prospective SDL exceeds portable bounds")
        if len({effect.field_pointer for effect in self.effects}) != len(self.effects):
            raise ValueError("prospective effect identities must be unique")
        if not validate_realization_value(
            self.effects, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True
        ).conformant:
            raise ValueError("prospective effect metadata exceeds portable bounds")
        return self

    @classmethod
    def for_request(
        cls,
        request: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
        manifest: BackendManifestV2Model,
        previous: RuntimeSnapshot,
        *,
        content: str,
        effects: tuple[AugmentationEffect, ...] = (),
    ) -> AugmentationPreparation:
        return cls(
            binding_digest=augmentation_binding_digest(request, manifest, previous), content=content, effects=effects
        )


def augmentation_binding_digest(
    request: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
    manifest: BackendManifestV2Model,
    previous: RuntimeSnapshot,
) -> str:
    """Seal the whole plan, including source, run, operation and producer identity."""
    from .plan_projection import runtime_plan_digest
    from .realization_preparation import preparation_snapshot_digest

    if request.materialization_source is None or not request.operation_id or manifest.realization_envelope is None:
        raise ValueError("augmentation preparation requires bound source and execution identity")
    return canonical_json_digest(
        {
            "profile": "backend-augmentation-scope-v1",
            "plan": runtime_plan_digest(request),
            "predecessor": preparation_snapshot_digest(previous),
            "manifest": manifest.model_dump(mode="json"),
        }
    )
