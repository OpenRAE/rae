package sdlrules

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestRuntimeCollectionReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/runtime-inventory.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Collections []runtimeCollectionFixture `json:"Collections"`
		Lookups     []struct {
			Family   string `json:"Family"`
			Pointer  string `json:"Pointer"`
			Identity string `json:"Identity"`
		} `json:"Lookups"`
	}
	if err = json.Unmarshal(raw, &reference); err != nil {
		t.Fatal(err)
	}
	if len(reference.Collections) != 17 || len(reference.Lookups) != 255 {
		t.Fatal("incomplete runtime collection reference")
	}
	if diff := cmp.Diff(runtimeFixtureCollections(reference.Collections), RuntimeFamilies()); diff != "" {
		t.Fatalf("runtime collections differ (-reference +actual):\n%s", diff)
	}
	for _, lookup := range reference.Lookups {
		t.Run(lookup.Family+lookup.Pointer, func(t *testing.T) {
			if actual := RuntimeCollectionIdentity(lookup.Family, lookup.Pointer); actual != lookup.Identity {
				t.Errorf("identity = %q; want %q", actual, lookup.Identity)
			}
		})
	}
}

func TestRuntimeCollectionsAreIndependent(t *testing.T) {
	pristine := RuntimeFamilies()
	modified := RuntimeFamilies()
	changeRuntimeCollectionCopy(modified)
	if diff := cmp.Diff(pristine, RuntimeFamilies()); diff != "" {
		t.Fatalf("caller changed shared collection metadata (-original +actual):\n%s", diff)
	}
}
func changeRuntimeCollectionCopy(collections []RuntimeCollection) {
	for i := range collections {
		collections[i].Collection = "changed"
		collections[i].Identity = "changed"
		changeRuntimeCollectionCopy(collections[i].Children)
	}
}

type runtimeCollectionFixture struct {
	Collection string                     `json:"Collection"`
	Identity   string                     `json:"Identity"`
	Children   []runtimeCollectionFixture `json:"Children"`
}

func runtimeFixtureCollections(values []runtimeCollectionFixture) []RuntimeCollection {
	if values == nil {
		return nil
	}
	result := make([]RuntimeCollection, len(values))
	for i, value := range values {
		result[i] = RuntimeCollection{value.Collection, value.Identity, runtimeFixtureCollections(value.Children)}
	}
	return result
}
