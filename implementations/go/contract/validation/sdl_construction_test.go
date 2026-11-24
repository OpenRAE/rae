package validation

import (
	"maps"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestSDLConstructionStagePins(t *testing.T) {
	owner, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"sdl-authoring-input-v1", "materialized-scenario-v1"} {
		t.Run(id, func(t *testing.T) {
			published := owner.contracts[id]
			altered := published
			altered.raw = maps.Clone(published.raw)
			defs := maps.Clone(constructionObject(t, published.raw["$defs"]))
			node := maps.Clone(constructionObject(t, defs["Node"]))
			node["allOf"] = []any{}
			defs["Node"] = node
			altered.raw["$defs"] = defs
			if _, err := compileSDLConstruction(id, altered); err == nil {
				t.Fatal("changed stage clauses were accepted")
			}
			if id == "materialized-scenario-v1" {
				defs = maps.Clone(constructionObject(t, published.raw["$defs"]))
				defs["_r221"] = map[string]any{}
				altered.raw["$defs"] = defs
				if _, err := compileSDLConstruction(id, altered); err == nil {
					t.Fatal("changed referenced clause was accepted")
				}
			}
		})
	}
	if owner.CheckSDLConstruction("sdl-authoring-input-v1", "#", []byte(`{"name":"a"}`), ingress.Limits{MaxBytes: 1024}, nil) == nil {
		t.Fatal("model checks were optional")
	}
	if owner.CheckSchema("sdl-authoring-input-v1", []byte(`{"name":"a","nodes":{"n":{"type":"compute","os_version":"22"}}}`), ingress.Limits{MaxBytes: 1024}) == nil {
		t.Fatal("published schema was mutated")
	}
}

func constructionObject(t *testing.T, value any) map[string]any {
	t.Helper()
	object, ok := value.(map[string]any)
	if !ok {
		t.Fatal("published construction fixture is not an object")
	}
	return object
}

func TestSDLConstructionRejectsUnknownRootStage(t *testing.T) {
	if _, err := constructionAnnotations(map[string][]annotation{"#": {{ID: "future-semantic-stage"}}}); err == nil {
		t.Fatal("unknown root annotation was silently omitted")
	}
}

func TestSDLLocalSemanticsRestoresRootRules(t *testing.T) {
	owner, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	const id = "sdl-authoring-input-v1"
	called := 0
	for _, key := range owner.Keys() {
		owner.rules[key] = Rule{Key: key, Check: func(Invocation) error { return nil }}
	}
	for _, annotation := range owner.contracts[id].annotations["#"] {
		key := Key{id, annotation.ID}
		owner.rules[key] = Rule{Key: key, Check: func(Invocation) error { called++; return nil }}
	}
	data := []byte(`{"name":"a"}`)
	limits := ingress.Limits{MaxBytes: len(data)}
	check := func(SchemaInstance) error { return nil }
	if err := owner.CheckSDLConstruction(id, "#", data, limits, check); err != nil || called != 0 {
		t.Fatalf("construction invoked semantic root: calls=%d err=%v", called, err)
	}
	if err := owner.CheckSDLLocalSemantics(id, data, limits, check); err != nil || called != len(owner.contracts[id].annotations["#"]) || called == 0 {
		t.Fatalf("local semantics omitted root rules: calls=%d err=%v", called, err)
	}
	if owner.CheckSDLLocalSemantics(id, data, limits, nil) == nil {
		t.Fatal("local semantics allowed missing model check")
	}
	if owner.CheckSDLLocalSemantics("unknown", data, limits, check) == nil {
		t.Fatal("unknown local semantic contract accepted")
	}
	var absent *Validator
	if absent.CheckSDLLocalSemantics(id, data, limits, check) == nil {
		t.Fatal("nil local semantic owner accepted")
	}
}
