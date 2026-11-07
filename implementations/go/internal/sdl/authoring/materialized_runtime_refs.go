package authoring

import "strings"

func runtimeValues(value any, path string) []any {
	return runtimePathValues(value, strings.Split(path, "."))
}
func runtimePathValues(value any, path []string) []any {
	if len(path) == 0 {
		if value == nil {
			return nil
		}
		return []any{value}
	}
	if path[0] != "*" {
		return runtimePathValues(object(value)[path[0]], path[1:])
	}
	values := []any{}
	for _, row := range array(value) {
		values = append(values, runtimePathValues(row, path[1:])...)
	}
	return values
}
func runtimeIDs(value any, path string) map[string]bool {
	ids := map[string]bool{}
	for _, raw := range runtimeValues(value, path) {
		ids[text(raw)] = true
	}
	return ids
}
func runtimeReference(reference string, ids map[string]bool) error {
	if reference == "" || variable(reference) || ids[reference] {
		return nil
	}
	return semanticInvalid()
}
func runtimeReferences(values []any, ids map[string]bool) error {
	for _, value := range values {
		if !variable(value) && !ids[text(value)] {
			return semanticInvalid()
		}
	}
	return nil
}
func runtimeOptionalReferences(root any, path string, ids map[string]bool) error {
	for _, reference := range runtimeValues(root, path) {
		if err := runtimeReference(text(reference), ids); err != nil {
			return err
		}
	}
	return nil
}

func (c runtimeChecks) familyReferences() error {
	for _, family := range []string{databaseServicesField, "dns_services", "ssh_servers", "datastore_services", platformApplicationsField, "mail_services", "security_monitoring_managers", "file_services"} {
		for _, raw := range array(c.runtime[family]) {
			if err := c.ownedService(text(object(raw)["service"])); err != nil {
				return err
			}
		}
	}
	if err := c.runtimeLocalReferences(); err != nil {
		return err
	}
	if err := c.detectionChannels(); err != nil {
		return err
	}
	return c.familyFileReferences()
}
func (c runtimeChecks) runtimeLocalReferences() error {
	for _, relation := range [][2]string{
		{"orchestration_authorities.*.control_interface_ref", "local_control_interfaces.*.control_interface_id"},
		{"network_detection_engines.*.sensor_ref", "network_sensors.*.network_sensor_id"},
	} {
		ids := runtimeIDs(c.runtime, relation[1])
		for _, raw := range runtimeValues(c.runtime, relation[0]) {
			if err := runtimeReference(text(raw), ids); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c runtimeChecks) familyFileReferences() error {
	for _, path := range []string{
		"network_sensors.*.configuration_file_refs.*", "network_sensors.*.log_file_refs.*", "network_sensors.*.evidence_refs.*",
		"dns_services.*.configuration_file_refs.*", "dns_services.*.log_file_refs.*", "dns_services.*.zones.*.zone_file_refs.*",
		"security_monitoring_managers.*.configuration_file_refs.*", "security_monitoring_managers.*.log_file_refs.*", "security_monitoring_managers.*.evidence_refs.*",
		"network_detection_engines.*.configuration_file_refs.*", "network_detection_engines.*.log_file_refs.*", "network_detection_engines.*.evidence_refs.*", "network_detection_engines.*.rule_sources.*.file_refs.*",
	} {
		if err := c.observedFiles(runtimeValues(c.runtime, path)); err != nil {
			return err
		}
	}
	return nil
}
func (c runtimeChecks) databaseReferences() error {
	for _, raw := range array(c.runtime[databaseServicesField]) {
		roles := runtimeIDs(raw, "roles.*.role_id")
		objects := map[string]map[string]bool{"database": runtimeIDs(raw, "databases.*.database_id"), "schema": runtimeIDs(raw, "databases.*.schemas.*.schema_id"), "table": runtimeIDs(raw, "databases.*.schemas.*.tables.*.table_id")}
		for _, grant := range array(object(raw)["grants"]) {
			if err := runtimeReference(text(object(grant)["grantee_role_ref"]), roles); err != nil {
				return err
			}
			kind := text(object(grant)["object_type"])
			if !variable(kind) {
				if err := runtimeReference(text(object(grant)["object_ref"]), objects[kind]); err != nil {
					return err
				}
			}
		}
	}
	return nil
}
func (c runtimeChecks) authorizationReferences() error {
	for _, authorization := range array(c.runtime["app_authorizations"]) {
		roles := runtimeIDs(authorization, "roles.*.role_id")
		for _, path := range []string{"permission_grants.*.role_ref", "role_mappings.*.role_ref"} {
			if err := runtimeOptionalReferences(authorization, path, roles); err != nil {
				return err
			}
		}
	}
	authorizations := runtimeIDs(c.runtime, "app_authorizations.*.app_authorization_id")
	for _, path := range []string{"datastore_services.*.authorization_ref", "platform_applications.*.authorization_ref"} {
		if err := runtimeOptionalReferences(c.runtime, path, authorizations); err != nil {
			return err
		}
	}
	return c.platformContentReferences()
}
func (c runtimeChecks) platformContentReferences() error {
	for _, application := range array(c.runtime[platformApplicationsField]) {
		content, markings := runtimeIDs(application, "content_objects.*.content_object_id"), runtimeIDs(application, "markings.*.marking_id")
		for _, raw := range array(object(application)["content_objects"]) {
			if err := runtimeReferences(array(object(raw)["references"]), content); err != nil {
				return err
			}
			if err := runtimeReferences(array(object(raw)["marking_refs"]), markings); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c runtimeChecks) sshReferences() error {
	users := runtimeIDs(c.runtime, "local_identity.users.*.username")
	if len(users) == 0 {
		return nil
	}
	for _, raw := range runtimeValues(c.runtime, "ssh_servers.*.match_rules.*.criteria.*") {
		criterion := object(raw)
		pattern := text(criterion["pattern"])
		if criterion["kind"] != "local_user" || variable(pattern) || strings.ContainsAny(pattern, "*?!,") {
			continue
		}
		if err := runtimeReference(pattern, users); err != nil {
			return err
		}
	}
	return nil
}

func (c runtimeChecks) detectionChannels() error {
	for _, value := range runtimeValues(c.runtime, "network_detection_engines.*.control_channels.*.service") {
		if err := c.ownedService(text(value)); err != nil {
			return err
		}
	}
	for _, path := range []string{"network_detection_engines.*.control_channels.*.path", "network_detection_engines.*.output_streams.*.path"} {
		for _, value := range runtimeValues(c.runtime, path) {
			if text(value) != "" {
				if err := c.observedFiles([]any{value}); err != nil {
					return err
				}
			}
		}
	}
	return nil
}
