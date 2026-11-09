package authoring

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type semanticPolicyRecord struct {
	Namespace []string `json:"namespace"`
	Pointer   string   `json:"field_pointer"`
	Concern   string   `json:"concern"`
}
type semanticPolicies struct {
	Augmentation *struct {
		Scopes []struct {
			Namespace []string `json:"namespace"`
			Scope     string   `json:"scope"`
		} `json:"scopes"`
	} `json:"augmentation_scope"`
	Realization *struct {
		Scopes      []semanticPolicyRecord `json:"scopes"`
		Constraints []semanticPolicyRecord `json:"constraints"`
	} `json:"realization"`
	Expansion *struct {
		Imports []struct {
			Namespace []string `json:"namespace"`
		} `json:"imports"`
		Designations []semanticPolicyRecord `json:"realization_designations"`
		Constraints  []semanticPolicyRecord `json:"realization_constraints"`
	} `json:"expansion_provenance"`
}

func (m *semanticModel) policyFacts() error {
	if json.Unmarshal(m.document.modelBytes(), &m.policies) != nil {
		return invalid()
	}
	return nil
}
func (m *semanticModel) knownNamespace(namespace []string) bool {
	if len(namespace) == 0 {
		return true
	}
	if m.policies.Expansion == nil {
		return false
	}
	for _, record := range m.policies.Expansion.Imports {
		if strings.Join(record.Namespace, ".") == strings.Join(namespace, ".") {
			return true
		}
	}
	return false
}
func (m *semanticModel) checkAugmentation(c *semanticCollector) {
	if m.document.contract == materializedContract || m.policies.Augmentation == nil {
		return
	}
	for _, rule := range m.policies.Augmentation.Scopes {
		if !m.knownNamespace(rule.Namespace) {
			c.report(semanticOwner{}, "Augmentation permission namespace does not resolve to an admitted import")
		}
		canonical, err := m.scopes.resolve(rule.Scope)
		if err != nil {
			c.report(semanticOwner{}, fmt.Sprintf("Augmentation permission scope '%s' does not resolve to a stable SDL semantic scope", rule.Scope))
		}
		if len(rule.Namespace) > 0 && err == nil && len(jsonpointer.Tokens(canonical)) >= 2 && !namespaceOwns(m.scopeNamespace(canonical), strings.Join(rule.Namespace, ".")) {
			c.report(semanticOwner{}, "Augmentation permission namespace does not own the addressed declaration")
		}
	}
}
func (m *semanticModel) checkRealization(c *semanticCollector) {
	if m.document.contract == materializedContract {
		return
	}
	var records, constraints []semanticPolicyRecord
	if m.policies.Realization != nil {
		records = append([]semanticPolicyRecord{{}}, m.policies.Realization.Scopes...)
		constraints = m.policies.Realization.Constraints
	} else if m.policies.Expansion != nil {
		records = m.policies.Expansion.Designations
		constraints = m.policies.Expansion.Constraints
	}
	for _, record := range records {
		if !m.knownNamespace(record.Namespace) {
			c.report(semanticOwner{}, "Realization designation references an unresolved module namespace")
		}
		if _, err := m.scopes.surface(record.Pointer); err != nil {
			pointer := record.Pointer
			if pointer == "" {
				pointer = "/"
			}
			c.report(semanticOwner{}, "Realization designation field_pointer does not resolve to a typed SDL surface: "+pointer)
		}
	}
	for _, constraint := range constraints {
		m.realizationConstraint(c, constraint)
	}
}
func (m *semanticModel) realizationConstraint(c *semanticCollector, record semanticPolicyRecord) {
	if !m.knownNamespace(record.Namespace) {
		c.report(semanticOwner{}, "Realization constraint references an unresolved module namespace")
		return
	}
	surface, err := m.scopes.surface(record.Pointer)
	if err != nil || surface.definition != "#/$defs/Node" {
		c.report(semanticOwner{}, "Realization constraint field_pointer must resolve to a compute node: "+record.Pointer)
	} else if surface.nodeKind == switchType {
		c.report(semanticOwner{}, fmt.Sprintf("Realization concern '%s' cannot target strict switch '%s'", record.Concern, record.Pointer))
	}
}
