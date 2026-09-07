"""Top-level compile pipeline: assemble the RuntimeModel from domain compilers."""

from collections.abc import Mapping

from raes import build_declaration_index
from raes.instantiate import admit_instantiated_scenario, instantiate_scenario
from raes.scenario import ExpandedScenario, InstantiatedScenario, Scenario
from raes.semantics.domain_topology import (
    analyze_domain_topology,
)
from raes.value_parsing import is_variable_ref

from ..capture_admission import compile_scenario_capture_demands
from ..models import (
    Diagnostic,
    RuntimeModel,
)
from .evaluation import _compile_assertions, _compile_condition_bindings, _compile_propositions
from .objectives import _compile_objectives
from .orchestration import (
    _compile_events,
    _compile_inject_bindings,
    _compile_inject_runtimes,
    _compile_scripts,
    _compile_stories,
)
from .participant_behaviors import (
    _compile_behavior_specifications,
    _compile_participant_behaviors,
    _compile_tool_affordances,
)
from .participant_contracts import (
    _compile_action_contracts,
    _compile_observation_boundaries,
    _compile_outcome_interpretation_rules,
)
from .participant_inject_deliveries import _compile_participant_inject_deliveries
from .placement import (
    _compile_account_placements,
    _compile_content_placements,
    _compile_domain_controller_placements,
)
from .provisioning import (
    _compile_capability_constraints,
    _compile_feature_bindings,
    _compile_node_runtimes,
    _compile_templates,
    _metadata_specs,
)
from .realization_requirements import _compile_realization
from .stateful_resources import _compile_generated_artifacts, _compile_persistent_volumes
from .time_model import compile_time_model
from .workflows import _compile_workflows


def compile_scenario_runtime_model(
    scenario: Scenario | ExpandedScenario | InstantiatedScenario,
    *,
    parameters: Mapping[str, object] | None = None,
    profile: str | None = None,
) -> RuntimeModel:
    """Instantiate an SDL scenario and compile it into runtime artifacts."""

    concrete_scenario = (
        scenario
        if isinstance(scenario, InstantiatedScenario)
        else instantiate_scenario(scenario, parameters=parameters, profile=profile)
    )
    return compile_runtime_model(concrete_scenario)


def compile_runtime_model(scenario: Scenario | ExpandedScenario | InstantiatedScenario) -> RuntimeModel:
    """Compile an SDL scenario into bound runtime objects."""

    scenario = (
        admit_instantiated_scenario(scenario)
        if isinstance(scenario, InstantiatedScenario)
        else instantiate_scenario(scenario)
    )
    build_declaration_index(scenario)
    diagnostics: list[Diagnostic] = []
    domain_analysis = analyze_domain_topology(
        identity_domains=scenario.identity_domains,
        nodes=scenario.nodes,
        accounts=scenario.accounts,
        relationships=scenario.relationships,
        is_unresolved=is_variable_ref,
    )

    (
        feature_templates,
        condition_templates,
        inject_templates,
        vulnerability_templates,
    ) = _compile_templates(scenario)
    entity_specs, agent_specs, relationship_specs = _metadata_specs(scenario)
    time_model = compile_time_model(scenario)

    networks, node_deployments = _compile_node_runtimes(scenario, diagnostics, domain_analysis)
    feature_bindings = _compile_feature_bindings(scenario, feature_templates, diagnostics)
    propositions = _compile_propositions(scenario)
    assertions = _compile_assertions(scenario)
    condition_bindings = _compile_condition_bindings(
        scenario,
        condition_templates,
        propositions,
        diagnostics,
    )
    injects = _compile_inject_runtimes(inject_templates)
    inject_bindings = _compile_inject_bindings(scenario, inject_templates, diagnostics)
    content_placements = _compile_content_placements(scenario, diagnostics)
    domain_controller_placements = _compile_domain_controller_placements(scenario, domain_analysis)
    account_placements = _compile_account_placements(
        scenario,
        diagnostics,
        domain_analysis,
        domain_controller_placements,
    )
    generated_artifacts = _compile_generated_artifacts(scenario)
    persistent_volumes = _compile_persistent_volumes(scenario)
    action_contracts = _compile_action_contracts(scenario)
    observation_boundaries = _compile_observation_boundaries(scenario)
    outcome_interpretation_rules = _compile_outcome_interpretation_rules(scenario)
    participant_behaviors = _compile_participant_behaviors(scenario, diagnostics)
    behavior_specifications = _compile_behavior_specifications(scenario, diagnostics)
    tool_affordances = _compile_tool_affordances(scenario, diagnostics)
    participant_inject_deliveries = _compile_participant_inject_deliveries(scenario)
    events = _compile_events(scenario, assertions, injects, inject_bindings, diagnostics)
    scripts = _compile_scripts(scenario, diagnostics)
    stories = _compile_stories(scenario, diagnostics)
    objectives = _compile_objectives(scenario, assertions, diagnostics)
    workflows = _compile_workflows(scenario, assertions, diagnostics)
    realization_requirements, realization_authority = _compile_realization(scenario, domain_analysis)

    return RuntimeModel(
        scenario_name=scenario.name,
        feature_templates=feature_templates,
        condition_templates=condition_templates,
        inject_templates=inject_templates,
        vulnerability_templates=vulnerability_templates,
        entity_specs=entity_specs,
        agent_specs=agent_specs,
        relationship_specs=relationship_specs,
        time_model=time_model,
        capability_constraints=_compile_capability_constraints(scenario),
        capture_demands=compile_scenario_capture_demands(scenario),
        networks=networks,
        node_deployments=node_deployments,
        feature_bindings=feature_bindings,
        propositions=propositions,
        assertions=assertions,
        condition_bindings=condition_bindings,
        injects=injects,
        inject_bindings=inject_bindings,
        content_placements=content_placements,
        domain_controller_placements=domain_controller_placements,
        account_placements=account_placements,
        generated_artifacts=generated_artifacts,
        persistent_volumes=persistent_volumes,
        action_contracts=action_contracts,
        observation_boundaries=observation_boundaries,
        outcome_interpretation_rules=outcome_interpretation_rules,
        participant_behaviors=participant_behaviors,
        behavior_specifications=behavior_specifications,
        tool_affordances=tool_affordances,
        participant_inject_deliveries=participant_inject_deliveries,
        events=events,
        scripts=scripts,
        stories=stories,
        workflows=workflows,
        objectives=objectives,
        diagnostics=diagnostics,
        realization_requirements=realization_requirements,
        realization_authority=realization_authority,
        realization_instance=scenario,
    )
