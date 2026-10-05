"""Lower complete lexical policies onto existing compiled resource owners."""

from raes.observation_scope import semantic_scope_namespace
from raes.scenario import InstantiatedScenario
from raes_contracts.execution_policy import EffectiveExecutionPolicy, resolve_execution_policy


def _pointer(section: str, name: str) -> str:
    escaped = name.replace("~", "~0").replace("/", "~1")
    return f"/{section}/{escaped}"


def compile_execution_policies(
    scenario: InstantiatedScenario, parts: dict[str, object]
) -> dict[str, tuple[EffectiveExecutionPolicy, ...]]:
    document = scenario.execution_policy
    if document is None:
        return {}
    payload = scenario.model_dump(mode="python")
    result = {}
    # Binding occurrences use their application site. Reusable workflow
    # definitions retain their own lexical namespace, including through calls.
    groups = {
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
    for group, section in groups.items():
        for address, resource in parts.get(group, {}).items():
            name = getattr(resource, "node_name", "") if section == "nodes" else resource.name
            name = name or resource.name
            if group == "domain_controller_placements":
                name = resource.domain_topology.domain_id
            elif group == "content_placements":
                name = resource.content_name
            elif group == "account_placements":
                name = resource.account_name
            pointer = _pointer(section, name)
            namespace = semantic_scope_namespace(payload, pointer)
            policies = []
            effective = resolve_execution_policy(
                document, pointer, namespace=namespace, evidence_requirements=scenario.evidence_requirements
            )
            if group in {"feature_bindings", "condition_bindings", "inject_bindings"}:
                kind = group.removesuffix("_bindings")
                declaration = _pointer(kind + "s", getattr(resource, kind + "_name"))
                defined = resolve_execution_policy(
                    document,
                    declaration,
                    namespace=semantic_scope_namespace(payload, declaration),
                    evidence_requirements=scenario.evidence_requirements,
                )
                occurrence = (
                    pointer
                    + "/"
                    + kind
                    + "s/"
                    + getattr(resource, kind + "_name").replace("~", "~0").replace("/", "~1")
                )
                application = resolve_execution_policy(
                    document, occurrence, namespace=namespace, evidence_requirements=scenario.evidence_requirements
                )
                # An explicit application scope overrides the complete definition
                # policy. An ambient caller default does not rebind it.
                effective = (
                    application if application is not None and "#/nodes" in application.governing_scope else defined
                )
            if effective is not None:
                policies.append(effective)
            if section == "workflows":
                for step_name in scenario.workflows[name].steps:
                    step_pointer = (
                        _pointer("workflows", name) + "/steps/" + step_name.replace("~", "~0").replace("/", "~1")
                    )
                    effective = resolve_execution_policy(
                        document,
                        step_pointer,
                        namespace=namespace,
                        evidence_requirements=scenario.evidence_requirements,
                    )
                    if effective is not None and "/steps" in effective.governing_scope:
                        policies.append(effective)
            if policies:
                result[address] = tuple(policies)
    return result
