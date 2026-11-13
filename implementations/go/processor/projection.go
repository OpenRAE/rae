package processor

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

// compiledProjection is the external document boundary. Compiler passes never
// decode this projection or exchange these maps.
func compiledProjection(model CompiledScenario) ([]byte, error) {
	document := map[string]any{"scenario_name": model.Name, "diagnostics": projectDiagnostics(model.Diagnostics), "execution_policies": map[string]any{}, "capability_constraints": compiledCapabilityProjection(model.CapabilityConstraints), "time_model": compiledTimeProjection(model.TimeModel), "capture_demands": []any{}, "realization_requirements": []any{}, "realization_authority": []any{}, "observation_demands": []any{}, "profile_authority": model.ProfileAuthority, "descriptor_profile_bindings": model.DescriptorProfiles}
	requirements := make([]any, len(model.RealizationRequirements))
	for index, requirement := range model.RealizationRequirements {
		fragment, err := realization.AdmitRequirement(requirement)
		if err != nil {
			return nil, err
		}
		requirements[index] = fragment.Document()
	}
	document["realization_requirements"] = requirements
	captures := make([]json.RawMessage, len(model.CaptureDemands))
	for i, demand := range model.CaptureDemands {
		captures[i] = demand.Payload.data
	}
	document["capture_demands"] = captures
	observations := make([]json.RawMessage, len(model.ObservationDemands))
	for i, demand := range model.ObservationDemands {
		observations[i] = demand.Payload.data
	}
	document["observation_demands"] = observations
	policies := map[string][]any{}
	for _, policy := range model.ExecutionPolicies {
		policies[policy.Address] = append(policies[policy.Address], policy.Policy.Document())
	}
	document["execution_policies"] = policies
	document["realization_authority"] = compiledAuthorityProjection(model.RealizationAuthority)
	if err := compiledResourceSections(document, model); err != nil {
		return nil, err
	}
	if err := value.ValidateProjected(document, value.Plan(), compiledProjectionValue); err != nil {
		return nil, err
	}
	return json.Marshal(document)
}
func compiledAuthorityProjection(input []realization.Authority) []any {
	authorities := make([]any, len(input))
	optional := func(text string) any {
		if text == "" {
			return nil
		}
		return text
	}
	for index, authority := range input {
		authorities[index] = map[string]any{"field_path": authority.FieldPath, termAddress: authority.Address, "domain": authority.Domain, "requirement_kind": authority.Concern, "payload_path": nonNilStrings(authority.PayloadPath), "mode": authority.Posture, "source": authority.Source, "provenance": authority.Provenance, "governing_scope": optional(authority.GoverningScope), "delegated": authority.Delegated, "verification_scope": optional(authority.ObservationScope), "required_observation_strength": optional(authority.ObservationStrength)}
	}
	return authorities
}
func compiledResourceSections(document map[string]any, model CompiledScenario) error {
	resourceSections := map[string]string{
		termNetwork: "networks", termNode: "node_deployments", "feature-binding": "feature_bindings", termProposition: termPropositions, termAssertion: termAssertions, termConditionBinding: "condition_bindings", termInject: termInjects, termInjectBinding: "inject_bindings", termContentPlacement: "content_placements", termDomainControllerPlacement: "domain_controller_placements", termAccountPlacement: "account_placements", termGeneratedArtifact: termGeneratedArtifacts, termPersistentVolume: termPersistentVolumes, termActionContract: termActionContracts, termObservationBoundary: termObservationBoundaries, termOutcomeInterpretationRule: termOutcomeInterpretationRules, termParticipantBehavior: "participant_behaviors", termBehaviorSpecification: termBehaviorSpecifications, "tool-affordance": termToolAffordances, "participant-inject-delivery": "participant_inject_deliveries", termEvent: termEvents, termScript: termScripts, termStory: termStories, termWorkflow: "workflows", termObjective: termObjectives,
	}
	groups := map[string]map[string]any{}
	for _, section := range resourceSections {
		groups[section] = map[string]any{}
	}
	for _, section := range []string{"feature_templates", "condition_templates", "inject_templates", "entity_specs", "agent_specs", "relationship_specs"} {
		groups[section] = map[string]any{}
	}
	compiledDefinitionsProjection(groups, model.Definitions)
	for _, resources := range [][]Resource{model.Resources, model.ParticipantResources} {
		for _, resource := range resources {
			section, present := resourceSections[resource.Kind]
			if !present {
				return invalidCompiled()
			}
			groups[section][resource.Address] = compiledResourceWire(resource)
		}
	}
	for section, resources := range groups {
		document[section] = resources
	}
	return nil
}
func compiledDefinitionsProjection(groups map[string]map[string]any, definitions []Definition) {
	for _, definition := range definitions {
		if metadata, ok := (map[string]string{"entity": "entity_specs", "agent": "agent_specs", "relationship": "relationship_specs"})[definition.Kind]; ok {
			groups[metadata][definition.Name] = json.RawMessage(definition.Payload.data)
			continue
		}
		section := definition.Kind + "_templates"
		if groups[section] != nil {
			groups[section][definition.Name] = map[string]any{"address": definition.Address, "name": definition.Name, "spec": json.RawMessage(definition.Payload.data)}
		}
	}
}
func compiledResourceProjection(resource Resource) (map[string]any, error) {
	parsed, err := compiledRawValue(resource.Payload.data)
	if err != nil {
		return nil, err
	}
	wire, ok := parsed.(map[string]any)
	if !ok {
		return nil, invalidCompiled()
	}
	wire[termAddress] = resource.Address
	wire["ordering_dependencies"] = nonNilStrings(resource.OrderingDependencies)
	wire["refresh_dependencies"] = nonNilStrings(resource.RefreshDependencies)
	return wire, nil
}

func nonNilStrings(input []string) []string {
	if input == nil {
		return []string{}
	}
	return input
}
func projectDiagnostics(input []diagnostic.Diagnostic) []map[string]any {
	output := make([]map[string]any, len(input))
	for i, finding := range input {
		output[i] = map[string]any{"code": finding.Code, "domain": finding.Domain, termAddress: finding.Address, "message": finding.Message, "severity": finding.Severity}
	}
	return output
}

// Private delayed projection keeps payload traversal inside the shared budget.
// JSON encoding runs only after every value has passed that aggregate guard.
type compiledResourceWire Resource

func (resource compiledResourceWire) MarshalJSON() ([]byte, error) {
	wire, err := compiledResourceProjection(Resource(resource))
	if err != nil {
		return nil, err
	}
	return json.Marshal(wire)
}
