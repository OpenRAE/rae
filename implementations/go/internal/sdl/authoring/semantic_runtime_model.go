package authoring

import "encoding/json"

// Runtime facts are closed projections of the constructed SDL runtime inventory.
// Each family adds only the fields its native semantic rules consume.
type semanticRuntime struct {
	Mail          []semanticMailService       `json:"mail_services"`
	Monitors      []semanticMonitoringManager `json:"security_monitoring_managers"`
	Datastores    []semanticDatastore         `json:"datastore_services"`
	Platforms     []semanticPlatform          `json:"platform_applications"`
	Orchestration []semanticOrchestration     `json:"orchestration_authorities"`
	Controls      []struct {
		ID string `json:"control_interface_id"`
	} `json:"local_control_interfaces"`
	Applications   []semanticApplication             `json:"applications"`
	Units          []semanticServiceUnit             `json:"service_manager_units"`
	Databases      []semanticDatabaseService         `json:"database_services"`
	DNS            []semanticDNSService              `json:"dns_services"`
	SSH            []semanticSSHServer               `json:"ssh_servers"`
	Authorizations []semanticAuthorization           `json:"app_authorizations"`
	Identity       *semanticLocalIdentity            `json:"local_identity"`
	Authorities    []semanticIdentityAuthority       `json:"identity_authorities"`
	Files          []semanticFileService             `json:"file_services"`
	Listeners      []semanticListener                `json:"service_listeners"`
	Processes      []semanticProcessIdentity         `json:"processes"`
	Capabilities   *semanticRuntimeCapabilities      `json:"linux_capabilities"`
	Policy         *semanticRuntimeOperationalPolicy `json:"operational_policy"`
	Filesystem     []semanticObservedPath            `json:"filesystem_inventory"`
	Sensors        []semanticNetworkSensor           `json:"network_sensors"`
	Engines        []semanticDetectionEngine         `json:"network_detection_engines"`
	Network        *semanticRuntimeNetwork           `json:"network"`
	Container      *semanticRuntimeContainer         `json:"container"`
}
type semanticRuntimeContainer struct {
	Namespaces *semanticRuntimeNamespaces `json:"namespaces"`
}
type semanticRuntimeNamespaces struct {
	Network *semanticNetworkNamespace `json:"network"`
}
type semanticRuntimeNetwork struct {
	Endpoints []semanticRuntimeEndpoint `json:"endpoints"`
	Published []semanticPublishedPort   `json:"published_ports"`
}
type semanticRuntimeEndpoint struct {
	Network string `json:"network"`
	Address string `json:"ip_address"`
	Gateway string `json:"gateway"`
}
type semanticNetworkNamespace struct {
	Target string `json:"target_node_ref"`
}

func (runtime *semanticRuntime) networkNamespace() *semanticNetworkNamespace {
	if runtime == nil || runtime.Container == nil || runtime.Container.Namespaces == nil {
		return nil
	}
	return runtime.Container.Namespaces.Network
}

func decodeSemanticRuntime(raw json.RawMessage) (*semanticRuntime, error) {
	var runtime *semanticRuntime
	if len(raw) == 0 {
		raw = json.RawMessage(nullType)
	}
	if err := json.Unmarshal(raw, &runtime); err != nil {
		return nil, invalid()
	}
	return runtime, nil
}

type semanticNetworkSensor struct {
	ID            string   `json:"network_sensor_id"`
	Networks      []string `json:"monitored_network_refs"`
	Configuration []string `json:"configuration_file_refs"`
	Logs          []string `json:"log_file_refs"`
	Evidence      []string `json:"evidence_refs"`
}
type semanticDetectionEngine struct {
	ID            string   `json:"network_detection_engine_id"`
	Sensor        string   `json:"sensor_ref"`
	Configuration []string `json:"configuration_file_refs"`
	Logs          []string `json:"log_file_refs"`
	Evidence      []string `json:"evidence_refs"`
	Sources       []struct {
		ID        string   `json:"source_id"`
		Files     []string `json:"file_refs"`
		Generator string   `json:"generated_by"`
	} `json:"rule_sources"`
	Networks []struct {
		ID         string   `json:"set_id"`
		References []string `json:"network_refs"`
	} `json:"network_sets"`
	Outputs []struct {
		ID   string `json:"stream_id"`
		Path string `json:"path"`
	} `json:"output_streams"`
	Channels []struct {
		ID      string `json:"channel_id"`
		Service string `json:"service"`
		Path    string `json:"path"`
	} `json:"control_channels"`
}
type semanticObservedPath struct {
	Path string `json:"path"`
}
type semanticSourcePath struct {
	Destination string `json:"destination_path"`
}

func (m *semanticModel) nodeRuntimeFacts(name string, node *semanticNode) error {
	raw := fieldValue(m.transport.Nodes)[name]
	var err error
	node.runtime, err = decodeSemanticRuntime(fieldValue(raw.Runtime))
	if err != nil {
		return err
	}
	node.paths = map[string]bool{}
	if node.runtime != nil {
		for _, file := range node.runtime.Filesystem {
			if file.Path != "" {
				node.paths[file.Path] = true
			}
		}
	}
	return addObservedSourcePaths(fieldValue(raw.Source), node.paths)
}
func addObservedSourcePaths(sourceData json.RawMessage, paths map[string]bool) error {
	if len(sourceData) == 0 || sourceData[0] != '{' {
		return nil
	}
	var source struct {
		Build *struct {
			Copied []semanticSourcePath `json:"copied_sources"`
			Inputs []semanticSourcePath `json:"source_inputs"`
		} `json:"build"`
	}
	if json.Unmarshal(sourceData, &source) != nil {
		return invalid()
	}
	if source.Build == nil {
		return nil
	}
	for _, group := range [][]semanticSourcePath{source.Build.Copied, source.Build.Inputs} {
		for _, item := range group {
			if item.Destination != "" {
				paths[item.Destination] = true
			}
		}
	}
	return nil
}
