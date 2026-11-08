package authoring

import "fmt"

type semanticIdentityAuthority struct {
	ID       string `json:"identity_authority_id"`
	Services []struct {
		ID      string `json:"service_id"`
		Service string `json:"service"`
	} `json:"services"`
	Subjects      []semanticCloudSubject `json:"subjects"`
	Policies      []semanticCloudPolicy  `json:"policies"`
	Relationships []struct {
		ID     string `json:"relationship_id"`
		Source string `json:"source_ref"`
		Target string `json:"target_ref"`
	} `json:"relationships"`
	Scopes       []semanticCloudScope       `json:"resource_scopes"`
	Uses         []semanticCloudUse         `json:"identity_uses"`
	Observations []semanticCloudObservation `json:"access_observations"`
}

func (a semanticIdentityAuthority) localRefs() map[string]bool {
	refs := map[string]bool{a.ID: true}
	for _, service := range a.Services {
		refs[service.ID] = true
	}
	for _, subject := range a.Subjects {
		refs[subject.ID] = true
	}
	for _, policy := range a.Policies {
		refs[policy.ID] = true
	}
	for _, relationship := range a.Relationships {
		refs[relationship.ID] = true
	}
	for _, scope := range a.Scopes {
		refs[scope.ID] = true
	}
	for _, use := range a.Uses {
		refs[use.ID] = true
	}
	for _, observation := range a.Observations {
		refs[observation.ID] = true
	}
	return refs
}
func (m *semanticModel) checkRuntimeIdentityAuthorities(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, authority := range node.runtime.Authorities {
			check.identityAuthority(authority)
		}
	}
}
func (r semanticRuntimeCheck) identityAuthority(a semanticIdentityAuthority) {
	label := fmt.Sprintf("Node '%s' runtime identity authority '%s'", r.node.name, a.ID)
	for _, service := range a.Services {
		r.ownedService(label+" service '"+service.ID+"'", service.Service)
	}
	refs := a.localRefs()
	for _, relationship := range a.Relationships {
		relLabel := label + " relationship '" + relationship.ID + "'"
		r.identityReference(relLabel, "source_ref", relationship.Source, refs)
		if relationship.Target != "" {
			r.identityReference(relLabel, "target_ref", relationship.Target, refs)
		}
	}
	for _, policy := range a.Policies {
		for _, ref := range policy.Applies {
			r.identityReference(label+" policy '"+policy.ID+"'", "applies_to_ref", ref, refs)
		}
	}
}
func (r semanticRuntimeCheck) identityReference(label, field, ref string, refs map[string]bool) {
	if !variable(ref) && !refs[ref] {
		r.reportf(label, "%s '%s' does not resolve inside identity authority", field, ref)
	}
}
