package admission

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
)

func TestManifestConstructorsPreserveDefaultAndCollectionSemantics(t *testing.T) {
	owner := boundTestOwner(t)
	var reference struct {
		Cases []struct {
			Name     string          `json:"name"`
			ID       string          `json:"contract_id"`
			Input    json.RawMessage `json:"input"`
			Expected json.RawMessage `json:"expected"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/manifest-constructor-projections.json", &reference)
	for _, test := range reference.Cases {
		t.Run(test.Name, func(t *testing.T) {
			actual, err := ManifestModelProjection(owner, test.ID, test.Input)
			if err != nil {
				t.Fatal(err)
			}
			a, e1 := canonjson.JCS(actual)
			b, e2 := canonjson.JCS(test.Expected)
			if e1 != nil || e2 != nil || string(a) != string(b) {
				var left, right any
				_ = decodeExact(a, &left)
				_ = decodeExact(b, &right)
				t.Fatal("manifest constructor differs", cmp.Diff(right, left))
			}
		})
	}
}
