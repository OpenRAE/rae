package authoring

import (
	"encoding/json"
	"fmt"
	"slices"
)

type semanticProxyUpstream struct {
	Route   string          `json:"route_ref"`
	Node    string          `json:"upstream_node_ref"`
	Service string          `json:"upstream_service_ref"`
	TLS     json.RawMessage `json:"client_tls_terminated"`
}
type semanticProxyCheck struct {
	model     *semanticModel
	collector *semanticCollector
	owner     semanticOwner
	label     string
}

func (p semanticProxyCheck) reportf(format string, args ...any) {
	p.collector.report(p.owner, p.label+" "+fmt.Sprintf(format, args...))
}
func (p semanticProxyCheck) node(ref, field string) string {
	if !concreteReference(ref) {
		return ""
	}
	if !p.model.definitions[nodesSection][ref] {
		p.reportf("%s '%s' does not resolve to a defined node", field, ref)
		return ""
	}
	return ref
}
func (m *semanticModel) upstreamTargetNode(target string) string {
	if !concreteReference(target) {
		return ""
	}
	if m.definitions[nodesSection][target] {
		return target
	}
	if node, _, known := m.findService(target); known {
		return node
	}
	entry, known := m.index.declarations[target]
	if known && len(entry.tokens) >= 5 && entry.tokens[0] == nodesSection && entry.tokens[2] == runtimeField {
		return entry.node
	}
	return ""
}
func (m *semanticModel) upstreamService(ref, upstream, target string) (string, string, bool) {
	if node, service, known := m.findService(ref); known {
		return node, service, true
	}
	node := upstream
	if !concreteReference(node) {
		node = m.upstreamTargetNode(target)
	}
	return node, ref, node != ""
}
func (p semanticProxyCheck) service(ref, upstream, target, field string) {
	if !concreteReference(ref) {
		return
	}
	node, service, known := p.model.upstreamService(ref, upstream, target)
	if !known {
		p.reportf("%s '%s' cannot be resolved without a concrete upstream node", field, ref)
		return
	}
	expected := upstream
	if expected == "" {
		expected = p.model.upstreamTargetNode(target)
	}
	if expected != "" && node != expected {
		p.reportf("%s '%s' must reference a service on upstream node '%s'", field, ref, expected)
		return
	}
	index, present := p.model.nodeIndex[node]
	if !present {
		p.reportf("upstream service node '%s' does not resolve to a defined node", node)
		return
	}
	if !slices.Contains(p.model.nodes[index].services, service) {
		p.reportf("%s '%s' does not resolve to a service on node '%s'", field, ref, node)
	}
}
func (m *semanticModel) checkRelationshipProxy(c *semanticCollector) {
	for _, row := range m.relationships {
		if row.proxy == nil {
			continue
		}
		check := semanticProxyCheck{m, c, semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s' proxy_upstream", row.name)}
		node := check.node(row.proxy.Node, "upstream_node_ref")
		check.service(row.proxy.Service, node, row.target, "upstream_service_ref")
		if route := check.route(row.proxy.Route, row.source); route != nil && route.Target != nil {
			check.agreement(*row.proxy, *route.Target, row.target)
		}
	}
}
func (m *semanticModel) sourceApplicationRoutes(source string) map[string]semanticApplicationRoute {
	var apps []semanticApplication
	entry, known := m.index.declarations[source]
	if known && entry.kind == applicationsField {
		if app := m.applicationReference(source, entry.node); app != nil {
			apps = []semanticApplication{*app}
		}
	} else if index, present := m.nodeIndex[source]; present && m.nodes[index].runtime != nil {
		apps = m.nodes[index].runtime.Applications
	} else {
		return nil
	}
	routes := map[string]semanticApplicationRoute{}
	for _, app := range apps {
		for _, route := range app.Routes {
			routes[route.ID] = route
		}
	}
	return routes
}
func (m *semanticModel) applicationReference(ref, owner string) *semanticApplication {
	index, present := m.nodeIndex[owner]
	if !present || m.nodes[index].runtime == nil {
		return nil
	}
	for _, app := range m.nodes[index].runtime.Applications {
		if nodesPrefix+owner+".runtime.applications."+app.ID == ref {
			return &app
		}
	}
	return nil
}
func (p semanticProxyCheck) route(ref, source string) *semanticApplicationRoute {
	if !concreteReference(ref) {
		return nil
	}
	routes := p.model.sourceApplicationRoutes(source)
	if routes == nil {
		return nil
	}
	route, present := routes[ref]
	if !present {
		p.reportf("route_ref '%s' does not resolve to an application route on source '%s'", ref, source)
		return nil
	}
	return &route
}
func (p semanticProxyCheck) agreement(upstream semanticProxyUpstream, route semanticUpstreamTarget, target string) {
	p.fieldAgreement("upstream node", upstream.Node, route.Node, "", "")
	node := upstream.Node
	if node == "" {
		node = route.Node
	}
	p.fieldAgreement("upstream service", upstream.Service, route.Service, node, target)
	left, right := string(upstream.TLS), string(route.TLS)
	if (left == trueTerm || left == falseTerm) && (right == trueTerm || right == falseTerm) && left != right {
		p.reportf("TLS-termination '%s' disagrees with the route's upstream_target value '%s'", pythonBool(left == trueTerm), pythonBool(right == trueTerm))
	}
}
func pythonBool(value bool) string {
	if value {
		return "True"
	}
	return "False"
}
func (p semanticProxyCheck) fieldAgreement(field, left, right, node, target string) {
	if !concreteReference(left) || !concreteReference(right) {
		return
	}
	agree := left == right
	if field == "upstream service" {
		leftNode, leftService, leftOK := p.model.upstreamService(left, node, target)
		rightNode, rightService, rightOK := p.model.upstreamService(right, node, target)
		if leftOK && rightOK {
			agree = leftNode == rightNode && leftService == rightService
		}
	}
	if !agree {
		p.reportf("%s '%s' disagrees with the route's upstream_target value '%s'", field, left, right)
	}
}

func concreteReference(value string) bool { return value != "" && !variable(value) }
