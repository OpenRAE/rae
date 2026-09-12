"""Top-level compile pipeline: assemble the RuntimeModel from domain compilers."""

from collections.abc import Mapping

from raes import build_declaration_index
from raes.instantiate import admit_instantiated_scenario, instantiate_scenario
from raes.scenario import ExpandedScenario, InstantiatedScenario, Scenario
from raes.semantics.domain_topology import (
    analyze_domain_topology,
)
from raes.value_parsing import is_variable_ref
from raes_contracts.realization_profiles import PlanProfileAuthority
from raes_contracts.realization_structure import validate_realization_value

from ..capture_admission import compile_scenario_capture_demands
from ..models import (
    Diagnostic,
    RuntimeModel,
)
from .evaluation import _compile_assertions, _compile_condition_bindings, _compile_propositions
from .objectives import _compile_objectives
from .observation_demands import compile_observation_demands
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
    profile_authority: PlanProfileAuthority | None = None,
) -> RuntimeModel:
    """Instantiate an SDL scenario and compile it into runtime artifacts."""

    concrete_scenario = (
        scenario
        if isinstance(scenario, InstantiatedScenario)
        else instantiate_scenario(scenario, parameters=parameters, profile=profile)
    )
    return compile_runtime_model(concrete_scenario, profile_authority=profile_authority)


def _admitted_profile_authority(profile_authority: PlanProfileAuthority | None) -> PlanProfileAuthority | None:
    """Revalidate a submitted profile carrier before it becomes compiled authority."""

    if profile_authority is None:
        return None
    if not validate_realization_value(profile_authority, python_carriers=True).conformant:
        raise ValueError("Plan profile carrier exceeds bounded public input limits")
    return PlanProfileAuthority.model_validate(profile_authority.model_dump(mode="json"))


def _compiled_structure_parts(
    scenario: InstantiatedScenario, diagnostics: list[Diagnostic], domain_analysis: object
) -> dict[str, object]:
    """Compile the declared structure: templates, resources, placements, and state."""

    feature_templates, condition_templates, inject_templates = _compile_templates(scenario)
    entity_specs, agent_specs, relationship_specs = _metadata_specs(scenario)
    networks, node_deployments = _compile_node_runtimes(scenario, diagnostics, domain_analysis)
    propositions = _compile_propositions(scenario)
    domain_controller_placements = _compile_domain_controller_placements(scenario, domain_analysis)
    return {
        "feature_templates": feature_templates,
        "condition_templates": condition_templates,
        "inject_templates": inject_templates,
        "entity_specs": entity_specs,
        "agent_specs": agent_specs,
        "relationship_specs": relationship_specs,
        "time_model": compile_time_model(scenario),
        "capability_constraints": _compile_capability_constraints(scenario),
        "capture_demands": compile_scenario_capture_demands(scenario),
        "networks": networks,
        "node_deployments": node_deployments,
        "feature_bindings": _compile_feature_bindings(scenario, feature_templates, diagnostics),
        "propositions": propositions,
        "condition_bindings": _compile_condition_bindings(scenario, condition_templates, propositions, diagnostics),
        "injects": _compile_inject_runtimes(inject_templates),
        "inject_bindings": _compile_inject_bindings(scenario, inject_templates, diagnostics),
        "content_placements": _compile_content_placements(scenario, diagnostics),
        "domain_controller_placements": domain_controller_placements,
        "account_placements": _compile_account_placements(
            scenario, diagnostics, domain_analysis, domain_controller_placements
        ),
        "generated_artifacts": _compile_generated_artifacts(scenario),
        "persistent_volumes": _compile_persistent_volumes(scenario),
    }


def _compiled_behavior_parts(
    scenario: InstantiatedScenario,
    diagnostics: list[Diagnostic],
    *,
    structure: dict[str, object],
    domain_analysis: object,
    declaration_index: object,
) -> dict[str, object]:
    """Compile behaviour, narrative, and realization over the compiled structure."""

    assertions = _compile_assertions(scenario)
    realization_requirements, realization_authority = _compile_realization(scenario, domain_analysis)
    return {
        "assertions": assertions,
        "action_contracts": _compile_action_contracts(scenario),
        "observation_boundaries": _compile_observation_boundaries(scenario),
        "outcome_interpretation_rules": _compile_outcome_interpretation_rules(scenario),
        "participant_behaviors": _compile_participant_behaviors(scenario, diagnostics),
        "behavior_specifications": _compile_behavior_specifications(scenario, diagnostics),
        "tool_affordances": _compile_tool_affordances(scenario, diagnostics),
        "participant_inject_deliveries": _compile_participant_inject_deliveries(scenario),
        "events": _compile_events(
            scenario, assertions, structure["injects"], structure["inject_bindings"], diagnostics
        ),
        "scripts": _compile_scripts(scenario, diagnostics),
        "stories": _compile_stories(scenario, diagnostics),
        "objectives": _compile_objectives(scenario, assertions, diagnostics),
        "workflows": _compile_workflows(scenario, assertions, diagnostics),
        "realization_requirements": realization_requirements,
        "realization_authority": realization_authority,
        "observation_demands": compile_observation_demands(scenario, declaration_index=declaration_index),
    }


def compile_runtime_model(
    scenario: Scenario | ExpandedScenario | InstantiatedScenario,
    *,
    profile_authority: PlanProfileAuthority | None = None,
) -> RuntimeModel:
    """Compile an SDL scenario into bound runtime objects."""

    authority = _admitted_profile_authority(profile_authority)
    scenario = (
        admit_instantiated_scenario(scenario)
        if isinstance(scenario, InstantiatedScenario)
        else instantiate_scenario(scenario)
    )
    declaration_index = build_declaration_index(scenario)
    diagnostics: list[Diagnostic] = []
    domain_analysis = analyze_domain_topology(
        identity_domains=scenario.identity_domains,
        nodes=scenario.nodes,
        accounts=scenario.accounts,
        relationships=scenario.relationships,
        is_unresolved=is_variable_ref,
    )
    structure = _compiled_structure_parts(scenario, diagnostics, domain_analysis)
    behavior = _compiled_behavior_parts(
        scenario,
        diagnostics,
        structure=structure,
        domain_analysis=domain_analysis,
        declaration_index=declaration_index,
    )
    return RuntimeModel(
        scenario_name=scenario.name,
        profile_authority=authority,
        realization_instance=scenario,
        diagnostics=diagnostics,
        **structure,
        **behavior,
    )
