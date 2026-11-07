package authoring

type declaration struct {
	target, authority, action, declared bool
	kind                                string
	node, parent                        string
	value, owner                        map[string]any
}

// Objective subjects include world declarations and truth claims about them.
func (d declaration) objectiveSubject() bool {
	return d.action || d.kind == propositionsField || d.kind == assertionsSection
}

type declarationIndex struct {
	aliases   map[string]map[string]declaration
	addresses map[string]bool
	collision bool
}

func (d *declarationIndex) add(address, alias string, category declaration) {
	category.declared = category.declared || category.target
	if d.addresses[address] {
		d.collision = true
	}
	d.addresses[address] = true
	for _, name := range []string{address, alias} {
		if name == "" {
			continue
		}
		if d.aliases[name] == nil {
			d.aliases[name] = map[string]declaration{}
		}
		if _, present := d.aliases[name][address]; !present {
			d.aliases[name][address] = category
		}
	}
}
func sectionCategory(section string) declaration {
	category := sectionFlags(section)
	category.kind = section
	return category
}
func sectionFlags(section string) declaration {
	switch section {
	case nodesSection, infrastructureField, featuresSection, contentField, accountsSection, identityDomainsField, identityForestsField, identityFacadesField, deploymentTenantsField, deploymentCellsField, persistentVolumesField, generatedArtifactsField, forwardingSection, agentsSection, entitiesField, relationshipsField:
		return declaration{target: true, authority: true, action: true}
	case actionsSection, boundariesSection, behaviorSection:
		return declaration{target: true, authority: true}
	case propositionsField, assertionsSection, conditionsSection, injectsSection, eventsSection, scriptsField, storiesField, variationPointsField:
		return declaration{target: true}
	case outcomeRulesSection:
		return declaration{}
	default:
		return declaration{declared: true}
	}
}
func indexDeclarations(value map[string]any) *declarationIndex {
	index := &declarationIndex{aliases: map[string]map[string]declaration{}, addresses: map[string]bool{}}
	index.add("scenario."+text(value["name"]), "", declaration{})
	for _, section := range declarationSections() {
		if section == entitiesField {
			index.entities(object(value[section]), "")
			continue
		}
		for name, raw := range object(value[section]) {
			address := section + "." + name
			alias := name
			if section == infrastructureField {
				alias = ""
			}
			category := sectionCategory(section)
			category.value = object(raw)
			index.add(address, alias, category)
			index.children(section, name, address, object(raw))
		}
	}
	for _, raw := range array(value[forwardingSection]) {
		index.add(forwardingSection+"."+text(object(raw)["forwarding_agent_id"]), "", declaration{target: true, authority: true, action: true, kind: forwardingSection, value: object(raw)})
	}
	return index
}
func (d *declarationIndex) entities(entities map[string]any, prefix string) {
	for name, raw := range entities {
		qualified := prefix + name
		d.add("entities."+qualified, qualified, declaration{target: true, authority: true, action: true, kind: entitiesField, value: object(raw)})
		d.entities(object(object(raw)[entitiesField]), qualified+".")
	}
}
func (d *declarationIndex) children(section, name, address string, value map[string]any) {
	switch section {
	case nodesSection:
		for role := range object(value["roles"]) {
			d.add(address+".roles."+role, "", declaration{})
		}
		d.namedItems(array(value[servicesField]), address+".services.", false, servicesField)
		if runtime := object(value["runtime"]); runtime != nil {
			d.runtime(runtime, address+".runtime.", "", name, "", nil, runtimeDeclarationSpecs())
		}
	case infrastructureField:
		d.namedItems(array(value["acls"]), address+".acls.", false, "acls")
	case contentField:
		d.namedItems(array(value["items"]), address+".items.", true, "content-item")
	case workflowsSection:
		for step := range object(value["steps"]) {
			d.add(address+".steps."+step, name+"."+step, declaration{})
		}
	case behaviorSection:
		for affordance := range object(value[toolAffordancesField]) {
			d.add(address+".tool_affordances."+affordance, "", declaration{declared: true})
		}
		for delivery := range object(value[participantInjectDeliveriesField]) {
			d.add(address+".participant_inject_deliveries."+delivery, "", declaration{target: true, authority: true})
		}
	case variationPointsField:
		container := "members"
		if value["kind"] == "alternative" {
			container = "alternatives"
		}
		for member := range object(value[container]) {
			d.add(address+"."+container+"."+member, name+"."+member, declaration{declared: true})
		}
	}
}
func (d *declarationIndex) namedItems(items []any, prefix string, aliases bool, kind string) {
	for _, raw := range items {
		name := text(object(raw)["name"])
		if name == "" {
			continue
		}
		alias := ""
		if aliases {
			alias = name
		}
		d.add(prefix+name, alias, declaration{target: true, authority: true, action: true, kind: kind, value: object(raw)})
	}
}

