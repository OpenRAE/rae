package governance

import (
	"math"
	"unicode/utf8"
)

const errNonstandardSchemaJSON = policyInputError("schema validation requires finite JSON numbers and Unicode scalar strings")

// This stricter validation profile is intentionally local to schema inputs.
// Publication hashing and other ordinary legacy readers keep their own profile.
func checkSchemaJSON(value any) error {
	pending := []any{value}
	for len(pending) > 0 {
		value := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		switch value := value.(type) {
		case float64:
			if math.IsNaN(value) || math.IsInf(value, 0) {
				return errNonstandardSchemaJSON
			}
		case string:
			if !utf8.ValidString(value) {
				return errNonstandardSchemaJSON
			}
		case *mapping:
			members, err := schemaJSONMembers(value)
			if err != nil {
				return err
			}
			pending = append(pending, members...)
		case []any:
			pending = append(pending, value...)
		}
	}
	return nil
}

func schemaJSONMembers(value *mapping) ([]any, error) {
	members := make([]any, 0, len(value.keys))
	for _, key := range value.keys {
		name, _ := key.(string)
		if !utf8.ValidString(name) {
			return nil, errNonstandardSchemaJSON
		}
		members = append(members, value.get(key))
	}
	return members, nil
}
