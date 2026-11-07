package authoring

import (
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type executionRule struct {
	scope, namespace string
	policy           map[string]any
}

func executionSection(section string) bool {
	return slices.Contains(executionSections(), section)
}

func nativeExecutionScope(pointer string) bool {
	tokens := jsonpointer.Tokens(pointer)
	if len(tokens) == 0 {
		return true
	}
	if !executionSection(tokens[0]) {
		return false
	}
	if len(tokens) <= 2 {
		return true
	}
	nested := tokens[0] == workflowsSection && tokens[2] == "steps" || tokens[0] == nodesSection && (tokens[2] == featuresSection || tokens[2] == conditionsSection || tokens[2] == injectsSection)
	return nested && len(tokens) <= 4
}

func lexicalNamespace(name string) string {
	if namespace, _, found := strings.CutLast(name, "."); found {
		return namespace
	}
	return ""
}

func namespaceOwns(owner, prefix string) bool {
	return prefix == "" || owner == prefix || strings.HasPrefix(owner, prefix+".")
}

func policyNamespace(value any) string {
	parts := make([]string, 0, len(array(value)))
	for _, part := range array(value) {
		parts = append(parts, text(part))
	}
	return strings.Join(parts, ".")
}

func (c materializedChecks) execution() error {
	document := object(c.value["execution_policy"])
	if document == nil {
		return nil
	}
	namespaces := map[string]bool{}
	for section, entries := range c.value {
		if executionSection(section) {
			for name := range object(entries) {
				namespaces[lexicalNamespace(name)] = true
			}
		}
	}
	rules := []executionRule{}
	for _, raw := range array(document[scopesField]) {
		value := object(raw)
		rule := executionRule{scope: text(value[scopeField]), namespace: policyNamespace(value[namespaceField]), policy: object(value[policyField])}
		if err := c.executionScope(rule, namespaces); err != nil {
			return err
		}
		rules = append(rules, rule)
	}
	if err := c.executionReferences(rules, object(document[defaultField])); err != nil {
		return err
	}
	return c.workflowPolicies(rules, object(document[defaultField]))
}

func (c materializedChecks) executionScope(rule executionRule, namespaces map[string]bool) error {
	canonical, err := c.scopes.resolve(rule.scope)
	if err != nil || !nativeExecutionScope(rule.scope) {
		return semanticInvalid()
	}
	found := false
	for namespace := range namespaces {
		found = found || namespaceOwns(namespace, rule.namespace)
	}
	if rule.namespace != "" && !found {
		return semanticInvalid()
	}
	tokens := jsonpointer.Tokens(canonical)
	if len(tokens) >= 2 && !namespaceOwns(lexicalNamespace(tokens[1]), rule.namespace) {
		return semanticInvalid()
	}
	return nil
}

func (c materializedChecks) executionReferences(rules []executionRule, fallback map[string]any) error {
	policies := []map[string]any{fallback}
	for _, rule := range rules {
		policies = append(policies, rule.policy)
	}
	for _, policy := range policies {
		if ref := text(policy["clock_ref"]); ref != "" && object(c.value["clocks"])[ref] == nil {
			return semanticInvalid()
		}
		if err := referencesPresent(array(policy[evidenceRefsField]), object(c.value["evidence_requirements"])); err != nil {
			return err
		}
	}
	return nil
}

func selectedExecutionRule(rules []executionRule, scope, namespace string, fallback map[string]any) executionRule {
	selected := executionRule{policy: fallback}
	matched := false
	for _, rule := range rules {
		if !namespaceOwns(namespace, rule.namespace) || rule.scope != "" && scope != rule.scope && !strings.HasPrefix(scope, rule.scope+"/") {
			continue
		}
		nsDepth, selectedDepth := strings.Count(rule.namespace, "."), strings.Count(selected.namespace, ".")
		if rule.namespace != "" {
			nsDepth++
		}
		if selected.namespace != "" {
			selectedDepth++
		}
		if !matched || nsDepth > selectedDepth || nsDepth == selectedDepth && strings.Count(rule.scope, "/") > strings.Count(selected.scope, "/") {
			selected, matched = rule, true
		}
	}
	return selected
}

func policyAttempts(policy map[string]any) *big.Int {
	if count, ok := modelInteger(object(policy[retryStep])["max_attempts"]); ok {
		return count
	}
	return big.NewInt(1)
}

func (c materializedChecks) workflowPolicies(rules []executionRule, fallback map[string]any) error {
	for name, raw := range object(c.value[workflowsSection]) {
		if err := workflowPolicy(name, object(raw), rules, fallback); err != nil {
			return err
		}
	}
	return nil
}

func workflowPolicy(name string, workflow map[string]any, rules []executionRule, fallback map[string]any) error {
	scope, namespace := "/workflows/"+name, lexicalNamespace(name)
	invocation := selectedExecutionRule(rules, scope, namespace, fallback)
	for stepName, rawStep := range object(workflow["steps"]) {
		step := object(rawStep)
		if text(step["type"]) != retryStep {
			continue
		}
		count, ok := modelInteger(step["max_attempts"])
		if !ok {
			return semanticInvalid()
		}
		if invocation.policy != nil && policyAttempts(invocation.policy).Cmp(big.NewInt(1)) > 0 && count.Cmp(big.NewInt(1)) > 0 {
			return semanticInvalid()
		}
		effective := selectedExecutionRule(rules, scope+"/steps/"+stepName, namespace, fallback)
		if effective.policy != nil && strings.Contains(effective.scope, "/steps") && policyAttempts(effective.policy).Cmp(count) != 0 {
			return semanticInvalid()
		}
	}
	return nil
}
