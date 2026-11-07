package authoring

func (c materializedChecks) relationshipProxy(relationship map[string]any) error {
	upstream := object(relationship["proxy_upstream"])
	if upstream == nil {
		return nil
	}
	node := text(upstream["upstream_node_ref"])
	if node != "" && !variable(node) && object(c.value[nodesSection])[node] == nil {
		return semanticInvalid()
	}
	service := text(upstream["upstream_service_ref"])
	if service != "" && !variable(service) {
		if _, _, ok := c.proxyService(service, node, text(relationship[targetField])); !ok {
			return semanticInvalid()
		}
	}
	routeRef := text(upstream["route_ref"])
	if routeRef == "" || variable(routeRef) {
		return nil
	}
	routes := c.proxyRoutes(text(relationship[sourceField]))
	if routes == nil {
		return nil
	}
	route := object(routes[routeRef])
	if route == nil {
		return semanticInvalid()
	}
	return c.proxyAgreement(upstream, object(route["upstream_target"]), text(relationship[targetField]))
}

func (c materializedChecks) proxyRoutes(source string) map[string]any {
	var applications []any
	if entry, ok := c.index.aliases[source][source]; ok && entry.kind == applicationsField {
		applications = []any{entry.value}
	} else {
		runtime := object(object(object(c.value[nodesSection])[source])["runtime"])
		if runtime == nil {
			return nil
		}
		applications = array(runtime[applicationsField])
	}
	routes := map[string]any{}
	for _, application := range applications {
		for _, route := range array(object(application)["routes"]) {
			routes[text(object(route)["route_id"])] = route
		}
	}
	return routes
}

func (c materializedChecks) proxyTargetNode(target string) string {
	if object(c.value[nodesSection])[target] != nil {
		return target
	}
	for name := range c.serviceOwners[target] {
		return name
	}
	entry, _ := c.index.aliases[target][target]
	return entry.node
}

func (c materializedChecks) proxyService(reference, upstream, target string) (string, string, bool) {
	expected := upstream
	if expected == "" || variable(expected) {
		expected = c.proxyTargetNode(target)
	}
	for node := range c.serviceOwners[reference] {
		if expected != "" && node != expected {
			return "", "", false
		}
		return node, reference, true
	}
	qualified := "nodes." + expected + ".services." + reference
	return expected, qualified, expected != "" && c.serviceOwners[qualified][expected]
}

func concreteProxyText(value string) bool { return value != "" && !variable(value) }

func (c materializedChecks) proxyAgreement(upstream, route map[string]any, target string) error {
	if route == nil {
		return nil
	}
	node, routeNode := text(upstream["upstream_node_ref"]), text(route["target_node_ref"])
	if concreteProxyText(node) && concreteProxyText(routeNode) && node != routeNode {
		return semanticInvalid()
	}
	if node == "" {
		node = routeNode
	}
	service, routeService := text(upstream["upstream_service_ref"]), text(route["target_service"])
	if concreteProxyText(service) && concreteProxyText(routeService) {
		leftNode, leftService, leftOK := c.proxyService(service, node, target)
		rightNode, rightService, rightOK := c.proxyService(routeService, node, target)
		if !leftOK || !rightOK || leftNode != rightNode || leftService != rightService {
			return semanticInvalid()
		}
	}
	left, right := upstream["client_tls_terminated"], route["tls_terminated_here"]
	if left != nil && right != nil && left != right {
		return semanticInvalid()
	}
	return nil
}
