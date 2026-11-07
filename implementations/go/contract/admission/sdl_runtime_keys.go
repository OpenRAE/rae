package admission

func sdlUniqueKey(rows any, field string, skipEmpty bool) bool {
	seen := map[string]bool{}
	for _, row := range array(rows) {
		value := at(row, field)
		if skipEmpty && (value == nil || value == "") {
			continue
		}
		key := "s:" + text(value)
		if n, ok := number(value); ok {
			key = "n:" + n.RatString()
		}
		if seen[key] {
			return false
		}
		seen[key] = true
	}
	return true
}
func sdlRuntimeKeys(v any) error {
	for _, pair := range [][2]string{
		{termEnvironment, termName}, {"environment_files", termName}, {"mounts", "target"}, {"local_control_interfaces", "control_interface_id"},
		{"filesystem_inventory", "path"}, {"processes", termName}, {"processes", termPID}, {"service_listeners", "service_listener_id"},
		{"applications", "application_id"}, {"database_services", "database_service_id"}, {"dns_services", "dns_service_id"},
		{"network_sensors", "network_sensor_id"}, {"network_detection_engines", "network_detection_engine_id"}, {"security_monitoring_managers", "security_monitoring_manager_id"},
		{"ssh_servers", "ssh_server_id"}, {"datastore_services", "datastore_service_id"}, {"platform_applications", "platform_application_id"},
		{termForwardingAgents, "forwarding_agent_id"}, {"orchestration_authorities", "orchestration_authority_id"}, {"app_authorizations", "app_authorization_id"},
		{"scheduled_jobs", "scheduled_job_id"}, {"service_manager_units", "unit_id"}, {"service_manager_units", "unit_name"},
		{"identity_authorities", "identity_authority_id"}, {"file_services", "file_service_id"}, {"mail_services", "mail_service_id"}, {"software_components", termComponentID},
	} {
		if !sdlUniqueKey(at(v, pair[0]), pair[1], true) {
			return invalid()
		}
	}
	packages := array(at(v, "packages"))
	if len(rowTupleSet(packages, "manager", termName, termArchitecture)) != len(packages) {
		return invalid()
	}
	return nil
}
