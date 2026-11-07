package authoring

func (c materializedChecks) forwardingReferences() error {
	seen := map[string]bool{}
	root := runtimeChecks{root: c}
	if err := root.forwardingAgents(array(c.value[forwardingSection]), seen); err != nil {
		return err
	}
	for name, raw := range object(c.value[nodesSection]) {
		runtime := object(object(raw)["runtime"])
		check := runtimeChecks{root: c, name: name}
		if err := check.forwardingAgents(array(runtime[forwardingSection]), seen); err != nil {
			return err
		}
		if err := check.ruleSourceGenerators(runtime); err != nil {
			return err
		}
	}
	return nil
}
func (c runtimeChecks) forwardingAgents(agents []any, seen map[string]bool) error {
	for _, raw := range agents {
		agent := object(raw)
		id := text(agent["forwarding_agent_id"])
		if id != "" && seen[id] {
			return semanticInvalid()
		}
		seen[id] = true
		for _, target := range array(agent["ship_targets"]) {
			if err := c.forwardingTarget(object(target)); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c runtimeChecks) forwardingTarget(target map[string]any) error {
	node, service := text(target["target_node_ref"]), text(target["target_service_ref"])
	if node != "" && !variable(node) && object(c.root.value[nodesSection])[node] == nil {
		return semanticInvalid()
	}
	if service == "" || variable(service) {
		return nil
	}
	if variable(node) {
		return nil
	}
	if node == "" {
		node = c.name
	}
	if node == "" {
		return semanticInvalid()
	}
	return c.serviceOnNode(node, service)
}
func (c runtimeChecks) ruleSourceGenerators(runtime map[string]any) error {
	for _, raw := range runtimeValues(runtime, "network_detection_engines.*.rule_sources.*.generated_by") {
		reference := text(raw)
		if reference == "" || variable(reference) {
			continue
		}
		matches := 0
		for _, declaration := range c.root.index.aliases[reference] {
			if declaration.kind == forwardingSection {
				matches++
			}
		}
		if matches != 1 {
			return semanticInvalid()
		}
	}
	return nil
}
