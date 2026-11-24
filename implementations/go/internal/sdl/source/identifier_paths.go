package source

import "strings"

// Runtime identity paths follow the published family vocabulary.
func runtimeIdentifier(tokens []string) bool {
	var family string
	var rest []string
	switch {
	case len(tokens) >= 6 && tokens[0] == nodesSection && tokens[2] == "runtime" && digits(tokens[4]):
		family = tokens[3]
		rest = tokens[5:]
	case len(tokens) >= 3 && tokens[0] == forwardingSection && digits(tokens[1]):
		family = forwardingSection
		rest = tokens[2:]
	default:
		return false
	}
	var normalized strings.Builder
	for i, t := range rest {
		if i%3 == 2 {
			if !digits(t) {
				return false
			}
			normalized.WriteString("/*")
		} else {
			normalized.WriteString("/" + t)
		}
	}
	switch family {
	case "service_listeners":
		return inWords(normalized.String(), "/service_listener_id")
	case "applications":
		return inWords(normalized.String(), "/application_id")
	case "database_services":
		return inWords(normalized.String(), "/database_service_id /database_service_id/databases/*/database_id")
	case "dns_services":
		return inWords(normalized.String(), "/dns_service_id /dns_service_id/zones/*/zone_id /dns_service_id/zones/*/zone_id/rrsets/*/rrset_id")
	case "identity_authorities":
		return inWords(normalized.String(), "/identity_authority_id /identity_authority_id/services/*/service_id /identity_authority_id/subjects/*/subject_id /identity_authority_id/policies/*/policy_id /identity_authority_id/relationships/*/relationship_id /identity_authority_id/resource_scopes/*/scope_id /identity_authority_id/identity_uses/*/use_id /identity_authority_id/access_observations/*/observation_id")
	case "file_services":
		return inWords(normalized.String(), "/file_service_id /file_service_id/shares/*/share_id /file_service_id/principals/*/principal_id /file_service_id/access_rules/*/rule_id /file_service_id/access_observations/*/observation_id")
	case "mail_services":
		return inWords(normalized.String(), "/mail_service_id /mail_service_id/components/*/component_id /mail_service_id/listeners/*/listener_id /mail_service_id/domains/*/domain_id /mail_service_id/mailbox_stores/*/store_id /mail_service_id/mailboxes/*/mailbox_id /mail_service_id/aliases/*/alias_id /mail_service_id/routing_rules/*/rule_id /mail_service_id/queues/*/queue_id /mail_service_id/settings/*/setting_id")
	case "network_sensors":
		return inWords(normalized.String(), "/network_sensor_id")
	case "network_detection_engines":
		return inWords(normalized.String(), "/network_detection_engine_id /network_detection_engine_id/rule_sources/*/source_id /network_detection_engine_id/network_sets/*/set_id /network_detection_engine_id/output_streams/*/stream_id /network_detection_engine_id/control_channels/*/channel_id")
	case "security_monitoring_managers":
		return inWords(normalized.String(), "/security_monitoring_manager_id /security_monitoring_manager_id/listeners/*/listener_id /security_monitoring_manager_id/components/*/component_id /security_monitoring_manager_id/agents/*/agent_id /security_monitoring_manager_id/agent_groups/*/group_id /security_monitoring_manager_id/content_sets/*/content_id /security_monitoring_manager_id/detection_definitions/*/definition_id /security_monitoring_manager_id/settings/*/setting_id")
	case "ssh_servers":
		return inWords(normalized.String(), "/ssh_server_id /ssh_server_id/match_rules/*/match_id")
	case "app_authorizations":
		return inWords(normalized.String(), "/app_authorization_id /app_authorization_id/principals/*/principal_id /app_authorization_id/roles/*/role_id /app_authorization_id/permission_grants/*/grant_id /app_authorization_id/role_mappings/*/mapping_id /app_authorization_id/tenants/*/tenant_id")
	case "scheduled_jobs":
		return inWords(normalized.String(), "/scheduled_job_id")
	case "datastore_services":
		return inWords(normalized.String(), "/datastore_service_id /datastore_service_id/nodes/*/node_id /datastore_service_id/nodes/*/node_id/plugins/*/plugin_id /datastore_service_id/nodes/*/node_id/endpoints/*/endpoint_id /datastore_service_id/partitions/*/partition_id /datastore_service_id/templates/*/template_id /datastore_service_id/mappings/*/mapping_id /datastore_service_id/settings/*/setting_id")
	case "platform_applications":
		return inWords(normalized.String(), "/platform_application_id /platform_application_id/secrets/*/secret_id /platform_application_id/secrets/*/secret_id/versions/*/version_id /platform_application_id/secrets/*/secret_id/consumers/*/selection_id /platform_application_id/cloud_limits/*/limit_id /platform_application_id/capabilities/*/capability_id /platform_application_id/organizations/*/organization_id /platform_application_id/tenants/*/tenant_id /platform_application_id/content_objects/*/content_object_id /platform_application_id/markings/*/marking_id /platform_application_id/upstream_bindings/*/binding_id /platform_application_id/connectors/*/connector_id /platform_application_id/settings/*/setting_id")
	case forwardingSection:
		return inWords(normalized.String(), "/forwarding_agent_id /forwarding_agent_id/sources/*/source_id /forwarding_agent_id/transforms/*/transform_id /forwarding_agent_id/ship_targets/*/target_id /forwarding_agent_id/reload_channels/*/reload_channel_id /forwarding_agent_id/settings/*/setting_id")
	case "orchestration_authorities":
		return inWords(normalized.String(), "/orchestration_authority_id /orchestration_authority_id/spawn_templates/*/template_id /orchestration_authority_id/realized_children/*/workload_id")
	default:
		return false
	}
}
