"""Addition permission over existing semantic scopes, independent of realization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from ._base import ContractModel
from .observation_demand import SemanticScope
from .realization_structure import semantic_address_contains

AUGMENTATION_SCOPE_CONTRACT = "backend-augmentation-scope-v1"
AugmentationPermission = Literal["open", "closed"]
ScopeNamespacePart = Annotated[str, Field(pattern=r"^(?:[a-z0-9][a-z0-9_-]{0,63}|__private)$", max_length=64)]


class AugmentationScopeRule(ContractModel):
    """One explicit node or concern permission, using a semantic address."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    scope: SemanticScope
    permission: AugmentationPermission
    namespace: tuple[ScopeNamespacePart, ...] = Field(default=(), max_length=31)


class AugmentationScopePolicy(ContractModel):
    """Authors opt into restrictions; omission imposes no new authoring burden."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    default: AugmentationPermission = "open"
    scopes: tuple[AugmentationScopeRule, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def _unique_scopes(self) -> AugmentationScopePolicy:
        if len({(rule.namespace, rule.scope) for rule in self.scopes}) != len(self.scopes):
            raise ValueError("augmentation scopes must be unique; equal-specificity rules cannot conflict")
        return self


OptionalAugmentationScope = Annotated[
    AugmentationScopePolicy | None,
    Field(exclude_if=lambda value: value is None, json_schema_extra={"x-raes-realization-dimension": False}),
]


@dataclass(frozen=True)
class AugmentationScopeDecision:
    permission: AugmentationPermission
    governing_scope: str


def effective_augmentation_scope(
    policy: AugmentationScopePolicy | None, scope: str, *, namespace: tuple[str, ...] | None = None
) -> AugmentationScopeDecision:
    """Resolve one canonical location; an explicit child overrides its default."""

    if policy is None:
        return AugmentationScopeDecision("open", "")
    tokens = scope.split("/")
    owner = (
        namespace
        if namespace is not None
        else (tuple(tokens[2].replace("~1", "/").replace("~0", "~").split(".")[:-1]) if len(tokens) > 2 else ())
    )
    layers: dict[tuple[str, ...], list[AugmentationScopeRule]] = {(): []}
    for rule in policy.scopes:
        if owner[: len(rule.namespace)] == rule.namespace and semantic_address_contains(rule.scope, scope):
            layers.setdefault(rule.namespace, []).append(rule)
    decision = AugmentationScopeDecision(policy.default, "")
    for namespace, rules in sorted(layers.items()):
        if rules:
            rule = max(rules, key=lambda item: len(item.scope.split("/")))
            decision = AugmentationScopeDecision(rule.permission, rule.scope)
        elif namespace:
            continue
        if decision.permission == "closed":
            return decision
    return decision
