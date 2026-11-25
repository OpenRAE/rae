package authoring

import (
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type importSymbols map[string]map[string]string

func symbolsFor(value map[string]any, namespace string, descriptor map[string]any) importSymbols {
	symbols := importSymbols{}
	exports := object(descriptor["exports"])
	for _, section := range declarationSections() {
		names := map[string]string{}
		for name := range object(value[section]) {
			names[name] = qualifiedImport(namespace, name, array(exports[section]))
		}
		symbols[section] = names
	}
	agents := map[string]string{}
	for _, raw := range array(value[forwardingSection]) {
		name := text(object(raw)[termForwardingAgentID])
		agents[name] = qualifiedImport(namespace, name, array(exports[forwardingSection]))
	}
	symbols[forwardingSection] = agents
	entities := map[string]bool{}
	collectEntityNames(object(value[entitiesField]), "", entities)
	for name := range entities {
		symbols[entitiesField][name] = qualifiedImport(namespace, name, array(exports[entitiesField]))
	}
	return symbols
}
func (s importSymbols) pointer(pointer string) string {
	tokens := jsonpointer.Tokens(pointer)
	if len(tokens) >= 2 {
		if renamed, present := s[tokens[0]][tokens[1]]; present {
			tokens[1] = renamed
		}
	}
	return jsonpointer.FromTokens(tokens)
}
func (c *composition) composePolicies(parent, incoming map[string]any, namespace string, descriptor map[string]any) error {
	symbols := symbolsFor(incoming, namespace, descriptor)
	augmentation, err := rewriteAugmentation(incoming, symbols, namespace)
	if err != nil {
		return err
	}
	execution := rewriteExecutionPolicy(object(incoming["execution_policy"]), symbols, namespace)
	safeState := rewriteSafeState(object(incoming[safeStateSection]), symbols, namespace)
	for name, imported := range map[string]map[string]any{"augmentation_scope": augmentation, "execution_policy": execution, safeStateSection: safeState} {
		if imported == nil {
			continue
		}
		local := object(parent[name])
		merged := map[string]any{scopesField: append(slices.Clone(array(local[scopesField])), array(imported[scopesField])...)}
		if supplied, present := local[defaultField]; present {
			merged[defaultField] = supplied
		}
		if err = c.checkBoundFragment("#/properties/"+name, merged); err != nil {
			return err
		}
		parent[name] = merged
	}
	return nil
}

//nolint:nilnil // An absent policy imposes no restriction.
func rewriteAugmentation(value map[string]any, symbols importSymbols, namespace string) (map[string]any, error) {
	policy := object(value["augmentation_scope"])
	if policy == nil {
		return nil, nil
	}
	scopes := []any{}
	rootRule := false
	for _, raw := range array(policy[scopesField]) {
		rule := maps.Clone(object(raw))
		scope, err := augmentationPointer(text(rule[scopeField]), value, symbols)
		if err != nil {
			return nil, err
		}
		rule[scopeField] = scope
		owner := policyNamespace(namespace, array(rule[namespaceField]))
		rule[namespaceField] = owner
		rootRule = rootRule || scope == "" && len(owner) == 1
		scopes = append(scopes, rule)
	}
	if namespace != "" && !rootRule {
		permission := openTerm
		if supplied, present := policy[defaultField]; present {
			permission = text(supplied)
		}
		scopes = append([]any{map[string]any{scopeField: "", "permission": permission, namespaceField: []any{namespace}}}, scopes...)
	}
	permission := any(openTerm)
	if namespace == "" {
		if supplied, present := policy[defaultField]; present {
			permission = supplied
		}
	}
	return map[string]any{defaultField: permission, scopesField: scopes}, nil
}
func augmentationPointer(pointer string, value map[string]any, symbols importSymbols) (string, error) {
	if !strings.HasPrefix(pointer, "/forwarding_agents/") {
		return symbols.pointer(pointer), nil
	}
	source, _, err := admission.ResolveSDLObservationScope(value, pointer)
	if err != nil {
		return "", err
	}
	renamed := maps.Clone(value)
	agents := []any{}
	for _, raw := range array(value[forwardingSection]) {
		agent := maps.Clone(object(raw))
		agent[termForwardingAgentID] = symbols[forwardingSection][text(agent[termForwardingAgentID])]
		agents = append(agents, agent)
	}
	renamed[forwardingSection] = agents
	_, canonical, err := admission.ResolveSDLObservationScope(renamed, source)
	return canonical, err
}
func rewriteExecutionPolicy(document map[string]any, symbols importSymbols, namespace string) map[string]any {
	if document == nil {
		return nil
	}
	scopes := []any{}
	for _, raw := range array(document[scopesField]) {
		rule := object(raw)
		for _, owner := range executionNamespaces(rule, symbols, namespace) {
			scopes = append(scopes, map[string]any{namespaceField: owner, scopeField: executionPointer(text(rule[scopeField]), symbols), policyField: rewritePolicy(object(rule[policyField]), symbols)})
		}
	}
	result := map[string]any{scopesField: scopes, defaultField: nil}
	if policy := object(document[defaultField]); policy != nil {
		rewritten := rewritePolicy(policy, symbols)
		if namespace != "" {
			result[scopesField] = append([]any{map[string]any{namespaceField: []any{namespace}, scopeField: "", policyField: rewritten}}, scopes...)
		} else {
			result[defaultField] = rewritten
		}
	}
	return result
}

// rewriteSafeState preserves safe-state definitions and private proof bindings
// across an import. An imported default governs only its own namespace; an
// unprefixed rewrite keeps the root default.
func rewriteSafeState(document map[string]any, symbols importSymbols, namespace string) map[string]any {
	if document == nil {
		return nil
	}
	rules := []map[string]any{}
	for _, raw := range array(document[scopesField]) {
		rules = append(rules, object(raw))
	}
	result := map[string]any{scopesField: []any{}, defaultField: nil}
	if state := object(document[defaultField]); state != nil {
		if namespace != "" {
			rules = append(rules, map[string]any{namespaceField: []any{}, scopeField: "", "state": state})
		} else {
			result[defaultField] = rewriteSafeStateValue(state, symbols)
		}
	}
	scopes := []any{}
	for _, rule := range rules {
		state := rewriteSafeStateValue(object(rule["state"]), symbols)
		for _, owner := range lexicalNamespaces(rule, symbols, namespace, []string{nodesSection}) {
			scopes = append(scopes, map[string]any{namespaceField: owner, scopeField: symbols.pointer(text(rule[scopeField])), "state": state})
		}
	}
	result[scopesField] = scopes
	return result
}
func rewriteSafeStateValue(state map[string]any, symbols importSymbols) map[string]any {
	result := safeStateValue(state)
	renamed := []any{}
	for _, ref := range array(state[assertionRefsField]) {
		replacement := ref
		if qualified, present := symbols[assertionsSection][text(ref)]; present {
			replacement = qualified
		}
		renamed = append(renamed, replacement)
	}
	result[assertionRefsField] = renamed
	return result
}
func rewritePolicy(policy map[string]any, symbols importSymbols) map[string]any {
	result := maps.Clone(policy)
	if reference := text(result["clock_ref"]); reference != "" {
		if renamed, present := symbols["clocks"][reference]; present {
			result["clock_ref"] = renamed
		}
	}
	if refs, present := result[evidenceRefsField]; present {
		renamed := []any{}
		for _, reference := range array(refs) {
			replacement := reference
			if qualified, present := symbols[evidenceRequirementsSection][text(reference)]; present {
				replacement = qualified
			}
			renamed = append(renamed, replacement)
		}
		result[evidenceRefsField] = renamed
	}
	return result
}
func executionPointer(pointer string, symbols importSymbols) string {
	tokens := jsonpointer.Tokens(symbols.pointer(pointer))
	if len(tokens) == 4 && tokens[0] == nodesSection && slices.Contains([]string{featuresSection, conditionsSection, injectsSection}, tokens[2]) {
		if renamed, present := symbols[tokens[2]][tokens[3]]; present {
			tokens[3] = renamed
		}
	}
	return jsonpointer.FromTokens(tokens)
}
func executionNamespaces(rule map[string]any, symbols importSymbols, namespace string) [][]any {
	return lexicalNamespaces(rule, symbols, namespace, executionSections())
}

// lexicalNamespaces rewrites one rule's lexical owner through the module
// symbol maps of the sections that it may address.
func lexicalNamespaces(rule map[string]any, symbols importSymbols, namespace string, sections []string) [][]any {
	owner := array(rule[namespaceField])
	prefix := policyNamespace(namespace, owner)
	if len(owner) == 0 {
		return [][]any{prefix}
	}
	targets := map[string][]any{}
	tokens := jsonpointer.Tokens(text(rule[scopeField]))
	for _, section := range sections {
		if len(tokens) > 0 && tokens[0] != section {
			continue
		}
		for old, renamed := range symbols[section] {
			if target := executionOwner(tokens, old, renamed, owner); target != nil {
				targets[strings.Join(stringItems(target), ".")] = target
			}
		}
	}
	if len(targets) == 0 {
		return [][]any{prefix}
	}
	result := [][]any{}
	for _, key := range slices.Sorted(maps.Keys(targets)) {
		result = append(result, targets[key])
	}
	return result
}
func executionOwner(tokens []string, old, renamed string, namespace []any) []any {
	if len(tokens) >= 2 && old != tokens[1] {
		return nil
	}
	oldParts, newParts := strings.Split(old, "."), strings.Split(renamed, ".")
	oldOwner, newOwner := oldParts[:len(oldParts)-1], newParts[:len(newParts)-1]
	if len(namespace) > len(oldOwner) || !slices.Equal(oldOwner[:len(namespace)], stringItems(namespace)) {
		return nil
	}
	depth := len(newOwner) - len(oldOwner) + len(namespace)
	result := make([]any, depth)
	for i, part := range newOwner[:depth] {
		result[i] = part
	}
	return result
}
func stringItems(items []any) []string {
	result := make([]string, len(items))
	for i, item := range items {
		result[i] = text(item)
	}
	return result
}
func executionSections() []string {
	return []string{nodesSection, featuresSection, conditionsSection, injectsSection, identityDomainsField, accountsSection, contentField, generatedArtifactsField, persistentVolumesField, eventsSection, scriptsField, storiesField, workflowsSection, propositionsField, assertionsSection, objectivesSection}
}

func policyNamespace(namespace string, owner []any) []any {
	if namespace == "" {
		return append([]any{}, owner...)
	}
	return append([]any{namespace}, owner...)
}
