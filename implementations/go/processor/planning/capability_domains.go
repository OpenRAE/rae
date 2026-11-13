package planning

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type capabilityDomainIndex struct {
	constraints       map[[2]string]processor.CapabilityConstraint
	hasOSRequirements map[string]bool
	owner             *admission.Validator
}

func newCapabilityDomains(model processor.CompiledScenario) (*capabilityDomainIndex, error) {
	owner, err := planOwner()
	if err != nil {
		return nil, err
	}
	result := &capabilityDomainIndex{constraints: map[[2]string]processor.CapabilityConstraint{}, hasOSRequirements: map[string]bool{}, owner: owner}
	for _, constraint := range model.CapabilityConstraints {
		key := [2]string{constraint.Address, constraint.Concern}
		if _, exists := result.constraints[key]; !exists {
			result.constraints[key] = constraint
		}
	}
	for _, requirement := range model.RealizationRequirements {
		if requirement.Kind == termOsFamily || requirement.Kind == termOsDistribution || requirement.Kind == termOsVersion {
			result.hasOSRequirements[requirement.Address] = true
		}
	}
	return result, nil
}
func (index *capabilityDomainIndex) domain(resource processor.Resource, kind, concern, concrete string) ([]string, *diagnostic.Diagnostic) {
	constraint, exists := index.constraints[[2]string{resource.Address, concern}]
	prefix, field := map[string]string{termOsFamily: termOsFamily, termOsDistribution: termOsDistribution, termOsVersion: termOsVersion, "node-architecture": "node-architecture"}[kind], strings.TrimPrefix(concern, "nodes.")
	failure := func(suffix, message string) ([]string, *diagnostic.Diagnostic) {
		d := planDiagnostic("provisioner."+prefix+suffix, termProvisioning, resource.Address, message)
		return nil, &d
	}
	if !exists {
		return concreteCapabilityDomain(resource, concern, concrete, prefix)
	}
	name := strings.Join(constraint.Parameter, ".")
	result := []string{}
	for _, scalar := range constraint.AllowedValues {
		fragment, err := index.normalizedScalar(concern, scalar)
		message := "Variable '" + name + "' has an invalid " + concern + " domain."
		if err != nil {
			if kind != termOsFamily {
				message = "Variable '" + name + "' allowed_values contain a value invalid for nodes." + field + "."
			}
			return failure("-variable-domain-invalid", message)
		}
		token, ok := fragment.Document().(string)
		if !ok || token == "" {
			return failure("-variable-domain-invalid", message)
		}
		if variableName(token) != "" {
			return failure("-variable-domain-invalid", "Variable '"+name+"' has a non-concrete "+concern+" domain.")
		}
		result = append(result, token)
	}
	return result, nil
}
func (index *capabilityDomainIndex) scalarSupport(resource processor.Resource, kind, concern, concrete string, supported []string, all bool) []diagnostic.Diagnostic {
	if concrete == "" {
		return nil
	}
	domain, failure := index.domain(resource, kind, concern, concrete)
	if failure != nil {
		return []diagnostic.Diagnostic{*failure}
	}
	feasible, unsupported := []string{}, []string{}
	for _, value := range domain {
		if slices.Contains(supported, value) {
			feasible = append(feasible, value)
		} else {
			unsupported = append(unsupported, value)
		}
	}
	if !all && len(feasible) > 0 || all && len(unsupported) == 0 {
		return nil
	}
	label, code := "OS family", "provisioner.unsupported-os-family"
	if all {
		label = "node architecture"
		code = "provisioner.unsupported-node-architecture"
	}
	message := "Provisioner does not support " + label + " '" + concrete + "'."
	if constraint, exists := index.constraints[[2]string{resource.Address, concern}]; exists {
		name := strings.Join(constraint.Parameter, ".")
		if all {
			slices.Sort(unsupported)
			unsupported = slices.Compact(unsupported)
			message = "Provisioner does not support all node architectures allowed by variable '" + name + "': " + quotedDomain(unsupported) + "."
		} else {
			message = "Provisioner supports no OS family allowed by variable '" + name + "'."
		}
	}
	return []diagnostic.Diagnostic{planDiagnostic(code, termProvisioning, resource.Address, message)}
}
func (index *capabilityDomainIndex) count(resource processor.Resource) (*big.Int, *diagnostic.Diagnostic) {
	constraint, exists := index.constraints[[2]string{resource.Address, "infrastructure.count"}]
	if !exists {
		if resource.Node == nil || resource.Node.Count == nil {
			return big.NewInt(1), nil
		}
		parsed, ok := new(big.Int).SetString(string(*resource.Node.Count), 10)
		if !ok {
			return nil, nil
		}
		return parsed, nil
	}
	maximum := new(big.Int)
	name := strings.Join(constraint.Parameter, ".")
	for _, scalar := range constraint.AllowedValues {
		count, valid := index.normalizedCount(scalar)
		if valid {
			if count.Cmp(maximum) > 0 {
				maximum = count
			}
			continue
		}
		d := planDiagnostic("provisioner.count-variable-domain-invalid", termProvisioning, resource.Address, "Variable '"+name+"' allowed_values contain a value invalid for infrastructure.count.")
		return nil, &d
	}
	return maximum, nil
}

func (index *capabilityDomainIndex) normalizedCount(scalar processor.Scalar) (*big.Int, bool) {
	fragment, err := admission.AdmitFragment(index.owner, admission.RealizationValue, scalar.Value(), ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		return nil, false
	}
	fragment, err = sdl.NormalizeCapabilityValue("infrastructure.count", fragment)
	if err != nil {
		return nil, false
	}
	number, ok := fragment.Document().(json.Number)
	if !ok {
		return nil, false
	}
	count, ok := new(big.Int).SetString(string(number), 10)
	return count, ok && count.Sign() > 0
}

//nolint:ireturn // The shared admission owner returns the exact native value handle.
func (index *capabilityDomainIndex) normalizedScalar(concern string, scalar processor.Scalar) (admission.Fragment, error) {
	fragment, err := admission.AdmitFragment(index.owner, admission.RealizationValue, scalar.Value(), ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		return nil, err
	}
	return sdl.NormalizeCapabilityValue(concern, fragment)
}

func quotedDomain(values []string) string {
	quoted := make([]string, len(values))
	for i, value := range values {
		quoted[i] = "'" + value + "'"
	}
	return strings.Join(quoted, ", ")
}

func concreteCapabilityDomain(resource processor.Resource, concern, concrete, prefix string) ([]string, *diagnostic.Diagnostic) {
	if variable := variableName(concrete); variable != "" {
		finding := planDiagnostic("provisioner."+prefix+"-variable-ref-unbound", termProvisioning, resource.Address, "Provisioner capability validation cannot resolve undeclared variable '"+variable+"' referenced by "+concern+".")
		return nil, &finding
	}
	if concrete == "" {
		return nil, nil
	}
	return []string{concrete}, nil
}