type runtimeDeclaration struct {
	collection, identity string
	children             []runtimeDeclaration
}

func (d *declarationIndex) runtime(value map[string]any, prefix, parentKind, node, parent string, owner map[string]any, specs []runtimeDeclaration) {
	for _, spec := range specs {
		kind := spec.collection
		if parentKind != "" {
			kind = parentKind + "." + kind
		}
		for _, raw := range array(value[spec.collection]) {
			item := object(raw)
			address := prefix + spec.collection + "." + text(item[spec.identity])
			root := owner
			if root == nil {
				root = item
			}
			d.add(address, "", declaration{target: true, authority: true, action: true, kind: kind, node: node, parent: parent, value: item, owner: root})
			d.runtime(item, address+".", kind, node, address, root, spec.children)
		}
	}
}
func (d *declarationIndex) ambiguous(reference string, authority bool) bool {
	if variable(reference) {
		return false
	}
	candidates := d.aliases[reference]
	if !authority {
		return len(candidates) > 1
	}
	count, eligible := 0, false
	for _, candidate := range candidates {
		if candidate.target {
			count++
		}
		eligible = eligible || candidate.authority
	}
	return eligible && count > 1
}
func rejectImportAmbiguities(value map[string]any) error {
	index := indexDeclarations(value)
	for _, section := range []string{agentsSection, behaviorSection} {
		for _, raw := range object(value[section]) {
			owner := object(raw)
			for _, binding := range object(owner[controlContextField]) {
				if index.ambiguous(text(object(binding)[declarationRefField]), false) {
					return invalid()
				}
			}
		}
	}
	return index.rejectBehaviorAmbiguities(object(value[behaviorSection]))
}
func (d *declarationIndex) rejectBehaviorAmbiguities(specs map[string]any) error {
	for _, raw := range specs {
		spec := object(raw)
		for _, binding := range object(spec[toolAffordancesField]) {
			if d.ambiguous(text(object(binding)[toolRefField]), false) {
				return invalid()
			}
		}
		for _, reference := range array(spec[authorityScopeRefsField]) {
			if d.ambiguous(text(reference), true) {
				return invalid()
			}
		}
	}
	return nil
}

