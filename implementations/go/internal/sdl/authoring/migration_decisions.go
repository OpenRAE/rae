package authoring

import (
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

func applySentinelDecisions(source *Document, decisions []sentinelDecision) (map[string]any, string) {
	if err := source.semantic.loadIntent(); err != nil {
		return nil, termSourceOrTargetInvalid
	}
	pointers := source.semantic.intent.sentinels
	if !sentinelDecisionsComplete(pointers, decisions) {
		return nil, "sentinel-decision-required"
	}
	decoded, err := ingress.Parse(source.JSON(), modelLimits(source.data), ingress.Object)
	if err != nil {
		return nil, termSourceOrTargetInvalid
	}
	payload := object(decoded)
	deletions := []string{}
	for _, decision := range decisions {
		remove, code := applySentinelDecision(payload, source, decision)
		if code != "" {
			return nil, code
		}
		if remove {
			deletions = append(deletions, decision.Pointer)
		}
	}
	slices.SortFunc(deletions, func(a, b string) int {
		first, second := jsonpointer.Tokens(a), jsonpointer.Tokens(b)
		i, _ := strconv.Atoi(first[len(first)-1])
		j, _ := strconv.Atoi(second[len(second)-1])
		if i != j {
			return j - i
		}
		return strings.Compare(a, b)
	})
	for _, pointer := range deletions {
		if _, err = changeMigrationValue(payload, jsonpointer.Tokens(pointer), nil, true); err != nil {
			return nil, termSourceOrTargetInvalid
		}
	}
	return payload, ""
}
func sentinelDecisionsComplete(pointers map[string]bool, decisions []sentinelDecision) bool {
	if len(pointers) != len(decisions) {
		return false
	}
	for _, decision := range decisions {
		if !pointers[decision.Pointer] {
			return false
		}
	}
	return true
}
func applySentinelDecision(payload map[string]any, source *Document, decision sentinelDecision) (bool, string) {
	switch decision.Interpretation {
	case "knowledge":
		return false, ""
	case "delegated":
		if !explicitOpenRealization(source.semantic.root, decision.Pointer) {
			return false, "delegation-needs-open-scope"
		}
		return true, ""
	default:
		if decision.Identity == nil {
			return false, termSourceOrTargetInvalid
		}
		if _, err := changeMigrationValue(payload, jsonpointer.Tokens(decision.Pointer), *decision.Identity, false); err != nil {
			return false, termSourceOrTargetInvalid
		}
		return false, ""
	}
}
func changeMigrationValue(value any, tokens []string, replacement any, remove bool) (any, error) {
	if len(tokens) == 0 {
		return nil, invalid()
	}
	if mapping := object(value); mapping != nil {
		return changeMigrationMapping(mapping, tokens, replacement, remove)
	}
	if items, ok := value.([]any); ok {
		return changeMigrationItems(items, tokens, replacement, remove)
	}
	return nil, invalid()
}
func changeMigrationMapping(mapping map[string]any, tokens []string, replacement any, remove bool) (any, error) {
	key := tokens[0]
	child, present := mapping[key]
	if !present {
		return nil, invalid()
	}
	if len(tokens) == 1 {
		if remove {
			delete(mapping, key)
		} else {
			mapping[key] = replacement
		}
		return mapping, nil
	}
	next, err := changeMigrationValue(child, tokens[1:], replacement, remove)
	if err != nil {
		return nil, err
	}
	mapping[key] = next
	return mapping, nil
}
func changeMigrationItems(items []any, tokens []string, replacement any, remove bool) (any, error) {
	index, valid := jsonpointer.ArrayIndex(tokens[0], len(items))
	if !valid {
		return nil, invalid()
	}
	if len(tokens) == 1 {
		if remove {
			return slices.Delete(items, index, index+1), nil
		}
		items[index] = replacement
		return items, nil
	}
	next, err := changeMigrationValue(items[index], tokens[1:], replacement, remove)
	if err != nil {
		return nil, err
	}
	items[index] = next
	return items, nil
}
func explicitOpenRealization(root map[string]any, pointer string) bool {
	table := object(root["realization"])
	if table == nil {
		return false
	}
	posture := text(table[defaultField])
	specificity := -1
	if posture == termUnspecified {
		posture = ""
	}
	for _, raw := range array(table[scopesField]) {
		rule := object(raw)
		if len(array(rule[namespaceField])) > 0 || rule["posture"] == termUnspecified {
			continue
		}
		scope := text(rule[fieldPointerField])
		if scope != "" && pointer != scope && !strings.HasPrefix(pointer, scope+"/") {
			continue
		}
		depth := len(jsonpointer.Tokens(scope))
		if depth > specificity {
			posture = text(rule["posture"])
			specificity = depth
		}
	}
	return posture == openTerm
}
