package processor_test

import (
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileEvidenceRetainsObservationAndCaptureDemands(t *testing.T) {
	scenario, err := sdl.ParseFile(os.DirFS("../../.."), "examples/scenarios/guided-web-probe.sdl.yaml", sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	view := compiled.Model().View()
	if len(view.CaptureDemands) != 1 || len(view.ObservationDemands) != 1 {
		t.Fatalf("capture=%d observation=%d", len(view.CaptureDemands), len(view.ObservationDemands))
	}
}
