package processor_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestResolvedRuntimeModelStaysOwnedAndRetainsOriginal(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: example\nrealization: {default: unspecified}\nnodes:\n  server:\n    type: compute\n    runtime:\n      environment: [{name: PUBLIC, value: example}]\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("../../../contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	if err != nil {
		t.Fatal(err)
	}
	var manifest binding.BackendManifestV2
	if checkErr := json.Unmarshal(raw, &manifest); checkErr != nil {
		t.Fatal(checkErr)
	}
	selected := compiledTestRequirement(t, compiled.Model(), "runtime-environment")
	if !selected.RecursivePending {
		t.Fatal("fixture did not retain source")
	}
	model, resolved, err := processor.ResolveRealization(compiled.Model(), realization.ResolveOptions{Manifest: manifest, Decisions: []realization.Decision{{Address: selected.Address, FieldPath: selected.FieldPath, Kind: selected.Kind, Closure: "open-world"}}})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := processor.AdmitRuntimeModel(model); err != nil {
		t.Fatal(err)
	}
	for i := range resolved.Requirements {
		if resolved.Requirements[i].Kind == selected.Kind {
			*resolved.Requirements[i].Posture = "changed"
		}
	}
	effective := compiledTestRequirement(t, model, selected.Kind)
	if effective.RecursivePending || effective.Posture == nil || *effective.Posture != "open" {
		t.Fatalf("effective requirement=%+v", effective)
	}
	original := compiledTestRequirement(t, compiled.Model(), selected.Kind)
	if !original.RecursivePending {
		t.Fatal("original model was changed")
	}
	if _, _, err := processor.ResolveRealization(foreignModel{}, realization.ResolveOptions{}); err == nil {
		t.Fatal("foreign model accepted")
	}
}

func compiledTestRequirement(t *testing.T, model processor.RuntimeModel, kind string) realization.Requirement {
	t.Helper()
	for _, requirement := range model.View().RealizationRequirements {
		if requirement.Kind == kind {
			return requirement
		}
	}
	t.Fatal("missing requirement", kind)
	return realization.Requirement{}
}
