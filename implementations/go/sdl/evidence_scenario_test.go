package sdl_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type foreignEvidenceScenario struct{ sdl.Scenario }

func (foreignEvidenceScenario) Document() map[string]any { panic("foreign scenario method called") }

func TestEvidenceScenarioRetainsAuthoredOwnerWithoutReopeningImports(t *testing.T) {
	sources := map[string][]byte{
		"space/main.yaml":         []byte("name: root\nimports:\n- source: local:parts/module.yaml\n  namespace: demo\n  version: '>=1,<2'\n"),
		"space/parts/module.yaml": []byte("name: module\nmodule: {id: example/demo, version: '1.2', exports: {nodes: [web]}}\nnodes: {web: {type: compute}}\n"),
	}
	scenario, err := sdl.ParseContext(sdl.SourceContext{Sources: sources, Root: "space/main.yaml"}, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	evidence, err := sdl.EvidenceScenario(scenario)
	if err != nil {
		t.Fatal(err)
	}
	digest, err := sdl.CanonicalDigest(scenario)
	if err != nil {
		t.Fatal(err)
	}
	if evidence.Value.ContractID() != "sdl-authoring-input-v1" || evidence.Digest != digest {
		t.Fatal("authored evidence lost its owner or canonical digest")
	}
	projection := evidence.Value.JSON()
	projection[0] = 'x'
	if evidence.Value.JSON()[0] != '{' {
		t.Fatal("public evidence projection changed its native owner")
	}
	concrete, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, rejected := range []sdl.Scenario{nil, concrete, foreignEvidenceScenario{scenario}} {
		if _, err := sdl.EvidenceScenario(rejected); err == nil {
			t.Fatal("non-authored or foreign scenario became relation authority")
		}
	}
}
