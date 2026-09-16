"""Preserve imported author restrictions through the canonical rewrite seam."""

from raes_contracts.augmentation_scope import AugmentationScopePolicy, AugmentationScopeRule
from raes_contracts.realization_structure import semantic_address_contains

from .._composition_provenance import prefixed_scope_pointer
from ..observation_scope import resolve_observation_scope


def rewrite_augmentation_scope(payload: dict, symbols: dict, namespace: str) -> None:
    raw = payload.get("augmentation_scope")
    if raw is None:
        return
    policy = AugmentationScopePolicy.model_validate(raw)
    prefix = (namespace,) if namespace else ()
    scopes = [
        AugmentationScopeRule(
            scope=_rewritten_scope(rule.scope, payload, symbols),
            permission=rule.permission,
            namespace=(*prefix, *rule.namespace),
        )
        for rule in policy.scopes
    ]
    if namespace and not any(rule.namespace == prefix and not rule.scope for rule in scopes):
        scopes.insert(0, AugmentationScopeRule(scope="", permission=policy.default, namespace=prefix))
    payload["augmentation_scope"] = AugmentationScopePolicy(
        default="open" if namespace else policy.default, scopes=tuple(scopes)
    ).model_dump(mode="python")


def _rewritten_scope(scope: str, payload: dict, symbols: dict) -> str:
    if not scope.startswith("/forwarding_agents/"):
        return prefixed_scope_pointer(scope, symbols=symbols)
    found, canonical = resolve_observation_scope(payload, scope)
    if found:
        agents = payload.get("forwarding_agents", [])
        for index, _agent in enumerate(agents):
            _, parent = resolve_observation_scope(payload, f"/forwarding_agents/{index}")
            if semantic_address_contains(parent, canonical):
                renamed = {
                    **payload,
                    "forwarding_agents": [
                        {
                            **item,
                            "forwarding_agent_id": symbols["forwarding_agents"].get(
                                item["forwarding_agent_id"], item["forwarding_agent_id"]
                            ),
                        }
                        for item in agents
                    ],
                }
                _, target = resolve_observation_scope(renamed, f"/forwarding_agents/{index}" + canonical[len(parent) :])
                if target is not None:
                    return target
    raise ValueError("augmentation scope has no stable forwarding-agent identity")


def merge_augmentation_scope(root: dict, incoming: dict) -> None:
    if incoming.get("augmentation_scope") is None:
        return
    local = AugmentationScopePolicy.model_validate(root.get("augmentation_scope") or {})
    imported = AugmentationScopePolicy.model_validate(incoming["augmentation_scope"])
    root["augmentation_scope"] = AugmentationScopePolicy(
        default=local.default, scopes=(*local.scopes, *imported.scopes)
    ).model_dump(mode="python")
