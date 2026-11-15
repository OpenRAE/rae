package admission

import (
	"encoding/base64"
	"encoding/json"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type experimentBinary struct{ data []byte }

func experimentBinaryDecode(text string) ([]byte, error) {
	cleaned := []byte{}
	padding := 0
	for _, char := range text {
		if char > 127 {
			return nil, experimentError("invalid-yaml")
		}
	}
	for index := range len(text) {
		char := text[index]
		if strings.ContainsRune("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", rune(char)) {
			cleaned = append(cleaned, char)
			padding = 0
			continue
		}
		if char != '=' {
			continue
		}
		padding++
	}
	switch len(cleaned) % 4 {
	case 2:
		if padding < 2 {
			return nil, experimentError("invalid-yaml")
		}
		cleaned = append(cleaned, '=', '=')
	case 3:
		if padding < 1 {
			return nil, experimentError("invalid-yaml")
		}
		cleaned = append(cleaned, '=')
	case 1:
		return nil, experimentError("invalid-yaml")
	default:
	}

	return decodeExperimentBase64(cleaned)
}
func decodeExperimentBase64(text []byte) ([]byte, error) {
	decoded, err := base64.StdEncoding.DecodeString(string(text))
	if err != nil {
		return nil, experimentError("invalid-yaml")
	}
	return decoded, nil
}
func (e *Validator) coerceExperimentBinary(document map[string]any) error {
	positions := map[string]bool{}
	if err := replaceExperimentBinary(document, "", positions); err != nil {
		return err
	}
	if len(positions) == 0 {
		return nil
	}
	raw, err := json.Marshal(document)
	if err != nil {
		return experimentError("contract-invalid")
	}
	projection, normalized, err := e.experimentConstructed(termExperimentAuthoringInputV1, raw, experimentProjectionLimits())
	if err != nil {
		return experimentError("contract-invalid")
	}
	allowed := map[string]bool{}
	err = e.low.CheckInstances(termExperimentAuthoringInputV1, normalized, experimentProjectionLimits(), func(instance validation.SchemaInstance) error {
		model := strings.TrimPrefix(instance.SchemaPointer, schemaDefinitionsPrefix)
		if instance.SchemaPointer == "#" {
			model = experimentRootModel(termExperimentAuthoringInputV1)
		}
		node, present := pointerAt(projection, instance.Path)
		if !present {
			return nil
		}
		for _, pattern := range experimentBinaryFields(model) {
			markBinaryFields(node, instance.Path, strings.Split(strings.TrimPrefix(pattern, "/"), "/"), positions, allowed)
		}
		return nil
	})
	if err != nil || len(allowed) != len(positions) {
		return experimentError("contract-invalid")
	}
	return nil
}
func experimentProjectionLimits() ingress.Limits {
	return ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}
}
func replaceExperimentBinary(node any, path string, positions map[string]bool) error {
	switch current := node.(type) {
	case map[string]any:
		for key, v := range current {
			next, err := replaceExperimentBinaryValue(v, path+"/"+binaryPointerToken(key), positions)
			if err != nil {
				return err
			}
			current[key] = next
		}
	case []any:
		for index, v := range current {
			next, err := replaceExperimentBinaryValue(v, path+"/"+strconv.Itoa(index), positions)
			if err != nil {
				return err
			}
			current[index] = next
		}
	}
	return nil
}
func replaceExperimentBinaryValue(node any, path string, positions map[string]bool) (any, error) {
	if binary, ok := node.(experimentBinary); ok {
		if !utf8.Valid(binary.data) {
			return nil, experimentError("contract-invalid")
		}
		positions[path] = true
		return string(binary.data), nil
	}
	return node, replaceExperimentBinary(node, path, positions)
}
func binaryPointerToken(token string) string {
	return strings.ReplaceAll(strings.ReplaceAll(token, "~", "~0"), "/", "~1")
}
func markBinaryFields(node any, path string, tokens []string, positions, allowed map[string]bool) {
	if len(tokens) == 0 {
		if positions[path] {
			allowed[path] = true
		}
		return
	}
	token, remaining := tokens[0], tokens[1:]
	if token != "*" {
		markBinaryFields(object(node)[token], path+"/"+binaryPointerToken(token), remaining, positions, allowed)
		return
	}
	switch current := node.(type) {
	case map[string]any:
		for key, child := range current {
			markBinaryFields(child, path+"/"+binaryPointerToken(key), remaining, positions, allowed)
		}
	case []any:
		for index, child := range current {
			markBinaryFields(child, path+"/"+strconv.Itoa(index), remaining, positions, allowed)
		}
	}
}
