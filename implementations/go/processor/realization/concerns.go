// Package realization owns the compiler and planner realization concerns.
package realization

import (
	"bytes"
	"encoding/json"
	"slices"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type concernDefinition struct {
	kind, section                             string
	authored, payload, identity, excluded     []string
	nonStatefulMountsOnly, sortScalarSequence bool
}

// The authored and payload paths are the reference concern registry's fixed
// contract mappings. Compiler lowering, projection and reconciliation share it.
//
//nolint:gochecknoglobals // This private contract table is fixed and never mutated or exposed.
var concernDefinitions = []concernDefinition{
	{kind: "node-type", section: termNodes, authored: []string{termType}, payload: []string{"node_kind"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termOsFamily, section: termNodes, authored: []string{"os"}, payload: []string{"os_family"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termOsDistribution, section: termNodes, authored: []string{"os_distribution"}, payload: []string{"os_distribution"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termOsVersion, section: termNodes, authored: []string{"os_version"}, payload: []string{"os_version"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "node-architecture", section: termNodes, authored: []string{termArchitecture}, payload: []string{termArchitecture}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "content-type", section: termContent, authored: []string{termType}, payload: []string{termSpec, termType}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termRuntimeEnvironment, section: termNodes, authored: []string{termRuntime, "environment"}, payload: []string{termSpec, termNode, termRuntime, "environment"}, identity: []string{termName}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termRuntimeMounts, section: termNodes, authored: []string{termRuntime, "mounts"}, payload: []string{termSpec, termNode, termRuntime, "mounts"}, identity: []string{termTarget}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: true, sortScalarSequence: false},
	{kind: termLinuxCapabilities, section: termNodes, authored: []string{termRuntime, "linux_capabilities"}, payload: []string{termSpec, termNode, termRuntime, "linux_capabilities"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termProcessResourceLimits, section: termNodes, authored: []string{termRuntime, termOperationalPolicy, termResourceLimits, "process_limits"}, payload: []string{termSpec, termNode, termRuntime, termOperationalPolicy, termResourceLimits, "process_limits"}, identity: []string{termIdentityMarker}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termPublishedPorts, section: termNodes, authored: []string{termRuntime, termNetwork, "published_ports"}, payload: []string{termSpec, termNode, termRuntime, termNetwork, "published_ports"}, identity: []string{termHostIP, termHostPort, termProtocol}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termForwardingAgents, section: termNodes, authored: []string{termRuntime, "forwarding_agents"}, payload: []string{termSpec, termNode, termRuntime, "forwarding_agents"}, identity: []string{"forwarding_agent_id"}, excluded: []string{termDescription, termEvidenceRefs, "ownership_role", termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termServiceListeners, section: termNodes, authored: []string{termRuntime, "service_listeners"}, payload: []string{termSpec, termNode, termRuntime, "service_listeners"}, identity: []string{"service_listener_id"}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-filesystem-inventory", section: termNodes, authored: []string{termRuntime, "filesystem_inventory"}, payload: []string{termSpec, termNode, termRuntime, "filesystem_inventory"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-local-control-interfaces", section: termNodes, authored: []string{termRuntime, "local_control_interfaces"}, payload: []string{termSpec, termNode, termRuntime, "local_control_interfaces"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-processes", section: termNodes, authored: []string{termRuntime, "processes"}, payload: []string{termSpec, termNode, termRuntime, "processes"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-restart-policy", section: termNodes, authored: []string{termRuntime, termOperationalPolicy, "restart"}, payload: []string{termSpec, termNode, termRuntime, termOperationalPolicy, "restart"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-node-memory-limit", section: termNodes, authored: []string{termRuntime, termOperationalPolicy, termResourceLimits, "memory"}, payload: []string{termSpec, termNode, termRuntime, termOperationalPolicy, termResourceLimits, "memory"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-node-memory-swap-limit", section: termNodes, authored: []string{termRuntime, termOperationalPolicy, termResourceLimits, "memory_swap"}, payload: []string{termSpec, termNode, termRuntime, termOperationalPolicy, termResourceLimits, "memory_swap"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-node-cpu-limit", section: termNodes, authored: []string{termRuntime, termOperationalPolicy, termResourceLimits, "cpu"}, payload: []string{termSpec, termNode, termRuntime, termOperationalPolicy, termResourceLimits, "cpu"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-node-pids-limit", section: termNodes, authored: []string{termRuntime, termOperationalPolicy, termResourceLimits, "pids"}, payload: []string{termSpec, termNode, termRuntime, termOperationalPolicy, termResourceLimits, "pids"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-entrypoint", section: termNodes, authored: []string{termRuntime, termContainer, "entrypoint"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "entrypoint"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-command", section: termNodes, authored: []string{termRuntime, termContainer, "command"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "command"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-log-driver", section: termNodes, authored: []string{termRuntime, termContainer, "log_driver"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "log_driver"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-log-options", section: termNodes, authored: []string{termRuntime, termContainer, "log_options"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "log_options"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-namespaces", section: termNodes, authored: []string{termRuntime, termContainer, "namespaces"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "namespaces"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-privileged", section: termNodes, authored: []string{termRuntime, termContainer, "privileged"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "privileged"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-read-only-rootfs", section: termNodes, authored: []string{termRuntime, termContainer, "read_only_rootfs"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "read_only_rootfs"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-publish-all-ports", section: termNodes, authored: []string{termRuntime, termContainer, "publish_all_ports"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "publish_all_ports"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-autoremove", section: termNodes, authored: []string{termRuntime, termContainer, "autoremove"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "autoremove"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-shm-size", section: termNodes, authored: []string{termRuntime, termContainer, "shm_size"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "shm_size"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-masked-paths", section: termNodes, authored: []string{termRuntime, termContainer, "masked_paths"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "masked_paths"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: true},
	{kind: "runtime-container-read-only-paths", section: termNodes, authored: []string{termRuntime, termContainer, "read_only_paths"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "read_only_paths"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: true},
	{kind: "runtime-container-cgroup-parent", section: termNodes, authored: []string{termRuntime, termContainer, "cgroup_parent"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "cgroup_parent"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-runtime-name", section: termNodes, authored: []string{termRuntime, termContainer, "runtime_name"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "runtime_name"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-init-process", section: termNodes, authored: []string{termRuntime, termContainer, "init_process"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "init_process"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-devices", section: termNodes, authored: []string{termRuntime, termContainer, "devices"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "devices"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-device-cgroup-rules", section: termNodes, authored: []string{termRuntime, termContainer, "device_cgroup_rules"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "device_cgroup_rules"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: true},
	{kind: "runtime-container-seccomp-profile", section: termNodes, authored: []string{termRuntime, termContainer, "seccomp_profile"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "seccomp_profile"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-security-opt", section: termNodes, authored: []string{termRuntime, termContainer, "security_opt"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "security_opt"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: true},
	{kind: "runtime-container-extra-hosts", section: termNodes, authored: []string{termRuntime, termContainer, "extra_hosts"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "extra_hosts"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-container-dns", section: termNodes, authored: []string{termRuntime, termContainer, "dns"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "dns"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: true},
	{kind: "runtime-container-dns-options", section: termNodes, authored: []string{termRuntime, termContainer, "dns_options"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "dns_options"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: true},
	{kind: "runtime-container-dns-search", section: termNodes, authored: []string{termRuntime, termContainer, "dns_search"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "dns_search"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: true},
	{kind: "runtime-container-group-add", section: termNodes, authored: []string{termRuntime, termContainer, "group_add"}, payload: []string{termSpec, termNode, termRuntime, termContainer, "group_add"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: true},
	{kind: "runtime-local-identity", section: termNodes, authored: []string{termRuntime, "local_identity"}, payload: []string{termSpec, termNode, termRuntime, "local_identity"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, "raw_entry", termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-identity-authorities", section: termNodes, authored: []string{termRuntime, "identity_authorities"}, payload: []string{termSpec, termNode, termRuntime, "identity_authorities"}, identity: []string{}, excluded: []string{"access_observations", termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-file-services", section: termNodes, authored: []string{termRuntime, "file_services"}, payload: []string{termSpec, termNode, termRuntime, "file_services"}, identity: []string{}, excluded: []string{"access_observations", termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-mail-services", section: termNodes, authored: []string{termRuntime, "mail_services"}, payload: []string{termSpec, termNode, termRuntime, "mail_services"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, "message_count", termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-network-hostname", section: termNodes, authored: []string{termRuntime, termNetwork, "hostname"}, payload: []string{termSpec, termNode, termRuntime, termNetwork, "hostname"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-network-domainname", section: termNodes, authored: []string{termRuntime, termNetwork, "domainname"}, payload: []string{termSpec, termNode, termRuntime, termNetwork, "domainname"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-network-endpoints", section: termNodes, authored: []string{termRuntime, termNetwork, "endpoints"}, payload: []string{termSpec, termNode, termRuntime, termNetwork, "endpoints"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-applications", section: termNodes, authored: []string{termRuntime, "applications"}, payload: []string{termSpec, termNode, termRuntime, "applications"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-database-services", section: termNodes, authored: []string{termRuntime, "database_services"}, payload: []string{termSpec, termNode, termRuntime, "database_services"}, identity: []string{"database_service_id"}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-dns-services", section: termNodes, authored: []string{termRuntime, "dns_services"}, payload: []string{termSpec, termNode, termRuntime, "dns_services"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-network-sensors", section: termNodes, authored: []string{termRuntime, "network_sensors"}, payload: []string{termSpec, termNode, termRuntime, "network_sensors"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-network-detection-engines", section: termNodes, authored: []string{termRuntime, "network_detection_engines"}, payload: []string{termSpec, termNode, termRuntime, "network_detection_engines"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, "loaded", termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-security-monitoring-managers", section: termNodes, authored: []string{termRuntime, "security_monitoring_managers"}, payload: []string{termSpec, termNode, termRuntime, "security_monitoring_managers"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, "loaded", termReadiness, "status"}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-ssh-servers", section: termNodes, authored: []string{termRuntime, "ssh_servers"}, payload: []string{termSpec, termNode, termRuntime, "ssh_servers"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-datastore-services", section: termNodes, authored: []string{termRuntime, "datastore_services"}, payload: []string{termSpec, termNode, termRuntime, "datastore_services"}, identity: []string{"datastore_service_id"}, excluded: []string{"creation_timestamp", termDescription, "doc_count", "doc_count_deleted", termEvidenceRefs, "open_closed_status", termReadiness, "store_size_bytes"}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-platform-applications", section: termNodes, authored: []string{termRuntime, "platform_applications"}, payload: []string{termSpec, termNode, termRuntime, "platform_applications"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness, "resolution_basis", "resolution_evidence_refs", "resolved_version_ref"}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-orchestration-authorities", section: termNodes, authored: []string{termRuntime, "orchestration_authorities"}, payload: []string{termSpec, termNode, termRuntime, "orchestration_authorities"}, identity: []string{"orchestration_authority_id"}, excluded: []string{termDescription, termEvidenceRefs, termReadiness, "realized_children"}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-app-authorizations", section: termNodes, authored: []string{termRuntime, "app_authorizations"}, payload: []string{termSpec, termNode, termRuntime, "app_authorizations"}, identity: []string{"app_authorization_id"}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-scheduled-jobs", section: termNodes, authored: []string{termRuntime, "scheduled_jobs"}, payload: []string{termSpec, termNode, termRuntime, "scheduled_jobs"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness, "run_state"}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-service-manager-units", section: termNodes, authored: []string{termRuntime, "service_manager_units"}, payload: []string{termSpec, termNode, termRuntime, "service_manager_units"}, identity: []string{"unit_id"}, excluded: []string{termDescription, termEvidenceRefs, "exit_code", "main_pid", termReadiness, "result", "status_text", "sub_state"}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-packages", section: termNodes, authored: []string{termRuntime, termPackages}, payload: []string{termSpec, termNode, termRuntime, termPackages}, identity: []string{termManager, termName}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termRuntimeRepositoryState, section: termNodes, authored: []string{termRuntime, termRepositoryState}, payload: []string{termSpec, termNode, termRuntime, termRepositoryState}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termPresence, termReadiness, "refinements"}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: termRuntimeSoftwareComponents, section: termNodes, authored: []string{termRuntime, termSoftwareComponents}, payload: []string{termSpec, termNode, termRuntime, termSoftwareComponents}, identity: []string{"component_id"}, excluded: []string{termDescription, termEvidenceRefs, "package_version_constraint", termPresence, termReadiness, "refinements", "version_constraint"}, nonStatefulMountsOnly: false, sortScalarSequence: false},
	{kind: "runtime-dependency-manifests", section: termNodes, authored: []string{termRuntime, "dependency_manifests"}, payload: []string{termSpec, termNode, termRuntime, "dependency_manifests"}, identity: []string{}, excluded: []string{termDescription, termEvidenceRefs, termReadiness}, nonStatefulMountsOnly: false, sortScalarSequence: false},
}

//nolint:gochecknoglobals // sync.Once publishes immutable admitted descriptors without request state.
var descriptorRegistry struct {
	once        sync.Once
	descriptors []Descriptor
	byKind      map[string]Descriptor
}

func loadConcernDescriptors() {
	descriptorRegistry.once.Do(func() {
		validator, err := realizationOwner()
		if err != nil {
			panic("realization: native descriptor validator unavailable")
		}
		descriptorRegistry.byKind = map[string]Descriptor{}
		for _, definition := range concernDefinitions {
			document := map[string]any{"section": definition.section, "authored_path": stringValues(definition.authored), "concern_kind": definition.kind, "payload_path": stringValues(definition.payload), "non_stateful_mounts_only": definition.nonStatefulMountsOnly, "explicitness_excluded_fields": stringValues(definition.excluded), "collection_identity_fields": stringValues(definition.identity)}
			fragment, err := admission.AdmitFragment(validator, admission.RealizationConcern, document, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
			if err != nil {
				panic("realization: invalid native concern descriptor")
			}
			descriptor := Descriptor{Kind: definition.kind, Section: definition.section, AuthoredPath: definition.authored, PayloadPath: definition.payload, IdentityFields: definition.identity, Document: fragment}
			descriptorRegistry.descriptors = append(descriptorRegistry.descriptors, descriptor)
			descriptorRegistry.byKind[definition.kind] = descriptor
		}
	})
}

// ConcernDescriptors returns independent views of the fixed concern registry.
func ConcernDescriptors() []Descriptor {
	loadConcernDescriptors()
	output := slices.Clone(descriptorRegistry.descriptors)
	for i := range output {
		output[i].AuthoredPath = slices.Clone(output[i].AuthoredPath)
		output[i].PayloadPath = slices.Clone(output[i].PayloadPath)
		output[i].IdentityFields = slices.Clone(output[i].IdentityFields)
	}
	return output
}

func nativeConcernDescriptor(kind string) (Descriptor, bool) {
	loadConcernDescriptors()
	descriptor, present := descriptorRegistry.byKind[kind]
	return descriptor, present
}
func stringValues(input []string) []any {
	result := make([]any, len(input))
	for i, v := range input {
		result[i] = v
	}
	return result
}
func nativeValue(raw []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var result any
	err := decoder.Decode(&result)
	return result, err
}
func concernDefinitionFor(kind string) (concernDefinition, bool) {
	for _, definition := range concernDefinitions {
		if definition.kind == kind {
			return definition, true
		}
	}
	if payload := derivedConcernPayload(kind); payload != nil {
		return concernDefinition{kind: kind, payload: payload}, true
	}
	return concernDefinition{}, false
}

// Derived provisioning concerns have exact payload authority without an
// authored leaf descriptor. Selection and readback share the same path owner.
func derivedConcernPayload(kind string) []string {
	switch kind {
	case "domain-topology":
		return []string{"domain_topology"}
	case "generated-artifact", "persistent-volume":
		return []string{termSpec}
	case "service-content-materialization", "service-search-index-schema-materialization":
		return []string{termServiceMaterialization}
	default:
		return nil
	}
}
