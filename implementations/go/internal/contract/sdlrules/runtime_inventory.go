package sdlrules

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

const (
	runtimeSettingID = "setting_id"
	runtimeSettings  = "settings"
)

// RuntimeCollection describes one addressable SDL inventory collection.
// It is descriptive metadata, without comparison or execution authority.
type RuntimeCollection struct {
	Collection string
	Identity   string
	Children   []RuntimeCollection
}

// RuntimeFamilies returns independent trees in reference declaration order.
// The published SDL contracts govern their fields and family-specific rules.
func RuntimeFamilies() []RuntimeCollection {
	return []RuntimeCollection{
		{"service_listeners", "service_listener_id", nil},
		{"applications", "application_id", nil},
		{"database_services", "database_service_id", []RuntimeCollection{{"databases", "database_id", nil}}},
		{"dns_services", "dns_service_id", []RuntimeCollection{{"zones", "zone_id", []RuntimeCollection{{"rrsets", "rrset_id", nil}}}}},
		{"identity_authorities", "identity_authority_id", []RuntimeCollection{{"services", "service_id", nil}, {"subjects", "subject_id", nil}, {"policies", "policy_id", nil}, {"relationships", "relationship_id", nil}, {"resource_scopes", "scope_id", nil}, {"identity_uses", "use_id", nil}, {"access_observations", "observation_id", nil}}},
		{"file_services", "file_service_id", []RuntimeCollection{{"shares", "share_id", nil}, {"principals", "principal_id", nil}, {"access_rules", "rule_id", nil}, {"access_observations", "observation_id", nil}}},
		{"mail_services", "mail_service_id", []RuntimeCollection{{"components", "component_id", nil}, {"listeners", "listener_id", nil}, {"domains", "domain_id", nil}, {"mailbox_stores", "store_id", nil}, {"mailboxes", "mailbox_id", nil}, {"aliases", "alias_id", nil}, {"routing_rules", "rule_id", nil}, {"queues", "queue_id", nil}, {runtimeSettings, runtimeSettingID, nil}}},
		{"network_sensors", "network_sensor_id", nil},
		{"network_detection_engines", "network_detection_engine_id", []RuntimeCollection{{"rule_sources", "source_id", nil}, {"network_sets", "set_id", nil}, {"output_streams", "stream_id", nil}, {"control_channels", "channel_id", nil}}},
		{"security_monitoring_managers", "security_monitoring_manager_id", []RuntimeCollection{{"listeners", "listener_id", nil}, {"components", "component_id", nil}, {"agents", "agent_id", nil}, {"agent_groups", "group_id", nil}, {"content_sets", "content_id", nil}, {"detection_definitions", "definition_id", nil}, {runtimeSettings, runtimeSettingID, nil}}},
		{"ssh_servers", "ssh_server_id", []RuntimeCollection{{"match_rules", "match_id", nil}}},
		{"app_authorizations", "app_authorization_id", []RuntimeCollection{{"principals", "principal_id", nil}, {"roles", "role_id", nil}, {"permission_grants", "grant_id", nil}, {"role_mappings", "mapping_id", nil}, {"tenants", "tenant_id", nil}}},
		{"scheduled_jobs", "scheduled_job_id", nil},
		{"datastore_services", "datastore_service_id", []RuntimeCollection{{"nodes", "node_id", []RuntimeCollection{{"plugins", "plugin_id", nil}, {"endpoints", "endpoint_id", nil}}}, {"partitions", "partition_id", nil}, {"templates", "template_id", nil}, {"mappings", "mapping_id", nil}, {runtimeSettings, runtimeSettingID, nil}}},
		{"platform_applications", "platform_application_id", []RuntimeCollection{{"secrets", "secret_id", []RuntimeCollection{{"versions", "version_id", nil}, {"consumers", "selection_id", nil}}}, {"cloud_limits", "limit_id", nil}, {"capabilities", "capability_id", nil}, {"organizations", "organization_id", nil}, {"tenants", "tenant_id", nil}, {"content_objects", "content_object_id", nil}, {"markings", "marking_id", nil}, {"upstream_bindings", "binding_id", nil}, {"connectors", "connector_id", nil}, {runtimeSettings, runtimeSettingID, nil}}},
		{"forwarding_agents", "forwarding_agent_id", []RuntimeCollection{{"sources", "source_id", nil}, {"transforms", "transform_id", nil}, {"ship_targets", "target_id", nil}, {"reload_channels", "reload_channel_id", nil}, {runtimeSettings, runtimeSettingID, nil}}},
		{"orchestration_authorities", "orchestration_authority_id", []RuntimeCollection{{"spawn_templates", "template_id", nil}, {"realized_children", "workload_id", nil}}},
	}
}

// RuntimeCollectionIdentity identifies a registered source-relative collection.
// Unknown families, non-collection paths and malformed indices return "".
// Indices describe path shape only; the lookup does not read inventory data.
func RuntimeCollectionIdentity(family, pointer string) string {
	var selected RuntimeCollection
	for _, collection := range RuntimeFamilies() {
		if strings.ReplaceAll(collection.Collection, "_", "-") == family {
			selected = collection
			break
		}
	}
	if selected.Identity == "" || pointer == "" {
		return selected.Identity
	}
	if !strings.HasPrefix(pointer, "/") {
		return ""
	}
	tokens := strings.Split(pointer[1:], "/")
	if len(tokens)%2 != 0 {
		return ""
	}
	for i := 0; i < len(tokens); i += 2 {
		if !jsonpointer.IsArrayIndex(tokens[i]) {
			return ""
		}
		selected = runtimeCollection(selected.Children, tokens[i+1])
		if selected.Identity == "" {
			return ""
		}
	}
	return selected.Identity
}

func runtimeCollection(collections []RuntimeCollection, name string) RuntimeCollection {
	for _, collection := range collections {
		if collection.Collection == name {
			return collection
		}
	}
	return RuntimeCollection{}
}
