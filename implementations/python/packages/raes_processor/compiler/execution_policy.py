"""Lower complete lexical policies onto existing compiled resource owners."""

from dataclasses import dataclass
from typing import Any, cast

from raes.observation_scope import semantic_scope_namespace
from raes.scenario import InstantiatedScenario
from raes_contracts.execution_policy import EffectiveExecutionPolicy, ExecutionPolicyDocument, resolve_execution_policy

from ..models.resources import DomainControllerPlacement, ResolvedResource

_GROUP_SECTIONS = {
    "networks": "nodes",
    "node_deployments": "nodes",
    "feature_bindings": "nodes",
    "condition_bindings": "nodes",
    "inject_bindings": "nodes",
    "domain_controller_placements": "identity_domains",
    "account_placements": "accounts",
    "content_placements": "content",
    "generated_artifacts": "generated_artifacts",
    "persistent_volumes": "persistent_volumes",
    "injects": "injects",
    "events": "events",
    "scripts": "scripts",
    "stories": "stories",
    "workflows": "workflows",
    "propositions": "propositions",
    "assertions": "assertions",
    "objectives": "objectives",
}
_BINDING_GROUPS = frozenset({"feature_bindings", "condition_bindings", "inject_bindings"})


def _pointer(section: str, name: str) -> str:
    escaped = name.replace("~", "~0").replace("/", "~1")
    return f"/{section}/{escaped}"


def _resource_name(group: str, section: str, resource: ResolvedResource) -> str:
    if group == "domain_controller_placements":
        return cast(DomainControllerPlacement, resource).domain_topology.domain_id
    attributes = {"content_placements": "content_name", "account_placements": "account_name"}
    name = getattr(resource, attributes.get(group, "name"))
    return (getattr(resource, "node_name", "") or name) if section == "nodes" else name


@dataclass
class _PolicyResolver:
    scenario: InstantiatedScenario
    document: ExecutionPolicyDocument
    payload: dict[str, Any]

    def resolve(self, pointer: str, namespace: tuple[str, ...] | None = None) -> EffectiveExecutionPolicy | None:
        return resolve_execution_policy(
            self.document,
            pointer,
            namespace=semantic_scope_namespace(self.payload, pointer) if namespace is None else namespace,
            evidence_requirements=self.scenario.evidence_requirements,
        )

    def binding_policy(self, group: str, pointer: str, resource: ResolvedResource) -> EffectiveExecutionPolicy | None:
        kind = group.removesuffix("_bindings")
        name = getattr(resource, kind + "_name")
        defined = self.resolve(_pointer(kind + "s", name))
        occurrence = pointer + _pointer(kind + "s", name)
        application = self.resolve(occurrence, semantic_scope_namespace(self.payload, pointer))
        # An explicit application scope overrides the complete definition policy.
        # An ambient caller default does not rebind it.
        return application if application is not None and "#/nodes" in application.governing_scope else defined

    def workflow_step_policies(self, name: str, pointer: str) -> list[EffectiveExecutionPolicy]:
        policies = []
        namespace = semantic_scope_namespace(self.payload, pointer)
        for step_name in self.scenario.workflows[name].steps:
            effective = self.resolve(pointer + _pointer("steps", step_name), namespace)
            if effective is not None and "/steps" in effective.governing_scope:
                policies.append(effective)
        return policies

    def resource_policies(
        self, group: str, section: str, resource: ResolvedResource
    ) -> tuple[EffectiveExecutionPolicy, ...]:
        name = _resource_name(group, section, resource)
        pointer = _pointer(section, name)
        effective = self.binding_policy(group, pointer, resource) if group in _BINDING_GROUPS else self.resolve(pointer)
        policies = [effective] if effective is not None else []
        if section == "workflows":
            policies.extend(self.workflow_step_policies(name, pointer))
        return tuple(policies)


def compile_execution_policies(
    scenario: InstantiatedScenario, parts: dict[str, Any]
) -> dict[str, tuple[EffectiveExecutionPolicy, ...]]:
    document = scenario.execution_policy
    if document is None:
        return {}
    resolver = _PolicyResolver(scenario, document, scenario.model_dump(mode="python"))
    result = {}
    for group, section in _GROUP_SECTIONS.items():
        for address, resource in parts.get(group, {}).items():
            policies = resolver.resource_policies(group, section, resource)
            if policies:
                result[address] = policies
    return result
