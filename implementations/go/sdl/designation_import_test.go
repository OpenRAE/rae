package sdl_test

import (
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestImportedRealizationDesignationsMatchInstantiatedQueries(t *testing.T) {
	for _, namespace := range []string{"lib", "outer.lib"} {
		t.Run(namespace, func(t *testing.T) {
			checkImportedDesignationQueries(t, namespace)
		})
	}
}

func checkImportedDesignationQueries(t *testing.T, namespace string) {
	t.Helper()
	files := fstest.MapFS{
		"main.yaml": {Data: []byte("name: root\nimports: [{path: child.yaml, namespace: " + namespace + "}]\n")},
		"child.yaml": {Data: []byte(`name: child
module: {id: example/child, version: 1.0.0, exports: {nodes: [host, other]}}
nodes: {host: {type: compute}, other: {type: compute}}
realization:
  default: closed
  scopes: [{field_pointer: /nodes/host, posture: open}]
`)},
	}
	if namespace == "outer.lib" {
		files["main.yaml"].Data = []byte("name: root\nimports: [{path: parent.yaml, namespace: outer}]\n")
		files["parent.yaml"] = &fstest.MapFile{Data: []byte("name: parent\nmodule: {id: example/parent, version: 1.0.0, exports: {nodes: [lib.host, lib.other]}}\nimports: [{path: child.yaml, namespace: lib}]\n")}
	}
	scenario, err := sdl.ParseContext(sdl.SourceContext{Root: "main.yaml", FS: files}, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, query := range []struct{ member, closure, governing string }{
		{"host", "open-world", "/nodes/" + namespace + ".host"},
		{"other", "closed-world", "/"},
	} {
		t.Run(query.member, func(t *testing.T) {
			pointer := "/nodes/" + namespace + "." + query.member
			expected := map[string]any{"closure": query.closure, "governing_scope": namespace + "#" + query.governing, "source": "scope", "delegated": false}
			checkImportedDesignationValue(t, scenario, instance, pointer, expected)
		})
	}
}

func checkImportedDesignationValue(t *testing.T, scenario, instance sdl.Scenario, pointer string, expected map[string]any) {
	t.Helper()
	concrete := importedDesignationValue(t, instance, pointer)
	if !cmp.Equal(concrete, expected) {
		t.Fatalf("instantiated designation %s=%v want=%v", pointer, concrete, expected)
	}
	authored := importedDesignationValue(t, scenario, pointer)
	if !cmp.Equal(authored, concrete) {
		t.Errorf("authored designation %s=%v differs from instantiated=%v", pointer, authored, concrete)
	}
	authored["closure"], authored["governing_scope"], authored["source"] = "changed", "changed", "changed"
	again := importedDesignationValue(t, scenario, pointer)
	if !cmp.Equal(again, expected) {
		t.Errorf("later authored query %s=%v want=%v after caller mutation", pointer, again, expected)
	}
	concrete["closure"] = "changed"
	if again := importedDesignationValue(t, instance, pointer); !cmp.Equal(again, expected) {
		t.Errorf("later instantiated query %s=%v want=%v after caller mutation", pointer, again, expected)
	}
}

func importedDesignationValue(t *testing.T, scenario sdl.Scenario, pointer string) map[string]any {
	t.Helper()
	fragment, err := sdl.ResolveRealizationDesignation(scenario, pointer)
	if err != nil {
		t.Fatal(err)
	}
	value, ok := fragment.Document().(map[string]any)
	if !ok {
		t.Fatal("designation did not return an object")
	}
	return value
}
