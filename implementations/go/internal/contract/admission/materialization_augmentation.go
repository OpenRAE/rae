package admission

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type materializationScopeRule struct {
	path, permission string
	namespace        []string
}

func (r *materializationInventory) augmentation() error {
	original, current := r.execution.original, r.execution.current
	if !matchingFields(original.full, current.full, "augmentation_scope", "evidence_requirements") {
		return invalid()
	}
	policy := at(original.full, "augmentation_scope")
	if policy == nil {
		return nil
	}
	rules := make([]materializationScopeRule, 0, len(array(at(policy, "scopes"))))
	remaining := 100000
	for _, rule := range array(at(policy, "scopes")) {
		path, _, err := materializationSemanticAddress(original, stringAt(rule, "scope"), &remaining)
		if err != nil {
			return err
		}
		rules = append(rules, materializationScopeRule{path, stringAt(rule, "permission"), stringsOf(at(rule, "namespace"))})
	}
	for _, difference := range array(at(current.full, "materialization_provenance", "origins")) {
		if err := r.augmentationDifference(difference, policy, rules, &remaining); err != nil {
			return err
		}
	}
	return nil
}
func (r *materializationInventory) ordinarySelection(difference any) bool {
	if stringAt(difference, "change") != "selected" {
		return false
	}
	field := r.execution.original.ordinary[stringAt(difference, "field_pointer")]
	if field == "" {
		return false
	}
	for _, authority := range array(at(r.execution.plan, "realization_authority")) {
		mode := stringAt(authority, "mode")
		if stringAt(authority, "field_path") == field && (mode == termOpen || mode == termConstrained) {
			return true
		}
	}
	return false
}
func materializationScopeContains(parent, child string) bool {
	left, right := jsonpointer.Tokens(parent), jsonpointer.Tokens(child)
	return len(left) <= len(right) && slices.Equal(left, right[:len(left)])
}
func materializationScopeOpen(policy any, rules []materializationScopeRule, location string, namespace []string) bool {
	layers := map[string][]materializationScopeRule{"": {}}
	for _, rule := range rules {
		if len(rule.namespace) <= len(namespace) && slices.Equal(rule.namespace, namespace[:len(rule.namespace)]) && materializationScopeContains(rule.path, location) {
			key := strings.Join(rule.namespace, ".")
			layers[key] = append(layers[key], rule)
		}
	}
	names := make([]string, 0, len(layers))
	for key := range layers {
		names = append(names, key)
	}
	slices.Sort(names)
	permission := text(defaultMember(policy, "default", termOpen))
	for _, name := range names {
		if selected := materializationMostSpecificScope(layers[name]); selected != "" {
			permission = selected
		}
		if permission == termClosed {
			return false
		}
	}
	return permission == termOpen
}

func (r *materializationInventory) augmentationDifference(difference, policy any, rules []materializationScopeRule, remaining *int) error {
	original, current := r.execution.original, r.execution.current

	if r.ordinarySelection(difference) {
		return nil
	}
	content := current
	if stringAt(difference, "change") == "removed" {
		content = original
	}
	location, namespace, err := materializationSemanticAddress(content, stringAt(difference, "field_pointer"), remaining)
	if err != nil {
		return err
	}
	if !materializationScopeOpen(policy, rules, location, namespace) {
		return invalid()
	}
	for _, rule := range rules {
		*remaining--
		if *remaining < 0 {
			return invalid()
		}
		if materializationScopeContains(location, rule.path) {
			_, owner, resolveErr := materializationSemanticAddress(original, rule.path, remaining)
			if resolveErr != nil {
				return resolveErr
			}
			if !materializationScopeOpen(policy, rules, rule.path, owner) {
				return invalid()
			}
		}
	}
	return nil
}

func materializationMostSpecificScope(rules []materializationScopeRule) string {
	selected := -1
	for index, rule := range rules {
		if selected < 0 || len(jsonpointer.Tokens(rule.path)) > len(jsonpointer.Tokens(rules[selected].path)) {
			selected = index
		}
	}
	if selected < 0 {
		return ""
	}
	return rules[selected].permission
}
