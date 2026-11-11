package authoring

import (
	"encoding/json"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestCompositionRewritesOwnedReferencesAndKeepsProse(t *testing.T) {
	root := []byte("name: root\nimports: [{path: shared.yaml, namespace: lib}]\n")
	child := []byte("name: shared\nmodule: {id: example/shared, version: 1.0.0, exports: {nodes: [host]}}\nnodes: {host: {type: compute, description: common, features: {common: ''}}}\nfeatures: {common: {type: configuration}}\n")
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	document, err := parser.Decode(Request{Source: root, Name: "main.yaml", FS: fstest.MapFS{"main.yaml": {Data: root}, "shared.yaml": {Data: child}}})
	if err != nil {
		t.Fatal(err)
	}
	family, err := parser.AdmitFamily(document)
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err = json.Unmarshal(family.JSON(), &payload); err != nil {
		t.Fatal(err)
	}
	node := object(object(payload[nodesSection])["lib.host"])
	if _, present := object(node[featuresSection])["lib.__private.common"]; !present {
		t.Fatal("local declaration reference was not namespaced")
	}
	if node["description"] != "common" {
		t.Fatal("reference rewriting changed opaque prose")
	}
}