func runtimeDeclarationSpecs() []runtimeDeclaration {
	return []runtimeDeclaration{
		{"service_listeners", "service_listener_id", nil},
		{applicationsField, "application_id", nil},
		{databaseServicesField, "database_service_id", []runtimeDeclaration{{"databases", "database_id", nil}}},
		{"dns_services", "dns_service_id", []runtimeDeclaration{{"zones", "zone_id", []runtimeDeclaration{{"rrsets", "rrset_id", nil}}}}},
		{"identity_authorities", "identity_authority_id", []runtimeDeclaration{{servicesField, "service_id", nil}, {"subjects", "subject_id", nil}, {"policies", "policy_id", nil}, {relationshipsField, "relationship_id", nil}, {"resource_scopes", "scope_id", nil}, {"identity_uses", "use_id", nil}, {accessObservationsField, observationIDField, nil}}},
		{"file_services", "file_service_id", []runtimeDeclaration{{"shares", "share_id", nil}, {"principals", "principal_id", nil}, {"access_rules", "rule_id", nil}, {accessObservationsField, observationIDField, nil}}},
		{"mail_services", "mail_service_id", []runtimeDeclaration{{"components", "component_id", nil}, {"listeners", "listener_id", nil}, {"domains", "domain_id", nil}, {"mailbox_stores", "store_id", nil}, {"mailboxes", "mailbox_id", nil}, {"aliases", "alias_id", nil}, {"routing_rules", "rule_id", nil}, {"queues", "queue_id", nil}, {settingsField, settingIDField, nil}}},
		{"network_sensors", "network_sensor_id", nil},
		{"network_detection_engines", "network_detection_engine_id", []runtimeDeclaration{{"rule_sources", "source_id", nil}, {"network_sets", "set_id", nil}, {"output_streams", "stream_id", nil}, {"control_channels", "channel_id", nil}}},
		{"security_monitoring_managers", "security_monitoring_manager_id", []runtimeDeclaration{{"listeners", "listener_id", nil}, {"components", "component_id", nil}, {"agents", "agent_id", nil}, {"agent_groups", "group_id", nil}, {"content_sets", "content_id", nil}, {"detection_definitions", "definition_id", nil}, {settingsField, settingIDField, nil}}},
		{"ssh_servers", "ssh_server_id", []runtimeDeclaration{{"match_rules", "match_id", nil}}},
		{"app_authorizations", "app_authorization_id", []runtimeDeclaration{{"principals", "principal_id", nil}, {"roles", "role_id", nil}, {"permission_grants", "grant_id", nil}, {"role_mappings", mappingIDField, nil}, {"tenants", "tenant_id", nil}}},
		{"scheduled_jobs", "scheduled_job_id", nil},
		{"datastore_services", "datastore_service_id", []runtimeDeclaration{{"nodes", "node_id", []runtimeDeclaration{{"plugins", "plugin_id", nil}, {"endpoints", "endpoint_id", nil}}}, {"partitions", "partition_id", nil}, {"templates", templateIDField, nil}, {"mappings", mappingIDField, nil}, {settingsField, settingIDField, nil}}},
		{platformApplicationsField, "platform_application_id", []runtimeDeclaration{{"secrets", "secret_id", []runtimeDeclaration{{"versions", "version_id", nil}, {"consumers", "selection_id", nil}}}, {"cloud_limits", "limit_id", nil}, {"capabilities", "capability_id", nil}, {"organizations", "organization_id", nil}, {"tenants", "tenant_id", nil}, {"content_objects", "content_object_id", nil}, {"markings", "marking_id", nil}, {"upstream_bindings", "binding_id", nil}, {"connectors", "connector_id", nil}, {settingsField, settingIDField, nil}}},
		{"forwarding_agents", "forwarding_agent_id", []runtimeDeclaration{{"sources", "source_id", nil}, {"transforms", "transform_id", nil}, {"ship_targets", "target_id", nil}, {"reload_channels", "reload_channel_id", nil}, {settingsField, settingIDField, nil}}},
		{"orchestration_authorities", "orchestration_authority_id", []runtimeDeclaration{{"spawn_templates", templateIDField, nil}, {"realized_children", "workload_id", nil}}},
	}
}

func (d *declarationIndex) effectTargets(value map[string]any) error {
	if d.collision {
		return semanticInvalid()
	}
	checked := map[string]bool{}
	for _, raw := range object(value[actionsSection]) {
		if err := d.checkEffects(array(object(raw)["effects"]), checked); err != nil {
			return err
		}
	}
	return nil
}
func (d *declarationIndex) actionTarget(reference string) bool {
	count, eligible := 0, false
	for _, candidate := range d.aliases[reference] {
		if candidate.target {
			count++
		}
		eligible = eligible || candidate.action
	}
	return count == 1 && eligible
}

func (d *declarationIndex) checkEffects(effects []any, checked map[string]bool) error {
	for _, effect := range effects {
		for _, rawRef := range array(object(effect)["target_refs"]) {
			reference := text(rawRef)
			if variable(reference) || checked[reference] {
				continue
			}
			if len(d.aliases[reference]) > 0 && !d.actionTarget(reference) {
				return semanticInvalid()
			}
			checked[reference] = true
		}
	}
	return nil
}

func (d *declarationIndex) uniqueDeclared(reference string) bool {
	count := 0
	for _, candidate := range d.aliases[reference] {
		if candidate.declared {
			count++
		}
	}
	return count == 1
}
