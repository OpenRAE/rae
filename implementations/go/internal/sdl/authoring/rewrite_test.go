package authoring

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestOwnedReferenceRewriteReference(t *testing.T) {
	raw, err := readCompressedFixture("testdata/rewrites.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var vectors struct {
		Cases []struct {
			Name       string         `json:"name"`
			Payload    map[string]any `json:"payload"`
			Descriptor map[string]any `json:"descriptor"`
			Output     map[string]any `json:"output"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	for _, vector := range vectors.Cases {
		t.Run(vector.Name, func(t *testing.T) {
			symbols := symbolsFor(vector.Payload, "lib", vector.Descriptor)
			if err := rewriteOwnedReferences(vector.Payload, symbols); err != nil {
				t.Fatal(err)
			}
			if err := rewritePolicyReferences(vector.Payload, symbols, "lib"); err != nil {
				t.Fatal(err)
			}
			if err := rewriteDeclarationKeys(vector.Payload, symbols); err != nil {
				t.Fatal(err)
			}
			if diff := cmp.Diff(vector.Output, vector.Payload); diff != "" {
				t.Errorf("rewrite differs from reference (-want +got):\n%s", diff)
			}
		})
	}
}
