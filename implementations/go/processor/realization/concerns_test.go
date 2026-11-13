package realization_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

func TestConcernDescriptorsShareOneImmutableRegistry(t *testing.T) {
	descriptors := realization.ConcernDescriptors()
	if len(descriptors) < 60 {
		t.Fatalf("incomplete concern registry: %d", len(descriptors))
	}
	seen := map[string]bool{}
	for _, descriptor := range descriptors {
		if seen[descriptor.Kind] {
			t.Fatalf("duplicate concern %s", descriptor.Kind)
		}
		seen[descriptor.Kind] = true
		if err := admission.CheckFragment(descriptor.Document, admission.RealizationConcern); err != nil {
			t.Fatal(err)
		}
		if len(descriptor.AuthoredPath) == 0 || len(descriptor.PayloadPath) == 0 {
			t.Fatalf("incomplete concern %s", descriptor.Kind)
		}
	}
	descriptors[0].AuthoredPath[0] = "changed"
	descriptors[0].PayloadPath[0] = "changed"
	if got := realization.ConcernDescriptors()[0]; got.AuthoredPath[0] != "type" || got.PayloadPath[0] != "node_kind" {
		t.Fatal("registry retained caller mutation")
	}
}

func TestConcernRegistryMatchesEveryIndependentReferenceDescriptor(t *testing.T) {
	raw, err := os.ReadFile("testdata/concern-registry-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var expected []map[string]any
	if decodeErr := json.Unmarshal(raw, &expected); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	actual := []map[string]any{}
	for _, descriptor := range realization.ConcernDescriptors() {
		document, ok := descriptor.Document.Document().(map[string]any)
		if !ok {
			t.Fatal("native descriptor is not a closed record")
		}
		actual = append(actual, document)
	}
	if diff := cmp.Diff(expected, actual); diff != "" {
		t.Fatalf("concern registry differs (-reference +native):\n%s", diff)
	}
}
