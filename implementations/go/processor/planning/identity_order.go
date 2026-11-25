package planning

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

// identityOrderDepth bounds the structural recursion of identity ordering.
const identityOrderDepth = 64

// identityOrdering orders keyed-collection members by semantic identity
// before a delivery comparison. Sequences keep their positions.
type identityOrdering struct{ definitions map[string]any }

func (o identityOrdering) order(value any, structure map[string]any, depth int) (any, error) {
	if depth > identityOrderDepth {
		return value, nil
	}
	switch structure["kind"] {
	case "definition-reference":
		target, _ := structure["target"].(string)
		definition, found := o.definitions[target].(map[string]any)
		if !found {
			return value, nil
		}
		return o.order(value, definition, depth+1)
	case "all-of":
		return o.allOf(value, structure, depth+1)
	case "recursive-record":
		return o.record(value, structure, depth+1)
	case "sequence":
		return o.sequence(value, structure, depth+1)
	case "keyed-collection":
		return o.keyed(value, structure, depth+1)
	default:
		return value, nil
	}
}

func (o identityOrdering) allOf(value any, structure map[string]any, depth int) (any, error) {
	constraints, _ := structure["constraints"].([]any)
	var err error
	for _, raw := range constraints {
		constraint, _ := raw.(map[string]any)
		if value, err = o.order(value, constraint, depth); err != nil {
			return nil, err
		}
	}
	return value, nil
}

func (o identityOrdering) record(value any, structure map[string]any, depth int) (any, error) {
	record, ok := value.(map[string]any)
	if !ok {
		return value, nil
	}
	fields, _ := structure["fields"].(map[string]any)
	result := make(map[string]any, len(record))
	for key, item := range record {
		field, found := fields[key].(map[string]any)
		if !found {
			result[key] = item
			continue
		}
		ordered, err := o.order(item, field, depth)
		if err != nil {
			return nil, err
		}
		result[key] = ordered
	}
	return result, nil
}

func (o identityOrdering) sequence(value any, structure map[string]any, depth int) (any, error) {
	values, ok := value.([]any)
	if !ok {
		return value, nil
	}
	items, _ := structure["items"].([]any)
	result := make([]any, len(values))
	for index, item := range values {
		result[index] = item
		if index >= len(items) {
			continue
		}
		constraint, _ := items[index].(map[string]any)
		ordered, err := o.order(item, constraint, depth)
		if err != nil {
			return nil, err
		}
		result[index] = ordered
	}
	return result, nil
}

type keyedMember struct {
	identity string
	value    map[string]any
}

func (o identityOrdering) keyed(value any, structure map[string]any, depth int) (any, error) {
	values, ok := value.([]any)
	if !ok {
		return value, nil
	}
	fields, _ := structure["identity_fields"].([]any)
	members, err := keyedMemberConstraints(structure)
	if err != nil {
		return nil, err
	}
	keyed := make([]keyedMember, len(values))
	for index, raw := range values {
		item, isRecord := raw.(map[string]any)
		if !isRecord {
			return value, nil
		}
		identity := make([]any, len(fields))
		for i, field := range fields {
			name, _ := field.(string)
			identity[i] = item[name]
		}
		key, err := canonicalDigest(identity)
		if err != nil {
			return nil, err
		}
		keyed[index] = keyedMember{key, item}
	}
	slices.SortStableFunc(keyed, func(a, b keyedMember) int { return strings.Compare(a.identity, b.identity) })
	result := make([]any, len(keyed))
	for index, item := range keyed {
		result[index] = item.value
		if constraint, found := members[item.identity]; found {
			ordered, err := o.order(item.value, constraint, depth)
			if err != nil {
				return nil, err
			}
			result[index] = ordered
		}
	}
	return result, nil
}

// keyedMemberConstraints indexes each declared member constraint by its identity digest.
func keyedMemberConstraints(structure map[string]any) (map[string]map[string]any, error) {
	members := map[string]map[string]any{}
	declared, _ := structure["members"].([]any)
	for _, raw := range declared {
		member, _ := raw.(map[string]any)
		identity, err := canonicalDigest(member["identity"])
		if err != nil {
			return nil, err
		}
		members[identity], _ = member["constraint"].(map[string]any)
	}
	return members, nil
}

// canonicalDigest is the reference sort key: the digest of the canonical JSON value.
func canonicalDigest(value any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", invalidPlan()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", invalidPlan()
	}
	return digest.SHA256(canonical), nil
}
