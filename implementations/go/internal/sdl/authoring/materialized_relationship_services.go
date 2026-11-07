package authoring

const (
	applicationsField    = "applications"
	runtimeMailDomainIDs = "domains.*.domain_id"
)

func (c materializedChecks) relationshipMail(relationship map[string]any) error {
	access := object(relationship[mailAccessField])
	if access == nil {
		return nil
	}
	target, ok := c.index.resolveTarget(text(relationship[targetField]), []string{"mail_services.*"})
	if !ok {
		return nil // Endpoint checks defer only an unresolved variable.
	}
	for field, path := range map[string]string{"listener_ref": "listeners.*.listener_id", "mailbox_ref": "mailboxes.*.mailbox_id", "domain_ref": runtimeMailDomainIDs} {
		if err := runtimeReference(text(access[field]), runtimeIDs(target.owner, path)); err != nil {
			return err
		}
	}
	return nil
}

func (c materializedChecks) relationshipForwarding(relationship map[string]any) error {
	edge := object(relationship["forwarding_edge"])
	reference := text(edge["forwarder_ref"])
	if reference == "" || variable(reference) {
		return nil
	}
	agents := append([]any(nil), array(c.value[forwardingSection])...)
	for _, node := range object(c.value[nodesSection]) {
		agents = append(agents, array(object(object(node)["runtime"])[forwardingSection])...)
	}
	var selected map[string]any
	for _, agent := range agents {
		if text(object(agent)["forwarding_agent_id"]) == reference {
			if selected != nil {
				return semanticInvalid()
			}
			selected = object(agent)
		}
	}
	if selected == nil {
		return semanticInvalid()
	}
	return forwardingProtocol(text(edge[protocolField]), array(selected["ship_targets"]))
}

func forwardingProtocol(protocol string, targets []any) error {
	if protocol == "" || protocol == "unknown" || variable(protocol) || len(targets) == 0 {
		return nil
	}
	for _, raw := range targets {
		target := text(object(raw)[protocolField])
		if target == "unknown" || variable(target) || target == protocol {
			return nil
		}
	}
	return semanticInvalid()
}

func (c materializedChecks) platformByID(reference string) (string, map[string]any) {
	for _, name := range c.nodeOrder {
		runtime := object(object(object(c.value[nodesSection])[name])["runtime"])
		for _, raw := range array(runtime[platformApplicationsField]) {
			if text(object(raw)["platform_application_id"]) == reference {
				return name, object(raw)
			}
		}
	}
	return "", nil
}

func (c materializedChecks) relationshipIntegration(relationship map[string]any) error {
	integration := object(relationship["service_integration"])
	if integration == nil {
		return nil
	}
	for _, field := range []string{"consumer_ref", "engine_ref"} {
		reference := text(integration[field])
		if reference != "" && !variable(reference) {
			if _, endpoint := c.platformByID(reference); endpoint == nil {
				return semanticInvalid()
			}
		}
	}
	name, engine := c.platformByID(text(integration["engine_ref"]))
	principal := text(integration["auth_principal_ref"])
	if engine == nil || principal == "" || variable(principal) {
		return nil
	}
	return c.integrationPrincipal(name, engine, principal)
}

func (c materializedChecks) integrationPrincipal(name string, engine map[string]any, principal string) error {
	runtime := object(object(object(c.value[nodesSection])[name])["runtime"])
	selected := text(engine["authorization_ref"])
	foundStore := false
	for _, authorization := range array(runtime["app_authorizations"]) {
		if selected != "" && !variable(selected) && text(object(authorization)["app_authorization_id"]) != selected {
			continue
		}
		foundStore = true
		if runtimeIDs(authorization, "principals.*.principal_id")[principal] {
			return nil
		}
	}
	if selected != "" && !variable(selected) && !foundStore {
		return nil // The engine's runtime check reports a missing selected store.
	}
	return semanticInvalid()
}
