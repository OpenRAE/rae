package authoring

import (
	"encoding/json"
	"fmt"
)

type semanticApplication struct {
	ID      string                     `json:"application_id"`
	Service string                     `json:"service"`
	Routes  []semanticApplicationRoute `json:"routes"`
}
type semanticApplicationRoute struct {
	ID        string                  `json:"route_id"`
	Templates []string                `json:"templates"`
	Static    []string                `json:"static_assets"`
	Target    *semanticUpstreamTarget `json:"upstream_target"`
}
type semanticUpstreamTarget struct {
	Node    string          `json:"target_node_ref"`
	Service string          `json:"target_service"`
	TLS     json.RawMessage `json:"tls_terminated_here"`
}
type semanticServiceUnit struct {
	ID      string `json:"unit_id"`
	Service string `json:"service"`
	Path    string `json:"unit_file_path"`
}

func (m *semanticModel) checkRuntimeApplications(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, app := range node.runtime.Applications {
			check.application(app)
		}
	}
}
func (r semanticRuntimeCheck) application(app semanticApplication) {
	label := fmt.Sprintf("Node '%s' runtime application '%s'", r.node.name, app.ID)
	r.ownedService(label, app.Service)
	for _, route := range app.Routes {
		routeLabel := label + " route '" + route.ID + "'"
		r.files(routeLabel, "templates", route.Templates)
		r.files(routeLabel, "static_assets", route.Static)
		if route.Target != nil {
			label := routeLabel + " upstream_target"
			check := semanticProxyCheck{r.model, r.collector, semanticOwner{nodesSection, r.node.name}, label + " upstream_target"}
			node := check.node(route.Target.Node, "target_node_ref")
			check.service(route.Target.Service, node, "", "target_service")
		}
	}
}
func (m *semanticModel) checkRuntimeServiceUnits(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, unit := range node.runtime.Units {
			label := fmt.Sprintf("Node '%s' runtime service_manager_unit '%s'", node.name, unit.ID)
			check.ownedService(label, unit.Service)
			if unit.Path != "" && len(node.paths) > 0 && !variable(unit.Path) && !node.paths[unit.Path] {
				check.reportf(label, "unit_file_path '%s' does not resolve to an observed file on the node", unit.Path)
			}
		}
	}
}
