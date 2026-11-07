package admission

import (
	"encoding/json"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func (r *materializationExecution) inventory() error {
	for _, domain := range []string{termProvisioning, termOrchestration, termEvaluation} {
		described := materializationScope(r.current.resources, domain)
		observed := materializationScope(object(at(r.actual, "entries")), domain)
		requirements := r.original.requirements
		if domain == r.domain {
			requirements = nil
		} else if len(observed) == 0 {
			observed = materializationScope(r.original.resources, domain)
		}
		if !equalSet(keySet(described), keySet(observed)) {
			return invalid()
		}
		for address, resource := range described {
			if err := r.entryMatches(observed[address], resource, requirements); err != nil {
				return err
			}
		}
	}
	return nil
}

func materializationScope(resources map[string]any, domain string) map[string]any {
	result := map[string]any{}
	for address, resource := range resources {
		if stringAt(resource, "domain") == domain {
			result[address] = resource
		}
	}
	return result
}

func (r *materializationExecution) entryMatches(entry, resource any, requirements []json.RawMessage) error {
	for _, field := range []string{"domain", "resource_type", termOrderingDependencies, termRefreshDependencies} {
		left, right := at(entry, field), at(resource, field)
		if field == termOrderingDependencies || field == termRefreshDependencies {
			left = defaultMember(entry, field, []any{})
			right = defaultMember(resource, field, []any{})
		}
		if !equal(left, right) {
			return invalid()
		}
	}
	if !equal(defaultMember(entry, "profile_bindings", []any{}), defaultMember(resource, "profile_bindings", []any{})) {
		return invalid()
	}
	expected, observed := at(resource, "payload"), at(entry, "payload")
	kind := stringAt(resource, "resource_type")
	if kind != termNode && kind != termNetwork {
		return require(equal(expected, observed))
	}
	if object(at(expected, "spec")) == nil || object(at(observed, "spec")) == nil {
		return invalid()
	}
	name := stringAt(expected, termName)
	left, err := r.normalizedNode(name, at(expected, "spec", termNode), requirements)
	if err != nil {
		return err
	}
	right, err := r.normalizedNode(name, at(observed, "spec", termNode), requirements)
	if err != nil {
		return err
	}
	d := materializationDiff{identities: r.current.identities, remaining: 100000}
	path := []string{termNodes, name}
	if err = d.walk(materializationOperand{left, true, path}, materializationOperand{right, true, path}); err != nil {
		return err
	}
	if len(d.origins) != 0 {
		return invalid()
	}
	ep, op := maps.Clone(object(expected)), maps.Clone(object(observed))
	es, os := maps.Clone(object(at(ep, "spec"))), maps.Clone(object(at(op, "spec")))
	es[termNode], os[termNode] = nil, nil
	ep["spec"], op["spec"] = es, os
	return require(equal(ep, op))
}

func (r *materializationExecution) normalizedNode(name string, node any, requirements []json.RawMessage) (any, error) {
	encoded, err := json.Marshal(node)
	if err != nil {
		return nil, invalid()
	}
	raw, err := r.context.NormalizeMaterializationNode(MaterializationNodeProjection{Name: name, Node: encoded, Requirements: requirements})
	if err != nil {
		return nil, invalid()
	}
	v, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, err
	}
	if err = value.Validate(v, value.Runtime()); err != nil {
		return nil, invalid()
	}
	return v, nil
}
