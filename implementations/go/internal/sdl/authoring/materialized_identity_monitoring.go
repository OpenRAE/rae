package authoring

func (c runtimeChecks) identityAuthorities() error {
	for _, raw := range array(c.runtime["identity_authorities"]) {
		authority := object(raw)
		ids := map[string]bool{text(authority["identity_authority_id"]): true}
		for _, spec := range [][2]string{{servicesField, "service_id"}, {"subjects", "subject_id"}, {"policies", "policy_id"}, {relationshipsField, "relationship_id"}, {"resource_scopes", "scope_id"}, {"identity_uses", "use_id"}, {accessObservationsField, observationIDField}} {
			for id := range runtimeIDs(authority, spec[0]+".*."+spec[1]) {
				ids[id] = true
			}
		}
		for _, service := range array(authority[servicesField]) {
			if err := c.ownedService(text(object(service)["service"])); err != nil {
				return err
			}
		}
		if err := identityLocalReferences(authority, ids); err != nil {
			return err
		}
	}
	return nil
}
func identityLocalReferences(authority map[string]any, ids map[string]bool) error {
	for _, relationship := range array(authority[relationshipsField]) {
		if err := runtimeReferences([]any{object(relationship)["source_ref"]}, ids); err != nil {
			return err
		}
		if err := runtimeReference(text(object(relationship)["target_ref"]), ids); err != nil {
			return err
		}
	}
	return runtimeReferences(runtimeValues(authority, "policies.*.applies_to_refs.*"), ids)
}

func (c runtimeChecks) securityMonitoring() error {
	for _, manager := range array(c.runtime["security_monitoring_managers"]) {
		if err := runtimeLocalRelations(manager, [][2]string{
			{"agent_groups.*.member_refs.*", "agents.*.agent_id"},
			{"agents.*.group_refs.*", "agent_groups.*.group_id"},
			{"detection_definitions.*.content_set_ref", "content_sets.*.content_id"},
			{"detection_definitions.*.if_sid_refs.*", detectionDefinitionIDs},
			{"detection_definitions.*.if_matched_sid_refs.*", detectionDefinitionIDs},
			{"detection_definitions.*.parent_definition_refs.*", detectionDefinitionIDs},
			{"settings.*.component_ref", runtimeComponentIDs},
		}); err != nil {
			return err
		}
		for _, service := range runtimeValues(manager, "listeners.*.service") {
			if err := c.ownedService(text(service)); err != nil {
				return err
			}
		}
		if err := c.monitoringFiles(manager); err != nil {
			return err
		}
		if err := c.monitoringTargets(manager); err != nil {
			return err
		}
	}
	return nil
}
func (c runtimeChecks) monitoringFiles(manager any) error {
	for _, path := range []string{"agent_groups.*.configuration_file_refs.*", "content_sets.*.file_refs.*", "detection_definitions.*.source_file_ref", "detection_definitions.*.evidence_refs.*", "settings.*.source_path"} {
		values := runtimeValues(manager, path)
		for _, value := range values {
			if text(value) != "" {
				if err := c.observedFiles([]any{value}); err != nil {
					return err
				}
			}
		}
	}
	return nil
}
func (c runtimeChecks) monitoringTargets(manager any) error {
	for _, definition := range array(object(manager)["detection_definitions"]) {
		if source := text(object(definition)["source_artifact_ref"]); source != "" {
			if err := c.root.index.targetReferences([]any{source}); err != nil {
				return err
			}
		}
		if err := c.root.index.targetReferences(array(object(definition)["target_refs"])); err != nil {
			return err
		}
	}
	return nil
}
