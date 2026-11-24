package admission

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

type runtimeCollectionLimitCase struct{ model, field, child, identity string }

func TestRuntimeInventoryCollectionLimits(t *testing.T) {
	var manifest struct {
		Baselines map[string]json.RawMessage `json:"baselines"`
	}
	readFullReferenceJSON(t, "testdata/runtime-constructors.json", &manifest)
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	for _, row := range []runtimeCollectionLimitCase{
		{"RuntimeSoftwareComponent", "repository_refs", "", ""},
		{"RuntimeSoftwareComponent", "refinements", "RuntimeSoftwareComponentRefinement", "refinement_id"},
		{"RuntimeSoftwareRepository", "refinements", "RuntimeSoftwareRepositoryRefinement", "refinement_id"},
		{"RuntimeSoftwareTrustBinding", "refinements", "RuntimeSoftwareTrustRefinement", "refinement_id"},
		{"RuntimeSoftwareRepositoryState", "repositories", "RuntimeSoftwareRepository", "repository_id"},
		{"RuntimeSoftwareRepositoryState", "trust_bindings", "RuntimeSoftwareTrustBinding", "trust_id"},
	} {
		for _, size := range []int{256, 257} {
			t.Run(fmt.Sprintf("%s.%s/%d", row.model, row.field, size), func(t *testing.T) {
				raw := runtimeCollectionLimitInput(t, manifest.Baselines, row, size)
				err := owner.CheckSDLConstruction("sdl-authoring-input-v1", "#/$defs/"+row.model, raw, ingress.Limits{MaxBytes: len(raw)})
				if (err == nil) != (size == 256) {
					t.Errorf("accepted = %v, %v; want %v", err == nil, err, size == 256)
				}
			})
		}
	}
}

func runtimeCollectionLimitInput(t *testing.T, baselines map[string]json.RawMessage, row runtimeCollectionLimitCase, size int) []byte {
	t.Helper()
	root := object(decodeRuleObject(t, string(baselines["#/$defs/"+row.model])))
	values := make([]any, size)
	for i := range values {
		identity := fmt.Sprintf("entry-%d", i)
		values[i] = identity
		if row.child != "" {
			child := object(decodeRuleObject(t, string(baselines["#/$defs/"+row.child])))
			child[row.identity] = identity
			values[i] = child
		}
	}
	root[row.field] = values
	return controlJSON(t, root)
}
