package authoring

import "fmt"

type semanticDatastore struct {
	ID            string `json:"datastore_service_id"`
	Service       string `json:"service"`
	Authorization string `json:"authorization_ref"`
}
type semanticPlatform struct {
	Scope  string `json:"resource_scope_ref"`
	Limits []struct {
		Scope string `json:"resource_scope_ref"`
	} `json:"cloud_limits"`
	Secrets       []semanticCloudSecret `json:"secrets"`
	ID            string                `json:"platform_application_id"`
	Service       string                `json:"service"`
	Authorization string                `json:"authorization_ref"`
	Content       []struct {
		ID         string   `json:"content_object_id"`
		References []string `json:"references"`
		Markings   []string `json:"marking_refs"`
	} `json:"content_objects"`
	Markings []struct {
		ID string `json:"marking_id"`
	} `json:"markings"`
}

func (runtime *semanticRuntime) authorizationIDs() map[string]bool {
	ids := map[string]bool{}
	for _, auth := range runtime.Authorizations {
		if auth.ID != "" {
			ids[auth.ID] = true
		}
	}
	return ids
}
func (r semanticRuntimeCheck) authorizationRef(label, ref string, ids map[string]bool) {
	if concreteReference(ref) && !ids[ref] {
		r.reportf(label, "authorization_ref '%s' does not resolve to an app_authorization on the same node", ref)
	}
}
func (m *semanticModel) checkRuntimeDatastores(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		ids := node.runtime.authorizationIDs()
		for _, store := range node.runtime.Datastores {
			label := fmt.Sprintf("Node '%s' runtime datastore service '%s'", node.name, store.ID)
			check.ownedService(label, store.Service)
			check.authorizationRef(label, store.Authorization, ids)
		}
	}
}
func (m *semanticModel) checkRuntimePlatforms(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, app := range node.runtime.Platforms {
			check.platform(app, node.runtime.authorizationIDs())
		}
	}
}
func (r semanticRuntimeCheck) platform(app semanticPlatform, authorizations map[string]bool) {
	label := fmt.Sprintf("Node '%s' runtime platform application '%s'", r.node.name, app.ID)
	r.ownedService(label, app.Service)
	r.authorizationRef(label, app.Authorization, authorizations)
	content, markings := map[string]bool{}, map[string]bool{}
	for _, item := range app.Content {
		content[item.ID] = true
	}
	for _, marking := range app.Markings {
		markings[marking.ID] = true
	}
	for _, item := range app.Content {
		itemLabel := label + " content_object '" + item.ID + "'"
		r.platformRefs(itemLabel, "reference", item.References, "content_object", content)
		r.platformRefs(itemLabel, "marking_ref", item.Markings, "marking", markings)
	}
}
func (r semanticRuntimeCheck) platformRefs(label, field string, refs []string, target string, ids map[string]bool) {
	for _, ref := range refs {
		if !variable(ref) && !ids[ref] {
			r.reportf(label, "%s '%s' does not resolve to a %s in the platform application", field, ref, target)
		}
	}
}

type semanticOrchestration struct {
	ID      string `json:"orchestration_authority_id"`
	Control string `json:"control_interface_ref"`
}

func (m *semanticModel) checkRuntimeOrchestration(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		controls := map[string]bool{}
		for _, control := range node.runtime.Controls {
			if control.ID != "" {
				controls[control.ID] = true
			}
		}
		for _, authority := range node.runtime.Orchestration {
			if concreteReference(authority.Control) && !controls[authority.Control] {
				check.reportf(fmt.Sprintf("Node '%s' runtime orchestration authority '%s'", node.name, authority.ID), "control_interface_ref '%s' does not resolve to a control interface in the same node's runtime.local_control_interfaces", authority.Control)
			}
		}
	}
}
