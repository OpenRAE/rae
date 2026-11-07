package authoring

import "github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"

type descriptorHost struct {
	section         string
	path            []string
	family, context string
}

func (c materializedChecks) descriptorProfiles() error {
	hosts := []descriptorHost{
		{identityFacadesField, []string{protocolField}, "identities", "identity-facade-protocol"},
		{relationshipsField, []string{forestTrustField, "trust_type"}, relationshipsField, "forest-trust-type"},
		{relationshipsField, []string{identityFederationField, protocolField}, relationshipsField, "identity-federation-protocol"},
		{relationshipsField, []string{identityFederationField, "mapping_intent"}, relationshipsField, "identity-federation-mapping-intent"},
	}
	for _, host := range hosts {
		for name, raw := range object(c.value[host.section]) {
			current := raw
			for _, field := range host.path {
				current = object(current)[field]
			}
			pointer := "#" + jsonpointer.FromTokens(append([]string{host.section, name}, host.path...))
			if err := descriptorOwner(object(current), pointer, host.family, host.context); err != nil {
				return err
			}
		}
	}
	for name, raw := range object(c.value[agentsSection]) {
		for id, access := range object(object(raw)["interactive_access"]) {
			pointer := "#" + jsonpointer.FromTokens([]string{agentsSection, name, "interactive_access", id, "channel"})
			if err := descriptorOwner(object(object(access)["channel"]), pointer, relationshipsField, "participant-interactive-access-channel"); err != nil {
				return err
			}
		}
	}
	return nil
}
func descriptorOwner(binding map[string]any, pointer, family, context string) error {
	if binding == nil {
		return nil
	}
	type entry struct {
		value map[string]any
		depth int
	}
	pending := []entry{{binding, 1}}
	count := 0
	for len(pending) > 0 {
		current := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		count++
		if count > 256 || current.depth > 16 {
			return semanticInvalid()
		}
		if err := descriptorLocalOwner(current.value, pointer, family, context); err != nil {
			return err
		}
		children := array(current.value["children"])
		if len(children) > 256-count-len(pending) {
			return semanticInvalid()
		}
		seen := map[string]bool{}
		for _, raw := range children {
			child := object(raw)
			id := text(child["binding_id"])
			if seen[id] {
				return semanticInvalid()
			}
			seen[id] = true
			pending = append(pending, entry{child, current.depth + 1})
		}
	}
	return nil
}

func descriptorLocalOwner(value map[string]any, pointer, family, context string) error {
	owner := object(value["owner"])
	expected := map[string]string{"owning_contract_id": authoringContract, "canonical_address": pointer, "concept_family": family, "lifecycle_phase": "authoring", "context": context, "use": "constraint"}
	for field, value := range expected {
		if text(owner[field]) != value {
			return semanticInvalid()
		}
	}
	if object(value["provenance"])["basis"] != "author-supplied" {
		return semanticInvalid()
	}
	return nil
}
