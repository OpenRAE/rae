package processor_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestParticipantSupportUsesNativeCompiledToolFacts(t *testing.T) {
	scenario, err := sdl.ParseFile(os.DirFS("../../.."), "examples/scenarios/participant-tools/tool-kit.sdl.yaml", sdl.DefaultParseOptions())
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
	var target binding.BackendManifestV2
	if json.Unmarshal(raw, &target) != nil {
		t.Fatal("manifest")
	}
	result, err := processor.ParticipantSupport(compiled.Model(), target, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Tools) != 1 || result.Tools[0].Code != "participant.tool-support-insufficient" {
		t.Fatalf("tools=%+v", result.Tools)
	}
	if _, err := processor.ParticipantSupport(foreignModel{}, target, nil); err == nil {
		t.Fatal("foreign model accepted")
	}
}
