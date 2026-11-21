package analysis

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestWitnessNativePhaseReadmission(t *testing.T) {
	source := []byte("name: satisfiable-control\nvariables:\n  platform: {type: string, allowed_values: [windows, linux], required: true}\nnodes:\n  target: {type: compute, os: '${platform}'}\n")
	scenario, err := sdl.Parse(source, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.InstantiateWithProfile(scenario, map[string]any{"platform": "linux"}, satisfiabilityProfile)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := sdl.DocumentBytes(instance)
	if err != nil {
		t.Fatal(err)
	}
	phase, err := (witnessPhaseOwner{ctx: context.Background()}).CompileMaterialization(admission.MaterializationCompileRequest{ContractID: "instantiated-scenario-v1", Source: raw})
	if err != nil {
		t.Fatal(err)
	}
	snapshotDigest, err := sdl.CanonicalDigest(instance)
	if err != nil {
		t.Fatal(err)
	}
	actual, err := hash(map[string]any{"profile": "raes-sdl-instantiated-snapshot/v2", "scenario": json.RawMessage(phase.FullDocument)})
	if err != nil {
		t.Fatal(err)
	}
	if snapshotDigest != actual {
		t.Fatalf("canonical snapshot %s phase %s\n%s", snapshotDigest, actual, phase.FullDocument)
	}
}
