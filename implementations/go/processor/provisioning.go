package processor

import (
	"bytes"
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

func (state *compilerState) nodeAddress(name string) string {
	node, exists := fieldValue(state.input.model.Nodes)[name]
	if exists && string(fieldValue(node.Type)) == termSwitch {
		return state.address(termProvision, termNetwork, name)
	}
	return state.address(termProvision, termNode, name)
}
func (state *compilerState) compileNodes() {
	nodes := fieldValue(state.input.model.Nodes)
	descriptors := realization.ConcernDescriptors()
	networks, compute := []Resource{}, []Resource{}
	findings := []diagnostic.Diagnostic{}
	for _, name := range orderedNames(nodes, state.names(termNodes)) {
		resource, local := state.compileNode(name, descriptors)
		if state.err != nil {
			return
		}
		findings = append(findings, local...)
		if resource.Kind == termNetwork {
			networks = append(networks, resource)
		} else {
			compute = append(compute, resource)
		}
	}
	state.model.Resources = append(state.model.Resources, networks...)
	state.model.Resources = append(state.model.Resources, compute...)
	state.addDiagnostics(findings)
}

type nodeWireSpec struct {
	Node           json.RawMessage `json:"node"`
	Infrastructure json.RawMessage `json:"infrastructure"`
}

func (state *compilerState) compileNode(name string, descriptors []realization.Descriptor) (Resource, []diagnostic.Diagnostic) {
	node := fieldValue(state.input.model.Nodes)[name]
	infra, hasInfra := fieldValue(state.input.model.Infrastructure)[name]
	addr := state.nodeAddress(name)
	dependencies, findings := state.nodeInfrastructureDependencies(name, addr)
	topology := state.topology.nodes[name]
	if topology != nil && topology.Role == "member" {
		for _, controller := range topology.ControllerAddresses {
			dependencies = append(dependencies, state.address(termProvision, "domain-controller", topology.DomainID, strings.TrimPrefix(controller, "provision.node.")))
		}
	}
	namespaceTarget := state.nodeNamespaceTarget(fieldValue(node.Runtime))
	if namespaceTarget != "" {
		dependencies = append(dependencies, namespaceTarget)
	}
	infrastructure := json.RawMessage("{}")
	if hasInfra {
		infrastructure = rawJSON(infra)
	}
	wire := nodeWireSpec{Node: state.nodeConcernProjection(name, descriptors), Infrastructure: infrastructure}
	resource := Resource{Address: addr, Name: name, Domain: termProvisioning, Kind: termNode, OrderingDependencies: dedupe(dependencies), RefreshDependencies: dedupe(dependencies), Topology: topology, HasACLs: hasInfra && len(fieldValue(infra.Acls)) > 0}
	if string(fieldValue(node.Type)) == termSwitch {
		state.compileNetworkNode(&resource, wire)
	} else {
		state.compileComputeNode(&resource, wire, namespaceTarget)
	}
	return resource, findings
}
func (state *compilerState) nodeConcernProjection(name string, descriptors []realization.Descriptor) json.RawMessage {
	omissions := [][]string{}
	for _, descriptor := range descriptors {
		if descriptor.Section == termNodes && !state.input.supplied[termNodesPrefix+name+"."+strings.Join(descriptor.AuthoredPath, ".")] {
			omissions = append(omissions, descriptor.AuthoredPath)
		}
	}
	return omitConcerns(rawJSON(fieldValue(state.input.model.Nodes)[name]), omissions)
}

type infrastructureReferenceGroup struct {
	refs          []string
	code, label   string
	requireSwitch bool
}

func (state *compilerState) nodeInfrastructureDependencies(name, address string) ([]string, []diagnostic.Diagnostic) {
	infrastructure, exists := fieldValue(state.input.model.Infrastructure)[name]
	dependencies := []string{}
	findings := []diagnostic.Diagnostic{}
	if !exists {
		return dependencies, findings
	}
	for _, group := range []infrastructureReferenceGroup{
		{fieldValue(infrastructure.Dependencies), "provisioning.infrastructure-dependency-ref", "infrastructure dependency", false},
		{fieldValue(infrastructure.Links), "provisioning.infrastructure-link-ref", "infrastructure link", true},
	} {
		for _, ref := range group.refs {
			dependency, finding := state.nodeInfrastructureReference(ref, address, group)
			if finding != nil {
				findings = append(findings, *finding)
			} else {
				dependencies = append(dependencies, dependency)
			}
		}
	}
	return dependencies, findings
}
func (state *compilerState) nodeInfrastructureReference(ref, address string, group infrastructureReferenceGroup) (string, *diagnostic.Diagnostic) {
	target, exists := fieldValue(state.input.model.Nodes)[ref]
	if !exists {
		finding := compileDiagnostic(group.code+"-unbound", termProvisioning, address, "Reference '"+ref+"' does not resolve to a defined "+group.label+".")
		return "", &finding
	}
	if group.requireSwitch && string(fieldValue(target.Type)) != termSwitch {
		finding := compileDiagnostic(group.code+"-invalid-type", termProvisioning, address, "Reference '"+ref+"' must resolve to a switch/network node for "+group.label+".")
		return "", &finding
	}
	return state.nodeAddress(ref), nil
}

type nodeNamespaceNetwork struct {
	TargetNodeRef string `json:"target_node_ref"`
}

type nodeContainerNamespaces struct {
	Network *nodeNamespaceNetwork `json:"network"`
}

type nodeContainerRuntime struct {
	Namespaces *nodeContainerNamespaces `json:"namespaces"`
}

func (state *compilerState) nodeNamespaceTarget(raw json.RawMessage) string {
	var runtime struct {
		Container *nodeContainerRuntime `json:"container"`
	}
	if err := json.Unmarshal(raw, &runtime); err != nil && len(raw) > 0 {
		state.err = invalidCompiled()
		return ""
	}
	if runtime.Container == nil || runtime.Container.Namespaces == nil || runtime.Container.Namespaces.Network == nil {
		return ""
	}
	return state.address(termProvision, termNode, strings.TrimPrefix(runtime.Container.Namespaces.Network.TargetNodeRef, termNodesPrefix))
}
func (state *compilerState) nodeCount(name string, strict bool) *json.Number {
	infra, exists := fieldValue(state.input.model.Infrastructure)[name]
	if !exists {
		return nil
	}
	raw := fieldValue(infra.Count)
	var count json.Number
	if json.Unmarshal(raw, &count) == nil {
		return &count
	}
	if strict && len(raw) > 0 && !bytes.Equal(raw, []byte(termNull)) {
		state.err = fault.New(fault.InvalidInput, "processor-count-range", nil)
	}
	return nil
}
func (state *compilerState) compileNetworkNode(resource *Resource, wire nodeWireSpec) {
	resource.Kind = termNetwork
	resource.Node = &NodeCapabilities{Kind: termSwitch, Count: state.nodeCount(resource.Name, false)}
	resource.Payload = state.payload(struct {
		Name     string       `json:"name"`
		Spec     nodeWireSpec `json:"spec"`
		NodeName string       `json:"node_name"`
		NodeKind string       `json:"node_kind"`
	}{resource.Name, wire, resource.Name, termSwitch})
}
func (state *compilerState) compileComputeNode(resource *Resource, wire nodeWireSpec, namespaceTarget string) {
	name := resource.Name
	node := fieldValue(state.input.model.Nodes)[name]
	osFamily, distribution, version, architecture := "", "", "", ""
	if state.input.supplied[termNodesPrefix+name+".os"] {
		osFamily = rawString(fieldValue(node.Os))
	}
	if state.input.supplied[termNodesPrefix+name+".os_distribution"] {
		distribution = rawString(fieldValue(node.OsDistribution))
	}
	if state.input.supplied[termNodesPrefix+name+".os_version"] {
		version = fieldValue(node.OsVersion)
	}
	if state.input.supplied[termNodesPrefix+name+".architecture"] {
		architecture = rawString(fieldValue(node.Architecture))
	}
	kind := string(fieldValue(node.Type))
	count := state.nodeCount(name, true)
	resource.Node = &NodeCapabilities{Kind: kind, OSFamily: osFamily, OSDistribution: distribution, OSVersion: version, Architecture: architecture, Count: count, NetworkNamespaceTarget: namespaceTarget}
	resource.Payload = state.payload(struct {
		Name                   string       `json:"name"`
		Spec                   nodeWireSpec `json:"spec"`
		NodeName               string       `json:"node_name"`
		NodeKind               string       `json:"node_kind"`
		OSFamily               string       `json:"os_family"`
		OSDistribution         string       `json:"os_distribution"`
		OSVersion              string       `json:"os_version"`
		Architecture           string       `json:"architecture"`
		Count                  *json.Number `json:"count"`
		NetworkNamespaceTarget string       `json:"network_namespace_target"`
		DomainTopology         any          `json:"domain_topology"`
	}{name, wire, name, kind, osFamily, distribution, version, architecture, count, namespaceTarget, topologyWire(resource.Topology)})
}

// omitConcerns visits each affected projection object once, even when many
// descriptor paths share the same runtime or container prefix.
func omitConcerns(raw json.RawMessage, paths [][]string) json.RawMessage {
	if len(paths) == 0 {
		return raw
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil || fields == nil {
		return raw
	}
	children := map[string][][]string{}
	removed := map[string]bool{}
	for _, path := range paths {
		if len(path) == 0 {
			continue
		}
		if len(path) == 1 {
			delete(fields, path[0])
			removed[path[0]] = true
			continue
		}
		children[path[0]] = append(children[path[0]], path[1:])
	}
	for name, paths := range children {
		if child, present := fields[name]; present && !removed[name] {
			fields[name] = omitConcerns(child, paths)
		}
	}
	return rawJSON(fields)
}
func (state *compilerState) compileFeatureBindings() {
	model := state.input.model
	nodes := fieldValue(model.Nodes)
	features := fieldValue(model.Features)
	findings := []diagnostic.Diagnostic{}
	for _, nodeName := range orderedNames(nodes, state.names(termNodes)) {
		node := nodes[nodeName]
		if string(fieldValue(node.Type)) != termCompute {
			continue
		}
		bindings := fieldValue(node.Features)
		nodeAddr := state.nodeAddress(nodeName)
		for _, name := range orderedNames(bindings, state.input.order["/nodes/"+escapePointer(nodeName)+"/features"]) {
			role := bindings[name]
			template, exists := features[name]
			if !exists {
				findings = append(findings, compileDiagnostic("provisioning.feature-template-ref-unbound", termProvisioning, nodeAddr, "Feature binding '"+name+"' on node '"+nodeName+"' does not resolve to a declared feature template."))
				continue
			}
			addr := state.address(termProvision, "feature", nodeName, name)
			dependencies := []string{nodeAddr}
			for _, dependency := range fieldValue(template.Dependencies) {
				if _, exists := bindings[dependency]; exists {
					dependencies = append(dependencies, state.address(termProvision, "feature", nodeName, dependency))
					continue
				}
				findings = append(findings, compileDiagnostic("provisioning.feature-dependency-binding-missing", termProvisioning, addr, "Feature binding '"+name+"' on node '"+nodeName+"' requires feature dependency '"+dependency+"' to also be bound on the same node."))
			}
			payload := struct {
				Name            string `json:"name"`
				Spec            any    `json:"spec"`
				NodeName        string `json:"node_name"`
				NodeAddress     string `json:"node_address"`
				FeatureName     string `json:"feature_name"`
				TemplateAddress string `json:"template_address"`
				RoleName        string `json:"role_name"`
			}{name, struct {
				Binding struct {
					Node string `json:"node"`
					Role string `json:"role"`
				} `json:"binding"`
				Template json.RawMessage `json:"template"`
			}{Binding: struct {
				Node string `json:"node"`
				Role string `json:"role"`
			}{nodeName, role}, Template: rawJSON(template)}, nodeName, nodeAddr, name, state.address("template", "feature", name), role}
			state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termProvisioning, Kind: "feature-binding", OrderingDependencies: dedupe(dependencies), RefreshDependencies: dedupe(dependencies), Payload: state.payload(payload)})
		}
	}
	state.addDiagnostics(findings)
}
