package processor

import (
	"bytes"
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type policyOrigin struct {
	pointer   string
	definedAt string
}

// Binding origins come from admitted declarations. Resource addresses are
// opaque identities and are never split to recover an SDL owner.
func (state *compilerState) bindingPolicyOrigins() map[string]policyOrigin {
	result := map[string]policyOrigin{}
	for nodeName, node := range fieldValue(state.input.model.Nodes) {
		for _, group := range []struct {
			section, domain, kind string
			bindings              map[string]string
		}{
			{termFeatures, termProvision, "feature", fieldValue(node.Features)},
			{termConditions, termEvaluation, "condition", fieldValue(node.Conditions)},
			{termInjects, termOrchestration, termInjectBinding, fieldValue(node.Injects)},
		} {
			for name := range group.bindings {
				result[state.address(group.domain, group.kind, nodeName, name)] = policyOrigin{
					pointer:   "/nodes/" + escapePointer(nodeName) + "/" + group.section + "/" + escapePointer(name),
					definedAt: "/" + group.section + "/" + escapePointer(name),
				}
			}
		}
	}
	return result
}

func policyNamespaceFor(pointer string) []string {
	// The first declaration key is a single JSON-pointer token, even when its
	// name contains module dots. Dots identify the declaration's module only.
	tokens := strings.Split(pointer, "/")
	if len(tokens) < 3 {
		return nil
	}
	name := strings.ReplaceAll(strings.ReplaceAll(tokens[2], "~1", "/"), "~0", "~")
	parts := strings.Split(name, ".")
	return parts[:len(parts)-1]
}

func (state *compilerState) compileExecutionPolicies() {
	state.model.ExecutionPolicies = []ExecutionPolicy{}
	raw := fieldValue(state.input.model.ExecutionPolicy)
	if len(raw) == 0 || bytes.Equal(raw, []byte(termNull)) || state.err != nil {
		return
	}
	owner, err := processorAdmissionOwner()
	if err != nil {
		state.err = err
		return
	}
	resolver, err := state.executionPolicyResolver(owner, raw)
	if err != nil {
		state.err = err
		return
	}
	origins := state.bindingPolicyOrigins()
	for _, resource := range state.model.Resources {
		effective, pointer := state.resourceExecutionPolicy(resource, origins, resolver)
		if effective != nil {
			state.model.ExecutionPolicies = append(state.model.ExecutionPolicies, ExecutionPolicy{Address: resource.Address, Domain: resource.Domain, Policy: effective})
		}
		if resource.Kind == termWorkflow {
			state.workflowExecutionPolicies(resource, pointer, resolver)
		}
	}
}

type executionPolicyResolver struct {
	state    *compilerState
	owner    *admission.Validator
	document admission.Fragment
	evidence map[string]admission.Fragment
}

func (state *compilerState) executionPolicyResolver(owner *admission.Validator, raw []byte) (*executionPolicyResolver, error) {
	document, err := admitPolicyFragment(owner, admission.OperationPolicyDocument, raw)
	if err != nil {
		return nil, err
	}
	evidence := map[string]admission.Fragment{}
	for ref, requirement := range fieldValue(state.input.model.EvidenceRequirements) {
		fragment, err := admitPolicyFragment(owner, admission.RealizationValue, rawJSON(requirement))
		if err != nil {
			return nil, err
		}
		evidence[ref] = fragment
	}
	return &executionPolicyResolver{state, owner, document, evidence}, nil
}

//nolint:ireturn // The shared owner returns a sealed admitted fragment.
func admitPolicyFragment(owner *admission.Validator, profile admission.FragmentProfile, raw []byte) (admission.Fragment, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var input any
	if decoder.Decode(&input) != nil {
		return nil, invalidCompiled()
	}
	return admission.AdmitFragment(owner, profile, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
}

//nolint:ireturn // The shared owner returns a sealed effective policy fragment.
func (resolver *executionPolicyResolver) resolve(pointer string, namespace []string) admission.Fragment {
	if resolver.state.err != nil {
		return nil
	}
	result, err := admission.ResolveExecutionPolicy(resolver.owner, resolver.document, pointer, namespace, resolver.evidence)
	if err != nil {
		resolver.state.err = err
	}
	return result
}

//nolint:ireturn // The shared owner returns a sealed effective policy fragment.
func (state *compilerState) resourceExecutionPolicy(resource Resource, origins map[string]policyOrigin, resolver *executionPolicyResolver) (admission.Fragment, string) {
	sections := map[string]string{
		termNetwork: termNodes, termNode: termNodes, termDomainControllerPlacement: "identity_domains",
		termAccountPlacement: termAccounts, termContentPlacement: termContent, termGeneratedArtifact: termGeneratedArtifacts,
		termPersistentVolume: termPersistentVolumes, termInject: termInjects, termEvent: termEvents, termScript: termScripts,
		termStory: termStories, termWorkflow: termWorkflows, termProposition: termPropositions, termAssertion: termAssertions, termObjective: termObjectives,
	}
	var effective admission.Fragment
	section, known := sections[resource.Kind]
	name := resource.Name
	if resource.Kind == termDomainControllerPlacement && resource.Topology != nil {
		name = resource.Topology.DomainID
	}
	pointer := "/" + section + "/" + escapePointer(name)
	if origin, binding := origins[resource.Address]; binding {
		effective = resolver.resolve(origin.definedAt, policyNamespaceFor(origin.definedAt))
		application := resolver.resolve(origin.pointer, policyNamespaceFor(origin.pointer))
		if strings.Contains(ownedPolicyScope(application), "#/nodes") {
			effective = application
		}
	} else if known {
		effective = resolver.resolve(pointer, policyNamespaceFor(pointer))
	}
	return effective, pointer
}
func (state *compilerState) workflowExecutionPolicies(resource Resource, pointer string, resolver *executionPolicyResolver) {
	if resource.Kind == termWorkflow {
		for _, step := range state.input.order[pointer+"/steps"] {
			effective := resolver.resolve(pointer+"/steps/"+escapePointer(step), policyNamespaceFor(pointer))
			if strings.Contains(ownedPolicyScope(effective), "/steps") {
				state.model.ExecutionPolicies = append(state.model.ExecutionPolicies, ExecutionPolicy{Address: resource.Address, Domain: resource.Domain, Policy: effective})
			}
		}
	}
}

// ownedPolicyScope reads an effective policy issued by the shared resolver.
func ownedPolicyScope(input admission.Fragment) string {
	if input == nil {
		return ""
	}
	document, ok := input.Document().(map[string]any)
	if !ok {
		panic("processor: invalid owned execution policy")
	}
	scope, ok := document["governing_scope"].(string)
	if !ok {
		panic("processor: invalid owned execution policy scope")
	}
	return scope
}
