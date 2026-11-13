package realization

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestPortableNodeCollectionsRefuseUnownedAndUnboundedInputs(t *testing.T) {
	if _, err := CompileNodeCollection(nil, nil); err == nil {
		t.Fatal("missing native source issued collection authority")
	}
	if _, err := NodeCollectionAdmits(nil, nil); err == nil {
		t.Fatal("missing collection authority admitted a node")
	}
	scenario, err := sdl.Parse([]byte("name: bounded-collection\nnodes: {host: {type: compute}}\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	if authority, compileErr := CompileNodeCollection(scenario, nil); compileErr != nil || authority != nil {
		t.Fatal("authored family issued concrete collection authority")
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	members := []NodeCollectionMember{{Address: "provision.node.host", Kind: "node", Name: "host"}}
	authority, err := CompileNodeCollection(instance, members)
	if err != nil || authority == nil {
		t.Fatalf("bounded native collection refused: %v", err)
	}
	tooMany := make([]NodeCollectionMember, 65537)
	if _, err := CompileNodeCollection(instance, tooMany); err == nil {
		t.Fatal("unbounded source collection admitted")
	}
	if _, err := NodeCollectionAdmits(authority, tooMany); err == nil {
		t.Fatal("unbounded selected collection admitted")
	}
	if _, err := nodeCollectionProjection(nil, make([]string, 4097)); err == nil {
		t.Fatal("unbounded namespace collection admitted")
	}
}
