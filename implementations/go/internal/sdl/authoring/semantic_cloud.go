package authoring

import "github.com/OpenRAE/rae/implementations/go/internal/base/graph"

func (c *semanticCloud) report(message string) { c.collector.report(semanticOwner{}, message) }
func (m *semanticModel) checkCloudResources(collector *semanticCollector) {
	c := newSemanticCloud(m, collector)
	c.scopeGraph()
	c.policyGraph()
	for _, item := range c.items {
		c.item(item)
	}
}
func (c *semanticCloud) exactModel(ref, kind, label string) bool {
	if variable(ref) {
		return false
	}
	entry, known := c.model.index.declarations[ref]
	if !known || entry.kind != kind || entry.node == "" {
		c.report("cloud-reference: " + label + " requires an exact reference of the declared kind")
		return false
	}
	return true
}
func (c *semanticCloud) resource(ref, label string, workload bool) {
	if variable(ref) {
		return
	}
	entry, known := c.model.index.declarations[ref]
	valid := known && (cloudResourceKind(entry.kind) || entry.node != "")
	if valid && workload {
		valid = c.workload(entry)
	}
	if !valid {
		c.report("cloud-reference: " + label + " requires an exact resource reference")
	}
}
func (c *semanticCloud) workload(entry declaration) bool {
	switch entry.kind {
	case servicesField, applicationsField, platformApplicationsField:
		return true
	case nodesSection:
		if len(entry.tokens) != 2 {
			return false
		}
		index, known := c.model.nodeIndex[entry.tokens[1]]
		return known && c.model.nodes[index].kind == computeType
	default:
		return false
	}
}
func (c *semanticCloud) scope(ref, label string) {
	if ref != "" {
		c.exactModel(ref, cloudScopes, label)
	}
}
func (c *semanticCloud) scopeGraph() {
	edges := map[string][]string{}
	for _, address := range c.scopeOrder {
		scope := c.scopes[address]
		if scope.Parent == "" {
			continue
		}
		if c.exactModel(scope.Parent, cloudScopes, "scope parent") {
			parent := c.scopes[scope.Parent]
			if parent != nil && parent.Provider != scope.Provider && !variable(parent.Provider) && !variable(scope.Provider) {
				c.report("cloud-provider: parent scope must retain the same provider identity")
			}
		}
		if c.scopes[scope.Parent] != nil {
			edges[address] = []string{scope.Parent}
		}
	}
	if graph.HasCycle(edges) {
		c.report("cloud-cycle: scope references must not form a cycle")
	}
}
func (c *semanticCloud) policyGraph() {
	edges := map[string][]string{}
	for _, address := range c.policyOrder {
		if access := c.policies[address].Access; access != nil && c.policies[access.Source] != nil {
			edges[address] = []string{access.Source}
		}
	}
	if graph.HasCycle(edges) {
		c.report("cloud-cycle: policy references must not form a cycle")
	}
}
func (c *semanticCloud) item(item semanticCloudItem) {
	switch {
	case item.authority != nil:
		c.authority(item.authority)
	case item.subject != nil:
		c.scope(item.subject.Scope, "subject scope")
	case item.policy != nil:
		if item.policy.Access != nil {
			c.policy(item.policy.Access)
		}
	case item.app != nil:
		c.scope(item.app.Scope, "application scope")
		for _, limit := range item.app.Limits {
			c.scope(limit.Scope, "service limit scope")
		}
	case item.secret != nil:
		c.secret(item.secret)
	}
}
func (c *semanticCloud) authority(a *semanticIdentityAuthority) {
	for _, use := range a.Uses {
		c.resource(use.Workload, "workload reference", true)
		c.exactModel(use.Principal, cloudSubjects, "principal reference")
		if use.Source != "" {
			c.exactModel(use.Source, cloudSubjects, "source principal reference")
		}
	}
	for _, observation := range a.Observations {
		c.exactModel(observation.Principal, cloudSubjects, "observed principal reference")
		c.resource(observation.Resource, "observed resource reference", false)
		for _, ref := range observation.Contexts {
			c.resource(ref, "observation context reference", false)
		}
	}
}
