package sdl_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestArtifactRequirementsReturnCompletePublishedSource(t *testing.T) {
	raw, err := os.ReadFile("../../../contracts/fixtures/artifact-requirements/artifact-requirement-v1/valid/exact-artifact.json")
	if err != nil {
		t.Fatal(err)
	}
	var wrapper map[string]json.RawMessage
	if json.Unmarshal(raw, &wrapper) != nil {
		t.Fatal("fixture")
	}
	scenarioJSON, err := json.Marshal(map[string]any{"name": "example", "nodes": map[string]any{"server": map[string]any{"type": "compute", "source": wrapper["source"]}}})
	if err != nil {
		t.Fatal(err)
	}
	scenario, err := sdl.Parse(scenarioJSON, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	requirements, err := sdl.ArtifactRequirements(scenario)
	if err != nil {
		t.Fatal(err)
	}
	if len(requirements) != 1 {
		t.Fatalf("requirements=%+v", requirements)
	}
	raw, err = json.Marshal(requirements[0].Document)
	if err != nil {
		t.Fatal(err)
	}
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	if err := owner.CheckPortable("artifact-requirement-v1", raw, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}); err != nil {
		t.Fatalf("incomplete artifact source: %s: %v", raw, err)
	}
	if len(requirements[0].Trail) != 4 || requirements[0].Trail[3] != "artifact_requirement" {
		t.Fatalf("trail=%v", requirements[0].Trail)
	}
}
