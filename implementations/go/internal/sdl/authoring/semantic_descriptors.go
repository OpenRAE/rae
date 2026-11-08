package authoring

import (
	"encoding/json"
	"fmt"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type semanticDescriptor struct {
	raw                      json.RawMessage
	owner                    semanticOwner
	pointer, family, context string
	binding                  binding.DomainProfileBindingV1
}

func (m *semanticModel) addDescriptor(owner semanticOwner, path []string, family, context string, raw json.RawMessage) error {
	if len(raw) == 0 || raw[0] != '{' {
		return nil
	}
	row := semanticDescriptor{raw: raw, owner: owner, pointer: "#" + jsonpointer.FromTokens(path), family: family, context: context}
	if err := json.Unmarshal(raw, &row.binding); err != nil {
		return invalid()
	}
	m.descriptors = append(m.descriptors, row)
	return nil
}
func (m *semanticModel) descriptorFacts() error {
	for _, name := range m.keys(identityFacadesField) {
		if err := m.addDescriptor(semanticOwner{identityFacadesField, name}, []string{identityFacadesField, name, protocolField}, "identities", "identity-facade-protocol", fieldValue(fieldValue(m.transport.IdentityFacades)[name].Protocol)); err != nil {
			return err
		}
	}
	if err := m.relationshipDescriptorFacts(); err != nil {
		return err
	}
	for _, name := range m.keys(agentsSection) {
		accesses := fieldValue(fieldValue(m.transport.Agents)[name].InteractiveAccess)
		for _, id := range m.keys(agentsSection, name, "interactive_access") {
			var access struct {
				Channel json.RawMessage `json:"channel"`
			}
			if err := json.Unmarshal(accesses[id], &access); err != nil {
				return invalid()
			}
			if err := m.addDescriptor(semanticOwner{agentsSection, name}, []string{agentsSection, name, "interactive_access", id, "channel"}, relationshipsField, "participant-interactive-access-channel", access.Channel); err != nil {
				return err
			}
		}
	}
	return nil
}
func (m *semanticModel) relationshipDescriptorFacts() error {
	for _, host := range []struct{ field, leaf, context string }{
		{forestTrustField, "trust_type", "forest-trust-type"},
		{identityFederationField, protocolField, "identity-federation-protocol"},
		{identityFederationField, "mapping_intent", "identity-federation-mapping-intent"},
	} {
		for _, name := range m.keys(relationshipsField) {
			selected, err := m.relationshipDescriptorField(name, host.field, host.leaf)
			if err != nil {
				return err
			}
			if err := m.addDescriptor(semanticOwner{relationshipsField, name}, []string{relationshipsField, name, host.field, host.leaf}, relationshipsField, host.context, selected); err != nil {
				return err
			}
		}
	}
	return nil
}
func (m *semanticModel) relationshipDescriptorField(name, field, leaf string) (json.RawMessage, error) {
	value := fieldValue(m.transport.Relationships)[name]
	raw := fieldValue(value.ForestTrust)
	if field == identityFederationField {
		raw = fieldValue(value.IdentityFederation)
	}
	if len(raw) == 0 {
		return nil, nil
	}
	var detail struct {
		Trust    json.RawMessage `json:"trust_type"`
		Protocol json.RawMessage `json:"protocol"`
		Mapping  json.RawMessage `json:"mapping_intent"`
	}
	if err := json.Unmarshal(raw, &detail); err != nil {
		return nil, invalid()
	}
	switch leaf {
	case "trust_type":
		return detail.Trust, nil
	case protocolField:
		return detail.Protocol, nil
	default:
		return detail.Mapping, nil
	}
}
func (m *semanticModel) checkDescriptorProfiles(c *semanticCollector) {
	for _, row := range m.descriptors {
		if !m.portableDescriptor(row) || !descriptorOwned(row) {
			c.report(row.owner, fmt.Sprintf("Field '%s': typed profile binding must be owned by its own field (owning_contract_id '%s', canonical_address '%s', concept_family '%s', lifecycle_phase 'authoring', context '%s', use 'constraint', author-supplied provenance; nested bindings keep this owner)", row.pointer, authoringContract, row.pointer, row.family, row.context))
		}
	}
}
func descriptorOwned(row semanticDescriptor) bool {
	type entry struct {
		binding binding.DomainProfileBindingV1
		depth   int
	}
	pending := []entry{{row.binding, 1}}
	count := 0
	for len(pending) > 0 {
		current := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		count++
		if count > 256 || current.depth > 16 || !descriptorBindingOwner(current.binding, row) {
			return false
		}
		children := fieldValue(current.binding.Children)
		if len(children) > 256-count-len(pending) {
			return false
		}
		seen := map[string]bool{}
		for _, child := range children {
			id := fieldValue(child.BindingId)
			if seen[id] {
				return false
			}
			seen[id] = true
			pending = append(pending, entry{binding.DomainProfileBindingV1(child), current.depth + 1})
		}
	}
	return true
}
func descriptorBindingOwner(value binding.DomainProfileBindingV1, row semanticDescriptor) bool {
	owner := fieldValue(value.Owner)
	return fieldValue(owner.OwningContractId) == authoringContract && fieldValue(owner.CanonicalAddress) == row.pointer && fieldValue(owner.ConceptFamily) == row.family && fieldValue(owner.LifecyclePhase) == "authoring" && fieldValue(owner.Context) == row.context && string(fieldValue(owner.Use)) == "constraint" && string(fieldValue(fieldValue(value.Provenance).Basis)) == "author-supplied"
}
