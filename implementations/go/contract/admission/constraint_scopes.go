package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type constraintScopeIndex struct {
	closure  *constraintClosure
	children map[string]*constraintScopeIndex
}

func (e *constraintEvaluation) operation() bool {
	e.operations++
	return e.operations <= e.limits.MaxOperations
}

func (e *constraintEvaluation) indexScopes() bool {
	e.scopes = &constraintScopeIndex{children: map[string]*constraintScopeIndex{}}
	for _, scope := range e.document.Scopes {
		if !e.operation() {
			return false
		}
		node := e.scopes
		for _, token := range jsonpointer.Tokens(scope.Pointer) {
			if !e.operation() {
				return false
			}
			if node.children[token] == nil {
				node.children[token] = &constraintScopeIndex{children: map[string]*constraintScopeIndex{}}
			}
			node = node.children[token]
		}
		closure := scope.Closure
		node.closure = &closure
	}
	return true
}

func (e *constraintEvaluation) inheritedClosure(pointer string) (constraintClosure, bool) {
	node, closure := e.scopes, e.document.DefaultClosure
	if node.closure != nil {
		closure = *node.closure
	}
	for _, token := range jsonpointer.Tokens(pointer) {
		if !e.operation() {
			return constraintClosure{}, false
		}
		node = node.children[token]
		if node == nil {
			break
		}
		if node.closure != nil {
			closure = *node.closure
		}
	}
	return closure, true
}

func (e *constraintEvaluation) scopeChildren(pointer string) (map[string]bool, bool) {
	node := e.scopes
	for _, token := range jsonpointer.Tokens(pointer) {
		if !e.operation() {
			return nil, false
		}
		node = node.children[token]
		if node == nil {
			return map[string]bool{}, true
		}
	}
	result := make(map[string]bool, len(node.children))
	for token := range node.children {
		if !e.operation() {
			return nil, false
		}
		result[token] = true
	}
	return result, true
}

func constraintFieldAt(rule *constraintNode, key string) *constraintNode {
	if rule == nil || rule.Kind != kindRecursiveRecord {
		return nil
	}
	if rule.fieldIndex == nil {
		rule.fieldIndex = make(map[string]*constraintNode, len(rule.Fields))
		for _, field := range rule.Fields {
			rule.fieldIndex[field.name] = field.rule
		}
	}
	return rule.fieldIndex[key]
}

func (e *constraintEvaluation) scopeTarget(actual any, pointer string) (any, *constraintNode, bool, constraintResult) {
	rule := e.document.Root
	for _, token := range jsonpointer.Tokens(pointer) {
		if !e.operation() {
			return nil, nil, false, constraintFailure("limit-exceeded", pointer, "Scope evaluation exceeded max_operations.")
		}
		var present bool
		var failure constraintResult
		actual, rule, present, failure = e.scopeStep(actual, rule, token, pointer)
		if !present || failure.Status != assuranceConformant {
			return actual, rule, present, failure
		}
	}
	return actual, rule, true, constraintSuccess()
}

func (e *constraintEvaluation) scopeStep(actual any, rule *constraintNode, token, pointer string) (any, *constraintNode, bool, constraintResult) {
	switch current := actual.(type) {
	case map[string]any:
		return scopeRecordTarget(current, rule, token, pointer)
	case []any:
		if rule != nil && rule.Kind == termKeyedCollection {
			return e.scopeKeyedTarget(current, rule, token, pointer)
		}
		return scopeSequenceTarget(current, rule, token, pointer)
	default:
		return nil, nil, false, constraintFailure(statusUnsupported, pointer, "A scope descends through a non-container value.")
	}
}

func scopeRecordTarget(current map[string]any, rule *constraintNode, token, pointer string) (any, *constraintNode, bool, constraintResult) {
	child, present := current[token]
	if !present {
		return nil, nil, false, constraintSuccess()
	}
	switch {
	case rule == nil || rule.Kind == termDelegated:
		return child, nil, true, constraintSuccess()
	case rule.Kind == kindRecursiveRecord:
		return child, constraintFieldAt(rule, token), true, constraintSuccess()
	default:
		return nil, nil, false, constraintFailure(statusUnsupported, pointer, "A scope cannot select record fields through this constraint kind.")
	}
}

func (e *constraintEvaluation) scopeKeyedTarget(current []any, rule *constraintNode, token, pointer string) (any, *constraintNode, bool, constraintResult) {
	if !strings.HasPrefix(token, "@sha256:") {
		return nil, nil, false, constraintFailure(statusUnsupported, pointer, "A keyed-collection scope must use a semantic member identity.")
	}
	indexed, failure := e.keyedIndex(rule, current, pointer)
	if failure.Status != assuranceConformant {
		return nil, nil, false, failure
	}
	declared, _, failure := e.keyedDeclarations(rule, pointer)
	if failure.Status != assuranceConformant {
		return nil, nil, false, failure
	}
	key := strings.TrimPrefix(token, "@")
	child, present := indexed[key]
	if !present {
		return nil, nil, false, constraintSuccess()
	}
	return child, declared[key], true, constraintSuccess()
}

