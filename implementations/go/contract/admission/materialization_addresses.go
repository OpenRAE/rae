package admission

import (
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

func materializationSemanticAddress(content *materializationCompiled, path string, remaining *int) (string, []string, error) {
	if len(path) > 4096 || jsonpointer.FromTokens(jsonpointer.Tokens(path)) != path {
		return "", nil, invalid()
	}
	current := content.full
	source, semantic := []string{}, []string{}
	var namespace []string
	for _, token := range jsonpointer.Tokens(path) {
		*remaining--
		if *remaining < 0 {
			return "", nil, invalid()
		}
		next, sourceToken, semanticToken, err := materializationAddressStep(current, token, materializationCollectionFields(source, content.identities), remaining)
		if err != nil {
			return "", nil, err
		}
		current = next
		source = append(source, sourceToken)
		semantic = append(semantic, semanticToken)
		if len(source) == 2 {
			var err error
			namespace, err = materializationAddressNamespace(source, current)
			if err != nil {
				return "", nil, err
			}
		}
	}
	return jsonpointer.FromTokens(semantic), namespace, nil
}
func materializationSemanticIndex(items []any, token string, fields []string, remaining *int) (int, string, error) {
	if len(items) > 4096 {
		return 0, "", invalid()
	}
	if len(fields) == 0 {
		index, err := strconv.Atoi(token)
		if err != nil || index < 0 || index >= len(items) || strconv.Itoa(index) != token {
			return 0, "", invalid()
		}
		return index, token, nil
	}
	seen := map[string]bool{}
	selected := -1
	canonical := ""
	for index, item := range items {
		*remaining--
		if *remaining < 0 {
			return 0, "", invalid()
		}
		commitment, err := materializationSemanticIdentity(item, fields)
		if err != nil || seen[commitment] {
			return 0, "", invalid()
		}
		seen[commitment] = true
		key := "@" + commitment
		if token == strconv.Itoa(index) || token == key {
			selected, canonical = index, key
		}
	}
	if selected < 0 {
		return 0, "", invalid()
	}
	return selected, canonical, nil
}
func materializationIdentityScalar(v any) bool {
	switch v.(type) {
	case string, bool:
		return true
	default:
		n, ok := number(v)
		return ok && n.IsInt()
	}
}

func materializationAddressStep(current any, token string, fields []string, remaining *int) (any, string, string, error) {
	if items, ok := current.([]any); ok {
		index, key, err := materializationSemanticIndex(items, token, fields, remaining)
		if err != nil {
			return nil, "", "", err
		}
		return items[index], strconv.Itoa(index), key, nil
	}
	child, present := object(current)[token]
	if !present {
		return nil, "", "", invalid()
	}
	return child, token, token, nil
}
func materializationAddressNamespace(source []string, current any) ([]string, error) {
	identity := source[1]
	if source[0] == termForwardingAgents {
		identity = stringAt(current, "forwarding_agent_id")
		if identity == "" {
			return nil, invalid()
		}
	}
	parts := strings.Split(identity, ".")
	return slices.Clone(parts[:len(parts)-1]), nil
}

func materializationSemanticIdentity(item any, fields []string) (string, error) {
	identity := make([]any, len(fields))
	for index, field := range fields {
		value, present := object(item)[field]
		if !present || !materializationIdentityScalar(value) {
			return "", invalid()
		}
		identity[index] = value
	}
	return jsonDigest(identity)
}
