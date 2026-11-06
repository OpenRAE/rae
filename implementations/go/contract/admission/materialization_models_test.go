package admission

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestMaterializationModelsRejectUnresolvedAndConflictingClaims(t *testing.T) {
	e := boundTestOwner(t)
	const id = "materialized-scenario-v1"
	const path = "fixtures/sdl/materialized-scenario-v1/valid/reference.json"
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	v := fixtureObject(t, path)
	if err := e.checkModels(id, controlJSON(t, v), limits); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"missing-origin-target", "inherited-origin", "duplicate-origin"} {
		t.Run(name, func(t *testing.T) {
			v := fixtureObject(t, path)
			origin := map[string]any{"field_pointer": "/name", "source_pointer": nil, "change": "added", "origin": "backend-realized"}
			switch name {
			case "missing-origin-target":
				origin["field_pointer"] = "/missing"
			case "inherited-origin":
				origin["origin"] = "author-declared"
			}
			origins := []any{origin}
			if name == "duplicate-origin" {
				origins = append(origins, origin)
			}
			object(v["materialization_provenance"])["origins"] = origins
			raw := controlJSON(t, v)
			if err := e.low.CheckSchema(id, raw, limits); err != nil {
				t.Fatal("mutation is not schema valid", err)
			}
			if err := e.checkModels(id, raw, limits); err == nil {
				t.Fatal("accepted invalid materialization model")
			}
		})
	}
}

func TestMaterializationTokenBoundaryMatchesQualifiedNames(t *testing.T) {
	for _, test := range []struct {
		value    any
		concrete bool
	}{
		{"prefix ${__private.input} suffix", false},
		{map[string]any{"safe": "${module.input}"}, false},
		{map[string]any{"${input}": "literal"}, true},
		{"${__private}", true},
		{"${Upper}", true},
		{"${" + strings.Repeat("a", 65) + "}", true},
		{"${" + strings.Repeat("a", 64) + "}", false},
	} {
		work := 0
		if got := materializationConcrete(test.value, &work); got != test.concrete {
			t.Errorf("concrete=%v want %v", got, test.concrete)
		}
	}
}

func TestMaterializationSubmissionUsesTheUTF8ByteLimit(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct {
		count int
		valid bool
	}{{2097152, true}, {2097153, false}} {
		raw := controlJSON(t, map[string]any{"sdl": strings.Repeat("é", test.count)})
		limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
		if err := e.low.CheckSchema("backend-materialization-attestation-v1", raw, limits); err != nil {
			t.Fatal(err)
		}
		if err := e.checkModels("backend-materialization-attestation-v1", raw, limits); (err == nil) != test.valid {
			t.Fatalf("count=%d error=%v", test.count, err)
		}
	}
}

func TestMaterializationProvenanceUsesExactNullableInstanceIdentity(t *testing.T) {
	v := map[string]any{"resource_bindings": []any{
		map[string]any{"address": "node.a", "node_name": "a", "instance_index": nil},
		map[string]any{"address": "node.a", "node_name": "a", "instance_index": jsonZero},
	}}
	if err := materializationProvenance(v); err != nil {
		t.Fatal(err)
	}
	object(array(v["resource_bindings"])[0])["instance_index"] = json.Number("0.0")
	if err := materializationProvenance(v); err == nil {
		t.Error("accepted duplicate integral instance identity")
	}
	for _, name := range []string{"a", "module.__private.node", "node-1"} {
		if !materializationQualified(name) {
			t.Errorf("refused %s", name)
		}
	}
	for _, name := range []string{"", "__private", "module.__private", "a..b", "Upper"} {
		if materializationQualified(name) {
			t.Errorf("accepted %s", name)
		}
	}
}
