package governance

import "github.com/OpenRAE/rae/implementations/go/base/fault"

// The reference's recursive Python comparison has a 1,000-call budget. It is
// distinct from the native JSON reader's larger container-depth allowance.
const publicationComparisonDepth = 1000

type publicationComparisonError struct{}

func (publicationComparisonError) Error() string {
	return "schema compatibility exceeds the comparison depth"
}
func (publicationComparisonError) Category() fault.Category { return fault.InvalidInput }

func publicationIgnored(key string, core bool) bool {
	switch key {
	case "$comment", "$id", "$schema", deprecatedStatus, descriptionField, "examples", "readOnly", titleField, "writeOnly":
		return true
	default:
		return core && (publicationObjectKeyword(key) || key == "default" || key == "enum")
	}
}

func publicationAnnotationEqual(left, right any, core bool) (bool, error) {
	oldValue, err := publicationWithoutAnnotations(left, core, 0)
	if err != nil {
		return false, err
	}
	newValue, err := publicationWithoutAnnotations(right, core, 0)
	if err != nil {
		return false, err
	}
	return publicationEqual(oldValue, newValue), nil
}

func publicationWithoutAnnotations(value any, core bool, depth int) (any, error) {
	if depth >= publicationComparisonDepth {
		return nil, publicationComparisonError{}
	}
	switch raw := value.(type) {
	case *mapping:
		return publicationAnnotatedObject(raw, core, depth)
	case []any:
		return publicationAnnotatedArray(raw, depth)
	default:
		return value, nil
	}
}

func publicationAnnotatedObject(raw *mapping, core bool, depth int) (*mapping, error) {
	result := newMapping()
	for _, key := range sortedMappingKeys(raw) {
		if publicationIgnored(key, core) {
			continue
		}
		child, err := publicationWithoutAnnotations(raw.get(key), false, depth+1)
		if err != nil {
			return nil, err
		}
		result.set(key, child)
	}
	return result, nil
}

func publicationAnnotatedArray(raw []any, depth int) ([]any, error) {
	result := make([]any, len(raw))
	for i, item := range raw {
		child, err := publicationWithoutAnnotations(item, false, depth+1)
		if err != nil {
			return nil, err
		}
		result[i] = child
	}
	return result, nil
}
