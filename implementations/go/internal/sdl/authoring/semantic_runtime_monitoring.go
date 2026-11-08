package authoring

import "fmt"

type semanticRuntimeComponent struct {
	ID string `json:"component_id"`
}
type semanticRuntimeSetting struct {
	ID        string `json:"setting_id"`
	Component string `json:"component_ref"`
	Path      string `json:"source_path"`
}
type semanticRuntimeChildListener struct {
	ID        string `json:"listener_id"`
	Service   string `json:"service"`
	Component string `json:"component_ref"`
}
type semanticMonitoringManager struct {
	ID            string                         `json:"security_monitoring_manager_id"`
	Service       string                         `json:"service"`
	Configuration []string                       `json:"configuration_file_refs"`
	Logs          []string                       `json:"log_file_refs"`
	Evidence      []string                       `json:"evidence_refs"`
	Components    []semanticRuntimeComponent     `json:"components"`
	Listeners     []semanticRuntimeChildListener `json:"listeners"`
	Groups        []struct {
		ID            string   `json:"group_id"`
		Members       []string `json:"member_refs"`
		Configuration []string `json:"configuration_file_refs"`
	} `json:"agent_groups"`
	Agents []struct {
		ID     string   `json:"agent_id"`
		Groups []string `json:"group_refs"`
	} `json:"agents"`
	Content []struct {
		ID    string   `json:"content_id"`
		Files []string `json:"file_refs"`
	} `json:"content_sets"`
	Definitions []semanticMonitoringDefinition `json:"detection_definitions"`
	Settings    []semanticRuntimeSetting       `json:"settings"`
}
type semanticMonitoringDefinition struct {
	ID       string   `json:"definition_id"`
	Content  string   `json:"content_set_ref"`
	File     string   `json:"source_file_ref"`
	Evidence []string `json:"evidence_refs"`
	SID      []string `json:"if_sid_refs"`
	Matched  []string `json:"if_matched_sid_refs"`
	Parents  []string `json:"parent_definition_refs"`
	Artifact string   `json:"source_artifact_ref"`
	Targets  []string `json:"target_refs"`
}
type semanticMonitoringIDs struct{ components, agents, groups, content, definitions map[string]bool }

func (manager semanticMonitoringManager) ids() semanticMonitoringIDs {
	ids := semanticMonitoringIDs{map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}}
	for _, component := range manager.Components {
		ids.components[component.ID] = true
	}
	for _, agent := range manager.Agents {
		ids.agents[agent.ID] = true
	}
	for _, group := range manager.Groups {
		ids.groups[group.ID] = true
	}
	for _, content := range manager.Content {
		ids.content[content.ID] = true
	}
	for _, definition := range manager.Definitions {
		ids.definitions[definition.ID] = true
	}
	return ids
}
func (m *semanticModel) checkRuntimeMonitoring(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, manager := range node.runtime.Monitors {
			check.monitoring(manager)
		}
	}
}
func (r semanticRuntimeCheck) monitoring(manager semanticMonitoringManager) {
	label := fmt.Sprintf("Node '%s' runtime security-monitoring manager '%s'", r.node.name, manager.ID)
	r.ownedService(label, manager.Service)
	r.fileGroups(label, manager.Configuration, manager.Logs, manager.Evidence)
	ids := manager.ids()
	for _, listener := range manager.Listeners {
		r.ownedService(label+" listener '"+listener.ID+"'", listener.Service)
	}
	r.monitoringAgents(label, manager, ids)
	for _, content := range manager.Content {
		r.files(label+" content_set '"+content.ID+"'", "file_refs", content.Files)
	}
	for _, definition := range manager.Definitions {
		r.monitoringDefinition(label+" detection_definition '"+definition.ID+"'", definition, ids)
	}
	for _, setting := range manager.Settings {
		settingLabel := label + " setting '" + setting.ID + "'"
		r.monitoringRef(settingLabel, "component_ref", setting.Component, "component", ids.components)
		r.optionalFile(settingLabel, "source_path", setting.Path)
	}
}
func (r semanticRuntimeCheck) monitoringAgents(label string, manager semanticMonitoringManager, ids semanticMonitoringIDs) {
	for _, group := range manager.Groups {
		groupLabel := label + " agent_group '" + group.ID + "'"
		r.files(groupLabel, "configuration_file_refs", group.Configuration)
		for _, member := range group.Members {
			r.monitoringRef(groupLabel, "member_ref", member, "agent", ids.agents)
		}
	}
	for _, agent := range manager.Agents {
		for _, group := range agent.Groups {
			r.monitoringRef(label+" agent '"+agent.ID+"'", "group_ref", group, "agent group", ids.groups)
		}
	}
}
func (r semanticRuntimeCheck) monitoringDefinition(label string, definition semanticMonitoringDefinition, ids semanticMonitoringIDs) {
	r.monitoringRef(label, "content_set_ref", definition.Content, "content set", ids.content)
	r.optionalFile(label, "source_file_ref", definition.File)
	r.files(label, evidenceRefsField, definition.Evidence)
	for _, group := range []struct {
		field string
		refs  []string
	}{{"if_sid_ref", definition.SID}, {"if_matched_sid_ref", definition.Matched}, {"parent_definition_ref", definition.Parents}} {
		for _, ref := range group.refs {
			r.monitoringRef(label, group.field, ref, "detection definition", ids.definitions)
		}
	}
	owner := semanticOwner{nodesSection, r.node.name}
	if concreteReference(definition.Artifact) {
		r.model.namedReference(r.collector, owner, label, "source_artifact_ref", definition.Artifact, referenceDeclared)
	}
	for _, ref := range definition.Targets {
		r.model.namedReference(r.collector, owner, label, "target_ref", ref, referenceTarget)
	}
}
func (r semanticRuntimeCheck) monitoringRef(label, field, ref, target string, ids map[string]bool) {
	if concreteReference(ref) && !ids[ref] {
		r.reportf(label, "%s '%s' does not resolve to a %s in the security-monitoring manager", field, ref, target)
	}
}
func (r semanticRuntimeCheck) optionalFile(label, field, path string) {
	if path != "" {
		r.files(label, field, []string{path})
	}
}
