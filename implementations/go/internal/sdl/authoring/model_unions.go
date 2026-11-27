package authoring

import (
	_ "embed"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// The reference member labels of each authoring union of models, recorded by
// tools/parity_sdl_union_labels.py.
//
//go:embed model_union_labels.json
var modelUnionLabelSource []byte

func modelUnionLabels() (map[string][]string, error) {
	labels := map[string][]string{}
	if err := json.Unmarshal(modelUnionLabelSource, &labels); err != nil {
		return nil, err
	}
	return labels, nil
}

// modelUnion admits a mapping through the first member that accepts it. When no
// member accepts it, every member's errors are located under its label.
func (w *normalizer) modelUnion(schema map[string]any, labels []string, value any, path []string, policy scalarPolicy, view source.View) (any, bool, error) {
	members := []map[string]any{}
	for _, item := range alternatives(schema) {
		if branch := object(item); branch["type"] != nullType {
			members = append(members, branch)
		}
	}
	if len(members) != len(labels) {
		return nil, false, nil
	}
	policy.Convert = nil
	prefix := jsonpointer.FromTokens(path)
	failures := make([]error, 0, len(members))
	for index, member := range members {
		result, err := w.walk(member, "", value, path, policy, view)
		if err == nil {
			return result, true, nil
		}
		failures = append(failures, &modelError{cause: err, causes: []error{err}, discriminator: labels[index], discriminatorPath: prefix})
	}
	return nil, true, &modelError{cause: invalid(), causes: failures}
}
