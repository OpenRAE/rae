package realization

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type processCapability struct {
	Resource  string       `json:"resource"`
	Scopes    []string     `json:"scopes"`
	Minimum   json.Number  `json:"minimum"`
	Maximum   *json.Number `json:"maximum"`
	Unlimited bool         `json:"supports_unlimited"`
}

// Input is a generated member of an already bounded and admitted manifest or
// envelope. The private projection retains exactly its domain coordinates.
func decodeProcessCapability(input any) (processCapability, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return processCapability{}, invalidRealization()
	}
	result := processCapability{Minimum: "0"}
	if err := json.Unmarshal(raw, &result); err != nil {
		return processCapability{}, invalidRealization()
	}
	slices.Sort(result.Scopes)
	return result, nil
}

func (c processCapability) document() map[string]any {
	var maximum any
	if c.Maximum != nil {
		maximum = *c.Maximum
	}
	return map[string]any{termResource: c.Resource, "scopes": stringValues(c.Scopes), "minimum": c.Minimum, "maximum": maximum, "supports_unlimited": c.Unlimited}
}
func (c processCapability) equal(other processCapability) bool {
	if c.Resource != other.Resource || !slices.Equal(c.Scopes, other.Scopes) || c.Unlimited != other.Unlimited || !payloadEqual(c.Minimum, other.Minimum) || (c.Maximum == nil) != (other.Maximum == nil) {
		return false
	}
	return c.Maximum == nil || payloadEqual(*c.Maximum, *other.Maximum)
}

func processSupportDiagnostic(requirement Requirement, declarations []supportDeclaration, envelope *binding.RealizationEnvelopeV1) (*diagnostic.Diagnostic, error) {
	compatible := []supportDeclaration{}
	for _, declaration := range declarations {
		if processSupportCompatible(requirement, declaration) {
			compatible = append(compatible, declaration)
		}
	}
	if len(compatible) == 0 {
		return supportFinding(requirement, "realization.unsupported-process-resource-limits", "Backend declares no typed process-resource-limit support with effective guest observation for '"+requirement.FieldPath+"'."), nil
	}
	configured, err := configuredProcessCapabilities(envelope)
	if err != nil {
		return nil, err
	}
	for _, declaration := range compatible {
		bound := boundProcessCapabilities(declaration.processLimits, configured)
		admitted, checkErr := processRequirementAdmitted(requirement, bound)
		if checkErr != nil {
			return nil, checkErr
		}
		if admitted {
			return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
		}
	}
	return supportFinding(requirement, "realization.process-resource-limit-domain-mismatch", "Backend process-resource-limit apparatus domain does not admit every authored resource, scope, and soft/hard value for '"+requirement.FieldPath+"'."), nil
}

func processRequirementAdmitted(requirement Requirement, bound []processCapability) (bool, error) {
	if requirement.Posture != nil && *requirement.Posture == termOpen {
		return len(bound) > 0, nil
	}
	return processDemandsAdmitted(requirement, bound)
}

func processSupportCompatible(requirement Requirement, declaration supportDeclaration) bool {
	supported := slices.Contains(declaration.exact, "declared-capability-match")
	if requirement.Posture != nil {
		switch *requirement.Posture {
		case termOpen:
			supported = declaration.mode == termOpenRealization
		case termConstrained:
			supported = slices.Contains(declaration.constraints, termProcessResourceLimits)
		}
	}
	return supported && sufficientlyObserved(requirement, []supportDeclaration{declaration})
}
func configuredProcessCapabilities(envelope *binding.RealizationEnvelopeV1) ([]processCapability, error) {
	configured := []processCapability{}
	if envelope != nil {
		for _, capability := range sourceValue(sourceValue(envelope.Configuration).ProcessResourceLimits) {
			decoded, err := decodeProcessCapability(capability)
			if err != nil {
				return nil, err
			}
			configured = append(configured, decoded)
		}
	}
	return configured, nil
}
func boundProcessCapabilities(capabilities, configured []processCapability) []processCapability {
	bound := []processCapability{}
	for _, capability := range capabilities {
		if slices.ContainsFunc(configured, capability.equal) {
			bound = append(bound, capability)
		}
	}
	return bound
}

func processDemandsAdmitted(requirement Requirement, capabilities []processCapability) (bool, error) {
	owner, err := realizationOwner()
	if err != nil {
		return false, err
	}
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	domains := map[processLeafIdentity]admission.Fragment{}
	for _, constraint := range requirement.ValueConstraints {
		domains[processLeafIdentity{constraint.IdentityDigest, constraint.Leaf}] = constraint.AllowedValues
	}
	fragments := make([]admission.Fragment, len(capabilities))
	for index, capability := range capabilities {
		fragment, checkErr := admission.AdmitFragment(owner, admission.RealizationValue, capability.document(), limits)
		if checkErr != nil {
			return false, checkErr
		}
		fragments[index] = fragment
	}
	for _, demand := range requirement.ProcessResourceLimits {
		matched, checkErr := processDemandAdmitted(owner, demand, domains, fragments, limits)
		if checkErr != nil {
			return false, checkErr
		}
		if !matched {
			return false, nil
		}
	}

	return true, nil
}

type processLeafIdentity struct{ identity, leaf string }

func processDemandAdmitted(owner *admission.Validator, demand ProcessResourceLimit, domains map[processLeafIdentity]admission.Fragment, fragments []admission.Fragment, limits ingress.Limits) (bool, error) {
	var err error
	soft, hard := domains[processLeafIdentity{demand.IdentityDigest, termSoft}], domains[processLeafIdentity{demand.IdentityDigest, termHard}]
	if soft == nil {
		soft, err = admission.AdmitFragment(owner, admission.RealizationValue, []any{demand.Soft.Document()}, limits)
		if err != nil {
			return false, err
		}
	}
	if hard == nil {
		hard, err = admission.AdmitFragment(owner, admission.RealizationValue, []any{demand.Hard.Document()}, limits)
		if err != nil {
			return false, err
		}
	}
	for _, capability := range fragments {
		admitted, checkErr := admission.ProcessResourceLimitCapabilityAdmits(owner, capability, demand.Resource, demand.Scope, soft, hard)
		if checkErr != nil {
			return false, checkErr
		}
		if admitted {
			return true, nil
		}
	}
	return false, nil
}
