package trial

import (
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestTrialToolSupportRequiresSelectedProcessor(t *testing.T) {
	family, err := sdl.ParseFile(os.DirFS("../../../.."), "examples/scenarios/participant-tools/tool-kit.sdl.yaml", sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(family, nil)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("../../../../contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	if err != nil {
		t.Fatal(err)
	}
	var backend binding.BackendManifestV2
	if json.Unmarshal(raw, &backend) != nil {
		t.Fatal("fixture")
	}
	err = admitToolSupport(compiled.Model(), map[ApparatusManifestKey]admission.ApparatusManifest{}, backend)
	var failure *compilationRefusalError
	if !errors.As(err, &failure) || failure.code != "tool-support-apparatus-missing" {
		t.Fatal("tool-bearing trial without processor admitted", err)
	}
}
