package sdl_test

import (
	"bytes"
	"encoding/json"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestPublicScenarioBindingOwnsInputsAndDefaults(t *testing.T) {
	input := []byte("name: example\nvariables:\n  count:\n    type: integer\n    default: 2\nnodes:\n  server:\n    type: compute\ninfrastructure:\n  server:\n    count: ${count}\n")
	family, err := sdl.Parse(input, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	clear(input)
	instance, err := sdl.Instantiate(family, nil)
	if err != nil {
		t.Fatal(err)
	}
	if !instance.SemanticallyValidated() {
		t.Fatal("Instantiate() returned an unvalidated scenario")
	}
	view := instance.Document()
	view["name"] = "mutated"
	if got := instance.Document()["name"]; got != "example" {
		t.Errorf("Document() name = %v, want example", got)
	}
	raw, err := sdl.DocumentBytes(instance)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Infrastructure map[string]struct {
			Count int `json:"count"`
		} `json:"infrastructure"`
	}
	if checkErr := json.Unmarshal(raw, &document); checkErr != nil {
		t.Fatal(checkErr)
	}
	if got := document.Infrastructure["server"].Count; got != 2 {
		t.Errorf("bound count = %d, want 2", got)
	}
	model, err := sdl.ModelBytes(instance)
	if err != nil || !bytes.Contains(model, []byte(`"nodes"`)) {
		t.Fatalf("ModelBytes() = %s, %v, want admitted model", model, err)
	}
	clear(raw)
	clear(model)
	if _, err := sdl.CanonicalDigest(instance); err != nil {
		t.Errorf("CanonicalDigest() after output mutation: %v", err)
	}
}

func TestPublicScenarioMetadataUsesAdmittedOwner(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: example\nnodes:\n  server: {type: compute}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	subjects, err := sdl.ConceptSubjects(scenario)
	if err != nil || len(subjects) == 0 {
		t.Fatalf("ConceptSubjects() = %v, %v, want declared subjects", subjects, err)
	}
	bindings, err := sdl.ReferenceBindings(scenario)
	if err != nil || len(bindings["nodes.server"]) != 1 {
		t.Fatalf("ReferenceBindings() = %v, %v", bindings, err)
	}
	bindings["nodes.server"][0] = "changed"
	bindings, err = sdl.ReferenceBindings(scenario)
	if err != nil || bindings["nodes.server"][0] == "changed" {
		t.Fatal("reference bindings retained caller mutation")
	}
	requirements, err := sdl.ArtifactRequirements(scenario)
	if err != nil || len(requirements) != 0 {
		t.Fatalf("ArtifactRequirements() = %v, %v, want no artifact demands", requirements, err)
	}
	designation, err := sdl.ResolveRealizationDesignation(scenario, "/nodes/server")
	if err != nil || requireType[map[string]any](t, designation.Document())["closure"] != "closed-world" {
		t.Fatalf("ResolveRealizationDesignation() = %v, %v, want closed legacy posture", designation, err)
	}
	for _, call := range []func() error{
		func() error { _, err := sdl.ConceptSubjects(nil); return err },
		func() error { _, err := sdl.ArtifactRequirements(nil); return err },
		func() error { _, err := sdl.ResolveRealizationDesignation(nil, ""); return err },
		func() error {
			_, err := sdl.ValidateExperimentSelectionAgainstFamily(binding.ExperimentAuthoringInputV1{}, nil)
			return err
		},
	} {
		if err := call(); err == nil {
			t.Error("metadata operation accepted a nil admitted handle")
		}
	}
}

func TestPublicScenarioContextContainsRootOverride(t *testing.T) {
	context := sdl.SourceContext{Root: "root.yaml", RootBytes: []byte("name: edited\n"), Sources: map[string][]byte{"root.yaml": []byte("name: saved\n")}}
	scenario, err := sdl.ParseContext(context, sdl.DefaultParseOptions())
	if err != nil || scenario.Document()["name"] != "edited" {
		t.Fatalf("ParseContext() = %v, %v, want supplied root override", scenario, err)
	}
	if !bytes.Contains(context.Sources["root.yaml"], []byte("saved")) {
		t.Fatal("ParseContext() changed supplied source data")
	}
	context.Root = "../escape.yaml"
	if _, err := sdl.ParseContext(context, sdl.DefaultParseOptions()); err == nil {
		t.Fatal("ParseContext() accepted an escaping root override")
	}
}

func TestPublicScenarioContextKeepsNestedImports(t *testing.T) {
	root := []byte("name: root\nimports:\n- source: local:parts/module.yaml\n  namespace: demo\n  version: '>=1,<2'\n")
	module := []byte("name: module\nmodule: {id: example/demo, version: '1.2', exports: {nodes: [web]}}\nnodes: {web: {type: compute}}\n")
	for _, context := range []sdl.SourceContext{
		{Root: "space/main.yaml", FS: fstest.MapFS{"space/main.yaml": &fstest.MapFile{Data: root}, "space/parts/module.yaml": &fstest.MapFile{Data: module}}},
		{Root: "space/main.yaml", Sources: map[string][]byte{"space/main.yaml": root, "space/parts/module.yaml": module}},
	} {
		scenario, err := sdl.ParseContext(context, sdl.DefaultParseOptions())
		if err != nil {
			t.Fatalf("ParseContext(nested local import): %v", err)
		}
		instance, err := sdl.Instantiate(scenario, nil)
		if err != nil {
			t.Fatal(err)
		}
		if nodes, ok := instance.Document()["nodes"].(map[string]any); !ok || len(nodes) != 1 {
			t.Fatalf("concrete imported nodes = %v, want one", instance.Document()["nodes"])
		}
	}
}

func TestPublicScenarioRefusesLimitsAndForeignPhase(t *testing.T) {
	options := sdl.DefaultParseOptions()
	options.Limits.MaxInputBytes = 4
	if _, err := sdl.Parse([]byte("name: example\n"), options); err == nil {
		t.Fatal("Parse() accepted input beyond the configured byte bound")
	}
	options = sdl.DefaultParseOptions()
	options.Limits.MaxDepth = 0
	if _, err := sdl.Parse([]byte("name: example\n"), options); err == nil {
		t.Fatal("Parse() accepted an invalid limit definition")
	}
	if _, err := sdl.Instantiate(nil, nil); err == nil {
		t.Fatal("Instantiate() accepted a nil phase handle")
	}
	if _, err := sdl.DocumentBytes(nil); err == nil {
		t.Fatal("DocumentBytes() accepted a nil phase handle")
	}
}

func TestPublicScenarioSuppliedSourcesRemainContained(t *testing.T) {
	sources := map[string][]byte{"root.yaml": []byte("name: example\n")}
	scenario, err := sdl.ParseSources(sources, "root.yaml", sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	clear(sources["root.yaml"])
	if got := scenario.Document()["name"]; got != "example" {
		t.Fatalf("ParseSources() retained caller data: %v", got)
	}
	if _, err := sdl.ParseSources(sources, "../root.yaml", sdl.DefaultParseOptions()); err == nil {
		t.Fatal("ParseSources() accepted a root outside supplied sources")
	}
	filesystem := fstest.MapFS{"root.yaml": &fstest.MapFile{Data: []byte("name: example\n")}}
	if _, err := sdl.ParseFile(filesystem, "../root.yaml", sdl.DefaultParseOptions()); err == nil {
		t.Fatal("ParseFile() accepted a root outside the supplied filesystem")
	}
}

func TestPublicScenarioParsePreservesFaultCategory(t *testing.T) {
	_, err := sdl.Parse([]byte("name: first\nname: second\n"), sdl.DefaultParseOptions())
	category, classified := fault.CategoryOf(err)
	if err == nil || !classified || category != fault.InvalidInput {
		t.Errorf("Parse(duplicate keys) = %v, want invalid input", err)
	}
}

func TestPublicScenarioReferencePurposesKeepOwnerDomains(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: purposes\nnodes:\n  server: {type: compute, services: [{name: http, port: 80}]}\n  lan: {type: switch}\ninfrastructure:\n  lan: {}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	operating, err := sdl.ReferenceBindingsFor(scenario, "operating-scope")
	if err != nil {
		t.Fatal(err)
	}
	if len(operating["http"]) != 1 || operating["http"][0] != "nodes.server.services.http" || len(operating["lan"]) != 1 || operating["lan"][0] != "infrastructure.lan" {
		t.Fatalf("operating scope = %v", operating)
	}
	declared, err := sdl.ReferenceBindingsFor(scenario, "declared")
	if err != nil {
		t.Fatal(err)
	}
	if len(declared["lan"]) != 1 || declared["lan"][0] != "nodes.lan" {
		t.Fatalf("declared domain = %v", declared["lan"])
	}
	actions, err := sdl.ReferenceBindingsFor(scenario, "action-target")
	if err != nil || len(actions["nodes.server.services.http"]) != 1 || actions["nodes.server.services.http"][0] != "nodes.server.services.http" || len(actions["http"]) != 0 {
		t.Fatalf("action-target domain = %v, %v", actions, err)
	}
	if _, err := sdl.ReferenceBindingsFor(scenario, "unknown"); err == nil {
		t.Fatal("unknown reference purpose accepted")
	}
}

func TestPublicScenarioConcurrentRequestIsolation(t *testing.T) {
	for _, name := range []string{"first", "second", "third", "fourth"} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			scenario, err := sdl.Parse([]byte("name: "+name+"\nnodes:\n  "+name+": {type: compute}\n"), sdl.DefaultParseOptions())
			if err != nil {
				t.Fatal(err)
			}
			bindings, err := sdl.ReferenceBindings(scenario)
			if err != nil || len(bindings[name]) != 1 || bindings[name][0] != "nodes."+name || scenario.Document()["name"] != name {
				t.Fatalf("request state leaked: %v %v", bindings, err)
			}
		})
	}
}

func TestPublicScenarioParseInstantiatedPreservesOrder(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: ordered\nnodes:\n  z: {type: compute}\n  a: {type: compute}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := sdl.DocumentBytes(instance)
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	model, err := sdl.ModelBytes(parsed)
	if err != nil {
		t.Fatal(err)
	}
	var projection struct {
		Nodes json.RawMessage `json:"nodes"`
	}
	if err := json.Unmarshal(model, &projection); err != nil {
		t.Fatal(err)
	}
	if bytes.Index(projection.Nodes, []byte(`"z":`)) > bytes.Index(projection.Nodes, []byte(`"a":`)) {
		t.Fatal("parsing an instantiated source sorted its declarations")
	}
}
