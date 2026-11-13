package planning

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

func bindRegenerationScopes(source []processor.Resource, resources map[string]plannedResource, scope *Scope) ([]diagnostic.Diagnostic, error) {
	findings := []diagnostic.Diagnostic{}
	for _, facts := range source {
		if facts.Kind != termGeneratedArtifact || facts.Artifact == nil || facts.Artifact.Kind != "random_value" {
			continue
		}
		owner, identity := regenerationIdentity(facts.RegenerationScope, scope)
		if owner == "" {
			continue
		}
		if identity == nil || *identity == "" {
			findings = append(findings, planDiagnostic("provisioner.missing-regeneration-scope-identity", termProvisioning, facts.Address, "A '"+facts.RegenerationScope+"' random value requires an authoritative "+owner+" identity to reconcile against."))
			continue
		}
		resource := resources[facts.Address]
		// This is the operation's wire projection. The decision above uses the
		// native generator and scope facts, never a decoded payload field.
		var payload map[string]json.RawMessage
		if json.Unmarshal(resource.payload, &payload) != nil {
			return nil, invalidPlan()
		}
		payload["scope_binding"] = rawProjection(owner + ":" + *identity)
		resource.payload = rawProjection(payload)
		resources[facts.Address] = resource
	}
	return findings, nil
}

func regenerationIdentity(regenerationScope string, scope *Scope) (string, *string) {
	switch regenerationScope {
	case "per_run":
		if scope != nil {
			return "run", scope.RunID
		}
		return "run", nil
	case "per_instantiation":
		if scope != nil {
			return "instantiation", scope.InstantiationID
		}
		return "instantiation", nil
	default:
		return "", nil
	}
}
