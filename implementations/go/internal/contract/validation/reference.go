package validation

import (
	"bytes"
	"encoding/json"
	"maps"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type referenceLookup struct {
	root      map[string]any
	remaining int
}

// CheckReferenceBinding checks a reference-model binding against the immutable
// published bundle. It exposes no schema or mutable data and grants no admission.
// Instance paths select properties and map wildcards, as the reference owner does.
func (v *Validator) CheckReferenceBinding(id, pointer, path string, keyFields []string) error {
	if v == nil || v.contracts[id].raw == nil {
		return failure(fault.InvalidInput, "contract-unknown")
	}
	if !strings.HasPrefix(pointer, "#/") || path == "" || len(keyFields) == 0 || len(keyFields) > 100000 || strings.Count(path, ".") > 100000 {
		return referenceFailure()
	}
	lookup := referenceLookup{v.contracts[id].raw, 100000}
	target, err := lookup.pointer(pointer)
	if err != nil {
		return err
	}
	target, err = lookup.resolve(target)
	if err != nil {
		return err
	}
	instance, err := lookup.instance(path)
	if err != nil {
		return err
	}
	if !referenceSchemaEqual(target, instance) {
		return referenceFailure()
	}
	properties, ok := target[keywordProperties].(map[string]any)
	if !ok {
		return referenceFailure()
	}
	seen := map[string]bool{}
	for _, field := range keyFields {
		if _, present := properties[field]; !present || seen[field] {
			return referenceFailure()
		}
		seen[field] = true
	}
	return nil
}
func referenceFailure() error { return failure(fault.InvalidInput, "contract-reference-binding") }
func (l *referenceLookup) pointer(pointer string) (map[string]any, error) {
	if !strings.HasPrefix(pointer, "#/") {
		return nil, referenceFailure()
	}
	var current any = l.root
	for _, token := range jsonpointer.Tokens(strings.TrimPrefix(pointer, "#")) {
		l.remaining--
		if l.remaining < 0 {
			return nil, referenceFailure()
		}
		mapping, ok := current.(map[string]any)
		if !ok {
			return nil, referenceFailure()
		}
		current, ok = mapping[token]
		if !ok {
			return nil, referenceFailure()
		}
	}
	result, ok := current.(map[string]any)
	if !ok {
		return nil, referenceFailure()
	}
	return result, nil
}
func (l *referenceLookup) resolve(node map[string]any) (map[string]any, error) {
	seen := map[string]bool{}
	current := node
	for {
		l.remaining--
		if l.remaining < 0 {
			return nil, referenceFailure()
		}
		if raw, present := current[keywordRef]; present {
			ref, ok := raw.(string)
			if !ok || seen[ref] {
				return nil, referenceFailure()
			}
			seen[ref] = true
			target, err := l.pointer(ref)
			if err != nil {
				return nil, err
			}
			current = target
			continue
		}
		next, collapsed := referenceNullable(current)
		if !collapsed {
			return current, nil
		}
		current = next
	}
}
func referenceNullable(node map[string]any) (map[string]any, bool) {
	branches, ok := node[keywordAnyOf].([]any)
	if !ok || len(branches) != 2 {
		return nil, false
	}
	var selected map[string]any
	nulls := 0
	for _, branch := range branches {
		candidate, ok := branch.(map[string]any)
		if !ok {
			return nil, false
		}
		if candidate[keywordType] == "null" {
			nulls++
		} else {
			selected = candidate
		}
	}
	return selected, nulls == 1 && selected != nil
}
func (l *referenceLookup) instance(path string) (map[string]any, error) {
	current := l.root
	for part := range strings.SplitSeq(path, ".") {
		resolved, err := l.resolve(current)
		if err != nil {
			return nil, err
		}
		var child any
		if part == "*" {
			child = resolved[keywordAdditionalProperties]
		} else {
			properties, _ := resolved[keywordProperties].(map[string]any)
			child = properties[part]
		}
		var ok bool
		current, ok = child.(map[string]any)
		if !ok {
			return nil, referenceFailure()
		}
	}
	return l.resolve(current)
}

func referenceSchemaEqual(a, b any) bool {
	switch left := a.(type) {
	case map[string]any:
		right, ok := b.(map[string]any)
		return ok && maps.EqualFunc(left, right, referenceSchemaEqual)
	case []any:
		right, ok := b.([]any)
		return ok && slices.EqualFunc(left, right, referenceSchemaEqual)
	case json.Number:
		right, ok := b.(json.Number)
		if !ok || !boundedNumber(left) || !boundedNumber(right) {
			return false
		}
		x, xok := new(big.Rat).SetString(string(left))
		y, yok := new(big.Rat).SetString(string(right))
		return xok && yok && x.Cmp(y) == 0
	default:
		x, xerr := json.Marshal(a)
		y, yerr := json.Marshal(b)
		return xerr == nil && yerr == nil && bytes.Equal(x, y)
	}
}
