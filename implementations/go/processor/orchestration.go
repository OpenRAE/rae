package processor

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func (state *compilerState) compileInjects() {
	injects := fieldValue(state.input.model.Injects)
	for _, name := range orderedNames(injects, state.names(termInjects)) {
		state.model.Resources = append(state.model.Resources, Resource{Address: state.address(termOrchestration, termInject, name), Name: name, Domain: termOrchestration, Kind: termInject, Payload: state.payload(struct {
			Name string          `json:"name"`
			Spec json.RawMessage `json:"spec"`
		}{name, rawJSON(injects[name])})})
	}
}
func (state *compilerState) compileInjectBindings() {
	nodes := fieldValue(state.input.model.Nodes)
	injects := fieldValue(state.input.model.Injects)
	findings := []diagnostic.Diagnostic{}
	for _, nodeName := range orderedNames(nodes, state.names(termNodes)) {
		node := nodes[nodeName]
		if string(fieldValue(node.Type)) != termCompute {
			continue
		}
		nodeAddr := state.nodeAddress(nodeName)
		bindings := fieldValue(node.Injects)
		for _, name := range orderedNames(bindings, state.input.order["/nodes/"+escapePointer(nodeName)+"/injects"]) {
			if _, exists := injects[name]; !exists {
				findings = append(findings, compileDiagnostic("orchestration.inject-template-ref-unbound", termOrchestration, nodeAddr, "Inject binding '"+name+"' on node '"+nodeName+"' does not resolve to a declared inject template."))
				continue
			}
			injectAddr := state.address(termOrchestration, termInject, name)
			addr := state.address(termOrchestration, termInjectBinding, nodeName, name)
			role := bindings[name]
			payload := struct {
				Name            string `json:"name"`
				Spec            any    `json:"spec"`
				NodeName        string `json:"node_name"`
				NodeAddress     string `json:"node_address"`
				InjectName      string `json:"inject_name"`
				TemplateAddress string `json:"template_address"`
				RoleName        string `json:"role_name"`
			}{name, struct {
				Binding struct {
					Node string `json:"node"`
					Role string `json:"role"`
				} `json:"binding"`
				InjectAddress string `json:"inject_address"`
			}{struct {
				Node string `json:"node"`
				Role string `json:"role"`
			}{nodeName, role}, injectAddr}, nodeName, nodeAddr, name, state.address("template", termInject, name), role}
			state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termOrchestration, Kind: termInjectBinding, OrderingDependencies: []string{injectAddr}, RefreshDependencies: []string{nodeAddr, injectAddr}, Payload: state.payload(payload)})
		}
	}
	state.addDiagnostics(findings)
}
func (state *compilerState) compileEvents() {
	events := fieldValue(state.input.model.Events)
	findings := []diagnostic.Diagnostic{}
	// Inject binding dependencies retain compiler declaration order.
	bindings := map[string][]string{}
	for _, resource := range state.model.Resources {
		if resource.Kind == termInjectBinding {
			bindings[resource.Name] = append(bindings[resource.Name], resource.Address)
		}
	}
	for _, name := range orderedNames(events, state.names(termEvents)) {
		event := events[name]
		addr := state.address(termOrchestration, termEvent, name)
		assertionNames, injectNames := nonNilStrings(fieldValue(event.Assertions)), nonNilStrings(fieldValue(event.Injects))
		assertions, assertionFindings := state.namedReferences(termAssertions, termEvaluation, termAssertion, assertionNames, referenceFindingContext{owner: addr, domain: termOrchestration, code: "orchestration.assertion-ref", label: termAssertion})
		injects, injectFindings := state.namedReferences(termInjects, termOrchestration, termInject, injectNames, referenceFindingContext{owner: addr, domain: termOrchestration, code: "orchestration.inject-ref", label: termInject})
		findings = append(findings, assertionFindings...)
		findings = append(findings, injectFindings...)
		bindingDependencies := []string{}
		for _, resource := range state.model.Resources {
			if resource.Kind == termInjectBinding {
				if slices.Contains(injectNames, resource.Name) {
					bindingDependencies = append(bindingDependencies, resource.Address)
				}
			}
		}
		ordering := dedupe(append(append([]string{}, injects...), bindingDependencies...))
		refresh := dedupe(append(append(append([]string{}, assertions...), injects...), bindingDependencies...))
		payload := struct {
			Name               string          `json:"name"`
			Spec               json.RawMessage `json:"spec"`
			AssertionNames     []string        `json:"assertion_names"`
			AssertionAddresses []string        `json:"assertion_addresses"`
			InjectNames        []string        `json:"inject_names"`
			InjectAddresses    []string        `json:"inject_addresses"`
		}{name, rawJSON(event), assertionNames, assertions, injectNames, injects}
		state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termOrchestration, Kind: termEvent, OrderingDependencies: ordering, RefreshDependencies: refresh, UsesAssertionRefs: len(assertions) > 0, Payload: state.payload(payload)})
	}
	state.addDiagnostics(findings)
}
func (state *compilerState) compileScripts() {
	scripts := fieldValue(state.input.model.Scripts)
	findings := []diagnostic.Diagnostic{}
	for _, name := range orderedNames(scripts, state.names(termScripts)) {
		script := scripts[name]
		addr := state.address(termOrchestration, termScript, name)
		events := fieldValue(script.Events)
		refs := orderedNames(events, state.input.order["/scripts/"+escapePointer(name)+"/events"])
		dependencies, local := state.namedReferences(termEvents, termOrchestration, termEvent, refs, referenceFindingContext{owner: addr, domain: termOrchestration, code: "orchestration.event-ref", label: termEvent})
		findings = append(findings, local...)
		payload := struct {
			Name           string          `json:"name"`
			Spec           json.RawMessage `json:"spec"`
			EventAddresses []string        `json:"event_addresses"`
		}{name, rawJSON(script), dependencies}
		state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termOrchestration, Kind: termScript, OrderingDependencies: dependencies, RefreshDependencies: dependencies, Payload: state.payload(payload)})
	}
	state.addDiagnostics(findings)
}
func (state *compilerState) compileStories() {
	stories := fieldValue(state.input.model.Stories)
	findings := []diagnostic.Diagnostic{}
	for _, name := range orderedNames(stories, state.names(termStories)) {
		story := stories[name]
		addr := state.address(termOrchestration, termStory, name)
		dependencies, local := state.namedReferences(termScripts, termOrchestration, termScript, fieldValue(story.Scripts), referenceFindingContext{owner: addr, domain: termOrchestration, code: "orchestration.script-ref", label: termScript})
		findings = append(findings, local...)
		payload := struct {
			Name            string          `json:"name"`
			Spec            json.RawMessage `json:"spec"`
			ScriptAddresses []string        `json:"script_addresses"`
		}{name, rawJSON(story), dependencies}
		state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termOrchestration, Kind: termStory, OrderingDependencies: dependencies, RefreshDependencies: dependencies, Payload: state.payload(payload)})
	}
	state.addDiagnostics(findings)
}
