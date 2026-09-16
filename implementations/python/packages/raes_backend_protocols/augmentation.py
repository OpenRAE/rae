"""Backend adapter for the dependency-neutral prospective-effects contract."""

from typing import Protocol

from raes_contracts.augmentation_preparation import AugmentationEffect, AugmentationPreparation
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
from raes_contracts.runtime_state import RuntimeSnapshot

from .capabilities import BackendManifest
from .manifest import backend_manifest_v2_model

AugmentationPlan = ProvisioningPlan | OrchestrationPlan | EvaluationPlan


class AugmentationPreparingProducer(Protocol):
    """Pure preparation; includes every in-world effect of the producer's phase."""

    def prepare_augmentation(self, plan: AugmentationPlan, snapshot: RuntimeSnapshot) -> AugmentationPreparation: ...


def augmentation_preparation(
    request: AugmentationPlan,
    manifest: BackendManifest,
    previous: RuntimeSnapshot,
    *,
    content: str,
    effects: tuple[AugmentationEffect, ...] = (),
) -> AugmentationPreparation:
    return AugmentationPreparation.for_request(
        request, backend_manifest_v2_model(manifest), previous, content=content, effects=effects
    )
