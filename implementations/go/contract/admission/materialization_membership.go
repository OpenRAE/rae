package admission

import (
	"encoding/json"
	"strings"
)

func (r *materializationInventory) membership() error {
	authority := r.execution.original.collection
	doc := at(authority, "constraint_document")
	root := at(doc, "root")
	if authority == nil || stringAt(doc, "semantic_profile") != "raes/portable-node-membership/v1" || stringAt(root, "kind") != "recursive-record" || len(array(at(doc, "scopes"))) > 0 || len(object(at(doc, "definitions"))) > 0 {
		return invalid()
	}
	groups := map[string]map[string]any{}
	for namespace := range object(at(root, "fields")) {
		groups[namespace] = map[string]any{}
	}
	for key, entry := range materializationScope(r.entries, termProvisioning) {
		if err := materializationMembershipEntry(key, entry, groups); err != nil {
			return err
		}
	}
	for namespace, actual := range groups {
		if err := materializationMembershipCollection(at(root, "fields", namespace), actual, at(doc, "default_closure")); err != nil {
			return err
		}
	}
	return nil
}

// The enclosing owner always emits normalized portable-node membership: a
// closed record of keyed collections containing exact identity records. This
// is the owner's canonical profile, not a general recursive-constraint API.
func materializationMembershipCollection(rule any, actual map[string]any, fallback any) error {
	if stringAt(rule, "kind") != "keyed-collection" || stringAt(rule, "collection_kind") != "portable-node" || !equal(at(rule, "identity_fields"), []string{fieldAddress}) || len(array(at(rule, "aliases"))) > 0 {
		return invalid()
	}
	minimum, maxok := integer(defaultMember(rule, "min_items", jsonZero))
	maximum, minok := integer(defaultMember(rule, "max_items", json.Number("4096")))
	if !maxok || !minok || len(actual) < minimum || len(actual) > maximum {
		return invalid()
	}
	unmatched := keySet(actual)
	for _, member := range array(at(rule, "members")) {
		if err := materializationMembershipMember(member, actual, fallback, unmatched); err != nil {
			return err
		}
	}
	closure := stringAt(rule, "closure", "posture")
	if closure == "" || closure == termUndefined {
		closure = stringAt(fallback, "posture")
	}
	return require(closure == termOpen || closure == termClosed && len(unmatched) == 0)
}
func materializationMembershipRecord(rule, actual, fallback any) error {
	if stringAt(rule, "kind") != "recursive-record" || object(actual) == nil {
		return invalid()
	}
	for field, child := range object(at(rule, "fields")) {
		if err := materializationMembershipField(child, actual, field); err != nil {
			return err
		}
	}
	closure := stringAt(rule, "closure", "posture")
	if closure == "" || closure == termUndefined {
		closure = stringAt(fallback, "posture")
	}
	return require(closure == termOpen || closure == termClosed && subset(mapKeys(actual), keySet(at(rule, "fields"))))
}

func materializationMembershipField(child, actual any, field string) error {
	observed, present := object(actual)[field]
	presence := text(defaultMember(child, "presence", requirementRequired))
	if presence == termForbidden && present || presence == requirementRequired && !present {
		return invalid()
	}
	if present && (stringAt(child, "kind") != termLiteral || !equal(at(child, "value"), observed)) {
		return invalid()
	}
	return nil
}

func materializationMembershipMember(member any, actual map[string]any, fallback any, unmatched map[string]bool) error {
	identity := array(at(member, termIdentity))
	if len(identity) != 1 {
		return invalid()
	}
	key := text(identity[0])
	observed, present := actual[key]
	child := at(member, "constraint")
	presence := text(defaultMember(child, "presence", requirementRequired))
	if presence == termForbidden && present || presence == requirementRequired && !present {
		return invalid()
	}
	if present {
		if err := materializationMembershipRecord(child, observed, fallback); err != nil {
			return err
		}
		delete(unmatched, key)
	}
	return nil
}

func materializationMembershipEntry(key string, entry any, groups map[string]map[string]any) error {
	kind := stringAt(entry, "resource_type")
	if kind != termNode && kind != termNetwork {
		return nil
	}
	name := stringAt(entry, "payload", termName)
	if !materializationQualified(name) {
		return invalid()
	}
	namespace, _, qualified := strings.CutLast(name, ".")
	if !qualified {
		namespace = ""
	}
	if groups[namespace] == nil {
		return invalid()
	}
	groups[namespace][key] = map[string]any{fieldAddress: key, termName: name, "resource_type": kind}
	return nil
}
