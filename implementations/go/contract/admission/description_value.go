package admission

import "encoding/json"

const (
	jsonZero json.Number = "0"
	json4096 json.Number = "4096"
)

func descriptiveValue(root any) error {
	pending := []any{root}
	for work := 0; len(pending) > 0; work++ {
		if work >= 4096 {
			return invalid()
		}
		v := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		children, err := descriptiveChildren(v)
		if err != nil {
			return err
		}
		pending = append(pending, children...)
	}
	return nil
}
func descriptiveChildren(v any) ([]any, error) {
	origin := stringAt(v, "origin")
	if origin != kindBackend && origin != termObservation || text(defaultMember(v, "presence", requirementRequired)) != requirementRequired {
		return nil, invalid()
	}
	kind := stringAt(v, termKind)
	if kind == termLiteral {
		return nil, nil
	}
	if text(defaultMember(at(v, "closure"), "posture", termUndefined)) != termUndefined || at(v, "closure", "universe") != nil || at(v, "closure", termProfile) != nil {
		return nil, invalid()
	}
	if !descriptiveCardinality(v, kind) {
		return nil, invalid()
	}
	var children []any
	switch kind {
	case kindRecursiveRecord:
		for _, child := range object(at(v, "fields")) {
			children = append(children, child)
		}
	case "sequence":
		children = array(at(v, termItems))
	case "keyed-collection":
		if err := descriptionMemberIdentities(v); err != nil {
			return nil, err
		}
		for _, member := range array(at(v, "members")) {
			children = append(children, at(member, termConstraint))
		}
	default:
		return nil, invalid()
	}
	return children, nil
}
func descriptionMemberIdentities(v any) error {
	if len(array(at(v, "aliases"))) > 0 || !fieldsUnique(v, "identity_fields") {
		return invalid()
	}
	seen := map[string]bool{}
	for _, member := range array(at(v, "members")) {
		actual, err := descriptionMemberIdentity(v, member)
		if err != nil {
			return err
		}
		declared, err := jsonDigest(at(member, termIdentity))
		if err != nil {
			return err
		}
		if actual != declared || seen[actual] {
			return invalid()
		}
		seen[actual] = true
	}
	return nil
}
func descriptionMemberIdentity(v, member any) (string, error) {
	constraint := at(member, termConstraint)
	if stringAt(constraint, termKind) != kindRecursiveRecord {
		return "", invalid()
	}
	identity := make([]any, 0, len(array(at(v, "identity_fields"))))
	for _, name := range stringsOf(at(v, "identity_fields")) {
		field := at(constraint, "fields", name)
		if stringAt(field, termKind) != termLiteral {
			return "", invalid()
		}
		identity = append(identity, at(field, "value"))
	}
	return jsonDigest(identity)
}

func descriptiveCardinality(v any, kind string) bool {
	return kind == kindRecursiveRecord || countEqual(defaultMember(v, "min_items", jsonZero), 0) && countEqual(defaultMember(v, "max_items", json4096), 4096)
}