func scopeSequenceTarget(current []any, rule *constraintNode, token, pointer string) (any, *constraintNode, bool, constraintResult) {
	if !jsonpointer.IsArrayIndex(token) || rule != nil && rule.Kind != termSequence {
		return nil, nil, false, constraintFailure(statusUnsupported, pointer, "A collection scope cannot be interpreted without its collection shape.")
	}
	index, present := jsonpointer.ArrayIndex(token, len(current))
	if !present {
		return nil, nil, false, constraintSuccess()
	}
	var selected *constraintNode
	if rule != nil && index < len(rule.Items) {
		selected = rule.Items[index]
	}
	return current[index], selected, true, constraintSuccess()
}

func (e *constraintEvaluation) closedScope(actual any, rule *constraintNode, pointer string) constraintResult {
	children, ok := e.scopeChildren(pointer)
	if !ok {
		return constraintFailure("limit-exceeded", pointer, "Scope child lookup exceeded max_operations.")
	}
	switch observed := actual.(type) {
	case map[string]any:
		return closedRecordScope(observed, rule, pointer, children)
	case []any:
		if rule != nil && rule.Kind == termKeyedCollection {
			return e.closedKeyedScope(observed, rule, pointer, children)
		}
		return closedSequenceScope(observed, rule, pointer, children)
	}
	return constraintSuccess()
}

func closedRecordScope(observed map[string]any, rule *constraintNode, pointer string, children map[string]bool) constraintResult {
	declared := map[string]bool{}
	if rule != nil && rule.Kind == kindRecursiveRecord {
		for _, field := range rule.Fields {
			declared[field.name] = true
		}
	}
	for key := range children {
		if !strings.HasPrefix(key, "@") && !jsonpointer.IsArrayIndex(key) {
			declared[key] = true
		}
	}
	for key := range observed {
		if !declared[key] {
			return constraintFailure("nonconformant", pointer, "A closed scope contains an undeclared record member in its named universe.")
		}
	}
	return constraintSuccess()
}

func (e *constraintEvaluation) closedKeyedScope(observed []any, rule *constraintNode, pointer string, children map[string]bool) constraintResult {
	indexed, failure := e.keyedIndex(rule, observed, pointer)
	if failure.Status != assuranceConformant {
		return failure
	}
	declared, _, failure := e.keyedDeclarations(rule, pointer)
	if failure.Status != assuranceConformant {
		return failure
	}
	for key := range indexed {
		if declared[key] == nil && !children["@"+key] {
			return constraintFailure("nonconformant", pointer, "A closed scope contains an undeclared collection member in its named universe.")
		}
	}
	return constraintSuccess()
}

func closedSequenceScope(observed []any, rule *constraintNode, pointer string, children map[string]bool) constraintResult {
	for index := range observed {
		if rule != nil && rule.Kind == termSequence && index < len(rule.Items) {
			continue
		}
		declared := false
		for token := range children {
			position, valid := jsonpointer.ArrayIndex(token, len(observed))
			declared = declared || valid && position == index
		}
		if !declared {
			return constraintFailure("nonconformant", pointer, "A closed scope contains an undeclared collection member in its named universe.")
		}
	}
	return constraintSuccess()
}

func (e *constraintEvaluation) scopeOverlays(actual any) []constraintResult {
	results := make([]constraintResult, 0, len(e.document.Scopes))
	for _, scope := range e.document.Scopes {
		observed, rule, present, failure := e.scopeTarget(actual, scope.Pointer)
		if failure.Status != assuranceConformant {
			results = append(results, failure)
			continue
		}
		if !present {
			continue
		}
		switch observed.(type) {
		case map[string]any, []any:
		default:
			results = append(results, constraintFailure(statusUnsupported, scope.Pointer, "A closure scope must address a record or collection value."))
			continue
		}
		if scope.Closure.Posture == "open" {
			continue
		}
		if rule != nil && rule.Kind == termDelegated {
			rule = nil
		} else if rule != nil && rule.Kind != kindRecursiveRecord && rule.Kind != termKeyedCollection && rule.Kind != termSequence {
			results = append(results, constraintFailure(statusUnsupported, scope.Pointer, "A closure scope cannot be interpreted for this constraint kind."))
			continue
		}
		results = append(results, e.closedScope(observed, rule, scope.Pointer))
	}
	return results
}
