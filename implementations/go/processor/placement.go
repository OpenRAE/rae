package processor

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func (state *compilerState) computeTarget(name, owner, code, label string) (string, []diagnostic.Diagnostic) {
	node, exists := fieldValue(state.input.model.Nodes)[name]
	if !exists {
		return "", []diagnostic.Diagnostic{compileDiagnostic(code+"-unbound", termProvisioning, owner, "Reference '"+name+"' does not resolve to a defined "+label+".")}
	}
	if string(fieldValue(node.Type)) != termCompute {
		return "", []diagnostic.Diagnostic{compileDiagnostic(code+"-invalid-type", termProvisioning, owner, "Reference '"+name+"' must resolve to a compute node for "+label+".")}
	}
	return state.nodeAddress(name), nil
}
func (state *compilerState) compileContentPlacements() {
	content := fieldValue(state.input.model.Content)
	findings := []diagnostic.Diagnostic{}
	for _, name := range orderedNames(content, state.names(termContent)) {
		declaration := content[name]
		addr := state.address(termProvision, termContent, name)
		target, local := state.computeTarget(fieldValue(declaration.Target), addr, "provisioning.content-target-ref", "content target")
		findings = append(findings, local...)
		if target == "" {
			continue
		}
		sourceWithoutService := declaration
		sourceWithoutService.ServiceMaterialization = binding.Field[json.RawMessage]{}
		service, serviceWire, dependencies, local := state.compileServiceMaterialization(fieldValue(declaration.ServiceMaterialization), fieldValue(declaration.Target), string(fieldValue(declaration.Type)), rawJSON(sourceWithoutService), addr)
		findings = append(findings, local...)
		if len(local) > 0 {
			continue
		}
		ordering := append([]string{target}, dependencies...)
		var source generatedValueSource
		if raw := fieldValue(declaration.TextFrom); len(raw) > 0 {
			if err := json.Unmarshal(raw, &source); err != nil {
				state.err = invalidCompiled()
				return
			}
		}
		if source.GeneratedArtifact != "" {
			artifact := state.sectionName(source.GeneratedArtifact, termGeneratedArtifacts)
			if _, exists := fieldValue(state.input.model.GeneratedArtifacts)[artifact]; exists {
				ordering = append(ordering, state.address(termProvision, termGeneratedArtifact, artifact))
			}
		}
		payload := struct {
			Name                   string          `json:"name"`
			Spec                   json.RawMessage `json:"spec"`
			ContentName            string          `json:"content_name"`
			TargetNode             string          `json:"target_node"`
			TargetAddress          string          `json:"target_address"`
			ServiceMaterialization any             `json:"service_materialization"`
		}{name, rawJSON(declaration), name, fieldValue(declaration.Target), target, serviceWire}
		state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termProvisioning, Kind: termContentPlacement, TargetAddress: target, ContentType: string(fieldValue(declaration.Type)), ServiceMaterialization: service, OrderingDependencies: dedupe(ordering), RefreshDependencies: dedupe(ordering), Payload: state.payload(payload)})
	}
	state.addDiagnostics(findings)
}
func (state *compilerState) compileAccountPlacements() {
	accounts := fieldValue(state.input.model.Accounts)
	findings := []diagnostic.Diagnostic{}
	controllers := state.controllerPlacementsByDomain()
	for _, name := range orderedNames(accounts, state.names(termAccounts)) {
		account := accounts[name]
		addr := state.address(termProvision, "account", name)
		target, local := state.computeTarget(fieldValue(account.Node), addr, "provisioning.account-node-ref", "account node")
		findings = append(findings, local...)
		if target == "" {
			continue
		}
		var topology *DomainTopology
		if node, found := state.topology.accountNodes[name]; found {
			topology = state.topology.nodes[node]
		}
		dependencies := []string{target}
		if topology != nil {
			dependencies = append(dependencies, controllers[topology.DomainID]...)
		}
		features := []string{}
		for _, item := range []struct {
			used    bool
			feature string
		}{
			{len(fieldValue(account.Groups)) > 0, "groups"}, {fieldValue(account.Mail) != "", "mail"}, {fieldValue(account.Spn) != "", "spn"}, {fieldValue(account.Shell) != "", "shell"}, {fieldValue(account.Home) != "", "home"}, {rawEnabled(fieldValue(account.Disabled)), termDisabled}, {rawString(fieldValue(account.AuthMethod)) != "" && rawString(fieldValue(account.AuthMethod)) != "password", "auth_method"}, {len(fieldValue(account.CredentialBindings)) > 0, "credential_bindings"},
		} {
			if item.used {
				features = append(features, item.feature)
			}
		}
		slices.Sort(features)
		payload := struct {
			Name           string          `json:"name"`
			Spec           json.RawMessage `json:"spec"`
			AccountName    string          `json:"account_name"`
			NodeName       string          `json:"node_name"`
			TargetAddress  string          `json:"target_address"`
			DomainTopology any             `json:"domain_topology"`
		}{name, rawJSON(account), name, fieldValue(account.Node), target, topologyWire(topology)}
		state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termProvisioning, Kind: termAccountPlacement, TargetAddress: target, Topology: topology, AccountFeatures: features, OrderingDependencies: dedupe(dependencies), RefreshDependencies: dedupe(dependencies), Payload: state.payload(payload)})
	}
	state.addDiagnostics(findings)
}
func (state *compilerState) controllerPlacementsByDomain() map[string][]string {
	controllers := map[string][]string{}
	for _, resource := range state.model.Resources {
		if resource.Kind == termDomainControllerPlacement && resource.Topology != nil {
			controllers[resource.Topology.DomainID] = append(controllers[resource.Topology.DomainID], resource.Address)
		}
	}
	return controllers
}

func rawEnabled(raw json.RawMessage) bool {
	return len(raw) > 0 && string(raw) != termNull && string(raw) != "false" && string(raw) != `""`
}
